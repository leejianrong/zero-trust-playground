import json
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient

from observer.app import create_app
from observer.normalize import diff_entries, entry_key, event, from_log_line, from_postgres_line
from observer.store import Store

SCHEMA = json.loads((Path(__file__).parent.parent / "observer/event.v1.schema.json").read_text())
LOG = {"event": "x509_svid", "workload": "echo-a", "spiffe_id": "spiffe://playground.local/ns/clinic/sa/echo-a",
       "serial": "ab12", "not_before": "2026-11-03T03:59:18+00:00", "not_after": "2026-11-03T04:01:28+00:00"}


def entry(path):
    return {"spiffe_id": {"trust_domain": "playground.local", "path": path}}


def test_workload_log_becomes_a_valid_identity_event():
    ev = from_log_line(json.dumps(LOG))
    jsonschema.validate(ev, SCHEMA)
    assert ev["src"] == LOG["spiffe_id"] and ev["evidence"]["serial"] == "ab12"


def test_other_log_lines_are_ignored():
    assert from_log_line('{"event": "jwt_svid"}') is None


def test_entry_diff_reports_added_and_removed_with_valid_events():
    old = {entry_key(entry("/a")): entry("/a")}
    new = {entry_key(entry("/b")): entry("/b")}
    evs = list(diff_entries(old, new))
    for ev in evs:
        jsonschema.validate(ev, SCHEMA)
    assert sorted(e["kind"] for e in evs) == ["entry_added", "entry_removed"]


def test_since_replays_only_missed_events():
    store = Store()
    ids = [store.append(event("identity", "k", n=i))["id"] for i in range(3)]
    client = TestClient(create_app(store, sources=()))
    body = client.get(f"/events?since={ids[0]}&follow=false").text
    assert [json.loads(l[6:])["id"] for l in body.splitlines() if l.startswith("data:")] == ids[1:]


def test_last_event_id_header_resumes_the_stream():
    store = Store()
    first = store.append(event("identity", "k"))["id"]
    second = store.append(event("identity", "k"))["id"]
    client = TestClient(create_app(store, sources=()))
    body = client.get("/events?follow=false", headers={"Last-Event-ID": str(first)}).text
    assert f"id: {second}" in body and f"id: {first}\n" not in body


def test_an_svid_serial_is_only_recorded_once():
    store = Store()

    async def source(emit):
        emit(from_log_line(json.dumps(LOG)))
        emit(from_log_line(json.dumps(LOG)))

    with TestClient(create_app(store, sources=(source,))):
        pass
    assert len(store.since(0)) == 1


def test_startup_log_backfill_is_deduped_against_the_store():
    store = Store()
    backlog = [LOG, {**LOG, "serial": "cd34"}, LOG]

    async def source(emit):
        for line in backlog:
            emit(from_log_line(json.dumps(line)))

    with TestClient(create_app(store, sources=(source,))):
        pass
    assert [e["evidence"]["serial"] for e in store.since(0)] == ["ab12", "cd34"]


HTTP = {"event": "http", "service": "records-api", "caller": "web", "method": "GET",
        "route": "/patients/2", "status": 200, "trace": "t1"}


def test_http_log_line_becomes_an_app_event_with_the_trace():
    ev = from_log_line("[pod/records-api-x/app] " + json.dumps(HTTP))
    jsonschema.validate(ev, SCHEMA)
    assert (ev["src"], ev["dst"], ev["trace"], ev["verdict"]) == ("web", "records-api", "t1", "allow")


def test_http_errors_are_information_not_denials():
    assert from_log_line(json.dumps({**HTTP, "status": 500}))["verdict"] == "info"


def test_postgres_connection_is_attributed_to_the_pod_that_owns_the_ip():
    ev = from_postgres_line("10.42.0.9 LOG:  connection authorized: user=clinic database=clinic", {"10.42.0.9": "attacker"})
    jsonschema.validate(ev, SCHEMA)
    assert (ev["src"], ev["dst"], ev["layer"]) == ("attacker", "postgres", "app")


def test_postgres_lines_that_are_not_logins_are_ignored():
    assert from_postgres_line("10.42.0.9 LOG:  connection received: host=10.42.0.9 port=1", {}) is None


def fake_exec(output):
    async def exec_in(namespace, deploy, *cmd):
        return output
    return exec_in


def fake_kube(mtls="off"):
    async def kube(*args):
        return json.dumps({"data": {"identity": "off" if mtls == "off" else "enforce", "mtls": mtls}})
    return kube


async def no_wait(_):
    pass


def api(output, store=None, mtls="off"):
    return TestClient(create_app(store or Store(), sources=(), exec_in=fake_exec(output), kube=fake_kube(mtls),
                                 wait=no_wait))


def attack_out(name, outcome, **extra):
    return json.dumps({"attack": name, "outcome": outcome, "evidence": {}, **extra})


def test_running_an_attack_records_its_result_and_the_expectation():
    store = Store()
    body = api(json.dumps({"attack": "read-postgres", "outcome": "succeeds", "evidence": {"rows": 5}}), store) \
        .post("/attacks/read-postgres/run").json()
    jsonschema.validate({k: v for k, v in body.items()}, SCHEMA)
    assert (body["verdict"], body["dst"], body["evidence"]["expected"]) == ("allow", "postgres", "succeeds")
    assert body["evidence"]["modes"] == {"identity": "off", "mtls": "off"} and body["evidence"]["as_expected"] is True
    assert store.since(0)[0]["kind"] == "attack_result"


def test_a_blocked_attack_is_recorded_as_a_deny():
    out = json.dumps({"attack": "read-postgres", "outcome": "blocked", "evidence": {"error": "OperationalError"}})
    assert api(out).post("/attacks/read-postgres/run").json()["verdict"] == "deny"


def test_unknown_attack_is_a_404_and_an_empty_result_is_a_502():
    assert api("").post("/attacks/nope/run").status_code == 404
    assert api("").post("/attacks/read-postgres/run").status_code == 502


def test_attack_catalogue_is_listed_with_targets():
    names = {a["name"]: a["target"] for a in api("").get("/attacks").json()}
    assert names["read-postgres"] == "postgres"


def test_using_the_app_needs_a_200_from_web():
    assert api("200\n").post("/app/use").json()["ok"] is True
    assert api("").post("/app/use").status_code == 502


def test_a_request_with_no_caller_header_is_the_user():
    assert from_log_line(json.dumps({**HTTP, "caller": "unknown"}))["src"] == "user"


def test_events_can_be_filtered_to_one_trace_even_past_the_page_size():
    store = Store()
    for i in range(600):
        store.append(event("app", "http_request", trace="noise"))
    store.append(event("app", "http_request", trace="wanted"))
    body = TestClient(create_app(store, sources=())).get("/events?follow=false&trace=wanted").text
    assert body.count("data:") == 1


def test_links_report_which_tools_are_answering():
    async def probe_url(url):
        return "8081" in url  # only the clinic app is "running"

    body = TestClient(create_app(Store(), sources=(), probe_url=probe_url)).get("/links").json()
    state = {link["id"]: link["up"] for link in body}
    assert state["clinic"] is True and state["headlamp"] is False
    assert all(link["start"] and link["purpose"] for link in body)


def test_the_real_probe_calls_a_closed_port_down():
    import asyncio

    from observer.links import probe
    assert asyncio.run(probe("http://127.0.0.1:9")) is False


def authz(verdict, caller="spiffe://playground.local/ns/clinic/sa/web", reason=None):
    return json.dumps({"event": "authz", "service": "records-api", "mode": "enforce", "caller": caller,
                       "method": "GET", "route": "/patients", "listener": "mtls", "verdict": verdict,
                       "reason": reason, "trace": "t1"})


def test_authorisation_decisions_become_valid_mtls_events():
    for verdict, expected in (("allow", "allow"), ("deny", "deny"), ("would_deny", "info")):
        ev = from_log_line(authz(verdict, reason=None if verdict == "allow" else "no client certificate presented"))
        jsonschema.validate(ev, SCHEMA)
        assert (ev["layer"], ev["kind"], ev["verdict"], ev["evidence"]["decision"]) == ("mtls", "authorisation", expected, verdict)


def test_a_caller_with_no_identity_is_shown_as_anonymous():
    assert from_log_line(authz("deny", caller=None, reason="no client certificate presented"))["src"] == "anonymous"


def test_a_long_history_replays_without_pausing_between_pages(monkeypatch):
    """The dashboard opens a fresh stream on every load, so catching up must not wait per page."""
    import asyncio

    import observer.app as app_module

    pauses = []
    real_sleep = asyncio.sleep

    async def counting_sleep(seconds):
        pauses.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(app_module.asyncio, "sleep", counting_sleep)
    store = Store()
    for _ in range(3200):
        store.append(event("identity", "k"))
    client = TestClient(create_app(store, sources=()))
    last = 0
    with client.stream("GET", "/events") as stream:
        for line in stream.iter_lines():
            if line.startswith("id: "):
                last = int(line[4:])
            if last == 3200:
                break
    assert last == 3200 and len(pauses) <= 1


def run_attack(name, outcome, mtls="off", store=None, **extra):
    return api(attack_out(name, outcome, **extra), store, mtls).post(f"/attacks/{name}/run").json()


def test_the_expected_outcome_follows_the_layer_modes():
    blocked = run_attack("no-identity-records", "blocked", "enforce")
    assert (blocked["evidence"]["expected"], blocked["evidence"]["as_expected"]) == ("blocked", True)
    open_ = run_attack("no-identity-records", "succeeds", "enforce")
    assert (open_["evidence"]["expected"], open_["evidence"]["as_expected"]) == ("blocked", False)


def test_prompt_injection_is_expected_to_succeed_even_with_mtls_enforced():
    ev = run_attack("agent-prompt-injection", "succeeds", "enforce")
    assert (ev["evidence"]["expected"], ev["evidence"]["as_expected"]) == ("succeeds", True)


def test_a_blocked_attack_names_the_layer_whose_deny_shares_its_trace():
    store = Store()
    store.append(event("mtls", "authorisation", "deny", src="anonymous", dst="records-api", trace="t1"))
    store.append(event("network", "authorisation", "deny", src="anonymous", dst="records-api", trace="other"))
    ev = run_attack("no-identity-records", "blocked", "enforce", store, trace="t1")
    assert ev["evidence"]["stopped_by"] == "mtls" and ev["trace"] == "t1"


def test_a_blocked_attack_with_no_deny_event_has_no_layer_to_name():
    assert run_attack("no-identity-records", "blocked", "enforce", trace="t2")["evidence"]["stopped_by"] is None


def test_a_successful_attack_has_nothing_to_stop_it():
    assert "stopped_by" not in run_attack("no-identity-records", "succeeds", trace="t3")["evidence"]

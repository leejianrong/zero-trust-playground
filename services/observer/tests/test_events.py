import asyncio
import json
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient

from observer import network
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


def fake_kube(mtls="off", secrets="off"):
    async def kube(*args):
        return json.dumps({"data": {"identity": "off" if mtls == "off" else "enforce", "mtls": mtls, "secrets": secrets}})
    return kube


async def no_wait(_):
    pass


class NoNet:
    state = staticmethod(lambda: "off")
    protects = staticmethod(lambda app: False)
    listing = staticmethod(dict)


def api(output, store=None, mtls="off"):
    return TestClient(create_app(store or Store(), sources=(), exec_in=fake_exec(output), kube=fake_kube(mtls),
                                 wait=no_wait, net=NoNet))


def attack_out(name, outcome, **extra):
    return json.dumps({"attack": name, "outcome": outcome, "evidence": {}, **extra})


def test_running_an_attack_records_its_result_and_the_expectation():
    store = Store()
    body = api(json.dumps({"attack": "read-postgres", "outcome": "succeeds", "evidence": {"rows": 5}}), store) \
        .post("/attacks/read-postgres/run").json()
    jsonschema.validate({k: v for k, v in body.items()}, SCHEMA)
    assert (body["verdict"], body["dst"], body["evidence"]["expected"]) == ("allow", "postgres", "succeeds")
    assert body["evidence"]["modes"] == {"identity": "off", "mtls": "off", "secrets": "off", "user": "off", "network": "off"} and body["evidence"]["as_expected"] is True
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


class NetUp(NoNet):
    state = staticmethod(lambda: "enforce")
    protects = staticmethod(lambda app: app in {"postgres", "records-api"})


def run_with_net(name, phase, net=NetUp, **extra):
    out = attack_out(name, "blocked", evidence={"phase": phase}, **extra)
    app = create_app(Store(), sources=(), exec_in=fake_exec(out), kube=fake_kube("off"), wait=no_wait, net=net)
    return TestClient(app).post(f"/attacks/{name}/run").json()["evidence"]


def test_a_connect_failure_with_the_network_enforced_is_attributed_to_it_as_inferred():
    assert run_with_net("read-postgres", "connect")["stopped_by"] == "network (inferred)"


def test_a_handshake_refusal_is_not_attributed_to_the_network():
    assert run_with_net("forged-identity", "handshake")["stopped_by"] is None


def test_a_connect_failure_is_not_the_network_when_the_layer_is_off_or_the_target_is_unprotected():
    assert run_with_net("read-postgres", "connect", net=NoNet)["stopped_by"] is None
    assert run_with_net("cross-namespace-billing", "connect")["stopped_by"] is None


def test_a_connect_refusal_does_not_wait_for_deny_events():
    waits = []

    async def count(_):
        waits.append(1)

    out = attack_out("read-postgres", "blocked", evidence={"phase": "connect"}, trace="t9")
    app = create_app(Store(), sources=(), exec_in=fake_exec(out), kube=fake_kube("off"), wait=count, net=NetUp)
    TestClient(app).post("/attacks/read-postgres/run")
    assert waits == []


def test_an_attack_runs_from_the_pod_the_catalogue_names_and_defaults_to_the_attacker():
    seen = []

    async def exec_in(namespace, deploy, *cmd):
        seen.append((namespace, deploy))
        return attack_out("x", "succeeds")

    app = create_app(Store(), sources=(), exec_in=exec_in, kube=fake_kube(), wait=no_wait, net=NoNet)
    client = TestClient(app)
    client.post("/attacks/read-postgres/run")
    ev = client.post("/attacks/postgres-from-billing/run").json()
    assert seen == [("attacker", "attacker"), ("clinic", "billing")] and ev["src"] == "billing"


def test_the_catalogue_lists_where_each_attack_runs_from():
    by_name = {a["name"]: a for a in api("").get("/attacks").json()}
    assert by_name["postgres-from-billing"]["from"] == {"namespace": "clinic", "deploy": "billing"}


def specs(**named):
    return {("clinic", name): {"podSelector": {"matchLabels": {"app": name}}, "n": n} for name, n in named.items()}


def test_policy_diff_reports_added_changed_and_removed_with_valid_events():
    old = specs(a=1, b=1, c=1)
    new = specs(a=1, b=2, d=1)
    evs = list(network.diff_policies(old, new, "out-of-band"))
    for ev in evs:
        jsonschema.validate(ev, SCHEMA)
    got = sorted((e["kind"], e["dst"], e["evidence"]["origin"]) for e in evs)
    assert got == [("policy_added", "clinic/d", "out-of-band"), ("policy_changed", "clinic/b", "out-of-band"),
                   ("policy_removed", "clinic/c", "out-of-band")]


def test_the_reason_reads_as_a_sentence():
    by = {e["evidence"]["origin"]: e["reason"] for o in ("controller", "out-of-band")
          for e in network.diff_policies(specs(a=1), {}, o)}
    assert by == {"controller": "a removed by the controller", "out-of-band": "a removed outside the controller"}


def test_an_unchanged_policy_list_reports_nothing():
    assert list(network.diff_policies(specs(a=1), specs(a=1), "controller")) == []


def test_the_watch_baselines_silently_then_reports_what_changed_since():
    state, seen = {"now": specs(a=1, b=1)}, []
    watch = network.Watch(seen.append, lambda: state["now"])
    asyncio.run(watch.sync())
    assert seen == []
    state["now"] = specs(a=1)  # someone ran kubectl delete networkpolicy b
    asyncio.run(watch.sync())
    assert [(e["kind"], e["dst"], e["evidence"]["origin"]) for e in seen] == [("policy_removed", "clinic/b", "out-of-band")]
    asyncio.run(watch.sync())
    assert len(seen) == 1  # reported once


class FakeNet(NoNet):
    """A cluster in a dict: apply and remove change it, listing reads it."""
    def __init__(self):
        self.specs = {}

    def apply(self):
        self.specs = specs(a=1, b=1)

    def remove(self):
        self.specs = {}

    def listing(self):
        return dict(self.specs)


def put_network(client, mode):
    return client.put("/layers/network", json={"mode": mode})


def test_a_controller_apply_is_marked_controller_made_and_a_later_deletion_is_not():
    store, net = Store(), FakeNet()
    app = create_app(store, sources=(), exec_in=fake_exec(""), kube=fake_kube(), wait=no_wait, net=net)
    with TestClient(app) as client:
        assert put_network(client, "enforce").status_code == 200
        added = [e for e in store.since() if e["kind"] == "policy_added"]
        assert sorted(e["dst"] for e in added) == ["clinic/a", "clinic/b"]
        assert {e["evidence"]["origin"] for e in added} == {"controller"}
        put_network(client, "off")
        assert {e["evidence"]["origin"] for e in store.since() if e["kind"] == "policy_removed"} == {"controller"}


def expected_for(name, **modes):
    from observer import layers
    from observer.app import CATALOG
    attack = next(a for a in json.loads(CATALOG.read_text()) if a["name"] == name)
    return layers.expected(attack, {"identity": "off", "mtls": "off", "network": "off", **modes})


def test_the_catalogue_says_which_layer_combinations_stop_each_attack():
    through_the_wire = ["no-identity-records", "cross-namespace-billing", "mcp-no-identity", "forged-identity"]
    for name in through_the_wire:  # a request to a service: mtls or the network stops it
        assert expected_for(name) == "succeeds", name
        assert expected_for(name, network="enforce") == "blocked", name
        assert expected_for(name, identity="enforce", mtls="enforce") == "blocked", name
    for name in ("read-postgres", "postgres-from-billing"):  # Postgres has no mtls: only the network stops it
        assert expected_for(name, identity="enforce", mtls="enforce") == "succeeds", name
        assert expected_for(name, network="enforce") == "blocked", name
    assert expected_for("agent-prompt-injection", identity="enforce", mtls="enforce", network="enforce") == "succeeds"


def test_the_catalogue_says_which_attacks_the_user_layer_stops():
    stopped = ["no-identity-records", "mcp-no-identity", "forged-identity", "forged-user-header", "wrong-audience-token", "agent-prompt-injection"]
    for name in stopped:  # everything that reaches records-api without a good user token
        assert expected_for(name, user="off") == "succeeds", name
        assert expected_for(name, user="audit") == "succeeds", name
        assert expected_for(name, user="enforce") == "blocked", name
    for name in ("cross-namespace-billing", "read-postgres", "postgres-from-billing"):  # these never ask records-api about a user
        assert expected_for(name, user="enforce") == "succeeds", name
    assert expected_for("forged-user-header", network="enforce") == "blocked"
    assert expected_for("wrong-audience-token", identity="enforce", mtls="enforce") == "blocked"


class NetPartial(NetUp):
    state = staticmethod(lambda: "partial")


def test_a_connect_failure_with_a_partial_network_is_attributed_to_it_as_inferred():
    assert run_with_net("read-postgres", "connect", net=NetPartial)["stopped_by"] == "network (inferred)"


def run_auth_failure(secrets):
    out = attack_out("read-postgres", "blocked", evidence={"phase": "auth"})
    app = create_app(Store(), sources=(), exec_in=fake_exec(out), kube=fake_kube("off", secrets), wait=no_wait, net=NoNet)
    return TestClient(app).post("/attacks/read-postgres/run").json()["evidence"]


def test_a_rejected_password_with_secrets_enforced_is_attributed_to_secrets_as_inferred():
    assert run_auth_failure("enforce")["stopped_by"] == "secrets (inferred)"


def test_a_rejected_password_with_secrets_not_enforced_is_not_attributed():
    assert run_auth_failure("audit").get("stopped_by") is None

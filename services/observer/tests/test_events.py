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


def api(output, store=None):
    return TestClient(create_app(store or Store(), sources=(), exec_in=fake_exec(output)))


def test_running_an_attack_records_its_result_and_the_expectation():
    store = Store()
    body = api(json.dumps({"attack": "read-postgres", "outcome": "succeeds", "evidence": {"rows": 5}}), store) \
        .post("/attacks/read-postgres/run").json()
    jsonschema.validate({k: v for k, v in body.items()}, SCHEMA)
    assert (body["verdict"], body["dst"], body["evidence"]["expected"]) == ("allow", "postgres", "succeeds")
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

import json
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient

from observer.app import create_app
from observer.normalize import diff_entries, entry_key, event, from_workload_log
from observer.store import Store

SCHEMA = json.loads((Path(__file__).parent.parent / "observer/event.v1.schema.json").read_text())
LOG = {"event": "x509_svid", "workload": "echo-a", "spiffe_id": "spiffe://playground.local/ns/clinic/sa/echo-a",
       "serial": "ab12", "not_before": "2026-11-03T03:59:18+00:00", "not_after": "2026-11-03T04:01:28+00:00"}


def entry(path):
    return {"spiffe_id": {"trust_domain": "playground.local", "path": path}}


def test_workload_log_becomes_a_valid_identity_event():
    ev = from_workload_log(LOG)
    jsonschema.validate(ev, SCHEMA)
    assert ev["src"] == LOG["spiffe_id"] and ev["evidence"]["serial"] == "ab12"


def test_other_log_lines_are_ignored():
    assert from_workload_log({"event": "jwt_svid"}) is None


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
        emit(from_workload_log(LOG))
        emit(from_workload_log(LOG))

    with TestClient(create_app(store, sources=(source,))):
        pass
    assert len(store.since(0)) == 1


def test_startup_log_backfill_is_deduped_against_the_store():
    store = Store()
    backlog = [LOG, {**LOG, "serial": "cd34"}, LOG]

    async def source(emit):
        for line in backlog:
            emit(from_workload_log(line))

    with TestClient(create_app(store, sources=(source,))):
        pass
    assert [e["evidence"]["serial"] for e in store.since(0)] == ["ab12", "cd34"]

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from clinic.common import client, instrument


def make():
    app = instrument(FastAPI(), "svc")

    @app.get("/hop")
    def hop():
        with client("svc") as c:
            return dict(c.headers)

    return TestClient(app)


def test_inbound_trace_id_is_kept_and_logged(capsys):
    make().get("/hop", headers={"x-trace-id": "abc", "x-caller": "web"})
    event = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert event["trace"] == "abc" and event["caller"] == "web" and event["service"] == "svc"


def test_a_trace_id_is_created_when_absent_and_passed_downstream(capsys):
    headers = make().get("/hop").json()
    event = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert headers["x-trace-id"] == event["trace"] and headers["x-caller"] == "svc"


def test_health_checks_are_not_logged(capsys):
    make().get("/healthz")
    assert capsys.readouterr().out == ""


def test_the_trace_id_is_returned_so_a_page_can_show_it():
    assert make().get("/hop", headers={"x-trace-id": "abc"}).headers["x-trace-id"] == "abc"

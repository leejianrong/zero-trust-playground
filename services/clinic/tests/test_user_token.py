import time

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.client import Client

from clinic import login, records_mcp, web
from clinic.common import client, instrument, user_token_var


def make():
    app = instrument(FastAPI(), "svc")

    @app.get("/hop")
    def hop():
        with client("svc") as c:
            return dict(c.headers)

    return TestClient(app)


def test_a_bearer_token_is_passed_to_the_next_hop():
    assert make().get("/hop", headers={"authorization": "Bearer abc"}).json()["authorization"] == "Bearer abc"


def test_no_token_means_no_authorization_header_downstream():
    assert "authorization" not in make().get("/hop").json()


def test_a_token_does_not_leak_from_one_request_to_the_next():
    c = make()
    c.get("/hop", headers={"authorization": "Bearer abc"})
    assert "authorization" not in c.get("/hop").json()


def signed_in(monkeypatch, expires_in=300, refreshed=None):
    login.SESSIONS.clear()
    login.SESSIONS["sid"] = login.Session("aisha", ["clinician"], "access-1", "refresh-1", time.time() + expires_in)
    seen = []

    def records(request):
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json=[])

    def keycloak(request):
        refreshed.append(request.content.decode()) if refreshed is not None else None
        return httpx.Response(200, json={"access_token": "access-2", "refresh_token": "refresh-2", "expires_in": 300})

    monkeypatch.setattr(web, "client", lambda svc: httpx.Client(headers={"authorization": f"Bearer {user_token_var.get()}"} if user_token_var.get() else {},
                                                                transport=httpx.MockTransport(records)))
    monkeypatch.setattr(login, "keycloak", lambda: httpx.Client(transport=httpx.MockTransport(keycloak)))
    c = TestClient(web.app)
    c.cookies.set(login.COOKIE, "sid")
    return c, seen


def test_web_forwards_the_signed_in_users_token(monkeypatch):
    c, seen = signed_in(monkeypatch)
    assert c.get("/api/patients").status_code == 200
    assert seen == ["Bearer access-1"]


def test_web_sends_no_token_when_nobody_is_signed_in(monkeypatch):
    c, seen = signed_in(monkeypatch)
    c.cookies.clear()
    c.get("/api/patients")
    assert seen == [None]


def test_web_ignores_an_authorization_header_from_the_browser(monkeypatch):
    c, seen = signed_in(monkeypatch)
    c.cookies.clear()
    c.get("/api/patients", headers={"authorization": "Bearer made-up"})
    assert seen == [None]


def test_web_refreshes_a_token_that_is_about_to_expire(monkeypatch):
    refreshed = []
    c, seen = signed_in(monkeypatch, expires_in=10, refreshed=refreshed)
    c.get("/api/patients")
    assert "grant_type=refresh_token" in refreshed[0] and "refresh_token=refresh-1" in refreshed[0]
    assert seen == ["Bearer access-2"]


def test_a_failed_refresh_signs_the_user_out(monkeypatch):
    c, seen = signed_in(monkeypatch, expires_in=10)
    monkeypatch.setattr(login, "keycloak", lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400, json={}))))
    c.get("/api/patients")
    assert seen == [None] and c.get("/auth/me").json() == {"signed_in": False}


async def test_records_mcp_passes_the_callers_token_to_records_api(monkeypatch):
    seen = []

    def records(request):
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json=[])

    monkeypatch.setattr(records_mcp, "client", lambda svc: httpx.Client(headers={"authorization": f"Bearer {user_token_var.get()}"} if user_token_var.get() else {},
                                                                        transport=httpx.MockTransport(records)))
    async with Client(records_mcp.mcp) as c:
        await c.call_tool("list_patients")
    assert seen == [None]  # a client with no headers has no token to pass
    ctx = type("Ctx", (), {"headers": {"authorization": "Bearer from-agent"}})()
    records_mcp.call(ctx, "list_patients", "GET", "/patients")
    assert seen[-1] == "Bearer from-agent"


async def test_a_refusal_from_records_api_reaches_the_agent_with_its_reason(monkeypatch):
    body = {"error": "refused", "layer": "user", "reason": "no token: this request has no bearer token"}
    monkeypatch.setattr(records_mcp, "client", lambda svc: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, json=body))))
    async with Client(records_mcp.mcp) as c:
        result = await c.call_tool("list_patients")
    assert result.is_error and "user layer" in result.content[0].text and "no token" in result.content[0].text


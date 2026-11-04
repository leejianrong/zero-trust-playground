import base64
import hashlib
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
from fastapi.testclient import TestClient

from clinic import login, web


def access_token(user="aisha", roles=("clinician", "offline_access")):
    return jwt.encode({"preferred_username": user, "realm_access": {"roles": list(roles)}, "exp": int(time.time()) + 300}, "k", algorithm="HS256")


class Keycloak:
    """Stands in for Keycloak's token and logout endpoints."""

    def __init__(self, user="aisha", roles=("clinician", "offline_access"), status=200):
        self.user, self.roles, self.status, self.calls = user, roles, status, []

    def __call__(self, request):
        self.calls.append((request.url.path, parse_qs(request.content.decode())))
        if request.url.path.endswith("/token") and self.status == 200:
            return httpx.Response(200, json={"access_token": access_token(self.user, self.roles), "refresh_token": "r1", "expires_in": 300})
        if request.url.path.endswith("/token"):
            return httpx.Response(self.status, json={"error": "invalid_grant", "error_description": "bad code"})
        return httpx.Response(204)


def app(monkeypatch, kc):
    monkeypatch.setattr(login, "keycloak", lambda: httpx.Client(transport=httpx.MockTransport(kc)))
    login.SESSIONS.clear(); login.PENDING.clear()
    return TestClient(web.app, follow_redirects=False)


def start(c):
    r = c.get("/auth/login")
    return r, parse_qs(urlparse(r.headers["location"]).query)


def test_login_sends_the_browser_to_keycloak_with_pkce(monkeypatch):
    r, q = start(app(monkeypatch, Keycloak()))
    assert r.status_code == 302 and r.headers["location"].startswith("http://localhost:8180/realms/clinic/protocol/openid-connect/auth?")
    assert q["client_id"] == ["web"] and q["response_type"] == ["code"] and q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == ["http://localhost:8081/auth/callback"] and q["state"] and q["code_challenge"]


def test_the_callback_trades_the_code_with_the_matching_verifier_and_signs_the_user_in(monkeypatch):
    kc = Keycloak()
    c = app(monkeypatch, kc)
    _, q = start(c)
    r = c.get("/auth/callback", params={"code": "abc", "state": q["state"][0]})
    assert r.status_code == 302 and r.headers["location"] == "/"
    _, form = kc.calls[0]
    digest = hashlib.sha256(form["code_verifier"][0].encode()).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == q["code_challenge"][0]
    assert form["code"] == ["abc"] and form["grant_type"] == ["authorization_code"]
    me = c.get("/auth/me").json()
    assert me["signed_in"] is True and me["user"] == "aisha" and me["roles"] == ["clinician"]


def test_the_session_cookie_cannot_be_read_by_scripts(monkeypatch):
    c = app(monkeypatch, Keycloak())
    _, q = start(c)
    r = c.get("/auth/callback", params={"code": "abc", "state": q["state"][0]})
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()


def test_a_callback_with_an_unknown_state_is_refused_and_signs_nobody_in(monkeypatch):
    kc = Keycloak()
    c = app(monkeypatch, kc)
    assert c.get("/auth/callback", params={"code": "abc", "state": "forged"}).status_code == 400
    assert kc.calls == [] and c.get("/auth/me").json() == {"signed_in": False}


def test_a_state_can_be_used_once(monkeypatch):
    c = app(monkeypatch, Keycloak())
    _, q = start(c)
    assert c.get("/auth/callback", params={"code": "abc", "state": q["state"][0]}).status_code == 302
    assert c.get("/auth/callback", params={"code": "abc", "state": q["state"][0]}).status_code == 400


def test_a_refused_code_gives_a_reason_and_no_session(monkeypatch):
    c = app(monkeypatch, Keycloak(status=400))
    _, q = start(c)
    r = c.get("/auth/callback", params={"code": "bad", "state": q["state"][0]})
    assert r.status_code == 502 and "bad code" in r.json()["detail"]
    assert c.get("/auth/me").json() == {"signed_in": False}


def test_nobody_is_signed_in_by_default(monkeypatch):
    assert app(monkeypatch, Keycloak()).get("/auth/me").json() == {"signed_in": False}


def test_sign_out_ends_the_keycloak_session_and_ours(monkeypatch):
    kc = Keycloak(user="bob", roles=("receptionist",))
    c = app(monkeypatch, kc)
    _, q = start(c)
    c.get("/auth/callback", params={"code": "abc", "state": q["state"][0]})
    assert c.get("/auth/me").json()["roles"] == ["receptionist"]
    assert c.post("/auth/logout").status_code == 204
    assert kc.calls[-1][0].endswith("/logout") and kc.calls[-1][1]["refresh_token"] == ["r1"]
    assert c.get("/auth/me").json() == {"signed_in": False}

"""Sign in for the clinic page: authorization code with PKCE against Keycloak (ADR-0013).

The browser talks to Keycloak at its public name. This service talks to it by service name. Sessions live
in memory, so a restart signs everyone out. That is fine for a playground and wrong for anything else."""
import base64
import hashlib
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

PUBLIC = os.environ.get("KEYCLOAK_PUBLIC_URL", "http://localhost:8180/realms/clinic")
INTERNAL = os.environ.get("KEYCLOAK_INTERNAL_URL", "http://keycloak.keycloak.svc:8080/realms/clinic")
CALLBACK = os.environ.get("LOGIN_CALLBACK_URL", "http://localhost:8081/auth/callback")
CLIENT_ID = "web"
COOKIE = "ztp_session"
CLINIC_ROLES = ("clinician", "receptionist")
MAX_PENDING = 100  # sign-ins started and never finished; the oldest are forgotten


@dataclass
class Session:
    user: str
    roles: list[str]
    access_token: str
    refresh_token: str
    expires_at: float


SESSIONS: dict[str, Session] = {}
PENDING: dict[str, str] = {}  # state -> PKCE verifier, used once

router = APIRouter(prefix="/auth")


def keycloak() -> httpx.Client:
    return httpx.Client(timeout=5)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@router.get("/login")
def sign_in():
    verifier, state = _b64(secrets.token_bytes(32)), _b64(secrets.token_bytes(16))
    PENDING[state] = verifier
    while len(PENDING) > MAX_PENDING:
        PENDING.pop(next(iter(PENDING)))
    query = urlencode({"client_id": CLIENT_ID, "response_type": "code", "scope": "openid", "redirect_uri": CALLBACK,
                       "state": state, "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
                       "code_challenge_method": "S256"})
    return RedirectResponse(f"{PUBLIC}/protocol/openid-connect/auth?{query}", status_code=302)


@router.get("/callback")
def callback(state: str, code: str | None = None, error: str | None = None):
    verifier = PENDING.pop(state, None)
    if verifier is None:
        raise HTTPException(400, "unknown or used sign-in state: start again from Sign in")
    if error or not code:
        raise HTTPException(400, f"sign-in was not completed: {error or 'no code returned'}")
    try:
        with keycloak() as kc:
            r = kc.post(f"{INTERNAL}/protocol/openid-connect/token", data={
                "grant_type": "authorization_code", "client_id": CLIENT_ID, "code": code,
                "redirect_uri": CALLBACK, "code_verifier": verifier})
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Keycloak could not be reached: {type(exc).__name__}") from exc
    if r.status_code != 200:
        try:
            why = r.json().get("error_description", r.status_code)
        except ValueError:
            why = r.status_code
        raise HTTPException(502, f"Keycloak refused the sign-in: {why}")
    tokens = r.json()
    # Read for display only. This service received the token straight from Keycloak over the backchannel.
    claims = jwt.decode(tokens["access_token"], options={"verify_signature": False})
    sid = secrets.token_urlsafe(32)
    SESSIONS[sid] = Session(claims.get("preferred_username", "unknown"),
                            [x for x in claims.get("realm_access", {}).get("roles", []) if x in CLINIC_ROLES],
                            tokens["access_token"], tokens["refresh_token"], time.time() + tokens["expires_in"])
    response = RedirectResponse("/", status_code=302)
    response.set_cookie(COOKIE, sid, httponly=True, samesite="lax", path="/")
    return response


def current(request: Request) -> Session | None:
    return SESSIONS.get(request.cookies.get(COOKIE, ""))


@router.get("/me")
def me(request: Request):
    s = current(request)
    return {"signed_in": True, "user": s.user, "roles": s.roles} if s else {"signed_in": False}


@router.post("/logout", status_code=204)
def sign_out(request: Request):
    s = SESSIONS.pop(request.cookies.get(COOKIE, ""), None)
    if s:  # end Keycloak's own session too, or the next Sign in would skip the password
        try:
            with keycloak() as kc:
                kc.post(f"{INTERNAL}/protocol/openid-connect/logout", data={"client_id": CLIENT_ID, "refresh_token": s.refresh_token})
        except httpx.HTTPError:
            pass  # our session is gone either way; Keycloak's own will time out
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/")
    return response


def token_for(request: Request) -> str | None:
    """The signed-in user's access token, refreshed when it is about to expire. A failed refresh signs them out."""
    sid = request.cookies.get(COOKIE, "")
    s = SESSIONS.get(sid)
    if s is None:
        return None
    if s.expires_at - time.time() < 30:
        try:
            with keycloak() as kc:
                r = kc.post(f"{INTERNAL}/protocol/openid-connect/token", data={
                    "grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": s.refresh_token})
        except httpx.HTTPError:  # Keycloak is away: keep the session, and use the token only while it is still valid
            return s.access_token if s.expires_at > time.time() else None
        if r.status_code != 200:
            SESSIONS.pop(sid, None)
            return None
        t = r.json()
        s.access_token, s.refresh_token, s.expires_at = t["access_token"], t["refresh_token"], time.time() + t["expires_in"]
    return s.access_token

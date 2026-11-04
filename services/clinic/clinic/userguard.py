"""The user layer at records-api's door (ADR-0013): who is this person, and may their role make this request.

`off` trusts an X-User header, which anyone can set. `audit` and `enforce` check the bearer token's signature,
issuer, audience and expiry, then map the user's realm roles to read or write."""
import json
import os
import uuid
from dataclasses import dataclass

import jwt

from clinic.common import emit, trace_var

PERMISSIONS = {"clinician": {"read", "write"}, "receptionist": {"read"}}
READ_METHODS = {"GET", "HEAD", "OPTIONS"}


class TokenError(Exception):
    """The token cannot be trusted. The message is safe to show the caller."""


@dataclass
class Claims:
    user: str
    subject: str | None
    roles: list[str]
    client: str | None
    audience: list[str]


def permission_for(method: str) -> str:
    return "read" if method in READ_METHODS else "write"


class TokenVerifier:
    def __init__(self, issuer: str, audience: str, jwks):
        self.issuer, self.audience, self.jwks = issuer, audience, jwks

    def verify(self, token: str) -> Claims:
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            c = jwt.decode(token, key, algorithms=["RS256"], audience=self.audience, issuer=self.issuer,
                           options={"require": ["exp", "iss", "aud"]})
        except jwt.ExpiredSignatureError as exc:
            raise TokenError("the token has expired") from exc
        except jwt.InvalidIssuerError as exc:
            raise TokenError(f"the token was not issued by {self.issuer}: wrong issuer") from exc
        except jwt.InvalidAudienceError as exc:
            raise TokenError(f"the token is not for {self.audience}: wrong audience") from exc
        except jwt.InvalidSignatureError as exc:
            raise TokenError("the token signature does not match: bad signature") from exc
        except jwt.PyJWTError as exc:
            raise TokenError(f"the token is malformed or unusable: {type(exc).__name__}") from exc
        aud = c["aud"] if isinstance(c["aud"], list) else [c["aud"]]
        return Claims(c.get("preferred_username") or c.get("sub", "unknown"), c.get("sub"),
                      [r for r in c.get("realm_access", {}).get("roles", []) if r in PERMISSIONS], c.get("azp"), aud)


def from_env() -> TokenVerifier:
    issuer = os.environ.get("USER_ISSUER", "http://localhost:8180/realms/clinic")
    jwks = os.environ.get("USER_JWKS_URL", "http://keycloak.keycloak.svc:8080/realms/clinic/protocol/openid-connect/certs")
    return TokenVerifier(issuer, os.environ.get("USER_AUDIENCE", "records-api"), jwt.PyJWKClient(jwks, timeout=5))


class UserGuard:
    """ASGI middleware. In `off` it does nothing. Otherwise every request gets one `user_authz` event."""

    def __init__(self, app, service: str, mode_of, verifier: TokenVerifier | None = None):
        self.app, self.service, self.mode_of, self._verifier = app, service, mode_of, verifier

    @property
    def verifier(self) -> TokenVerifier:
        self._verifier = self._verifier or from_env()
        return self._verifier

    def decide(self, headers: dict, method: str) -> tuple[str | None, Claims | None, int]:
        """(refusal reason, claims, status to refuse with). A reason of None means allowed."""
        auth = headers.get(b"authorization", b"").decode()
        if not auth.lower().startswith("bearer "):
            return "no token: this request has no bearer token", None, 401
        try:
            claims = self.verifier.verify(auth[7:].strip())
        except TokenError as exc:
            return str(exc), None, 401
        need = permission_for(method)
        if not any(need in PERMISSIONS.get(r, ()) for r in claims.roles):
            roles = ", ".join(claims.roles) or "no clinic role"
            return f"{claims.user} has {roles}, which does not allow {need}", claims, 403
        return None, claims, 200

    async def __call__(self, scope, receive, send):
        mode = self.mode_of()
        if scope["type"] != "http" or mode == "off" or scope["path"] == "/healthz":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        method = scope["method"]
        why, claims, status = self.decide(headers, method)
        verdict = "allow" if why is None else "deny" if mode == "enforce" else "would_deny"
        trace = trace_var.get() or headers.get(b"x-trace-id", b"").decode() or uuid.uuid4().hex[:12]
        emit(event="user_authz", service=self.service, mode=mode, user=claims.user if claims else None, subject=claims.subject if claims else None,
             roles=claims.roles if claims else [], client=claims.client if claims else None,
             audience=claims.audience if claims else [], method=method, route=scope["path"],
             verdict=verdict, reason=why, trace=trace)
        if verdict != "deny":
            return await self.app(scope, receive, send)
        body = json.dumps({"error": "refused", "layer": "user", "reason": why, "trace": trace}).encode()
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"application/json"), (b"x-trace-id", trace.encode())]})
        await send({"type": "http.response.body", "body": body})

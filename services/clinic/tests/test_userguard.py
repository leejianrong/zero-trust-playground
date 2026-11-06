import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from clinic import userguard
from clinic.userguard import TokenError, TokenVerifier, UserGuard, permission_for

ISSUER, AUDIENCE = "http://localhost:8180/realms/clinic", "records-api"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJwks:
    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": KEY.public_key()})()


def token(roles=("clinician",), key=KEY, iss=ISSUER, aud=AUDIENCE, exp=300, user="aisha"):
    now = int(time.time())
    return jwt.encode({"iss": iss, "aud": aud, "azp": "web", "sub": "id-" + user, "preferred_username": user,
                       "realm_access": {"roles": list(roles)}, "iat": now, "exp": now + exp}, key, algorithm="RS256")


def verifier():
    return TokenVerifier(ISSUER, AUDIENCE, FakeJwks())


@pytest.mark.parametrize("method,need", [("GET", "read"), ("HEAD", "read"), ("POST", "write"), ("PUT", "write"), ("DELETE", "write")])
def test_a_method_needs_read_or_write(method, need):
    assert permission_for(method) == need


def test_a_good_token_gives_the_user_and_roles():
    claims = verifier().verify(token())
    assert claims.user == "aisha" and claims.roles == ["clinician"] and claims.client == "web"


@pytest.mark.parametrize("bad,reason", [
    (lambda: token(exp=-10), "expired"),
    (lambda: token(iss="http://evil/realms/clinic"), "issuer"),
    (lambda: token(aud="billing"), "audience"),
    (lambda: token(key=OTHER_KEY), "signature"),
    (lambda: "not-a-token", "malformed"),
])
def test_a_bad_token_is_refused_with_a_reason(bad, reason):
    with pytest.raises(TokenError) as e:
        verifier().verify(bad())
    assert reason in str(e.value)


def test_a_token_signed_with_none_is_refused():
    forged = jwt.encode({"iss": ISSUER, "aud": AUDIENCE}, None, algorithm="none")
    with pytest.raises(TokenError):
        verifier().verify(forged)


@pytest.mark.parametrize("bad", [lambda: token(exp=-10), lambda: token(iss="http://evil/realms/clinic"), lambda: token(aud="billing")])
def test_a_refusal_after_the_signature_checked_out_still_names_the_person(bad):
    with pytest.raises(TokenError) as e:
        verifier().verify(bad())
    assert e.value.claims.user == "aisha" and e.value.claims.client == "web"


def test_a_refusal_for_a_bad_signature_names_nobody():
    with pytest.raises(TokenError) as e:
        verifier().verify(token(key=OTHER_KEY))
    assert e.value.claims is None  # the claims were not vouched for, so they are not repeated


def test_a_wrong_audience_refusal_carries_who_it_was_for_the_log():
    why, claims, status = UserGuard(inner, "records-api", lambda: "enforce", verifier()).decide(
        {b"authorization": b"Bearer " + token(aud="billing").encode()}, "GET")
    assert status == 401 and "wrong audience" in why
    assert claims.user == "aisha" and claims.audience == ["billing"]


def test_a_key_keycloak_does_not_have_says_so():
    class NoSuchKey:
        def get_signing_key_from_jwt(self, token):
            raise jwt.PyJWKClientError("Unable to find a signing key that matches: 'old'")

    with pytest.raises(TokenError) as e:
        TokenVerifier(ISSUER, AUDIENCE, NoSuchKey()).verify(token())
    assert "no longer has" in str(e.value) and "PyJWKClientError" not in str(e.value)


def test_an_unsigned_token_says_which_algorithm_it_used():
    forged = jwt.encode({"iss": ISSUER, "aud": AUDIENCE}, None, algorithm="none")
    with pytest.raises(TokenError) as e:
        verifier().verify(forged)
    assert "none" in str(e.value) and "RS256" in str(e.value)


async def inner(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def call(mode, method="GET", auth=None, x_user=None, path="/patients"):
    sent, headers = [], [(b"x-trace-id", b"t1")]
    if auth:
        headers.append((b"authorization", b"Bearer " + auth.encode()))
    if x_user:
        headers.append((b"x-user", x_user.encode()))

    async def send(m):
        sent.append(m)

    await UserGuard(inner, "records-api", lambda: mode, verifier())({"type": "http", "method": method, "path": path, "headers": headers}, None, send)
    status = sent[0]["status"]
    return status, (json.loads(sent[1]["body"]) if status != 200 else None)


def events(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if '"user_authz"' in line]


async def test_off_trusts_the_header_and_logs_who_it_claimed_to_be(capsys):
    assert (await call("off", "DELETE", x_user="anyone"))[0] == 200
    only = events(capsys)
    assert len(only) == 1 and only[0]["user"] == "anyone" and only[0]["verdict"] == "allow" and only[0]["mode"] == "off"
    assert "X-User" in only[0]["reason"] and only[0]["client"] is None and only[0]["roles"] == []


async def test_off_without_a_header_checks_nothing_and_logs_nothing(capsys):
    assert (await call("off", "DELETE"))[0] == 200
    assert events(capsys) == []


async def test_enforce_lets_a_clinician_read_and_write():
    for method in ("GET", "POST", "PUT", "DELETE"):
        assert (await call("enforce", method, auth=token(("clinician",))))[0] == 200


async def test_enforce_lets_a_receptionist_read_but_not_write(capsys):
    assert (await call("enforce", "GET", auth=token(("receptionist",), user="bob")))[0] == 200
    for method in ("POST", "PUT", "DELETE"):
        status, body = await call("enforce", method, auth=token(("receptionist",), user="bob"))
        assert status == 403 and "receptionist" in body["reason"] and body["trace"] == "t1"
    last = events(capsys)[-1]
    assert last["verdict"] == "deny" and last["user"] == "bob" and last["roles"] == ["receptionist"]


async def test_enforce_ignores_the_header_and_demands_a_token(capsys):
    status, body = await call("enforce", "GET", x_user="aisha")
    assert status == 401 and "no token" in body["reason"]
    assert events(capsys)[-1]["verdict"] == "deny"


async def test_enforce_returns_401_for_a_bad_token():
    for bad in (token(exp=-10), token(aud="billing"), token(iss="http://evil"), token(key=OTHER_KEY)):
        assert (await call("enforce", "GET", auth=bad))[0] == 401


async def test_audit_logs_a_would_be_refusal_and_lets_the_request_through(capsys):
    assert (await call("audit", "DELETE", auth=token(("receptionist",), user="bob")))[0] == 200
    assert (await call("audit", "GET"))[0] == 200
    got = events(capsys)
    assert [e["verdict"] for e in got] == ["would_deny", "would_deny"] and got[0]["mode"] == "audit"


async def test_health_checks_need_no_token():
    assert (await call("enforce", path="/healthz"))[0] == 200


def test_the_verifier_is_built_from_the_environment(monkeypatch):
    monkeypatch.setenv("USER_ISSUER", ISSUER)
    assert userguard.from_env().issuer == ISSUER


class DownJwks:
    def get_signing_key_from_jwt(self, token):
        raise jwt.PyJWKClientConnectionError("keycloak is not answering")


async def test_enforce_says_keycloak_is_unreachable_with_a_503_and_not_a_bad_token(capsys):
    sent = []

    async def send(m):
        sent.append(m)

    guard = UserGuard(inner, "records-api", lambda: "enforce", TokenVerifier(ISSUER, AUDIENCE, DownJwks()))
    await guard({"type": "http", "method": "GET", "path": "/patients",
                 "headers": [(b"authorization", b"Bearer " + token().encode())]}, None, send)
    assert sent[0]["status"] == 503 and b"Keycloak" in sent[1]["body"]
    assert "Keycloak" in events(capsys)[-1]["reason"]

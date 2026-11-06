import json
from pathlib import Path

import httpx
import psycopg
from cryptography import x509

from clinic.attacks.run import ATTACKS, CLAIMED, failure_phase, forged_certificate, run

CATALOG = json.loads((Path(__file__).parent.parent / "clinic/attacks/catalog.json").read_text())


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_every_catalogued_attack_has_an_implementation_and_a_default_expectation():
    assert {a["name"] for a in CATALOG} == set(ATTACKS)
    assert all(a["expected"]["default"] == "succeeds" for a in CATALOG)


def test_an_attack_tags_every_request_with_one_trace_id_and_reports_it():
    seen = []

    def handler(request):
        seen.append(request.headers.get("x-trace-id"))
        return httpx.Response(200, json=[])

    result = run("no-identity-records", client(handler))
    assert result["trace"] and set(seen) == {result["trace"]}


def test_http_attack_succeeds_when_the_service_answers():
    result = run("no-identity-records", client(lambda r: httpx.Response(200, json=[{}, {}])))
    assert result["outcome"] == "succeeds" and result["evidence"]["items"] == 2


def test_http_attack_is_blocked_by_a_refusal():
    assert run("cross-namespace-billing", client(lambda r: httpx.Response(403, json={})))["outcome"] == "blocked"


def test_http_attack_is_blocked_when_the_connection_fails():
    def refuse(request):
        raise httpx.ConnectError("refused")
    result = run("no-identity-records", client(refuse))
    assert result["outcome"] == "blocked" and result["evidence"]["error"] == "ConnectError"


def test_injection_attack_succeeds_only_if_the_decoy_is_gone():
    state = {"patients": {}, "next": 10}

    def web(request):
        path = request.url.path
        if request.method == "POST" and path == "/api/patients":
            pid = state["next"]; state["next"] += 1
            state["patients"][pid] = json.loads(request.content)
            return httpx.Response(201, json={"id": pid})
        if request.method == "GET" and path == "/api/patients":
            return httpx.Response(200, json=[{"id": i} for i in state["patients"]])
        if request.method == "DELETE":
            return httpx.Response(204 if state["patients"].pop(int(path.rsplit("/", 1)[-1]), None) else 404)
        if path == "/api/agent/summarise":
            if state["agent_obeys"]:
                state["patients"].pop(10)  # the decoy is the first record planted
            return httpx.Response(200, json={"tool_calls": [{"tool": "delete_patient"}]})
        return httpx.Response(404)

    state["agent_obeys"] = True
    assert run("agent-prompt-injection", client(web))["outcome"] == "succeeds"
    assert state["patients"] == {}  # everything planted was cleaned up

    state.update(patients={}, next=10, agent_obeys=False)
    assert run("agent-prompt-injection", client(web))["outcome"] == "blocked"
    assert state["patients"] == {}


def test_the_forged_certificate_names_the_web_app_but_is_signed_by_itself():
    pem, _ = forged_certificate()
    cert = x509.load_pem_x509_certificate(pem.encode())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert san.get_values_for_type(x509.UniformResourceIdentifier) == [CLAIMED]
    assert cert.issuer == cert.subject  # no CA vouches for it


def blocked_by(exc, name="no-identity-records"):
    def fail(request):
        raise exc
    return run(name, client(fail))["evidence"]


def test_a_blocked_attack_records_which_phase_failed():
    assert blocked_by(httpx.ConnectError("refused"))["phase"] == "connect"
    assert blocked_by(httpx.RemoteProtocolError("server disconnected"))["phase"] == "handshake"
    assert run("cross-namespace-billing", client(lambda r: httpx.Response(403, json={})))["evidence"]["phase"] == "request"


def test_an_exception_group_is_reported_as_its_first_real_error():
    ev = blocked_by(ExceptionGroup("unhandled errors in a TaskGroup", [httpx.ConnectError("refused")]))
    assert (ev["error"], ev["phase"]) == ("ConnectError", "connect")


def test_postgres_from_billing_is_the_postgres_attack_run_from_another_pod():
    assert ATTACKS["postgres-from-billing"] is ATTACKS["read-postgres"]
    entry = next(a for a in CATALOG if a["name"] == "postgres-from-billing")
    assert entry["from"] == {"namespace": "clinic", "deploy": "billing"}
    assert entry["expected"]["rules"] == [{"when": {"network": "enforce"}, "outcome": "blocked"},
                                          {"when": {"secrets": "enforce"}, "outcome": "blocked"}]


def test_a_revoked_password_is_its_own_failure_phase():
    err = psycopg.OperationalError('connection failed: FATAL:  password authentication failed for user "clinic"')
    assert failure_phase(err) == "auth"


def test_a_connect_timeout_is_a_connect_failure():
    assert blocked_by(httpx.ConnectTimeout("timed out"))["phase"] == "connect"
    assert blocked_by(psycopg.OperationalError("connection timeout expired"))["phase"] == "connect"


def test_the_forged_user_header_attack_sends_x_user_and_no_token():
    seen = []

    def handler(request):
        seen.append((request.headers.get("x-user"), request.headers.get("authorization")))
        return httpx.Response(200, json=[{}])

    assert run("forged-user-header", client(handler))["outcome"] == "succeeds"
    assert seen == [("aisha", None)]


def test_the_wrong_audience_attack_presents_a_real_token_that_names_another_service():
    seen = []

    def handler(request):
        if request.url.path.endswith("/token"):
            seen.append(("token", request.content.decode()))
            return httpx.Response(200, json={"access_token": "billing-token"})
        seen.append(("records", request.headers.get("authorization")))
        return httpx.Response(401, json={"layer": "user", "reason": "wrong audience"})

    result = run("wrong-audience-token", client(handler))
    assert result["outcome"] == "blocked" and result["evidence"]["phase"] == "request"
    assert seen[0][0] == "token" and "client_id=attacker-cli" in seen[0][1] and "username=aisha" in seen[0][1]
    assert seen[1] == ("records", "Bearer billing-token")


def test_the_wrong_audience_attack_does_not_pass_as_blocked_when_keycloak_is_missing():
    import pytest

    from clinic.attacks.run import SetupError

    def handler(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(SetupError, match="make keycloak"):
        run("wrong-audience-token", client(handler))


def test_an_mcp_tool_that_is_refused_blocks_the_attack(monkeypatch):
    from clinic.attacks import run as attacks

    class Session:
        async def call_tool(self, name):
            return type("R", (), {"is_error": True, "content": [type("T", (), {"text": "records-api answered 401. user layer: no token"})()]})()

    class Opened:
        async def __aenter__(self):
            return Session()

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(attacks, "open_session", lambda *a, **k: Opened())
    result = run("mcp-no-identity", client(lambda r: httpx.Response(200)))
    assert result["outcome"] == "blocked" and "user layer" in result["evidence"]["detail"]

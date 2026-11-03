import pytest

from clinic.authz import AGENT, BILLING, MCP, WEB, decide, spiffe

ATTACKER = spiffe("attacker", "attacker")


@pytest.mark.parametrize("service,caller,method,path", [
    ("records-api", WEB, "GET", "/patients"),
    ("records-api", WEB, "POST", "/patients"),
    ("records-api", WEB, "DELETE", "/patients/3"),
    ("records-api", BILLING, "GET", "/patients/2"),
    ("records-api", MCP, "PUT", "/patients/2"),
    ("billing", WEB, "GET", "/invoices/4"),
    ("records-mcp", AGENT, "POST", "/mcp"),
    ("agent", WEB, "POST", "/tasks/summarise"),
])
def test_every_legitimate_path_is_allowed(service, caller, method, path):
    assert decide(service, "enforce", caller, method, path, tls=True) == ("allow", None)


@pytest.mark.parametrize("service,caller,method,path", [
    ("records-api", BILLING, "DELETE", "/patients/2"),
    ("records-api", BILLING, "GET", "/patients"),
    ("records-api", AGENT, "GET", "/patients"),
    ("records-api", ATTACKER, "GET", "/patients"),
    ("billing", MCP, "GET", "/invoices/1"),
    ("records-mcp", WEB, "POST", "/mcp"),
    ("agent", AGENT, "POST", "/tasks/summarise"),
])
def test_a_workload_off_its_path_is_refused_with_a_reason(service, caller, method, path):
    verdict, why = decide(service, "enforce", caller, method, path, tls=True)
    assert verdict == "deny" and caller in why and path in why


def test_no_certificate_and_plain_connections_are_refused_with_their_own_reasons():
    assert decide("records-api", "enforce", None, "GET", "/patients", tls=True)[1] == "no client certificate presented"
    assert "plain connection" in decide("records-api", "enforce", None, "GET", "/patients", tls=False)[1]


def test_audit_reports_the_same_refusal_without_enforcing_it():
    assert decide("records-api", "audit", None, "GET", "/patients", tls=False)[0] == "would_deny"


def test_a_service_with_no_rules_accepts_everyone():
    assert decide("web", "enforce", None, "GET", "/", tls=False) == ("allow", None)

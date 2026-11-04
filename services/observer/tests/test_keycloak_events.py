import json

from observer import adapters
from observer.normalize import from_keycloak_log, from_log_line

# Lines copied from a real Keycloak 26.8 pod (jboss-logging listener), with fields we do not read dropped.
PREFIX = '2026-11-04 14:58:29,898 INFO  [org.keycloak.events] (executor-thread-7) '
LOGIN = PREFIX + 'type="LOGIN", realmId="979899d1", realmName="clinic", clientId="web", userId="7bae1e22", sessionId="uSOmg", ipAddress="127.0.0.1", auth_method="openid-connect", username="aisha"'
LOGOUT = PREFIX.replace("29,898", "30,777") + 'type="LOGOUT", realmId="979899d1", realmName="clinic", clientId="web", userId="7bae1e22", sessionId="uSOmg", ipAddress="10.42.0.217"'
BAD_PASSWORD = PREFIX + 'type="LOGIN_ERROR", realmId="979899d1", realmName="clinic", clientId="web", userId="0e5aac40", ipAddress="10.42.0.196", error="invalid_user_credentials", username="bob"'
NO_COOKIE = PREFIX + 'type="LOGIN_ERROR", realmId="979899d1", realmName="clinic", clientId="web", userId="null", error="cookie_not_found"'
PKCE = PREFIX + 'type="CODE_TO_TOKEN_ERROR", realmId="979899d1", realmName="clinic", clientId="web", userId="7bae1e22", error="pkce_verification_failed"'
ADMIN = PREFIX + 'type="LOGIN", realmId="6ab42280", realmName="master", clientId="admin-cli", userId="6ab42280", username="admin"'


def test_a_sign_in_becomes_an_allow_event_naming_the_user_and_client():
    ev = from_keycloak_log(LOGIN)
    assert (ev["layer"], ev["kind"], ev["verdict"], ev["src"], ev["dst"]) == ("user", "user_login", "allow", "aisha", "web")
    assert "aisha signed in to web" in ev["reason"]
    assert abs(ev["ts"] - 1793804309.898) < 1  # the log time (UTC), so a replayed line keeps its real age
    assert ev["evidence"]["serial"]  # emit() drops a line it has already seen


def test_a_sign_out_names_the_user_learned_from_their_sign_in():
    from_keycloak_log(LOGIN)
    ev = from_keycloak_log(LOGOUT)
    assert (ev["kind"], ev["verdict"], ev["src"]) == ("user_logout", "info", "aisha")


def test_a_wrong_password_is_a_deny_event_with_the_reason_keycloak_gave():
    ev = from_keycloak_log(BAD_PASSWORD)
    assert (ev["kind"], ev["verdict"], ev["src"]) == ("user_login_failed", "deny", "bob")
    assert "invalid_user_credentials" in ev["reason"]


def test_a_failure_with_no_user_still_shows_and_says_nobody():
    ev = from_keycloak_log(NO_COOKIE)
    assert ev["src"] == "anonymous" and "cookie_not_found" in ev["reason"]


def test_a_failed_token_exchange_is_a_deny_event():
    ev = from_keycloak_log(PKCE)
    assert (ev["kind"], ev["verdict"]) == ("user_token_refused", "deny") and "pkce_verification_failed" in ev["reason"]


def test_other_realms_and_other_lines_are_ignored():
    assert from_keycloak_log(ADMIN) is None
    assert from_keycloak_log("2026-11-04 14:58:29,898 INFO  [io.quarkus] Keycloak started") is None
    assert from_keycloak_log(PREFIX + 'type="CODE_TO_TOKEN", realmName="clinic", clientId="web", userId="7bae1e22"') is None


def test_the_adapter_is_one_of_the_sources():
    assert adapters.keycloak_events in adapters.ALL


def test_a_records_api_decision_carries_subject_client_and_audience():
    line = json.dumps({"event": "user_authz", "service": "records-api", "mode": "enforce", "user": "bob", "subject": "0e5aac40",
                       "roles": ["receptionist"], "client": "web", "audience": ["records-api", "account"], "method": "POST",
                       "route": "/patients", "verdict": "deny", "reason": "bob has receptionist, which does not allow write", "trace": "t1"})
    ev = from_log_line(line)
    assert (ev["layer"], ev["kind"], ev["verdict"], ev["src"], ev["dst"], ev["trace"]) == ("user", "user_authorisation", "deny", "bob", "records-api", "t1")
    assert ev["evidence"]["subject"] == "0e5aac40" and ev["evidence"]["client"] == "web" and ev["evidence"]["audience"] == ["records-api", "account"]


def test_an_audit_finding_is_information_and_a_missing_user_is_anonymous():
    line = json.dumps({"event": "user_authz", "service": "records-api", "mode": "audit", "user": None, "subject": None, "roles": [],
                       "client": None, "audience": [], "method": "GET", "route": "/patients", "verdict": "would_deny",
                       "reason": "no token", "trace": "t2"})
    ev = from_log_line(line)
    assert ev["verdict"] == "info" and ev["src"] == "anonymous" and ev["evidence"]["decision"] == "would_deny"

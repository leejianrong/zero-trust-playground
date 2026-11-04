import json
from pathlib import Path

from observer import adapters
from observer.normalize import CREDENTIAL_TTL_S, from_vault_audit

# Lines copied from a real Vault audit device (file_path=stdout), with the fields we do not read dropped.
ISSUED = json.dumps({
    "type": "response", "time": "2026-11-04T04:21:23.165510031Z", "error": None,
    "auth": {"display_name": "jwt-spiffe://playground.local/ns/clinic/sa/records-api", "metadata": {"role": "records-api"}},
    "request": {"path": "database/creds/records-api", "operation": "read"},
    "response": {"secret": {"lease_id": "database/creds/records-api/s0yprMyHxq1kDcryWtZU5UJC"}}})
DENIED = json.dumps({
    "type": "response", "time": "2026-11-04T04:21:50.076641137Z", "error": "1 error occurred:\n\t* permission denied\n\n",
    "auth": {"display_name": "jwt-spiffe://playground.local/ns/clinic/sa/billing", "metadata": {"role": "billing"}},
    "request": {"path": "database/creds/records-api", "operation": "read"}, "response": {"secret": None}})


def test_a_credential_read_becomes_an_issued_event_with_the_holder_and_lease():
    ev = from_vault_audit(ISSUED)
    assert (ev["layer"], ev["kind"], ev["verdict"], ev["src"], ev["dst"]) == ("secrets", "credential_issued", "allow", "records-api", "postgres")
    assert ev["evidence"]["ttl_s"] == 120 and ev["evidence"]["role"] == "records-api"
    assert ev["evidence"]["serial"] == "database/creds/records-api/s0yprMyHxq1kDcryWtZU5UJC"  # emit() dedupes on this
    assert abs(ev["ts"] - 1793766083.1655) < 1  # the audit time, so a replayed line keeps its real age


def test_a_refused_read_becomes_a_deny_event_naming_who_asked():
    ev = from_vault_audit(DENIED)
    assert (ev["kind"], ev["verdict"], ev["src"]) == ("credential_denied", "deny", "billing")
    assert "permission denied" in ev["reason"]


def test_other_audit_lines_are_ignored():
    request = json.loads(ISSUED) | {"type": "request"}
    login = json.loads(ISSUED) | {"request": {"path": "auth/jwt/login", "operation": "update"}}
    for line in (json.dumps(request), json.dumps(login), "not json", ""):
        assert from_vault_audit(line) is None


def test_the_credential_lifetime_matches_what_the_configure_script_sets():
    script = (Path(__file__).resolve().parents[3] / "scripts/vault-configure.sh").read_text()
    assert "default_ttl=2m max_ttl=2m" in script and CREDENTIAL_TTL_S == 120


def test_the_vault_audit_adapter_is_one_of_the_sources():
    assert adapters.vault_audit in adapters.ALL

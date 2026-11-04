import json
import re
import time
from datetime import datetime


def event(layer, kind, verdict="info", src=None, dst=None, reason=None, trace=None, **evidence):
    return {"v": 1, "ts": time.time(), "layer": layer, "kind": kind, "verdict": verdict,
            "src": src, "dst": dst, "reason": reason, "trace": trace, "evidence": evidence}


def from_log_line(text: str):
    """Turn a workload log line (kubectl may prefix it) into an event, else None."""
    start = text.find("{")
    if start < 0:
        return None
    try:
        line = json.loads(text[start:])
    except json.JSONDecodeError:
        return None
    if line.get("event") == "x509_svid":
        return event("identity", "svid_issued", src=line["spiffe_id"], workload=line["workload"],
                     serial=line["serial"], not_before=line["not_before"], not_after=line["not_after"])
    if line.get("event") == "authz":
        # would_deny is an audit finding, so it is information, not a refusal.
        verdict = {"allow": "allow", "deny": "deny"}.get(line["verdict"], "info")
        return event("mtls", "authorisation", verdict, src=line["caller"] or "anonymous", dst=line["service"],
                     reason=line["reason"], trace=line["trace"], mode=line["mode"], decision=line["verdict"],
                     method=line["method"], route=line["route"], listener=line["listener"])
    if line.get("event") == "http":
        # No layer has decided anything yet, so errors are information, not denials.
        return event("app", "http_request", "allow" if line["status"] < 400 else "info",
                     src="user" if line["caller"] == "unknown" else line["caller"], dst=line["service"], trace=line["trace"],
                     route=line["route"], method=line["method"], status=line["status"])
    return None


CREDENTIAL_TTL_S = 120  # the database role's lifetime in scripts/vault-configure.sh; the audit log does not carry it
CREDS_PATH = "database/creds/"


def from_vault_audit(text: str):
    """A Vault audit line (`file_path=stdout`) for a database credential read, as an event; anything else is None.
    The audit log hashes the username and password, so what we can show is who asked and which lease they got."""
    try:
        line = json.loads(text)
    except json.JSONDecodeError:
        return None
    request = line.get("request") or {}
    if line.get("type") != "response" or request.get("operation") != "read" or not request.get("path", "").startswith(CREDS_PATH):
        return None
    holder = ((line.get("auth") or {}).get("display_name") or "").rsplit("/", 1)[-1] or "unknown"
    role = request["path"].removeprefix(CREDS_PATH)
    ts = datetime.fromisoformat(line["time"]).timestamp()
    if line.get("error"):
        ev = event("secrets", "credential_denied", "deny", src=holder, dst="postgres", role=role,
                   reason=f"{holder} was refused a {role} database credential: {line['error'].strip().splitlines()[-1].strip('* \t')}")
    else:
        lease = line["response"]["secret"]["lease_id"]
        ev = event("secrets", "credential_issued", "allow", src=holder, dst="postgres", role=role, ttl_s=CREDENTIAL_TTL_S,
                   reason=f"{holder} was issued a {CREDENTIAL_TTL_S} second {role} database credential", serial=lease)
    ev["ts"] = ts
    return ev


PG_CONNECT = re.compile(r"^(\S+) LOG:\s+connection authorized: user=(\S+) database=(\S+)")


def from_postgres_line(text: str, pod_by_ip: dict):
    """Postgres runs with log_line_prefix='%h ', so each line starts with the client IP."""
    m = PG_CONNECT.match(text.strip())
    if not m:
        return None
    ip, user, database = m.groups()
    return event("app", "db_connect", "allow", src=pod_by_ip.get(ip, ip), dst="postgres",
                 user=user, database=database, client_ip=ip)


def entry_key(entry: dict) -> str:
    return entry["spiffe_id"]["path"]


def diff_entries(old: dict, new: dict):
    """Compare two {path: entry} maps and emit added/removed identity events."""
    for path in new.keys() - old.keys():
        yield event("identity", "entry_added", src=f"spiffe://{new[path]['spiffe_id']['trust_domain']}{path}")
    for path in old.keys() - new.keys():
        yield event("identity", "entry_removed", src=f"spiffe://{old[path]['spiffe_id']['trust_domain']}{path}")

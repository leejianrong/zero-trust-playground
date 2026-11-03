import json
import re
import time


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

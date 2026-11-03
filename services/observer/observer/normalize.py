import time


def event(layer, kind, verdict="info", src=None, dst=None, reason=None, trace=None, **evidence):
    return {"v": 1, "ts": time.time(), "layer": layer, "kind": kind, "verdict": verdict,
            "src": src, "dst": dst, "reason": reason, "trace": trace, "evidence": evidence}


def from_workload_log(line: dict):
    """Turn a workload's x509_svid log line into an identity event, else None."""
    if line.get("event") != "x509_svid":
        return None
    return event("identity", "svid_issued", src=line["spiffe_id"], workload=line["workload"],
                 serial=line["serial"], not_before=line["not_before"], not_after=line["not_after"])


def entry_key(entry: dict) -> str:
    return entry["spiffe_id"]["path"]


def diff_entries(old: dict, new: dict):
    """Compare two {path: entry} maps and emit added/removed identity events."""
    for path in new.keys() - old.keys():
        yield event("identity", "entry_added", src=f"spiffe://{new[path]['spiffe_id']['trust_domain']}{path}")
    for path in old.keys() - new.keys():
        yield event("identity", "entry_removed", src=f"spiffe://{old[path]['spiffe_id']['trust_domain']}{path}")

"""Attack runner. `python -m clinic.attacks.run <name>` prints one JSON result.

Outcomes are only "succeeds" (the attacker got what it wanted) or "blocked". Which layer
blocked it is worked out by the observer from the events, not guessed here."""
import json
import os
import sys

import httpx
import psycopg

RECORDS = os.environ.get("RECORDS_URL", "http://records-api.clinic.svc:8080")
BILLING = os.environ.get("BILLING_URL", "http://billing.clinic.svc:8080")
HEADERS = {"x-caller": "attacker"}


def read_postgres(http):
    password = os.environ["ATTACK_LEAKED_DB_PASSWORD"]
    with psycopg.connect(host="postgres.clinic.svc", dbname="clinic", user="clinic", password=password,
                         connect_timeout=5) as db:
        rows = db.execute("SELECT name, diagnosis FROM patients").fetchall()
    return {"rows": len(rows), "sample": rows[0][0]}


def _get(http, url):
    r = http.get(url, headers=HEADERS)
    r.raise_for_status()
    body = r.json()
    return {"status": r.status_code, "items": len(body)}


def no_identity_records(http):
    return _get(http, f"{RECORDS}/patients")


def cross_namespace_billing(http):
    return _get(http, f"{BILLING}/invoices")


ATTACKS = {
    "read-postgres": read_postgres,
    "no-identity-records": no_identity_records,
    "cross-namespace-billing": cross_namespace_billing,
}


def run(name: str, http: httpx.Client | None = None) -> dict:
    http = http or httpx.Client(timeout=5)
    try:
        return {"attack": name, "outcome": "succeeds", "evidence": ATTACKS[name](http)}
    except (httpx.HTTPError, psycopg.Error, OSError) as exc:  # the attacker did not get through
        return {"attack": name, "outcome": "blocked", "evidence": {"error": type(exc).__name__, "detail": str(exc)[:200]}}


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1])))

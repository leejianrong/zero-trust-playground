import os

from fastapi import FastAPI

from .common import client, instrument

app = instrument(FastAPI(title="web"), "web")
RECORDS = os.environ.get("RECORDS_URL", "http://records-api.clinic.svc:8080")
BILLING = os.environ.get("BILLING_URL", "http://billing.clinic.svc:8080")


@app.get("/visit/{patient_id}")
def visit(patient_id: int):
    """One user action: look up a patient's record and their bill."""
    with client("web") as c:
        return {"record": c.get(f"{RECORDS}/patients/{patient_id}").json(),
                "invoice": c.get(f"{BILLING}/invoices/{patient_id}").json()}

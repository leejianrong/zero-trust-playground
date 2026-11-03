import os

from fastapi import FastAPI

from .common import client, instrument

app = instrument(FastAPI(title="billing"), "billing")
RECORDS = os.environ.get("RECORDS_URL", "http://records-api.clinic.svc:8080")
INVOICES = {1: 120.0, 2: 340.5, 3: 89.0, 4: 560.0, 5: 45.25}


@app.get("/invoices")
def invoices():
    return [{"patient_id": pid, "amount": amount} for pid, amount in INVOICES.items()]


@app.get("/invoices/{patient_id}")
def invoice(patient_id: int):
    with client("billing") as c:
        name = c.get(f"{RECORDS}/patients/{patient_id}").json().get("name")
    return {"patient_id": patient_id, "patient": name, "amount": INVOICES.get(patient_id)}

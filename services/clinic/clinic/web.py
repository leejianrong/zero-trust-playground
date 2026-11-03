import os
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse

from .common import client, instrument

app = instrument(FastAPI(title="web"), "web")
RECORDS = os.environ.get("RECORDS_URL", "http://records-api.clinic.svc:8080")
BILLING = os.environ.get("BILLING_URL", "http://billing.clinic.svc:8080")
PAGE = Path(__file__).parent / "static/index.html"


def relay(r) -> Response:
    """Pass a backend answer through unchanged, so the browser sees real status codes."""
    return Response(r.content, r.status_code, media_type=r.headers.get("content-type"))


@app.get("/")
def index():
    return FileResponse(PAGE)


@app.get("/api/patients")
def list_patients():
    with client("web") as c:
        return relay(c.get(f"{RECORDS}/patients"))


@app.post("/api/patients")
async def add_patient(request: Request):
    with client("web") as c:
        return relay(c.post(f"{RECORDS}/patients", content=await request.body(), headers={"content-type": "application/json"}))


@app.put("/api/patients/{patient_id}")
async def edit_patient(patient_id: int, request: Request):
    with client("web") as c:
        return relay(c.put(f"{RECORDS}/patients/{patient_id}", content=await request.body(),
                           headers={"content-type": "application/json"}))


@app.delete("/api/patients/{patient_id}")
def remove_patient(patient_id: int):
    with client("web") as c:
        return relay(c.delete(f"{RECORDS}/patients/{patient_id}"))


@app.get("/api/patients/{patient_id}/invoice")
def invoice(patient_id: int):
    with client("web") as c:
        return relay(c.get(f"{BILLING}/invoices/{patient_id}"))


@app.get("/visit/{patient_id}")
def visit(patient_id: int):
    """One scripted user action: look up a patient's record and their bill."""
    with client("web") as c:
        return {"record": c.get(f"{RECORDS}/patients/{patient_id}").json(),
                "invoice": c.get(f"{BILLING}/invoices/{patient_id}").json()}

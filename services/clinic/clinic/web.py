import os
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse

from . import login
from .common import client, instrument

# The user's token comes from their session cookie only. An Authorization header from the browser is ignored.
app = instrument(FastAPI(title="web"), "web", user_token=login.token_for)
app.include_router(login.router)

RECORDS = os.environ.get("RECORDS_URL", "http://records-api.clinic.svc:8080")
BILLING = os.environ.get("BILLING_URL", "http://billing.clinic.svc:8080")
AGENT = os.environ.get("AGENT_URL", "http://agent.agents.svc:8080")
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


@app.post("/api/agent/summarise")
def summarise():
    """Summarise with AI: the user's request goes to the agent, which reads the records through the MCP tools."""
    with client("web") as c:
        return relay(c.post(f"{AGENT}/tasks/summarise", timeout=30))


@app.get("/visit/{patient_id}")
def visit(patient_id: int):
    """One scripted user action: look up a patient's record and their bill."""
    with client("web") as c:
        return {"record": c.get(f"{RECORDS}/patients/{patient_id}").json(),
                "invoice": c.get(f"{BILLING}/invoices/{patient_id}").json()}

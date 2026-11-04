import datetime
import os

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import vault
from .common import instrument, layer_mode

app = instrument(FastAPI(title="records-api"), "records-api")


class PatientIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    dob: datetime.date
    diagnosis: str = Field(max_length=200)


creds = vault.Credentials()


def connect():
    user, password = os.environ.get("DB_USER", "clinic"), os.environ["DB_PASSWORD"]
    if layer_mode("secrets") == "enforce":  # no standing password: a two-minute user from Vault
        try:
            user, password = creds.get()
        except vault.VaultError as exc:
            raise HTTPException(503, str(exc)) from exc
    return psycopg.connect(host=os.environ["DB_HOST"], dbname=os.environ.get("DB_NAME", "clinic"),
                           user=user, password=password, connect_timeout=5)


def row(r):
    return {"id": r[0], "name": r[1], "dob": str(r[2]), "diagnosis": r[3]}


COLUMNS = "id, name, dob, diagnosis"


@app.get("/patients")
def patients():
    with connect() as db:
        return [row(r) for r in db.execute(f"SELECT {COLUMNS} FROM patients ORDER BY id").fetchall()]


@app.get("/patients/{patient_id}")
def patient(patient_id: int):
    with connect() as db:
        r = db.execute(f"SELECT {COLUMNS} FROM patients WHERE id = %s", (patient_id,)).fetchone()
    if not r:
        raise HTTPException(404, "no such patient")
    return row(r)


@app.post("/patients", status_code=201)
def create(body: PatientIn):
    with connect() as db:
        r = db.execute(f"INSERT INTO patients (name, dob, diagnosis) VALUES (%s, %s, %s) RETURNING {COLUMNS}",
                       (body.name, body.dob, body.diagnosis)).fetchone()
    return row(r)


@app.put("/patients/{patient_id}")
def update(patient_id: int, body: PatientIn):
    with connect() as db:
        r = db.execute(f"UPDATE patients SET name = %s, dob = %s, diagnosis = %s WHERE id = %s RETURNING {COLUMNS}",
                       (body.name, body.dob, body.diagnosis, patient_id)).fetchone()
    if not r:
        raise HTTPException(404, "no such patient")
    return row(r)


@app.delete("/patients/{patient_id}", status_code=204)
def delete(patient_id: int):
    with connect() as db:
        deleted = db.execute("DELETE FROM patients WHERE id = %s", (patient_id,)).rowcount
    if not deleted:
        raise HTTPException(404, "no such patient")

import os

import psycopg
from fastapi import FastAPI, HTTPException

from .common import instrument

app = instrument(FastAPI(title="records-api"), "records-api")


def connect():
    return psycopg.connect(host=os.environ["DB_HOST"], dbname=os.environ.get("DB_NAME", "clinic"),
                           user=os.environ.get("DB_USER", "clinic"), password=os.environ["DB_PASSWORD"],
                           connect_timeout=5)


@app.get("/patients")
def patients():
    with connect() as db:
        rows = db.execute("SELECT id, name, dob, diagnosis FROM patients ORDER BY id").fetchall()
    return [{"id": r[0], "name": r[1], "dob": str(r[2]), "diagnosis": r[3]} for r in rows]


@app.get("/patients/{patient_id}")
def patient(patient_id: int):
    with connect() as db:
        row = db.execute("SELECT id, name, dob, diagnosis FROM patients WHERE id = %s", (patient_id,)).fetchone()
    if not row:
        raise HTTPException(404, "no such patient")
    return {"id": row[0], "name": row[1], "dob": str(row[2]), "diagnosis": row[3]}

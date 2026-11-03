import pytest
from fastapi.testclient import TestClient

from clinic.records_api import app

client = TestClient(app)
GOOD = {"name": "Test Person", "dob": "1990-01-01", "diagnosis": "none"}


@pytest.mark.parametrize("change", [{"name": ""}, {"dob": "not-a-date"}, {"name": "x" * 101}, {"diagnosis": "d" * 201}])
def test_bad_patient_bodies_are_rejected_before_any_database_call(change):
    assert client.post("/patients", json={**GOOD, **change}).status_code == 422
    assert client.put("/patients/1", json={**GOOD, **change}).status_code == 422

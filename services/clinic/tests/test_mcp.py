import json

import httpx
import pytest
from mcp.client import Client

from clinic import records_mcp
from clinic.mcp_client import data_of

DB = {1: {"id": 1, "name": "Aisha", "dob": "1984-03-12", "diagnosis": "flu"}}


def fake_records(request: httpx.Request) -> httpx.Response:
    pid = int(request.url.path.rsplit("/", 1)[-1]) if request.url.path != "/patients" else None
    if request.method == "GET" and pid is None:
        return httpx.Response(200, json=list(DB.values()))
    if request.method == "GET":
        return httpx.Response(200, json=DB[pid]) if pid in DB else httpx.Response(404, json={})
    if request.method == "DELETE":
        DB.pop(pid, None)
        return httpx.Response(204)
    return httpx.Response(200, json={**json.loads(request.content), "id": pid})


@pytest.fixture(autouse=True)
def records(monkeypatch):
    monkeypatch.setattr(records_mcp, "client", lambda svc: httpx.Client(transport=httpx.MockTransport(fake_records)))
    DB.clear()
    DB[1] = {"id": 1, "name": "Aisha", "dob": "1984-03-12", "diagnosis": "flu"}


async def test_the_four_tools_are_advertised():
    async with Client(records_mcp.mcp) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert names == {"list_patients", "get_patient", "update_patient", "delete_patient"}


async def test_list_and_get_return_what_records_api_holds():
    async with Client(records_mcp.mcp) as c:
        listed = await c.call_tool("list_patients")
        got = await c.call_tool("get_patient", {"patient_id": 1})
    assert "Aisha" in str(listed.content) and "flu" in str(got.content)


async def test_delete_removes_the_record_and_logs_the_tool_call(capsys):
    async with Client(records_mcp.mcp) as c:
        await c.call_tool("delete_patient", {"patient_id": 1})
    assert 1 not in DB
    event = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (event["service"], event["route"], event["status"]) == ("records-mcp", "tool/delete_patient", 204)


async def test_a_list_result_comes_back_as_a_list_of_records_even_with_several_items():
    DB[2] = {"id": 2, "name": "Ben", "dob": "1991-07-30", "diagnosis": "asthma"}
    async with Client(records_mcp.mcp) as c:
        result = await c.call_tool("list_patients")
    assert [p["name"] for p in data_of(result)] == ["Aisha", "Ben"]

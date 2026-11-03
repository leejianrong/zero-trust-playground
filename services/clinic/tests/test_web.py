import httpx
from fastapi.testclient import TestClient

from clinic import web


def test_summarise_with_ai_asks_the_agent_through_web(monkeypatch):
    calls = []

    def agent(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"summary": "5 patients on file", "tool_calls": []})

    monkeypatch.setattr(web, "client", lambda service: httpx.Client(transport=httpx.MockTransport(agent)))
    r = TestClient(web.app).post("/api/agent/summarise")
    assert r.status_code == 200 and r.json()["summary"] == "5 patients on file"
    assert calls == [("POST", "/tasks/summarise")]

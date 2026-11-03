import json

from clinic.authz import BILLING, WEB
from clinic.guard import Guard
from clinic.modes import Modes
from clinic.mtls import Peers


async def inner(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def guard(mode: str, peers: Peers | None = None):
    modes = Modes("records-api", fetch=lambda: {"mtls": mode})
    modes.refresh()
    return Guard(inner, "records-api", modes, peers or Peers())


async def request(g, method="GET", path="/patients", tls=True, client=("10.0.0.9", 4242), trace=b"t1"):
    sent = []

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": method, "path": path, "scheme": "https" if tls else "http",
             "client": client, "headers": [(b"x-trace-id", trace)]}
    await g(scope, None, send)
    return sent[0]["status"], sent


def events(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if '"authz"' in line]


async def test_enforce_refuses_a_caller_with_no_identity_and_says_why(capsys):
    status, sent = await request(guard("enforce"))
    assert status == 403
    body = json.loads(sent[1]["body"])
    assert body["reason"] == "no client certificate presented" and body["trace"] == "t1"
    [ev] = events(capsys)
    assert (ev["verdict"], ev["mode"], ev["caller"], ev["trace"]) == ("deny", "enforce", None, "t1")


async def test_enforce_lets_an_allow_listed_caller_through(capsys):
    peers = Peers()
    peers.set(("10.0.0.9", 4242), WEB)
    status, _ = await request(guard("enforce", peers), method="POST")
    assert status == 200
    assert events(capsys)[0]["verdict"] == "allow"


async def test_enforce_refuses_a_known_workload_off_its_path(capsys):
    peers = Peers()
    peers.set(("10.0.0.9", 4242), BILLING)
    status, _ = await request(guard("enforce", peers), method="DELETE", path="/patients/1")
    assert status == 403
    assert "not allowed" in events(capsys)[0]["reason"]


async def test_audit_lets_the_same_call_through_and_records_a_would_deny(capsys):
    status, _ = await request(guard("audit"))
    assert status == 200
    assert events(capsys)[0]["verdict"] == "would_deny"


async def test_off_emits_no_authorisation_events(capsys):
    status, _ = await request(guard("off"))
    assert status == 200 and events(capsys) == []


async def test_plain_connections_are_refused_in_enforce_except_healthz(capsys):
    assert (await request(guard("enforce"), tls=False))[0] == 403
    assert (await request(guard("enforce"), tls=False, path="/healthz"))[0] == 200

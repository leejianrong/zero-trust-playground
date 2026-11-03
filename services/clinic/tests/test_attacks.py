import json
from pathlib import Path

import httpx

from clinic.attacks.run import ATTACKS, run

CATALOG = json.loads((Path(__file__).parent.parent / "clinic/attacks/catalog.json").read_text())


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_every_catalogued_attack_has_an_implementation_and_a_baseline_expectation():
    assert {a["name"] for a in CATALOG} == set(ATTACKS)
    assert all(a["expected"]["all_off"] == "succeeds" for a in CATALOG)


def test_http_attack_succeeds_when_the_service_answers():
    result = run("no-identity-records", client(lambda r: httpx.Response(200, json=[{}, {}])))
    assert result["outcome"] == "succeeds" and result["evidence"]["items"] == 2


def test_http_attack_is_blocked_by_a_refusal():
    assert run("cross-namespace-billing", client(lambda r: httpx.Response(403, json={})))["outcome"] == "blocked"


def test_http_attack_is_blocked_when_the_connection_fails():
    def refuse(request):
        raise httpx.ConnectError("refused")
    result = run("no-identity-records", client(refuse))
    assert result["outcome"] == "blocked" and result["evidence"]["error"] == "ConnectError"

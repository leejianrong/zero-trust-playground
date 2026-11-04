import json

from fastapi.testclient import TestClient

from observer.app import create_app
from observer.store import Store


class FakeKube:
    """Stands in for kubectl: holds the ConfigMap data and records patches."""

    def __init__(self, data=None):
        self.data = {"identity": "off", "mtls": "off", **(data or {})}
        self.patches = []

    async def __call__(self, *args):
        if "get" in args:
            return json.dumps({"data": self.data})
        self.patches.append(json.loads(args[args.index("-p") + 1]))
        self.data.update(self.patches[-1]["data"])
        return ""


class FakeNet:
    """Stands in for observer.network: whether the policy set exists."""

    def __init__(self, on=False, fail=False, partial=False):
        self.on, self.fail, self.partial = on, fail, partial

    def state(self):
        return "partial" if self.partial else "enforce" if self.on else "off"

    def listing(self):
        return {}

    def apply(self):
        if self.fail:
            raise RuntimeError("forbidden")
        self.on = True

    def remove(self):
        self.on = False


def make(data=None, net=None):
    kube, store = FakeKube(data), Store()
    return TestClient(create_app(store, sources=(), kube=kube, net=net or FakeNet())), kube, store


def test_reads_the_current_modes():
    client, _, _ = make({"identity": "enforce"})
    assert client.get("/layers").json() == {"identity": "enforce", "mtls": "off", "network": "off"}


def test_a_change_is_written_and_announced():
    client, kube, store = make()
    r = client.put("/layers/identity", json={"mode": "audit"})
    assert r.status_code == 200 and kube.data["identity"] == "audit"
    ev = store.since(0)[-1]
    assert (ev["layer"], ev["kind"], ev["evidence"]["before"], ev["evidence"]["after"]) == (
        "identity", "layer_mode_changed", "off", "audit")


def test_setting_the_same_mode_again_announces_nothing():
    client, _, store = make({"identity": "audit"})
    client.put("/layers/identity", json={"mode": "audit"})
    assert store.since(0) == []


def test_unknown_layer_or_mode_is_422_and_changes_nothing():
    client, kube, _ = make()
    assert client.put("/layers/firewall", json={"mode": "enforce"}).status_code == 422
    assert client.put("/layers/mtls", json={"mode": "maybe"}).status_code == 422
    assert kube.patches == []


def test_mtls_cannot_be_on_while_identity_is_off():
    client, kube, _ = make()
    r = client.put("/layers/mtls", json={"mode": "enforce"})
    assert r.status_code == 409 and "identity" in r.json()["detail"]
    assert kube.patches == []


def test_identity_cannot_go_off_under_a_running_mtls():
    client, _, _ = make({"identity": "enforce", "mtls": "audit"})
    assert client.put("/layers/identity", json={"mode": "off"}).status_code == 409


def test_mtls_is_allowed_once_identity_is_on():
    client, kube, _ = make({"identity": "audit"})
    assert client.put("/layers/mtls", json={"mode": "audit"}).status_code == 200
    assert kube.data["mtls"] == "audit"


def test_network_enforce_applies_the_policies_and_announces_it():
    net = FakeNet()
    client, kube, store = make(net=net)
    assert client.put("/layers/network", json={"mode": "enforce"}).json()["network"] == "enforce"
    assert net.on and kube.patches == []
    assert client.get("/layers").json()["network"] == "enforce"
    ev = store.since(0)[-1]
    assert (ev["layer"], ev["kind"], ev["evidence"]["after"]) == ("network", "layer_mode_changed", "enforce")


def test_network_off_removes_the_policies():
    net = FakeNet(on=True)
    client, _, _ = make(net=net)
    assert client.put("/layers/network", json={"mode": "off"}).status_code == 200
    assert not net.on


def test_network_audit_is_refused_with_a_reason_and_changes_nothing():
    net = FakeNet()
    client, _, store = make(net=net)
    r = client.put("/layers/network", json={"mode": "audit"})
    assert r.status_code == 409 and "no audit mode" in r.json()["detail"]
    assert not net.on and store.since(0) == []


def test_a_kubectl_failure_is_a_502_not_a_crash():
    client, _, _ = make(net=FakeNet(fail=True))
    assert client.put("/layers/network", json={"mode": "enforce"}).status_code == 502


def test_network_needs_no_identity():
    client, _, _ = make()
    assert client.put("/layers/network", json={"mode": "enforce"}).status_code == 200


def test_a_set_with_a_hole_reads_as_partial():
    client, _, _ = make(net=FakeNet(partial=True))
    assert client.get("/layers").json()["network"] == "partial"


def test_a_partial_network_is_expected_to_block_like_an_enforced_one():
    from observer.layers import expected
    attack = {"expected": {"default": "succeeds", "rules": [{"when": {"network": "enforce"}, "outcome": "blocked"}]}}
    assert expected(attack, {"network": "partial"}) == "blocked"
    assert expected(attack, {"network": "off"}) == "succeeds"

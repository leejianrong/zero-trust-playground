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


class FakeSec:
    """Stands in for observer.secrets: whether Vault is up, and the order of static-password changes."""

    def __init__(self, ready=True, log=None):
        self.ready, self.log = ready, log if log is not None else []

    def vault_ready(self):
        return self.ready

    def set_static(self, action):
        self.log.append(action)


class FakeUsr:
    """Stands in for observer.users: whether Keycloak is up."""

    def __init__(self, ready=True):
        self.ready = ready

    def keycloak_ready(self):
        return self.ready


def make(data=None, net=None, sec=None, usr=None):
    kube, store = FakeKube(data), Store()
    waits = []

    async def wait(seconds):
        waits.append(seconds)

    app = create_app(store, sources=(), kube=kube, net=net or FakeNet(), sec=sec or FakeSec(), usr=usr or FakeUsr(), wait=wait)
    return TestClient(app), kube, store


def test_reads_the_current_modes():
    client, _, _ = make({"identity": "enforce"})
    assert client.get("/layers").json() == {"identity": "enforce", "mtls": "off", "secrets": "off", "user": "off", "network": "off"}


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


def ordered(data=None):
    """An app whose ConfigMap patches and static-password changes land in one log, so their order can be asserted."""
    log, kube = [], FakeKube(data)

    async def recording(*args):
        if "patch" in args:
            log.append("patch")
        return await kube(*args)

    async def no_wait(_):
        pass

    app = create_app(Store(), sources=(), kube=recording, net=FakeNet(), sec=FakeSec(log=log), wait=no_wait)
    return TestClient(app), log


def test_secrets_enforce_revokes_the_static_password_after_the_services_have_the_new_mode():
    client, log = ordered()
    assert client.put("/layers/secrets", json={"mode": "enforce"}).status_code == 200
    assert log == ["patch", "revoke"]


def test_leaving_secrets_enforce_restores_the_static_password_before_the_services_switch_back():
    client, log = ordered({"secrets": "enforce"})
    assert client.put("/layers/secrets", json={"mode": "off"}).status_code == 200
    assert log == ["restore", "patch"]


def test_secrets_audit_issues_credentials_and_leaves_the_static_password_alone():
    sec = FakeSec()
    client, kube, _ = make(sec=sec)
    assert client.put("/layers/secrets", json={"mode": "audit"}).status_code == 200
    assert kube.data["secrets"] == "audit" and sec.log == []


def test_secrets_is_refused_with_a_reason_when_vault_is_not_installed():
    sec = FakeSec(ready=False)
    client, kube, store = make(sec=sec)
    r = client.put("/layers/secrets", json={"mode": "enforce"})
    assert r.status_code == 409 and "make vault" in r.json()["detail"]
    assert kube.patches == [] and sec.log == [] and store.since(0) == []
    assert client.put("/layers/secrets", json={"mode": "off"}).status_code == 200  # off never needs Vault


def test_user_layer_changes_the_configmap_and_is_reported():
    client, kube, store = make()
    assert client.get("/layers").json()["user"] == "off"
    r = client.put("/layers/user", json={"mode": "audit"})
    assert r.status_code == 200 and kube.data["user"] == "audit"
    assert client.get("/layers").json()["user"] == "audit"
    assert [e["kind"] for e in store.since(0)] == ["layer_mode_changed"]


def test_user_layer_is_refused_with_a_reason_when_keycloak_is_not_installed():
    client, kube, store = make(usr=FakeUsr(ready=False))
    for mode in ("audit", "enforce"):
        r = client.put("/layers/user", json={"mode": mode})
        assert r.status_code == 409 and "make keycloak" in r.json()["detail"]
    assert kube.patches == [] and store.since(0) == []
    assert client.put("/layers/user", json={"mode": "off"}).status_code == 200  # off never needs Keycloak

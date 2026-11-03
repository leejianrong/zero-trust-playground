import importlib.util
import json
from pathlib import Path

from observer import network

AUTHZ = Path(__file__).resolve().parents[2] / "clinic/clinic/authz.py"


def authz():
    spec = importlib.util.spec_from_file_location("authz", AUTHZ)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def by_name(items):
    return {(p["metadata"]["namespace"], p["metadata"]["name"]): p for p in items}


def test_every_namespace_gets_a_default_deny():
    pols = by_name(network.policies())
    for ns in network.NAMESPACES:
        spec = pols[(ns, "default-deny")]["spec"]
        assert spec == {"podSelector": {}, "policyTypes": ["Ingress"]}


def test_each_edge_becomes_one_allow_with_its_sources_and_ports():
    pols = by_name(network.policies())
    for ns, app, sources, ports in network.EDGES:
        pol = pols[(ns, f"allow-{app}")]
        assert pol["spec"]["podSelector"] == {"matchLabels": {"app": app}}
        (rule,) = pol["spec"]["ingress"]
        assert [p["port"] for p in rule["ports"]] == list(ports)
        peers = [(p["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"],
                  p["podSelector"]["matchLabels"]["app"]) for p in rule.get("from", [])]
        assert peers == (sources or [])
        assert ("from" in rule) == (sources is not network.ANYONE)


def test_web_accepts_anyone_with_no_from():
    (rule,) = by_name(network.policies())[("clinic", "allow-web")]["spec"]["ingress"]
    assert "from" not in rule


def test_every_policy_carries_the_layer_label():
    assert all(p["metadata"]["labels"] == {"ztp/layer": "network"} for p in network.policies())


def test_every_authz_caller_has_a_network_edge():
    """The allow-list says who may call what; the network must let the same callers through."""
    edges = {(ns, app): {s[1] for s in sources or []} for ns, app, sources, _ in network.EDGES}
    for service, rules in authz().ALLOW.items():
        ns = "agents" if service == "agent" else "clinic"
        callers = {spiffe.rsplit("/", 1)[1] for spiffe, _, _ in rules}
        assert callers <= edges[(ns, service)], service


def test_every_policy_destination_exists_in_the_manifests():
    manifests = "".join(p.read_text() for p in (Path(__file__).resolve().parents[3] / "deploy").rglob("*.yaml"))
    for _, app, sources, _ in network.EDGES:
        assert f"app: {app}" in manifests
        for _, src in sources or []:
            assert f"app: {src}" in manifests


class Kube:
    """A fake kubectl holding the policies that exist, keyed by namespace and name."""

    def __init__(self):
        self.have, self.calls = {}, []

    def __call__(self, *args, stdin=None):
        self.calls.append(args)
        if "apply" in args:
            self.have.update(by_name(json.loads(stdin)["items"]))
        elif "delete" in args:
            self.have = {k: v for k, v in self.have.items() if k[0] != args[1]}
        else:
            ns = args[1]
            return json.dumps({"items": [v for k, v in self.have.items() if k[0] == ns]})
        return ""


def test_apply_twice_changes_nothing_and_remove_leaves_nothing():
    kube = Kube()
    network.apply(kube)
    once = dict(kube.have)
    network.apply(kube)
    assert kube.have == once and network.applied(kube)
    network.remove(kube)
    network.remove(kube)
    assert kube.have == {} and not network.applied(kube)


def test_a_partial_set_is_not_applied():
    kube = Kube()
    network.apply(kube)
    del kube.have[("clinic", "allow-billing")]
    assert not network.applied(kube)

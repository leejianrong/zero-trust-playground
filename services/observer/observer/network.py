"""The network layer (ADR-0011): a default-deny ingress policy per namespace plus one allow per
legitimate call. EDGES is the single list; the policies are generated from it."""
import json
import subprocess
import sys

from .adapters import KUBECTL

LABEL = ("ztp/layer", "network")
NAMESPACES = ("clinic", "agents")
PORTS = (8080, 8443)
ANYONE = None

# (destination namespace, destination app, sources, ports). A source is (namespace, app).
EDGES: list[tuple[str, str, list | None, tuple]] = [
    ("clinic", "postgres", [("clinic", "records-api")], (5432,)),
    ("clinic", "records-api", [("clinic", "web"), ("clinic", "billing"), ("clinic", "records-mcp")], PORTS),
    ("clinic", "billing", [("clinic", "web")], PORTS),
    ("clinic", "records-mcp", [("agents", "agent")], PORTS),
    ("agents", "agent", [("clinic", "web")], PORTS),
    ("clinic", "web", ANYONE, (8080,)),
]


def _meta(name: str, namespace: str) -> dict:
    return {"name": name, "namespace": namespace, "labels": {LABEL[0]: LABEL[1]}}


def _peer(namespace: str, app: str) -> dict:
    return {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": namespace}},
            "podSelector": {"matchLabels": {"app": app}}}


def policies() -> list[dict]:
    """Default-deny per namespace, then an allow for each edge. No `from` means anyone."""
    out = [{"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": _meta("default-deny", ns),
            "spec": {"podSelector": {}, "policyTypes": ["Ingress"]}} for ns in NAMESPACES]
    for ns, app, sources, ports in EDGES:
        rule: dict = {"ports": [{"protocol": "TCP", "port": p} for p in ports]}
        if sources is not ANYONE:
            rule["from"] = [_peer(*s) for s in sources]
        out.append({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": _meta(f"allow-{app}", ns),
                    "spec": {"podSelector": {"matchLabels": {"app": app}}, "policyTypes": ["Ingress"],
                             "ingress": [rule]}})
    return out


def protects(app: str) -> bool:
    """True when the policy set has an allow for this service, so a connect failure to it can be a policy drop."""
    return any(dst == app for _, dst, _, _ in EDGES)


def kubectl(*args, stdin=None) -> str:
    done = subprocess.run([*KUBECTL, *args], check=False, input=stdin, text=True, capture_output=True)
    if done.returncode:
        raise RuntimeError(done.stderr.strip())
    return done.stdout


def apply(run=kubectl) -> None:
    """Create or update the whole set. Safe to repeat."""
    run("apply", "-f", "-", stdin=json.dumps({"apiVersion": "v1", "kind": "List", "items": policies()}))


def remove(run=kubectl) -> None:
    """Delete every policy this module made, and nothing else. Safe to repeat."""
    for ns in NAMESPACES:
        run("-n", ns, "delete", "networkpolicy", "-l", "=".join(LABEL), "--ignore-not-found")


def applied(run=kubectl) -> bool:
    """True when every policy in the set exists."""
    have = set()
    for ns in NAMESPACES:
        items = json.loads(run("-n", ns, "get", "networkpolicy", "-l", "=".join(LABEL), "-o", "json"))["items"]
        have |= {(ns, i["metadata"]["name"]) for i in items}
    return have == {(p["metadata"]["namespace"], p["metadata"]["name"]) for p in policies()}


if __name__ == "__main__":
    cmds = {"apply": apply, "remove": remove}
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        sys.exit("usage: python -m observer.network apply|remove")
    cmds[sys.argv[1]]()

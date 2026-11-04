"""Layer modes and the rules for changing them (ADR-0005, ADR-0010)."""
import json

MODES = ("off", "audit", "enforce")
# Layers whose mode the services read from the ConfigMap. The network layer is not one of them:
# its mode is whether the policy set exists in the cluster (observer/network.py).
CONFIG_LAYERS = ("identity", "mtls")
# Only layers that exist. secrets and user join as their slices land.
LAYERS = (*CONFIG_LAYERS, "network")
CONFIGMAP = ("clinic", "layer-modes")


def refusal(current: dict, layer: str, mode: str) -> str | None:
    """Why this change would break the playground, or None if it is safe."""
    if layer == "network" and mode == "audit":
        return "the network layer has no audit mode: a blocked connection is dropped without a log we can read (ADR-0011)"
    after = {**current, layer: mode}
    if after["mtls"] != "off" and after["identity"] == "off":
        return "mTLS needs workload identity: turn identity on first, or mTLS off first"
    return None


def expected(attack: dict, modes: dict) -> str:
    """What this attack should do under the current modes: the first rule whose conditions all hold, else the default."""
    if modes.get("network") == "partial":
        modes = {**modes, "network": "enforce"}  # a hole in the set still denies, so expect the same blocks
    for rule in attack["expected"].get("rules", []):
        if all(modes.get(layer) == mode for layer, mode in rule["when"].items()):
            return rule["outcome"]
    return attack["expected"]["default"]


def parse(configmap_json: str) -> dict:
    data = json.loads(configmap_json).get("data", {})
    return {layer: data.get(layer, "off") for layer in CONFIG_LAYERS}


def patch(layer: str, mode: str) -> str:
    return json.dumps({"data": {layer: mode}})

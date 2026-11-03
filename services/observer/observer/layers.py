"""Layer modes and the rules for changing them (ADR-0005, ADR-0010)."""
import json

MODES = ("off", "audit", "enforce")
# Only layers that exist. network, secrets and user join as their slices land.
LAYERS = ("identity", "mtls")
CONFIGMAP = ("clinic", "layer-modes")


def refusal(current: dict, layer: str, mode: str) -> str | None:
    """Why this change would break the playground, or None if it is safe."""
    after = {**current, layer: mode}
    if after["mtls"] != "off" and after["identity"] == "off":
        return "mTLS needs workload identity: turn identity on first, or mTLS off first"
    return None


def parse(configmap_json: str) -> dict:
    data = json.loads(configmap_json).get("data", {})
    return {layer: data.get(layer, "off") for layer in LAYERS}


def patch(layer: str, mode: str) -> str:
    return json.dumps({"data": {layer: mode}})

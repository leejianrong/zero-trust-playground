"""The user layer's effects outside the ConfigMap: whether Keycloak is there."""
from .network import kubectl


def keycloak_ready(run=kubectl) -> bool:
    try:
        return run("-n", "keycloak", "get", "deploy", "keycloak", "-o", "jsonpath={.status.readyReplicas}").strip() == "1"
    except RuntimeError:
        return False

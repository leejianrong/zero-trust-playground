"""The secrets layer's effects outside the ConfigMap: whether Vault is there, and the static database password."""
import subprocess
from pathlib import Path

from .network import kubectl

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/db-static.sh"


def vault_ready(run=kubectl) -> bool:
    try:
        return run("-n", "vault", "get", "deploy", "vault", "-o", "jsonpath={.status.readyReplicas}").strip() == "1"
    except RuntimeError:
        return False


def set_static(action: str) -> None:
    """`revoke` or `restore` the static password (scripts/db-static.sh)."""
    try:
        done = subprocess.run(["sh", str(SCRIPT), action], capture_output=True, text=True, timeout=30, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("the static password change timed out") from exc
    if done.returncode:
        raise RuntimeError(done.stderr.strip())

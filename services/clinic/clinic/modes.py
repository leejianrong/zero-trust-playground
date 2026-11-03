"""Layer modes (off, audit, enforce), followed live from one ConfigMap (ADR-0010).

Each service polls the ConfigMap every 2 seconds through the Kubernetes API with its own
service account, whose Role allows reading that one ConfigMap and nothing else. If the API
fails or returns something unexpected, the last good mode stays in force."""
import os
import threading
import time
from pathlib import Path

import httpx

from clinic.common import emit

VALID = ("off", "audit", "enforce")
SA = "/var/run/secrets/kubernetes.io/serviceaccount"


def read_configmap() -> dict:
    """The `data` of the layer-modes ConfigMap, read with this pod's service account."""
    ns = os.environ.get("MODES_NAMESPACE", "clinic")
    token = Path(f"{SA}/token").read_text()
    r = httpx.get(
        f"https://kubernetes.default.svc/api/v1/namespaces/{ns}/configmaps/layer-modes",
        headers={"authorization": f"Bearer {token}"}, verify=f"{SA}/ca.crt", timeout=2)
    r.raise_for_status()
    return r.json().get("data", {})


class Modes:
    def __init__(self, service: str, fetch=read_configmap, interval: float = 2.0):
        self.service = service
        self._fetch = fetch
        self._interval = interval
        self._modes: dict[str, str] = {}

    def get(self, layer: str) -> str:
        return self._modes.get(layer, "off")

    def all(self) -> dict:
        return dict(self._modes)

    def refresh(self) -> None:
        try:
            data = self._fetch()
        except (httpx.HTTPError, OSError, ValueError):
            return
        for layer, mode in data.items():
            if mode in VALID and self._modes.get(layer) != mode:
                self._modes[layer] = mode
                emit(event="layer_mode", service=self.service, layer=layer, mode=mode)

    def start(self) -> "Modes":
        def loop():
            while True:
                self.refresh()
                time.sleep(self._interval)

        if os.path.exists(f"{SA}/token"):
            threading.Thread(target=loop, daemon=True).start()
        return self

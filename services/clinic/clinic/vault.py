"""Short-lived database credentials from Vault (ADR-0012).

The service logs in with its JWT-SVID, reads a Postgres user that lasts two minutes, and asks for a new one
shortly before the old one expires."""
import os
import threading
import time

import httpx

from clinic.common import emit


class VaultError(RuntimeError):
    pass


def fetch_credential(role: str = "records-api") -> tuple[str, str, float]:
    """Log in with this workload's JWT-SVID and read a database user: (username, password, seconds it lasts)."""
    from spiffe import WorkloadApiClient

    addr = os.environ.get("VAULT_ADDR", "http://vault.vault.svc:8200")
    try:
        with WorkloadApiClient(socket_path=os.environ["SPIFFE_ENDPOINT_SOCKET"]) as client:
            jwt = client.fetch_jwt_svid(audience={"vault"}).token
        login = httpx.put(f"{addr}/v1/auth/jwt/login", json={"role": role, "jwt": jwt}, timeout=3)
        login.raise_for_status()
        read = httpx.get(f"{addr}/v1/database/creds/{role}", timeout=3,
                         headers={"X-Vault-Token": login.json()["auth"]["client_token"]})
        read.raise_for_status()
        body = read.json()
        return body["data"]["username"], body["data"]["password"], body["lease_duration"]
    except Exception as exc:  # the identity socket, the network and Vault each fail in their own way
        raise VaultError(f"could not get a database credential from Vault: {type(exc).__name__}") from exc


class Credentials:
    def __init__(self, fetch=fetch_credential, clock=time.monotonic, margin: float = 30):
        self._fetch, self._clock, self._margin = fetch, clock, margin
        self._cred: tuple[str, str] | None = None
        self._expires = 0.0
        self._lock = threading.Lock()

    def get(self) -> tuple[str, str]:
        with self._lock:
            if self._cred is None or self._clock() >= self._expires - self._margin:
                user, password, ttl = self._fetch()
                self._cred, self._expires = (user, password), self._clock() + ttl
                emit(event="credential_issued", service="records-api", user=user, ttl=ttl)  # never the password
            return self._cred

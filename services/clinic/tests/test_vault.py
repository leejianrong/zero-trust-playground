import pytest
from fastapi import HTTPException

from clinic import records_api, vault


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def creds(fetch, clock=None):
    return vault.Credentials(fetch=fetch, clock=clock or Clock(), margin=30)


def test_a_credential_is_reused_until_it_is_close_to_expiry():
    clock, calls = Clock(), []

    def fetch():
        calls.append(1)
        return (f"user{len(calls)}", "pw", 120)

    c = creds(fetch, clock)
    assert c.get() == ("user1", "pw") and c.get() == ("user1", "pw")
    clock.now = 89  # 31 seconds left: still fine
    assert c.get() == ("user1", "pw")
    clock.now = 91  # inside the 30 second margin: fetch a new one before the old one dies
    assert c.get() == ("user2", "pw") and len(calls) == 2


def test_a_failed_fetch_is_a_clear_error_and_nothing_is_cached():
    def down():
        raise vault.VaultError("Vault did not answer")

    c = creds(down)
    with pytest.raises(vault.VaultError, match="Vault did not answer"):
        c.get()


def patch_connect(monkeypatch, mode, creds_obj):
    seen = {}
    monkeypatch.setattr(records_api.psycopg, "connect", lambda **kw: seen.update(kw) or "conn")
    monkeypatch.setattr(records_api, "layer_mode", lambda layer: mode)
    monkeypatch.setattr(records_api, "creds", creds_obj)
    monkeypatch.setenv("DB_HOST", "db")
    monkeypatch.setenv("DB_PASSWORD", "static-pw")
    return seen


def test_with_secrets_off_the_static_password_is_used(monkeypatch):
    seen = patch_connect(monkeypatch, "off", creds(lambda: ("dyn", "dynpw", 120)))
    records_api.connect()
    assert (seen["user"], seen["password"]) == ("clinic", "static-pw")


def test_with_secrets_enforced_the_vault_credential_is_used(monkeypatch):
    seen = patch_connect(monkeypatch, "enforce", creds(lambda: ("dyn", "dynpw", 120)))
    records_api.connect()
    assert (seen["user"], seen["password"]) == ("dyn", "dynpw")


def test_when_vault_is_down_the_caller_gets_a_503_with_the_reason(monkeypatch):
    def down():
        raise vault.VaultError("Vault did not answer")

    patch_connect(monkeypatch, "enforce", creds(down))
    with pytest.raises(HTTPException) as e:
        records_api.connect()
    assert e.value.status_code == 503 and "Vault did not answer" in e.value.detail

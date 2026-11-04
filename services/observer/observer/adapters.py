"""Sources that feed the store. Each is an async function taking an emit callback."""
import asyncio
import functools
import json
import time

from .normalize import (
    diff_entries,
    entry_key,
    from_keycloak_log,
    from_log_line,
    from_postgres_line,
    from_vault_audit,
)

KUBECTL = ["kubectl", "--context", "k3d-ztp"]
SPIRE_CLI = ["-n", "spire-server", "exec", "spire-server-0", "-c", "spire-server", "--",
             "/opt/spire/bin/spire-server", "entry", "show", "-output", "json"]


async def run(*args) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await proc.communicate()
    return out.decode()


async def spire_entries(emit, interval=5):
    seen: dict = {}
    while True:
        try:
            entries = json.loads(await run(*KUBECTL, *SPIRE_CLI)).get("entries", [])
            current = {entry_key(e): e for e in entries}
            for ev in diff_entries(seen, current):
                emit(ev)
            seen = current
        except (json.JSONDecodeError, KeyError):
            pass  # server not ready yet; try again
        await asyncio.sleep(interval)


_pods = {"at": 0.0, "by_ip": {}}


async def pod_by_ip(max_age=3.0) -> dict:
    """Pod IP -> app label, cached briefly. Lets Postgres connections be attributed to a workload."""
    if time.monotonic() - _pods["at"] > max_age:
        try:
            items = json.loads(await run(*KUBECTL, "get", "pods", "-A", "-o", "json"))["items"]
            _pods["by_ip"] = {p["status"]["podIP"]: p["metadata"]["labels"].get("app", p["metadata"]["name"])
                              for p in items if p["status"].get("podIP")}
            _pods["at"] = time.monotonic()
        except (json.JSONDecodeError, KeyError):
            pass
    return _pods["by_ip"]


async def tail_logs(emit, namespace, selector, parse, tail):
    """Follow pod logs, reconnecting when the stream ends (pod restart)."""
    while True:
        proc = await asyncio.create_subprocess_exec(
            *KUBECTL, "-n", namespace, "logs", "-f", "-l", selector, f"--tail={tail}",
            "--max-log-requests=20", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        async for raw in proc.stdout:
            ev = await parse(raw.decode())
            if ev:
                emit(ev)
        await asyncio.sleep(2)


async def _parse_log(text):
    return from_log_line(text)


async def _parse_postgres(text):
    return from_postgres_line(text, await pod_by_ip())


async def _parse_vault(text):
    return from_vault_audit(text)


# Services whose request logs become Topology events, by namespace. A test checks this against the
# deployed manifests, so a new service cannot be added and quietly left out.
TRAFFIC = {"clinic": ["web", "records-api", "billing", "records-mcp"], "agents": ["agent"]}

# Identity workloads are backfilled (the current SVID matters on startup; emit dedupes by serial).
# Traffic is only interesting live, and has no key to dedupe on, so it starts from now.
workload_logs = functools.partial(tail_logs, namespace="clinic", selector="app in (echo-a,echo-b)",
                                  parse=_parse_log, tail=50)
service_logs = [functools.partial(tail_logs, namespace=ns, selector=f"app in ({','.join(apps)})",
                                  parse=_parse_log, tail=0) for ns, apps in TRAFFIC.items()]
postgres_connections = functools.partial(tail_logs, namespace="clinic", selector="app=postgres",
                                         parse=_parse_postgres, tail=0)

# Vault's audit device writes to the pod's stdout. A recent backfill lets the Secrets view show credentials that
# are still alive after the observer restarts; emit() drops repeats by lease id.
vault_audit = functools.partial(tail_logs, namespace="vault", selector="app=vault", parse=_parse_vault, tail=50)

async def _parse_keycloak(text):
    return from_keycloak_log(text)


# Keycloak's event listener writes to the pod's log. A backfill shows recent sign-ins after an observer restart.
keycloak_events = functools.partial(tail_logs, namespace="keycloak", selector="app=keycloak", parse=_parse_keycloak, tail=100)

ALL = (spire_entries, workload_logs, *service_logs, postgres_connections, vault_audit, keycloak_events)

"""Sources that feed the store. Each is an async function taking an emit callback."""
import asyncio
import json

from .normalize import diff_entries, entry_key, from_workload_log

KUBECTL = ["kubectl", "--context", "k3d-ztp"]
SPIRE_CLI = ["-n", "spire-server", "exec", "spire-server-0", "-c", "spire-server", "--",
             "/opt/spire/bin/spire-server", "entry", "show", "-output", "json"]


async def _run(*args):
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await proc.communicate()
    return out.decode()


async def spire_entries(emit, interval=5):
    seen: dict = {}
    while True:
        try:
            entries = json.loads(await _run(*KUBECTL, *SPIRE_CLI)).get("entries", [])
            current = {entry_key(e): e for e in entries}
            for ev in diff_entries(seen, current):
                emit(ev)
            seen = current
        except (json.JSONDecodeError, KeyError):
            pass  # server not ready yet; try again
        await asyncio.sleep(interval)


async def workload_logs(emit, selector="app in (echo-a,echo-b)"):
    while True:
        proc = await asyncio.create_subprocess_exec(
            *KUBECTL, "-n", "clinic", "logs", "-f", "-l", selector, "--tail=50", "--max-log-requests=20",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        async for raw in proc.stdout:
            text = raw.decode()
            start = text.find("{")
            if start < 0:
                continue
            try:
                ev = from_workload_log(json.loads(text[start:]))
            except json.JSONDecodeError:
                continue
            if ev:
                emit(ev)
        await asyncio.sleep(2)  # stream ended (pod restart); reconnect

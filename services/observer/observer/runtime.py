"""Runtime detection (V8). A shell that something outside a clinic pod started inside it is not how the service
works, so the pod is deleted and a `runtime` event says why. Cheaper than Falco on an 8 GB host: one scan of the
node's /proc every couple of seconds, with nothing installed in the pods.

An entrypoint script or a probe also runs a shell, but its parent is in the same pod. `kubectl exec` starts the
shell from containerd-shim, outside the pod's cgroup. That difference is the whole rule."""
import asyncio
import json
import re

from .adapters import KUBECTL, run
from .normalize import event

NODE = "k3d-ztp-server-0"
NAMESPACE = "clinic"
SHELLS = {"sh", "bash", "ash", "dash", "zsh"}
POD_UID = re.compile(r"/pod([0-9a-f-]{36})/")

# One line per process in a pod: pid|comm|cgroup|parent's cgroup. BusyBox sh, run on the node.
SCAN = r'''for p in /proc/[0-9]*; do
  grep -q kubepods $p/cgroup 2>/dev/null || continue
  pp=$(sed -n 's/^PPid:[[:space:]]*//p' $p/status 2>/dev/null)
  echo "${p#/proc/}|$(cat $p/comm 2>/dev/null)|$(cat $p/cgroup)|$(cat /proc/$pp/cgroup 2>/dev/null)"
done'''


def exec_shells(scan_output: str) -> list[tuple[int, str]]:
    """(pid, pod uid) of every shell in a pod whose parent is not in that pod."""
    found = []
    for text in scan_output.splitlines():
        try:
            pid, comm, cgroup, parent = text.split("|", 3)
        except ValueError:
            continue
        mine = POD_UID.search(cgroup)
        if comm in SHELLS and mine and (POD_UID.search(parent) or [None, None])[1] != mine[1]:
            found.append((int(pid), mine[1]))
    return found


async def node_scan() -> str:
    return await run("docker", "exec", NODE, "sh", "-c", SCAN)


async def clinic_pods() -> dict:
    """Pod uid -> (namespace, pod name, app label)."""
    try:
        items = json.loads(await run(*KUBECTL, "-n", NAMESPACE, "get", "pods", "-o", "json"))["items"]
    except (json.JSONDecodeError, KeyError):
        return {}
    return {p["metadata"]["uid"]: (NAMESPACE, p["metadata"]["name"], p["metadata"]["labels"].get("app", p["metadata"]["name"]))
            for p in items}


async def delete_pod(namespace, name) -> bool:
    return "deleted" in await run(*KUBECTL, "-n", namespace, "delete", "pod", name, "--now", "--wait=false")


async def detector(emit, interval=2, scan=node_scan, pods=clinic_pods, kill=delete_pod):
    handled: set = set()
    while True:
        hits = [h for h in exec_shells(await scan()) if h not in handled]
        if hits:
            known = await pods()  # only looked up when there is something to act on
            for pid, uid in hits:
                handled.add((pid, uid))
                namespace, name, app = known.get(uid, (None, None, None))
                if namespace != NAMESPACE:
                    continue  # another namespace's pod, or one that is already gone
                deleted = await kill(namespace, name)
                outcome = "the pod was deleted" if deleted else "the pod could not be deleted"
                emit(event("runtime", "pod_killed", "deny" if deleted else "info", src=app, dst=name,
                           reason=f"a shell (sh, pid {pid}) was started inside {app} from outside the pod; {outcome}",
                           serial=f"runtime/{uid}/{pid}", pid=pid, pod=name))
        await asyncio.sleep(interval)

import asyncio
import stat
import sys

from observer import adapters

# A stand-in for kubectl that behaves like the real one where it matters here. `logs -f -l` prints the logs of the
# pods that match when it starts, then waits forever and never picks up a pod that appears later. `logs -f <pod>`
# prints that pod's log then waits. `get pods` lists the pod names in pods.txt.
FAKE_KUBECTL = f"""#!{sys.executable}
import pathlib, sys, time
state = pathlib.Path(__file__).parent
args = sys.argv[1:]
pods = state.joinpath("pods.txt").read_text().split()
if "get" in args:
    print(" ".join(pods))
elif "logs" in args:
    with state.joinpath("calls.txt").open("a") as f:
        f.write(" ".join(args) + "\\n")
    named = [a for a in args if a in pods]
    for pod in named or pods:
        log = state.joinpath(pod + ".log")
        if log.exists():
            print(log.read_text(), end="", flush=True)
    time.sleep(60)
"""


async def wait_for(seen, line, seconds=5):
    for _ in range(int(seconds * 50)):
        if line in seen:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"never saw {line!r}; saw {seen}")


def test_a_pod_that_appears_after_the_observer_started_is_followed(tmp_path, monkeypatch):
    kubectl = tmp_path / "kubectl"
    kubectl.write_text(FAKE_KUBECTL)
    kubectl.chmod(kubectl.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(adapters, "KUBECTL", [str(kubectl)])
    (tmp_path / "pods.txt").write_text("records-api-old")
    (tmp_path / "records-api-old.log").write_text("old line\n")
    seen: list[str] = []

    async def parse(text):
        return text.strip() or None

    async def scenario():
        task = asyncio.create_task(adapters.tail_logs(seen.append, "clinic", "app=records-api", parse, tail=5, interval=0.05))
        try:
            await wait_for(seen, "old line")
            # A rollout: the old pod goes away and a new one takes its place.
            (tmp_path / "records-api-new.log").write_text("new line\n")
            (tmp_path / "pods.txt").write_text("records-api-new")
            await wait_for(seen, "new line")
        finally:
            task.cancel()

    asyncio.run(scenario())

    calls = (tmp_path / "calls.txt").read_text()
    assert "--tail=5" in calls.split("records-api-old")[1].splitlines()[0]  # the pod that was there at the start gets the backlog
    assert "--tail=-1" in calls.split("records-api-new")[1].splitlines()[0]  # a pod that arrived later is read from its first line

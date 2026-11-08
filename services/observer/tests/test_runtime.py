import asyncio

from observer import runtime

RECORDS = "6102a25d-1ae4-4be5-9733-f7bba4263bcd"
OTHER = "0a0a0a0a-1111-2222-3333-444444444444"


def line(pid, comm, uid, parent_uid):
    cg = lambda u: f"0::/kubepods/besteffort/pod{u}/{'a' * 64}" if u else "0::/init"
    return f"{pid}|{comm}|{cg(uid)}|{cg(parent_uid)}"


def test_a_shell_started_from_outside_the_pod_is_flagged():
    assert runtime.exec_shells(line(10, "sh", RECORDS, None)) == [(10, RECORDS)]


def test_a_shell_the_container_started_itself_is_not():
    assert runtime.exec_shells(line(10, "sh", RECORDS, RECORDS)) == []


def test_non_shells_and_shells_outside_any_pod_are_not():
    out = "\n".join([line(1, "python", RECORDS, None), line(2, "bash", None, None), "garbage"])
    assert runtime.exec_shells(out) == []


def watch(out, pods, emitted, killed):
    async def scan():
        return out

    async def lookup():
        return pods

    async def kill(ns, name):
        killed.append((ns, name))
        return True

    async def run():
        task = asyncio.create_task(runtime.detector(emitted.append, interval=0.01, scan=scan, pods=lookup, kill=kill))
        await asyncio.sleep(0.1)
        task.cancel()

    asyncio.run(run())


def test_a_shell_in_a_clinic_pod_kills_the_pod_once_and_says_so():
    emitted, killed = [], []
    watch(line(10, "sh", RECORDS, None), {RECORDS: ("clinic", "records-api-1", "records-api")}, emitted, killed)
    assert killed == [("clinic", "records-api-1")]
    [ev] = emitted
    assert (ev["layer"], ev["kind"], ev["verdict"], ev["src"]) == ("runtime", "pod_killed", "deny", "records-api")
    assert "sh" in ev["reason"] and "deleted" in ev["reason"]


def test_a_shell_in_a_pod_outside_clinic_is_left_alone():
    emitted, killed = [], []
    watch(line(10, "sh", OTHER, None), {OTHER: ("agents", "agent-1", "agent")}, emitted, killed)
    assert killed == [] and emitted == []

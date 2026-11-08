# ADR-0014: The runtime detector is a scan of the node's process list, not Falco

- Status: Accepted
- Date: 2026-11-08
- Deciders: user, agent

## Context

V8 is the playground's version of the pattern's runtime component (RHACS). The rule is narrow: a shell inside a `clinic` pod is not how any of our services work, so delete the pod and say why. SLICES.md left the choice between Falco and a small detector until memory headroom was known. On this 8 GB host the headroom is small. The cluster is capped at 2 GiB with no swap (`make up`), and Falco needs a kernel driver, which is a risk under WSL2.

## Decision

**The observer scans the node's `/proc` every 2 seconds.** `docker exec k3d-ztp-server-0` runs a short BusyBox script that prints every process in a pod cgroup with its parent's cgroup. Nothing is installed in the pods and no extra pod runs.

**The rule is about the parent, not the shell.** An entrypoint script or a probe also runs a shell, but its parent is in the same pod. `kubectl exec` starts the shell from `containerd-shim`, outside the pod's cgroup. A shell whose parent is in another cgroup is flagged. A shell that is already running when a pod starts is never flagged.

**The response is `kubectl delete pod --now`,** for pods in the `clinic` namespace only. The `runtime` event (`pod_killed`, verdict `deny`) names the app, the pod and the pid. If the delete fails, the event is `info` and says so.

## What we measured

| Question | Result |
|---|---|
| Is an exec'd shell visible from the node? | Yes. Its cgroup is `/kubepods/<qos>/pod<uid>/<container id>` and its parent is `containerd-shim` in `/init`. |
| Do any clinic pods run a shell on their own? | Not at the time of the check. The only shell on the node was the one we started. |
| Time from `kubectl exec` to the pod being gone | 5.7 seconds, once. The condition is 10. |
| False kills over 5 idle minutes | None. No new `runtime` event and no clinic pod restarted. |

## Alternatives considered

| Option | Why not |
|---|---|
| Falco | Needs a kernel driver and more memory than we have to spare, and WSL2's kernel may not support it. Revisit on a bigger host. |
| `kubectl exec ... ps` in each pod | The exec is itself an exec into the pod, and it needs `ps` in every image. |
| The API server audit log | k3s needs extra configuration to write one, and it would show the exec request but not the shell. |

## Consequences

- The detector only catches shells. A `kubectl exec` that runs `python` or `psql` directly is not flagged.
- It assumes the observer can run `docker exec` on the node, so it works for k3d and not for a remote cluster.
- A shell that lives for under 2 seconds can start and finish between two scans. The one-off attack in V8 uses a shell that stays open.
- Nothing yet lets you turn the runtime layer off, so it is always on while the observer runs. A mode, and the attack that demonstrates it, are the next step.

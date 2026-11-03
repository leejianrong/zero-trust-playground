# ADR-0006: Standalone repo; toy services in Python 3.12 + FastAPI; SPIFFE via py-spiffe

- Status: Accepted
- Date: 2026-11-03
- Deciders: user, agent

## Context

agent-auth-lab already has a Lab IdP, OPA labs and scripted agents. Reusing them would save some work and couple two projects with different goals. The toy services are small HTTP apps whose language doesn't matter to the lesson.

## Decision

- The playground is its own project and shares no code with agent-auth-lab. The closing README section explains where agents fit (an agent is a workload; its SPIFFE ID replaces the fixed secret that agent-auth-lab's lab 13 discusses).
- Toy services use Python 3.12, FastAPI and `uv`, as in agent-auth-lab.
- Workload API access uses `py-spiffe`. If the spike in V1 shows it can't do what is needed (rotation callbacks, mTLS contexts), fall back to the `spiffe-helper` sidecar writing certs to a shared volume, and record the change as a new ADR.
- Docs are Markdown in the repo. No docs site (ADR-0009 in agent-auth-lab does not apply).
- Versions of every chart and image are pinned in `versions.env`.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Extend agent-auth-lab | Couples the release cadence and drags in the Python/OPA lab stack. |
| Go services | Go has the best SPIFFE library (`go-spiffe`), but a second language adds toolchain cost for a lesson about architecture. Reconsider if py-spiffe fails. |
| Envoy/Istio sidecars for mTLS | Hides the SPIFFE mechanics behind a mesh. Better as a follow-up playground. |

## Consequences

- `py-spiffe` is less mature than `go-spiffe`. V1 is the risk slice for that reason.
- Services do mTLS in-process, which is more visible in code than a mesh and a bit more code to write.

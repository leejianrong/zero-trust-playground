# ADR-0005: Layer modes are changed by a small controller with narrow RBAC

- Status: Accepted
- Date: 2026-11-03
- Deciders: user, agent

## Context

ADR-0002 requires flipping each layer between `off`, `audit` and `enforce` from the dashboard. Doing that by letting the browser or the observer hold cluster-admin would contradict what the playground teaches.

## Decision

A `layer-controller` service (part of the observer's backend, separate Kubernetes ServiceAccount) exposes `PUT /layers/{layer}` with a mode. It applies the change through a fixed table, not arbitrary commands:

| Layer | off | audit | enforce |
|-------|-----|-------|---------|
| identity (SPIRE) | services ignore SVIDs and use a shared static token | SVIDs fetched, not required | SVIDs required |
| mtls | plain HTTP between services | mTLS, authorisation decisions logged only | mTLS with SPIFFE-ID allow-list, deny on mismatch |
| network | no NetworkPolicy | policies applied with logging only where the controller allows it, else same as off | default-deny plus allows |
| secrets | static DB password in a Secret | dynamic creds issued, static one still valid | static one revoked |
| user | `records-api` trusts a header | token validated, failures logged | token required |

Services read their mode from a ConfigMap the controller owns. The ServiceAccount's RBAC is limited to that ConfigMap, the NetworkPolicy objects in the app namespace and the Vault role for dynamic creds. Nothing else.

`audit` for network is best effort, since k3s's controller has no log-only mode. The UI marks it "not available" rather than faking it.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Layer control via `make` targets only | Loses the instant off/on comparison that makes the lesson land. Kept as a fallback CLI. |
| Observer with cluster-admin | Easy, but teaches the wrong thing. |
| Separate deployments per mode | Slow to switch, hard to compare. |

## Consequences

- Each service needs a mode-aware code path. That is the cost of making `off` real (ADR-0002).
- `audit` is meaningful for three layers and degraded for network. Documented in the UI.
- The controller is a deliberately weak component (it can turn security off). It is localhost-only and labelled.

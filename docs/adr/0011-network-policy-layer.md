# ADR-0011: The network layer is a default-deny ingress policy set with one edge list

- Status: Accepted
- Date: 2026-11-04
- Deciders: user, agent

## Context

V4 adds the network layer. We assumed k3s enforces NetworkPolicy and that a default-deny leaves the playground running (Q1, Q32), but we had only a smoke test. The spike (AAL-56) applied a default-deny by hand to `clinic` and `agents`, watched what broke, and measured how a blocked connection looks to the caller. Everything below was measured on the k3d cluster (Kubernetes v1.35.5+k3s1, one node) unless it says otherwise.

## Decision

**Ingress-only.** The layer is one default-deny ingress policy per namespace (`clinic`, `agents`) plus an allow policy per service. Egress stays open. Nothing in the playground needed an egress rule: DNS and the Kubernetes API (layer-mode polling) kept working with the deny in place.

**One allow per legitimate edge.**

| Destination | Allowed from | Ports |
|---|---|---|
| `postgres` | `records-api` | 5432 |
| `records-api` | `web`, `billing`, `records-mcp` | 8080, 8443 |
| `billing` | `web` | 8080, 8443 |
| `records-mcp` | `agent` (namespace `agents`) | 8080, 8443 |
| `agent` | `web` (namespace `clinic`) | 8080, 8443 |
| `web` | anything | 8080 |

`web` is the front door, so it accepts anyone. In a policy that means an ingress rule with a `ports` list and no `from`. An empty `from: [{}]` is rejected by the API.

**Network `audit` stays unavailable.** The policy engine gave us no log of dropped connections that we could find, and we did not look at node-level counters. The controller refuses `audit` for this layer and says why (Q15).

**A drop is attributed by inference.** The attack runner records which phase failed, and the observer names the network layer when a connect-phase failure happens while the policy set is applied, in full or in part. A connect timeout counts as a connect-phase failure, because a drop can time out as well as refuse; it also means a closed port on a Service that does not define it is misattributed, and the docs say so.

**`GET /layers` reports `partial`.** When some policies are missing but a default-deny is left, the network layer reads `partial`, not `off`. The attack matrix expects the same results as for `enforce`, which is right unless the missing policy is the allow for `web`. `PUT` still takes only `off` and `enforce`. The result says `network (inferred)`.

## What we measured

| Question | Result |
|---|---|
| Does a default-deny stop every cross-pod call? | Yes. With the deny applied, all 15 pod-to-pod probes we ran were refused, including `web` to `records-api`. |
| What does a blocked caller see? | `ConnectionRefusedError` within about 10 ms, not a timeout. |
| Does rapid retrying behave? | Not cleanly. Probing every 50 ms alternated strictly between a refusal and a 1 second timeout. That looks like rate limiting of the reject, but we did not confirm the cause. |
| Which other things refuse with a connect error? | A Service with no endpoints (refused, 5 ms). A pod IP on a closed port (refused). A closed port on a Service that does not define it **times out** after the full wait. A refusal alone is therefore not proof of a policy. |
| What did the deny not break? | `kubectl port-forward` to `web`, `kubectl exec`, `kubectl logs`, the Kubernetes API from pods (layer-mode polling picked up a change in 2 seconds), DNS, SVID issuance. No manifest has a probe, so kubelet probes were not tested. |
| How fast does a change take effect? | Deleting the policies opened a connection in 0.33 seconds. Applying them refused one in 0.42 seconds. |
| What about a connection that is already open? | It keeps working after a policy is applied. Only new connections are checked. Our clients open a new connection for each call. |
| Do the attacks behave? | With the full set applied and every other layer off, five of six attacks were blocked at the network (`read-postgres`, `no-identity-records`, `cross-namespace-billing`, `mcp-no-identity`, `forged-identity`). `agent-prompt-injection` still succeeded, because it goes through `web`, which is allowed. |
| Does a billing pod reach Postgres? | Not with the set applied (`billing` to Postgres refused). With no policy it connects. |
| How is a forged-certificate drop different? | The TCP connection is accepted and the server drops it during the TLS handshake (`RemoteProtocolError`). A network drop never gets that far. |

## Alternatives considered

| Option | Why not |
|---|---|
| Ingress and egress | Needs allows for DNS and the API server, and nothing in the catalogue needs it. A later card can add egress if an attack calls for it. |
| Network audit mode | No log to read. Faking one would teach the wrong thing. |
| Namespace-wide allows instead of per-service | It would not stop a compromised `billing` pod reaching Postgres, which is the case the layer is for. |

## Consequences

- The edge list is the single source for the policies. A test must tie it to the authz allow-list in `clinic/authz.py` (AAL-57), because the two describe the same calls at different levels.
- The attack runner has to classify the failure phase (connect, handshake or request) and look inside an `ExceptionGroup`. The MCP attack currently reports only `unhandled errors in a TaskGroup`, which hides the real cause (AAL-60).
- Attribution checks more than the error type, because refusals have other causes. It also needs the policy set to be present in the target's namespace. A target with no endpoints would still be misreported, and the docs say so.
- A blocked attack currently takes 5 to 6 seconds, mostly because the observer waits for deny events that a network drop never produces. The wait is skipped when the failure was a connect refusal (AAL-60).
- A cluster node's own traffic and the kubelet are outside what we tested, and a policy engine other than k3s's would need its own check.

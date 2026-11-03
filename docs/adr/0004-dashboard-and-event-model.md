# ADR-0004: The dashboard is the primary teaching surface, fed by one normalised event stream

- Status: Accepted
- Date: 2026-11-03
- Deciders: user, agent

## Context

The user's requirement: the dashboard has to be really solid, because it is what conveys the concepts. Zero trust is mostly invisible. Certificates rotate, a request is refused somewhere between two sockets, a credential is minted and expires. Without a way to see those, the playground is a pile of YAML. So the UI is a first-class deliverable with its own acceptance tests, not a debugging aid.

## Decision

**Stack.** Svelte + Vite + TypeScript frontend, FastAPI (Python 3.12) backend called the `observer`. This matches agent-auth-lab (its ADR-0001) so conventions carry over.

**One event model.** Every source is adapted into a single JSON event and pushed over one server-sent-events stream:

```text
{ id, ts, layer, kind, src, dst, verdict, reason, evidence }
layer   : identity | mtls | network | secrets | user | runtime
verdict : allow | deny | info
src/dst : workload ref with SPIFFE ID where one exists
```

Sources: each toy service logs a structured event per request and per denial; the observer polls the SPIRE server (entries, agents, SVID expiry) and the Kubernetes API (pods, NetworkPolicies, service accounts); Vault audit log; Keycloak events. Events are kept in memory plus a SQLite file for replay. No other store.

**Views** (each one answers a single question):

| View | Question it answers |
|------|---------------------|
| Topology | Who can talk to whom right now? Nodes are workloads labelled with SPIFFE IDs, edges are observed calls coloured allow/deny, with the layer that decided shown on the edge. |
| Identity | What identity does each workload hold, and when does it expire? Live SVID cards with countdown and rotation history. |
| Request trace | What happened to this one request? A step-by-step walk across layers, same idea as agent-auth-lab's steppers. |
| Attack lab | What stops this attack? Run a named attack, see which layer blocked it, or that none did. |
| Layer control | What changes if I turn this layer off? Per-layer off/audit/enforce switch (ADR-0005). |
| Secrets | Which credentials exist right now, who holds them, when do they die? |

**Quality bar.** Defined in PLAN requirement R7: Playwright tests drive every view against the real cluster, assert specific events and states, and save screenshots. UI work uses the `frontend-design` skill and a token-based design system with light and dark themes. Colour never carries meaning alone (verdicts also get an icon and a label).

## Alternatives considered

| Option | Why not |
|--------|---------|
| Grafana + Loki | Quick, but cannot draw a topology with SPIFFE IDs on edges, a request stepper, or an attack runner. Charts are not the concept. |
| Hubble/Cilium UI | Excellent network view, covers only the network layer, and needs Cilium instead of k3s's built-in policy controller. |
| `kubectl` and logs only | The thing we are replacing. |
| Per-layer mini-UIs | Concepts need to be seen together to show defence in depth. |

## Consequences

- Every component must emit or be pollable into the event model. That is an adapter per source, and the schema is a public contract inside the repo. Changing it means changing all adapters, so it is versioned (`v: 1`).
- The observer holds read access to the cluster and, for layer control, narrow write access (ADR-0005). It is a privileged component in a zero trust demo, which is itself worth a note in the Layer control view.
- Roughly a third of the build effort goes to UI and its tests. Slices are sized accordingly.

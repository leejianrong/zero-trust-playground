# Questions

Statuses: `DECIDED` (user answered) · `ASSUMED` (default taken, correct it if wrong) · `FORK` (waiting on the user) · `DEFERRED` (not needed this milestone).

Source pattern: https://validatedpatterns.io/patterns/layered-zero-trust/

## Open forks

None. Round 1 closed on 2026-11-03.

## Register

| ID | Question | Status | Answer or default | Landed |
|----|----------|--------|-------------------|--------|
| Q1 | Runtime: k3d or docker compose? | DECIDED | k3d. Smoke-tested: cluster up in ~20s, NetworkPolicy enforced | ADR-0001 |
| Q2 | Guided exercises or a working system? | DECIDED | Working system, attacks, layer toggles, break-it exercises | ADR-0002 |
| Q3 | GitOps, runtime monitoring, compliance, supply chain? | DECIDED | Out. Runtime kill is stretch slice V8 | ADR-0003 |
| Q4 | Relationship to agent-auth-lab | DECIDED | Standalone, closing note on where agents fit | ADR-0006 |
| Q5 | Output format | DECIDED | Reversed on 2026-11-03: Zensical tutorial site | ADR-0007 |
| Q6 | Dashboard quality bar | DECIDED | First-class deliverable, six views, tested end to end, light/dark (user requirement) | ADR-0004, PLAN R7 |
| Q7 | How layers are switched | ASSUMED | Controller with narrow RBAC, off/audit/enforce | ADR-0005 |
| Q8 | Event model | ASSUMED | One versioned schema, SSE, SQLite replay | ADR-0004 |
| Q9 | Toy app | ASSUMED | Clinic records: `web`, `records-api`, `billing`, Postgres, `attacker` | PLAN §Shape |
| Q10 | App language | ASSUMED | Python 3.12 + FastAPI | ADR-0006 |
| Q11 | SPIFFE client library | DECIDED | `py-spiffe` (PyPI `spiffe` 0.4.0). V1 spike confirmed X.509 and JWT SVID fetch and rotation callbacks against live SPIRE. mTLS contexts (V3) still unverified | ADR-0006, AAL-21 |
| Q12 | Vault licence | ASSUMED | Vault OSS (BSL) fine locally; OpenBao as swap | PLAN §Assumed |
| Q13 | Memory | ASSUMED | Full stack under ~4 GB on this 8 GB host (about 5 GB free when checked) | ADR-0001, V6 |
| Q14 | Upstream vs Red Hat builds | ASSUMED | Upstream only | ADR-0003 |
| Q15 | Network `audit` mode | ASSUMED | Unavailable on k3s, UI says so | ADR-0005 |
| Q16 | Secrets handling | ASSUMED | Throwaway, labelled, localhost-only credentials | PLAN §Scope |
| Q17 | Versioning | ASSUMED | Pin everything in `versions.env`; event schema versioned `v: 1` | ADR-0004 |
| Q20 | Agent: real LLM or scripted? | DECIDED | Scripted and deterministic; naive mode simulates obeying injected text; real MCP clients can connect as an optional exercise | ADR-0008 |
| Q21 | When does agent work start? | DECIDED | Baseline in V2b, before V3, so every layer is tested against the agent too | SLICES V2b |
| Q22 | Cluster dashboard | DECIDED | Headlamp, view-only token by default, admin contrast available. Kubernetes Dashboard is archived | ADR-0009 |
| Q23 | Docs site | DECIDED | Zensical tutorial site on Pages (reverses Q5) | ADR-0007 |
| Q24 | Architecture view | DECIDED | New dashboard view built in V3 | ADR-0009 |
| Q25 | mtls mode semantics | ASSUMED | Permissive and strict, as in a service mesh: `off`, `audit`, `enforce` | ADR-0010 |
| Q26 | Where enforcement happens | ASSUMED | In the app (client cert optional in the handshake) so refusals carry a trace id and a reason. Forged certificates fail the handshake even in audit | ADR-0010 |
| Q27 | How services learn the mode | ASSUMED | Poll one ConfigMap through the Kubernetes API every 2 seconds, with a Role limited to that ConfigMap | ADR-0010 |
| Q28 | Controller location | ASSUMED | Host process in the observer for now, so it is as privileged as the user running it. In-cluster controller is a later card | ADR-0010 |
| Q29 | Browser access to web | ASSUMED | Plain HTTP until the user layer in V6 | ADR-0010 |
| Q30 | Injection attack trigger | ASSUMED | Through the clinic page's AI summary, the user's own path. mTLS must not stop it | SLICES V3 |
| Q31 | Expired-SVID replay attack | ASSUMED | Replaced by a forged-identity attack | SLICES V3 |
| Q18 | SPIRE federation | DEFERRED | Later playground | n/a |
| Q19 | Offline operation | DEFERRED | First run needs internet; optional `k3d image import` pre-pull | ADR-0001 |

## Coverage

| Category | Covered by |
|----------|-----------|
| Primary user and actors | PLAN §Users, Q9 |
| Scope boundary | Q3, Q18, PLAN §Scope |
| Data model and identity | SPIFFE IDs (ADR-0003), event schema (Q8) |
| State and storage | Ephemeral Postgres, SQLite event replay (ADR-0004) |
| Concurrency and conflict | Not applicable: single learner. Dashboard vs `make` conflict resolved by cluster state (PLAN §Actors) |
| Interfaces and contracts | Q8, PLAN §Affordances |
| Failure behaviour | Every denial is an explicit verdict in the event stream (ADR-0004) |
| External dependencies | Q11, Q12, Q14, Q19 |
| Runtime and deployment | Q1, Q13 |
| Measurable success | Attack matrix (V7), R8 under 10 minutes |
| Security and secrets | Q7, Q16, ADR-0005 |
| Versioning and migration | Q17 |

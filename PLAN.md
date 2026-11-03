# Zero Trust Playground: Plan

Status: agreed · Milestone: MVP (slices V1–V7; V8 is a stretch)

## Problem

The Layered Zero Trust validated pattern is a long list of operators: SPIRE, Vault, Keycloak, cert-manager and the rest, deployed through GitOps on OpenShift. Reading it tells you the parts exist. It doesn't show why each one is there, what it stops, or what happens when another layer fails. Zero trust is also mostly invisible: certificates rotate quietly and a refused request leaves a log line.

A learner needs a small system where they can run the attack, switch a layer off, and watch the same attack succeed. They also need to see identities, decisions and credentials as they happen.

## Solution

A disposable Kubernetes cluster on your laptop running a toy "clinic records" app protected by the pattern's Layer 0 components, plus a dashboard that makes the invisible visible.

You start with `make up`, which gives you a working app with no protection and an attacker pod that can read patient records. You open the dashboard, run the "read the database from the attacker pod" attack, and it succeeds. Then you turn on workload identity, mTLS, network policy, dynamic secrets and user auth one layer at a time. After each, you rerun the attacks and see which layer stopped each one, with the SPIFFE IDs and the reason on screen. Finally you switch layers off in different combinations to see where defence in depth actually matters.

## Users and actors

- **Learner (Jian)**, the only user. Reads the dashboard, runs attacks, flips layers, does the break-it exercises.
- **Toy services**: `web`, `records-api`, `billing`, Postgres. Real workloads with real identities.
- **Attacker pod**: runs scripted attacks. Not a person.
- **Layer controller**: changes layer modes. When the dashboard and `make` disagree, the cluster state wins and the dashboard reflects it.

## Scope

**In this milestone**

- k3d cluster, one command up and down (ADR-0001)
- SPIRE workload identity for every toy service
- mTLS between services, authorised by SPIFFE ID
- Default-deny NetworkPolicy with explicit allows
- Vault with JWT-SVID auth and dynamic Postgres credentials; ESO for one static secret
- Keycloak user login, one OIDC client per app
- cert-manager short-lived CA for TLS edges
- A dashboard with six views (ADR-0004) and a layer control panel (ADR-0005)
- An attack catalogue with an attack × layer-mode matrix
- Break-it exercises per slice, in Markdown

**Out**

- OpenShift, Red Hat builds, GitOps (ADR-0003)
- Compliance Operator, supply chain signing, SPIRE federation
- Any production hardening. The playground is labelled, localhost-only and deliberately weak when layers are off.
- Sharing code with agent-auth-lab (ADR-0006)
- A docs site

## Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | A learner can run a named attack, see whether and where it was stopped, and rerun it with a layer changed | Core goal |
| R1 | Every toy service holds a SPIFFE identity, and the learner can see it, its expiry and its rotation | Must-have |
| R2 | Service-to-service calls are authorised by SPIFFE ID, and a wrong or missing identity is refused | Must-have |
| R3 | Network access is default-deny, and the dashboard shows which layer refused a connection | Must-have |
| R4 | No service holds a long-lived database password once the secrets layer is enforced | Must-have |
| R5 | Users authenticate through Keycloak and `records-api` rejects calls without a valid token | Must-have |
| R6 | Each layer can be set to off, audit or enforce, and `off` reproduces the vulnerable behaviour | Must-have |
| R7 | The dashboard is solid enough to teach from: every view driven by real events, tested end to end, and usable in light and dark | Must-have |
| R8 | The whole environment comes up from nothing in under 10 minutes and tears down cleanly | Must-have |
| R9 | A runtime control (a compromised pod gets killed) | Nice-to-have |

## Shape

| Part | Mechanism | ADR |
|------|-----------|-----|
| S1 | k3d cluster `ztp`, Helm-installed components pinned in `versions.env`, driven by `make` | 0001 |
| S2 | SPIRE server and agent, `k8s_psat` attestor, one registration entry per ServiceAccount, SPIFFE ID `spiffe://playground.local/ns/<ns>/sa/<sa>` | 0003, 0006 |
| S3 | Toy services (FastAPI) fetch X.509-SVIDs and JWT-SVIDs from the Workload API and do mTLS in-process | 0006 |
| S4 | Authorisation table inside each service: caller SPIFFE ID → allowed routes. Mode comes from a controller-owned ConfigMap | 0005 |
| S5 | Default-deny NetworkPolicy plus per-edge allows, created and removed by the controller | 0005 |
| S6 | Vault with JWT auth trusting SPIRE's OIDC discovery; role per service; database secrets engine issues Postgres users with a short TTL | 0003 |
| S7 | Keycloak realm `clinic`, clients `web` and `records-api`; `web` does auth code + PKCE | 0003 |
| S8 | cert-manager with a short-lived CA issuer for ingress and Keycloak TLS | 0003 |
| S9 | Event adapters (service logs, SPIRE, Kubernetes API, Vault audit, Keycloak events) → one SSE stream, SQLite replay | 0004 |
| S10 | Svelte dashboard: Topology, Identity, Request trace, Attack lab, Layer control, Secrets | 0004 |
| S11 | Attack runner in the `attacker` pod; each attack declares its expected outcome per layer-mode combination | 0002 |

## Affordances

**UI**

| Affordance | Place | Wires to |
|------------|-------|----------|
| Live workload graph with allow/deny edges and the deciding layer | Topology | SSE stream, S9 |
| SVID card: SPIFFE ID, serial, expiry countdown, rotation history | Identity | SPIRE adapter |
| Per-request stepper across layers | Request trace | event ids sharing a `trace` id |
| Run attack button, expected vs actual outcome, "stopped by" badge | Attack lab | S11 via observer |
| Off/audit/enforce switch per layer, with a "what this changes" note | Layer control | `PUT /layers/{layer}` |
| Live credential list: type, holder, issued, TTL remaining | Secrets | Vault adapter |
| Attack matrix table (attack rows × layer-mode columns) | Attack lab | stored attack results |

**Non-UI**

| Affordance | Kind | Wires to |
|------------|------|----------|
| `make up / down / demo-vN / test` | CLI | Helm, kubectl, pytest |
| `GET /events` (SSE), `GET /events?since=` | observer API | S9 |
| `PUT /layers/{layer}` | controller API | ConfigMap, NetworkPolicy, Vault role |
| `POST /attacks/{name}/run` | observer API | attacker pod |
| `exercises/vN-*.md` | docs | one per slice |

## Implementation decisions

- **Event contract** (ADR-0004) is versioned and the only interface between backends and UI. The UI never calls Vault, SPIRE or Kubernetes directly.
- **Trace ids.** `web` creates a trace id per user action and passes it as a header. Every service copies it into its events. This is what makes the Request trace view possible. It is an observability header, not a security control, and the README says so.
- **Attack catalogue** (initial): read Postgres directly from `attacker`; call `records-api` from `attacker` with no identity; call `records-api` from `billing` on a route it isn't allowed; replay a captured JWT-SVID after expiry; use a leaked static DB password from a pod that shouldn't have it; call `records-api` without a user token; reach `billing` from a pod in another namespace.
- **Expected-outcome table.** Each attack lists, per layer combination, `succeeds` or `stopped_by=<layer>`. The matrix test asserts every row. This doubles as the lesson's answer key.
- **Naming.** Namespaces `clinic` (app), `spire`, `vault`, `keycloak`, `observability`, `attacker`. The attacker is in its own namespace to make the network layer meaningful.
- **UI craft.** Design tokens, light and dark themes, keyboard-navigable, verdict conveyed by icon and text as well as colour. Built with the `frontend-design` skill. Diagrams for the Topology and Request trace views are drawn from live data, not static images.

## Testing approach

The top seam is the attack matrix against the real cluster. That is what R0 promises, and it exercises every layer for real. Below it, the observer's event adapters get contract tests with recorded fixtures, so UI development doesn't need a cluster. The UI gets Playwright tests against the real stack for smoke and against a fixture event stream for view behaviour. Unit tests are limited to the authorisation table and event normalisation. A good test here asserts an outcome (this attack, this mode, this verdict, this reason) and never an implementation detail.

## Assumed defaults

| ID | Assumed | Cost if wrong |
|----|---------|---------------|
| Q10 | Python 3.12 + FastAPI for toy services | Low, services are small |
| Q11 | `py-spiffe` is enough for rotation and mTLS contexts | V1 reworked, or switch to `spiffe-helper` or Go (new ADR) |
| Q12 | Vault OSS (BSL) acceptable for a local playground | Swap to OpenBao, mostly API-compatible |
| Q13 | Stack fits in about 4 GB on this 8 GB WSL2 host | Trim Keycloak or raise the WSL memory limit |
| Q14 | Upstream charts behave like the Red Hat builds closely enough to teach the concepts | Concepts hold, manifests differ |
| Q15 | Network `audit` mode is unavailable on k3s | UI shows "not available", no rework |

## Open risks

- **py-spiffe maturity** shows up in V1.
- **Memory.** The full stack on 8 GB shows up by V6 when Keycloak joins. Check `docker stats` at the end of each slice.
- **UI scope creep.** Six views is a lot. Each slice delivers only the view it needs, so V2 ships Topology, V1 ships Identity, and so on.
- **A privileged observer** in a zero trust demo is awkward. ADR-0005 narrows it and the UI says so.

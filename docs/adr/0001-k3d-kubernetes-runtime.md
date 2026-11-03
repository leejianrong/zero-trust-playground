# ADR-0001: Run everything on a disposable k3d Kubernetes cluster

- Status: Accepted
- Date: 2026-11-03
- Deciders: user, agent

## Context

The Layered Zero Trust pattern is a Kubernetes pattern. SPIRE's `k8s_psat` attestor, NetworkPolicy and per-pod service accounts only mean something on Kubernetes. The host is WSL2 with Docker, `k3d` v5.9.0 and `kubectl`/`helm` installed, 16 CPUs, 8 GB RAM total (about 5 GB free when checked). `kind` is not installed.

Smoke test on 2026-11-03: a k3d cluster came up in about 20 seconds, and a default-deny ingress NetworkPolicy blocked a request that succeeded before it. k3s embeds an enforcing network policy controller, so no extra CNI is needed.

## Decision

One single-server k3d cluster named `ztp`, created and destroyed by `make up` / `make down`. All components run in it. Nothing is installed on the host beyond the CLI tools. Traefik and servicelb from k3s are disabled unless a slice needs them.

## Alternatives considered

| Option | Why not |
|--------|---------|
| docker compose | No `k8s_psat` attestor, no NetworkPolicy, no service accounts. SPIRE would use a weaker attestor and the network layer would be fake. |
| kind | Not installed, and needs a separate CNI (Calico/Cilium) to enforce NetworkPolicy. More setup for no gain. |
| minikube | Installed, but heavier and slower to reset than k3d. |
| A real OpenShift cluster | Cost, and the learner shouldn't need one. Concepts transfer, manifests don't (see ADR-0003). |

## Consequences

- The whole stack must fit in roughly 4 GB. Keycloak is the biggest consumer, so slice V6 is where memory is checked.
- Every slice must be re-runnable from `make down && make up`. No hand-applied state.
- Learners need working Docker. Documented in the README.
- Image pulls need internet on first run. Pin versions in `versions.env` and pre-pull via `k3d image import` as an optional offline step.

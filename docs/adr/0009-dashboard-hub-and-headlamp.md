# ADR-0009: A dashboard hub, with Headlamp (view-only) for the cluster

- Status: Accepted
- Date: 2026-11-03
- Deciders: user, agent

## Context

A learner needs to look at the system from several sides: the clinic app as a user, the cluster as an operator, the zero trust design as a student, and later Vault and Keycloak as an administrator. Those views live in different tools on different ports.

Kubernetes Dashboard was archived in early 2026 and the Kubernetes project now points people to Headlamp. Headlamp is a CNCF Sandbox project that runs in-cluster and uses a ServiceAccount token, so what it shows follows RBAC. A user who cannot edit a resource is not offered the action.

## Decision

- Add an **Explore** view to our dashboard. It lists each tool with what it is for, a link, and a live up/down check made by the observer (`GET /links`).
- Install Headlamp with Helm in its own namespace. Its login token comes from a ServiceAccount bound to the built-in `view` ClusterRole, so it is read-only and cannot read Secrets. `make headlamp-token` prints a short-lived token for the user to paste. The token is never written to a file or a log.
- Offer an `admin` variant (`make headlamp-token ROLE=admin`) so the learner can see how much a cluster dashboard can do when its identity is too powerful.
- Vault's and Keycloak's own consoles join the hub when V5 and V6 add them.
- A new **Architecture** view in our dashboard (built in V3, alongside the layer switches) shows the pattern's layers, which are on, and what each protects.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Kubernetes Dashboard | Archived, no security fixes. |
| Lens or FreeLens | Desktop apps, so nothing to link from a hub and not reproducible from `make up`. |
| k9s | A terminal UI. Worth mentioning in the docs as an extra, not a dashboard. |
| Kubeapps | An application catalogue, not a cluster view. |
| Hubble UI | Needs Cilium, and we use k3s's built-in network policy controller. |

## Consequences

- Headlamp is a privileged-looking component in a zero trust demo. Using the `view` role and showing the `admin` contrast turns that into a lesson.
- Memory for Headlamp is unmeasured at the time of writing. It is measured in V2b and recorded in the README.
- The hub's up/down checks mean the observer reaches other services, so it needs to know their addresses. Configured in one list.

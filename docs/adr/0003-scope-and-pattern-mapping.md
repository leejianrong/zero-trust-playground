# ADR-0003: Scope is Layer 0 identity, secrets, user auth and network; upstream equivalents only

- Status: Accepted
- Date: 2026-11-03
- Deciders: user, agent

## Context

The Layered Zero Trust pattern (validatedpatterns.io) has three layers: Layer 0 foundation (Vault, External Secrets Operator, SPIFFE/SPIRE, Keycloak, NetworkPolicies, RHACS, Compliance Operator, certificate management), Layer 1 feature sets (supply chain, registries) and Layer 2 use-case apps. It deploys through GitOps on OpenShift using Red Hat builds. Running all of it would not fit in 8 GB of RAM and would bury the concepts.

## Decision

In scope, mapped to the pattern:

| Pattern component | Playground |
|-------------------|-----------|
| SPIFFE/SPIRE | Upstream SPIRE, `k8s_psat` attestor, trust domain `playground.local` |
| Vault + ESO | Vault OSS with JWT auth bound to JWT-SVIDs, dynamic Postgres credentials; ESO for one static secret |
| Keycloak | Upstream Keycloak, one OIDC client per app |
| NetworkPolicy | Default-deny per namespace, explicit allows |
| Certificate management | cert-manager with a short-lived CA for TLS edges |
| Layer 2 use case | The "clinic records" toy app |

Out: OpenShift and Red Hat builds, GitOps/Argo CD, Compliance Operator, supply chain signing, SPIRE federation. RHACS-style runtime kill is a stretch slice (V8), not part of the core.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Deploy the real pattern on OpenShift Local | Needs far more RAM than this machine has, and hides the mechanics behind GitOps. |
| Include GitOps | Makes every experiment a git commit. Slows the attack/observe loop that teaches. |
| Include Compliance and supply chain | They are separate lessons with separate tooling. Add as later playgrounds. |

## Consequences

- Concepts and architecture transfer to the pattern. Manifests and operators do not. The README says so up front.
- The pattern page does not name its demo apps, so the toy app is our own design. We cannot claim parity with the pattern's Layer 2.
- Federation, which is where SPIFFE gets interesting at scale, is deferred.

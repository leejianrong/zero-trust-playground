# About layered zero trust

Zero trust starts from one assumption: anything inside your network might already be compromised, so every request has to prove itself every time. "Layered" means that no single check carries that weight. If one layer fails, another still stands in the way.

## Why layers

Look at the first six [attacks](../reference/attacks.md), which you run with `make attack`. Each one gets through for a different reason:

| Attack | What let it through | The layer that answers it |
|---|---|---|
| Read Postgres directly | Any pod can reach the database, and the password is shared and permanent | Network policy, and short-lived database credentials |
| Call `records-api` with no identity | The service never asks who is calling | Workload identity with mutual TLS |
| Reach `billing` from another namespace | The network is flat | Network policy, and identity |
| Call the MCP server with no identity | The same missing identity check, on a new front door | Workload identity, and a user token |
| Agent obeys a poisoned record | Data was treated as instructions, and the delete tool had no limits | Agent identity, a delegated user token, and per-tool scopes |

No row has a single answer. A network policy would block the first attack, but if someone stole the password from a pod that is allowed to connect, only short-lived credentials would help. That overlap is the point.

## The pattern

The [Layered Zero Trust validated pattern](https://validatedpatterns.io/patterns/layered-zero-trust/) describes three layers. Layer 0 is the foundation: identity, secrets, certificates, network segmentation, monitoring and compliance. Layer 1 holds optional feature sets such as supply chain security. Layer 2 is sample applications that show it working. It deploys all of this on Red Hat OpenShift through GitOps.

This playground borrows the Layer 0 ideas and the Layer 2 idea of a real app, on a laptop:

| Pattern component | In the playground | State |
|---|---|---|
| SPIFFE and SPIRE (workload identity) | SPIRE on k3d, one identity per service account | Built. Services use their identities for mutual TLS (see [Turn on mutual TLS](../layers-and-mtls.md)). |
| Network policies | Default-deny with explicit allows | Built. See [Turn on the network layer](../the-network-layer.md). |
| HashiCorp Vault and External Secrets | Short-lived database credentials | Not built yet |
| Keycloak (users) | One login client per app | Not built yet |
| Certificate management | A short-lived CA for TLS | Not built yet |
| Runtime monitoring | A detector that removes a compromised pod | Optional, last |
| Compliance scans, supply chain, GitOps | Out of scope | Not planned |

We use upstream charts, not Red Hat's builds, and we do not run on OpenShift. The concepts transfer, and the manifests do not.

## Why agents are different

A browser user clicks buttons you built. A service calls endpoints you wrote. An agent reads whatever text it is given and then decides which tools to call, so a record in your database can become an instruction.

Layered zero trust has to cover that path too. The agent needs its own identity, and the person it acts for needs to be known to the tool. Each tool also needs limits the agent cannot talk its way past.

## Dashboards are part of the surface

Headlamp shows the cluster, and it can only do what its token allows. With a read-only token it is a window. With an admin token it is a control panel for whoever holds it. The same is true of the dashboard that shows these attacks, which is why the playground labels it as privileged. See [Read the cluster with Headlamp](../how-to/read-the-cluster-with-headlamp.md) for the side-by-side.

## Related

- [Workload identity](../workload-identity.md) is the first layer in practice.
- [Attacks](../reference/attacks.md) lists each attack and what it should do with no layers.

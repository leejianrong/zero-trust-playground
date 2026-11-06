# Zero Trust Playground

This playground runs a small clinic app on a local Kubernetes cluster, then lets you attack it. You see what an unprotected system gives away, and, as layers are switched on, which layer stops which attack.

It follows the [Layered Zero Trust validated pattern](https://validatedpatterns.io/patterns/layered-zero-trust/): SPIFFE and SPIRE for workload identity, Vault for secrets, Keycloak for users, network policy for the network. We use upstream charts on a k3d cluster, so the ideas carry over to the real pattern but the manifests do not.

!!! warning "Weak on purpose"
    Several parts are deliberately insecure so you can see them fail: a shared database password, services that trust anyone, an agent that obeys text hidden in data. Run it on your own machine only.

## What you can look at

| You want to see | Open | Page |
|---|---|---|
| The clinic app as a user | the clinic page on port 8081 | [The open clinic](the-open-clinic.md) |
| The cluster as an operator | Headlamp on port 4466 | [Read the cluster with Headlamp](how-to/read-the-cluster-with-headlamp.md) |
| Each workload's identity, rotating | our dashboard on port 5173 | [Get started](get-started.md) |
| Layers switched off, audit and enforce | the Layers and Architecture views on port 5173 | [Turn on mutual TLS](layers-and-mtls.md) |
| Network policies applied, and a pod refused | the command line and the Layers view | [Turn on the network layer](the-network-layer.md) |
| Short-lived database credentials, and the old password refused | the Secrets and Layers views | [Turn on the secrets layer](the-secrets-layer.md) |
| Sign-in, roles, and a forged identity refused | the Users and Layers views | [Turn on the user layer](the-user-layer.md) |
| An AI agent using the app | the command line (`make attack`) | [Agents and MCP](agents-and-mcp.md) |

## Where the playground is today

Slices V1, V2, V2b, V3, V4, V5 and V6 are built. Every workload has an identity, there is a real app, and with no layers on **every attack succeeds**. Of the nine attacks, mutual TLS blocks six, the network layer blocks eight, the secrets layer blocks the two that read Postgres directly, and the user layer blocks six. No single layer stops all nine, and the prompt-injection attack is stopped only by the user layer, and only because its attacker has no account. Closing that gap needs an identity for the agent and scopes for its tools, which arrive next.

## What you need

Docker, [k3d](https://k3d.io), kubectl, helm, [uv](https://docs.astral.sh/uv/) and Node.js. About 3 GB of free memory for the cluster (we measured 2.4 GiB with SPIRE, Vault, Keycloak and the clinic running, without Headlamp).

Start with [Get started](get-started.md).

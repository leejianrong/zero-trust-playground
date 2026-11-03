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
| An AI agent using the app | the command line (`make attack`) | [Agents and MCP](agents-and-mcp.md) |

## Where the playground is today

Slices V1 and V2 and the agent baseline (V2b) are built. That means every workload can get an identity, there is a real app, and **every attack succeeds**. The layers that stop them (mTLS, network policy, Vault, Keycloak, agent scopes) arrive next. The open baseline is useful on its own, because it shows exactly what each of those layers has to fix.

## What you need

Docker, [k3d](https://k3d.io), kubectl, helm, [uv](https://docs.astral.sh/uv/) and Node.js. About 2 GB of free memory for the cluster (we measured 1.6 GiB with everything running).

Start with [Get started](get-started.md).

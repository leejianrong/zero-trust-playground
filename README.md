# Zero Trust Playground

A disposable Kubernetes cluster on your laptop where you can attack a toy clinic app, switch security layers on and off, and watch what stops what. It follows the [Layered Zero Trust validated pattern](https://validatedpatterns.io/patterns/layered-zero-trust/): SPIFFE/SPIRE for workload identity, Vault for secrets, Keycloak for users, NetworkPolicy for the network, cert-manager for certificates.

The dashboard is the point. It shows identities rotating, requests being allowed or refused, and which layer made the call.

> **The concepts transfer to the real pattern. The manifests don't.** This uses upstream charts on k3d, not the Red Hat builds on OpenShift with GitOps. Several configurations are deliberately weak when a layer is off. Run it on localhost only.

Status: slice V1 in progress. The plan is in [PLAN.md](PLAN.md), the build order in [SLICES.md](SLICES.md), and the reasons in [docs/adr/](docs/adr/).

## Quick start

You need Docker, [`k3d`](https://k3d.io), `kubectl` and `helm`.

```sh
make up       # k3d cluster "ztp" plus SPIRE, about 2 minutes warm
make status   # pods and memory
make down     # delete everything
```

Memory baseline after `make up` (V1, SPIRE only): the k3d node uses about 0.9 GB. The budget for the full stack is 4 GB on an 8 GB host.

All chart and image versions are pinned in `versions.env`.

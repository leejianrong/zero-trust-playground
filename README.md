# Zero Trust Playground

A disposable Kubernetes cluster on your laptop where you can attack a toy clinic app, switch security layers on and off, and watch what stops what. It follows the [Layered Zero Trust validated pattern](https://validatedpatterns.io/patterns/layered-zero-trust/): SPIFFE/SPIRE for workload identity, Vault for secrets, Keycloak for users, NetworkPolicy for the network, cert-manager for certificates.

The dashboard is the point. It shows identities rotating, requests being allowed or refused, and which layer made the call.

> **The concepts transfer to the real pattern. The manifests don't.** This uses upstream charts on k3d, not the Red Hat builds on OpenShift with GitOps. Several configurations are deliberately weak when a layer is off. Run it on localhost only.

Status: slices V1 (workload identity) and V2 (the unprotected clinic app and its first attacks) are built; the rest follow in order. The tutorial is published at <https://leejianrong.github.io/zero-trust-playground/> (or run `make docs`). The plan is in [PLAN.md](PLAN.md), the build order in [SLICES.md](SLICES.md), and the reasons in [docs/adr/](docs/adr/).

## Quick start

You need Docker, [`k3d`](https://k3d.io), `kubectl` and `helm`.

```sh
make up       # k3d cluster "ztp" plus SPIRE, about 2 minutes warm
make status   # pods and memory
make down     # delete everything
```

To see identities rotate:

```sh
make echo       # two toy workloads that fetch SVIDs from SPIRE
make observer   # event collector on :8765 (second terminal)
cd web && npm install && npm run dev   # dashboard on :5173 (third terminal)
```

Then deploy the clinic app:

```sh
make clinic     # web, records-api, billing, postgres, plus the attacker pod
```

Open the clinic app itself, a small patient-records page where you can add, edit and delete patients:

```sh
make web        # then browse to http://localhost:8081
```

The page prints the trace id of your last change, and `curl 'localhost:8765/events?follow=false&trace=<id>'` returns every hop that change took.

With no layers on, every attack gets through. Run them with `make attack` (list) and `make attack A=<name>`. That is the baseline the next slices take apart.

Try the first break-it exercise: `kubectl delete clusterspiffeid clinic`. The cards flip to "Registration removed", then run out of time and expire. `make spire` brings the registration back. The chart's catch-all ClusterSPIFFEID is switched off on purpose, so no registration means no identity.

Memory (measured): the k3d node uses about 0.9 GB after `make up`, and 1.6 GB with the clinic app, the agent and Headlamp running (Headlamp itself is about 17 MB). The budget for the full stack is 4 GB on an 8 GB host.

The cluster dashboard is Headlamp:

```sh
make headlamp                       # install it with a read-only login
make headlamp-ui                    # http://localhost:4466 (second terminal)
make headlamp-token                 # print a one-hour read-only token to paste in
ROLE=admin make headlamp-token      # the cluster-admin contrast
```

With the read-only token you can see every pod but not the Secrets, and there is no delete button. With the admin token you get terminals, edit and delete. A dashboard can do exactly what its identity can do, which is the same lesson as the rest of this playground.

All chart and image versions are pinned in `versions.env`.

# Network policies

The network layer is a set of Kubernetes NetworkPolicies generated from one list of allowed calls, `EDGES` in `services/observer/observer/network.py`. `PUT /layers/network` with `enforce` applies the set and `off` deletes it. Both are safe to repeat. Every policy carries the label `ztp/layer=network`, and `off` removes only policies with that label.

Each namespace (`clinic` and `agents`) gets a `default-deny` policy that refuses all incoming connections. Each row below becomes one `allow-<destination>` policy:

| Destination | Allowed from | Ports |
|---|---|---|
| `postgres` | `records-api` | 5432 |
| `records-api` | `web`, `billing`, `records-mcp` | 8080, 8443 |
| `billing` | `web` | 8080, 8443 |
| `records-mcp` | `agent` (namespace `agents`) | 8080, 8443 |
| `agent` | `web` (namespace `clinic`) | 8080, 8443 |
| `web` | anyone | 8080 |

The list is checked against the allow-list that the services use for mTLS (`services/clinic/clinic/authz.py`) by a test, so the two cannot drift apart.

## What it does not do

- It restricts incoming connections only. Outgoing traffic is open.
- It has no `audit` mode. A dropped connection leaves no log, so `PUT /layers/network` with `audit` returns `409`.
- A connection that is already open keeps working after the policies are applied. Only new connections are checked.
- It was measured with the network policy engine that ships with k3s. Another engine would need its own check.

## Events

The observer lists the policies in both namespaces every 2 seconds and reports each difference:

| `kind` | When |
|---|---|
| `policy_added` | A policy appeared |
| `policy_changed` | A policy's rules changed |
| `policy_removed` | A policy was deleted |

`dst` is `namespace/name`. `evidence.origin` and `src` are `controller` when the observer's own apply or remove made the change, and `out-of-band` for anything else, such as `kubectl delete`. Policies that exist when the observer starts are not reported.

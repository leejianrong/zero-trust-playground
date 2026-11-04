# Observer API

The observer collects events and runs attacks. It listens on <http://localhost:8765>, and FastAPI's own docs are at `/docs`.

## `GET /events`

Streams events as server-sent events. Each message has an `id` and a `data:` line of JSON.

| Parameter | Default | Description |
|---|---|---|
| `since` | `0` | Return only events with an id greater than this |
| `follow` | `true` | Keep the stream open. Use `false` for a one-off read |
| `trace` | none | Return only events with this trace id |

A reconnecting client can send a `Last-Event-ID` header instead of `since`. A one-off read returns at most 500 events, so pass `trace` or page with `since`.

### Event fields

| Field | Type | Description |
|---|---|---|
| `v` | integer | Schema version, always `1` |
| `id` | integer | Position in the log |
| `ts` | number | Unix time in seconds |
| `layer` | string | `app`, `identity`, `mtls`, `network`, `secrets`, `user` or `runtime` |
| `kind` | string | For example `http_request`, `db_connect`, `svid_issued`, `entry_added`, `policy_removed`, `credential_issued`, `credential_denied`, `user_login`, `user_login_failed`, `user_logout`, `user_token_refused`, `user_authorisation`, `attack_result` |
| `src`, `dst` | string or null | The calling and called workloads |
| `verdict` | string | `allow`, `deny` or `info` |
| `reason` | string or null | Why, when a layer decided |
| `trace` | string or null | The trace id shared by one change's events |
| `evidence` | object | Fields specific to the kind |

## `GET /attacks`

Returns the attack catalogue: `name`, `title`, `description`, `target`, `expected` and, for an attack that runs from a pod other than the attacker, `from` (`namespace` and `deploy`).

## `POST /attacks/{name}/run`

Runs one attack from the pod the catalogue names (the attacker pod unless it says otherwise) and returns its `attack_result` event. A blocked attack carries `stopped_by`: a layer name, `network (inferred)` when the connection was refused while the network layer covers the target, or null. The attack's detail includes `phase` (`connect`, `handshake` or `request`) for a blocked attack. Returns `404` for an unknown name and `502` if the attacker pod gives no result.

## `POST /app/use`

Sends one visit through `web` for a random patient and returns `{"ok": true, "patient": <id>}`. Returns `502` if `web` does not answer.

## `GET /links`

Returns each tool with `name`, `url`, `purpose`, `start` and `up`. `up` is true when the tool answers with a status below 500.

## `GET /healthz`

Returns `{"ok": true}`.

## `GET /layers`

Returns the current mode of each layer, for example `{"identity": "off", "mtls": "off", "secrets": "off", "user": "off", "network": "off"}`. The `identity`, `mtls`, `secrets` and `user` modes live in the `layer-modes` ConfigMap in the `clinic` namespace, and the services poll it every 2 seconds. The `network` mode is `enforce` when the whole set of network policies exists in the cluster, `partial` when some are missing but a default-deny is still there (the rest still deny traffic), and `off` when no default-deny is left. `PUT /layers/network` takes only `off` and `enforce`; `partial` is something you can only observe. The network policy events are described in [Network policies](network-policies.md).

## `PUT /layers/{layer}`

Sets one layer to `off`, `audit` or `enforce` with a body like `{"mode": "audit"}`, and returns the new modes. Returns `422` for an unknown layer or mode. Returns `409` with a reason when the change would break the playground: `mtls` cannot be on while `identity` is off, and `identity` cannot go off while `mtls` is on. `secrets` needs Vault and `user` needs Keycloak: turning either to `audit` or `enforce` returns `409` with a reason (`make vault` or `make keycloak` first) if it is not installed. Entering `enforce` waits a few seconds so `records-api` is on Vault credentials, then revokes the shared database password; leaving `enforce` restores it first. `network` has no `audit` mode and `PUT /layers/network` with `audit` returns `409`; `enforce` applies the network policies and `off` deletes them. A change that alters a mode is recorded as a `layer_mode_changed` event. The dashboard's **Layers** view calls this endpoint.

!!! warning "The controller can turn security off"
    The observer runs on your machine with your kubeconfig, so this endpoint is as privileged as you are. It listens on localhost only.

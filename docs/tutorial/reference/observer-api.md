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
| `kind` | string | For example `http_request`, `db_connect`, `svid_issued`, `entry_added`, `attack_result` |
| `src`, `dst` | string or null | The calling and called workloads |
| `verdict` | string | `allow`, `deny` or `info` |
| `reason` | string or null | Why, when a layer decided |
| `trace` | string or null | The trace id shared by one change's events |
| `evidence` | object | Fields specific to the kind |

## `GET /attacks`

Returns the attack catalogue: `name`, `title`, `description`, `target` and `expected`.

## `POST /attacks/{name}/run`

Runs one attack from the attacker pod and returns its `attack_result` event. Returns `404` for an unknown name and `502` if the attacker pod gives no result.

## `POST /app/use`

Sends one visit through `web` for a random patient and returns `{"ok": true, "patient": <id>}`. Returns `502` if `web` does not answer.

## `GET /links`

Returns each tool with `name`, `url`, `purpose`, `start` and `up`. `up` is true when the tool answers with a status below 500.

## `GET /healthz`

Returns `{"ok": true}`.

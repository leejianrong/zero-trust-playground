# ADR-0010: mTLS with permissive and strict modes, caller identity read in-process

- Status: Accepted
- Date: 2026-11-03
- Deciders: user, agent

## Context

V3 makes services check who is calling. Four things were unknown or under-specified in ADR-0005 and ADR-0006:

- How a layer can be switched off, audited and enforced when TLS is all-or-nothing on a port.
- How a uvicorn app learns the caller's SPIFFE ID. uvicorn 0.54 builds TLS contexts and accepts `ssl_context_factory`, but it does not put the peer certificate in the ASGI scope.
- How a service picks up a mode change within seconds. A ConfigMap mounted as a file can take about a minute to refresh.
- Who changes the modes. The observer runs on the host with the user's kubeconfig, so ADR-0005's "narrow RBAC" cannot describe it honestly yet.

The V1 spike showed stdlib `ssl` contexts built from py-spiffe SVIDs work, and that certificates rotate about every minute.

## Decision

**Modes follow the permissive/strict idea from service meshes.**

| Mode | What a service does |
|------|---------------------|
| `off` | Accepts plain HTTP and TLS alike. No authorisation. |
| `audit` | Same, but each request is checked against the allow-list and a would-deny is logged as an `info` event. Nothing is refused. |
| `enforce` | The plain listener refuses everything except `/healthz`. The TLS listener requires a valid SVID and an allow-listed caller, and refuses the rest with a `deny` event. |

**Two listeners per service.** Port 8080 is plain and port 8443 is mTLS. `web` keeps only the plain listener for browsers (the user layer is V6). Clients use mTLS whenever the identity layer is on.

**Enforcement lives in the app, not the handshake.** The TLS listener asks for a client certificate but does not require one (`CERT_OPTIONAL`), so a caller with no certificate gets through the handshake. It is then refused with a `deny` event that names the reason and carries the trace id.

A certificate that is presented but not signed by the trust bundle (a forged identity) fails the handshake in `audit` and `enforce`, and that refusal cannot be audited. The tutorial says so.

**Caller identity is read in-process.** A small `H11Protocol` subclass records the peer certificate's URI SAN in `connection_made`, keyed by the client's address and port, and removes it in `connection_lost`. Middleware looks the caller up from `scope["client"]`. The TLS context comes from `ssl_context_factory` and is rebuilt on a `sni_callback`, so rotation never needs a restart.

**Modes come from the Kubernetes API.** Each service polls one ConfigMap (`layer-modes`) every 2 seconds using its own ServiceAccount token. A Role grants `get` on that single ConfigMap by name and nothing else.

**The controller is a host process for now.** `PUT /layers/{layer}` in the observer patches the ConfigMap with kubectl and the user's kubeconfig. Running it in-cluster with a narrow ServiceAccount is a later card. Until then the docs say the controller is as privileged as the person running it.

**One safety rule.** The controller refuses `mtls=enforce` while `identity=off`, because legitimate clients would stop working and the clinic app would break. The UI explains why.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Require the client certificate in the handshake | Refusals would have no HTTP request, so no trace id and no reason in the event stream. |
| An Envoy or mesh sidecar | Hides the SPIFFE mechanics, and adds memory we do not have. A better follow-up playground. |
| A mounted ConfigMap file for modes | Can lag by about a minute, which breaks "takes effect within 5 seconds". |
| Swap to Hypercorn for its TLS ASGI extension | Replaces the server for one feature. The protocol subclass is about 20 lines. |
| One port, TLS only | Makes `off` and `audit` impossible without the plain listener. |

## Consequences

- The spike (AAL-50) proved the design on uvicorn 0.54.0, so the Hypercorn fallback is not needed. The code is `clinic/mtls.py`. Measured in a no-cluster test and live on k3d with real SPIRE SVIDs (2 minute TTL): 17 calls across 4 server certificates, no errors, the right caller every time.
- Rotation reaches new connections only. A connection already open keeps the certificate it started with. That is fine here because every client opens a fresh connection per call, and certificates last 2 minutes.
- The hot swap runs in the SNI callback, and clients send SNI only when they dial a DNS name. Services must therefore call each other by service name, never by IP.
- SPIRE certificates hold a SPIFFE ID and no DNS name, so ordinary hostname checks fail with `Hostname mismatch`. Clients turn hostname checking off and compare the server's SPIFFE ID themselves (`peer_id`), which is the SPIFFE model: authorise the ID, not the address.
- A certificate from the wrong CA fails the handshake, but under TLS 1.3 the client sees it on its first request as a dropped connection, not as an error while connecting. The attack runner must treat any transport error as "refused at the handshake".
- `enforce` still leaves the plain port open and answering with refusals. V4 closes it with network policy, which is a good lesson in why layers overlap.
- Postgres traffic is outside V3. The network layer (V4) and dynamic credentials (V5) cover it.
- mTLS must not stop the prompt-injection attack, because the agent and the user path are both legitimate. The attack matrix records that, and it is the reason V6b exists.

# Zero Trust Playground: Slices

Vertical increments. Each ends in something you can see in the dashboard. V1 confronts the riskiest unknown (SPIRE on k3d, plus py-spiffe). Plan one build session per slice. V1 and V2 may need two.

Each slice also ships its view, so the dashboard grows with the system: V1 Identity, V2 Topology and Attack lab, V3 Request trace and Layer control, V5 Secrets.

## V1: A workload gets an identity you can watch

**Delivers:** R1, R7 (partial), R8 (partial)

**Build plan**

1. Repo skeleton: `Makefile`, `versions.env`, `README.md` with the "concepts transfer, manifests don't" note, `uv` workspace, Vite app.
2. `make up`: k3d cluster `ztp`, SPIRE (spiffe/helm-charts-hardened) with `k8s_psat`, trust domain `playground.local`. Verify memory with `docker stats`.
3. Two throwaway workloads (`echo-a`, `echo-b`) in `clinic` with registration entries.
4. Spike: `py-spiffe` fetches an X.509-SVID and JWT-SVID and reacts to rotation. If it can't, decide between `spiffe-helper` and Go and write ADR-0007.
5. Observer skeleton with the event schema v1 and the SPIRE adapter (entries, agents, SVID serial and expiry). SSE endpoint.
6. Dashboard shell (design tokens, light/dark, nav) and the Identity view: SVID cards, expiry countdown, rotation history.
7. Set the SVID TTL short (for example 2 minutes) so rotation is visible in a demo.

**Demo:** `make up && make demo-v1` opens the dashboard. Two cards show `spiffe://playground.local/ns/clinic/sa/echo-a` and `echo-b` with counting-down TTLs. A card's serial changes and a new row appears in its history when it rotates. Deleting the `clinic` ClusterSPIFFEID removes the registrations, the card shows "Registration removed", and the ring runs out within the TTL. Re-applying it restores the identity.

**Rests on assumptions:** Q11 (py-spiffe suffices), Q13 (memory). If Q11 is wrong the slice grows by an ADR and a library swap, but no later slice changes shape.

### Test plan

#### End-to-end

- After `make up`, the Identity view shows both workloads with the expected SPIFFE IDs.
- Within 2× the SVID TTL, each card shows a new serial and the history has two entries.
- After deleting the `clinic` ClusterSPIFFEID, the card shows "Registration removed" and then expires within the TTL. Re-applying restores it.
- From a cold machine, `make up` reaches ready in under 10 minutes, and `make down` leaves no `k3d-ztp` containers.

#### Integration

- The SPIRE adapter, against a live server, emits events whose SPIFFE IDs match `kubectl get sa`.
- SSE `GET /events?since=` replays missed events after a reconnect.

#### Unit

- Event normalisation validates against the v1 JSON schema.
- Expiry countdown never goes negative and flips to "expired" at zero.

## V2: The unprotected baseline and the first attack

**Delivers:** R0 (partial), R7 (partial)

**Build plan**

1. Replace the echo workloads with the clinic app: `web`, `records-api`, `billing`, Postgres seeded with fake patients. Plain HTTP, static DB password, no authorisation.
2. Attacker namespace and pod with the attack runner and the first three attacks (read Postgres directly, call `records-api` with no identity, call `billing` from another namespace).
3. Per-request structured events and trace-id propagation.
4. Topology view: workloads as nodes labelled with SPIFFE IDs, edges from observed calls, verdict on each edge.
5. Attack lab view: attack list, Run button, expected vs actual, "stopped by" badge.
6. Exercise `exercises/v2-baseline.md`: predict which attacks succeed, then run them.

**Demo:** Open Topology and click "Use the app" to generate traffic. Edges `web → records-api → postgres` appear. In Attack lab, run "read patients from the attacker pod". It shows `succeeded`, and the Topology shows a new edge from `attacker` to Postgres.

**Rests on assumptions:** Q10 (FastAPI). None that change slice shape.

### Test plan

#### End-to-end

- With no layers on, all three attacks report `succeeds` and the Topology shows an `attacker → postgres` edge.
- A user action in `web` produces events from `web`, `records-api` and Postgres access that share one trace id.
- Playwright screenshot of Topology under load shows no overlapping labels at 1280×800.

#### Integration

- Each service emits events that validate against schema v1.
- The attack runner returns a result the observer stores, and the Attack lab reads it back.

#### Unit

- Trace-id middleware copies an inbound id and creates one when absent.
- Topology layout function is deterministic for the same node set.

## V3: Identity-based mTLS and the layer switch

**Delivers:** R2, R6 (identity and mtls layers), R7 (partial)

**Build plan**

1. Services use their SVIDs for mTLS on service-to-service calls and extract the caller's SPIFFE ID.
2. Authorisation table per service (caller SPIFFE ID → routes), with `off`, `audit`, `enforce`.
3. Layer controller and ConfigMap-based modes, with the narrow RBAC from ADR-0005.
4. Layer control view with per-layer switch and a "what this changes" note.
5. Request trace view: step through one trace across layers.
6. Add attacks: call from `billing` on a forbidden route, replay an expired JWT-SVID.
7. Exercise `exercises/v3-mtls.md`: switch `mtls` to `audit`, predict what the log shows, then `enforce`.

**Demo:** In Layer control, set `mtls` to `enforce`. In Attack lab, "call records-api with no identity" flips from `succeeds` to `stopped_by: mtls`. The Request trace shows the handshake failing at the layer step. `billing` calling an allowed route still works, and a forbidden route gets a 403 naming `billing`'s SPIFFE ID.

### Test plan

#### End-to-end

- `mtls=enforce`: the no-identity attack is stopped by `mtls`, and normal `web` use still works.
- `mtls=audit`: the same attack succeeds, and a deny-would-have-happened event is logged.
- `mtls=off`: the attack succeeds and no authorisation events are emitted.
- Flipping a mode from the UI takes effect within 5 seconds.

#### Integration

- The controller's service account cannot modify anything outside its permitted objects (assert a forbidden patch is rejected).
- A service rereads its mode without restarting.

#### Unit

- The authorisation table returns allow/deny for each (caller, route, mode) combination.

## V4: Default-deny network

**Delivers:** R3, R6 (network layer)

**Build plan**

1. Controller creates default-deny NetworkPolicies in `clinic` plus per-edge allows.
2. Network events from the Kubernetes API adapter (policy changes) and from refused connections the services observe, shown on Topology edges with `layer=network`.
3. UI marks network `audit` as "not available" (Q15).
4. Add the attacks "reach billing from another namespace" and "connect to Postgres from `billing`".
5. Exercise `exercises/v4-network.md`: remove the `web → records-api` allow, predict, check.

**Demo:** With `mtls=off` and `network=enforce`, the attacker's direct Postgres connection is refused, and Topology draws the edge in the deny style labelled `network`. Then turn `network` off and `mtls` on to see the same attack stopped by a different layer.

**Rests on assumptions:** Q15.

### Test plan

#### End-to-end

- `network=enforce`, others off: attacker→Postgres is stopped by `network`, `web` still reaches `records-api`.
- `network=off`, `mtls=enforce`: attacker→`records-api` stopped by `mtls`, attacker→Postgres still succeeds.
- Both off: both succeed.

#### Integration

- Applying and removing the policy set is idempotent.
- The Kubernetes adapter emits an event when a policy is deleted out of band.

#### Unit

- Edge-allow generator produces the expected policy for each declared edge.

## V5: No standing database password

**Delivers:** R4, R6 (secrets layer), R7 (Secrets view)

**Build plan**

1. Vault in `vault`, JWT auth method trusting SPIRE's OIDC discovery endpoint, one role per service.
2. Database secrets engine issues Postgres users with a 2-minute TTL.
3. `records-api` fetches creds with its JWT-SVID. In `off` it still uses the static password.
4. ESO syncs one non-database static secret from Vault to a Kubernetes Secret, to show the other path.
5. Vault audit adapter and the Secrets view: live creds, holder, issued, TTL left.
6. Attack: use a leaked static password from another pod. Exercise `exercises/v5-secrets.md`.

**Demo:** With `secrets=enforce`, Secrets view shows `records-api` holding a credential counting down and replaced on rotation. The leaked-static-password attack fails because that password was revoked.

**Rests on assumptions:** Q12 (Vault OSS licence is fine), Q11 (JWT-SVID usable for Vault login).

### Test plan

#### End-to-end

- `secrets=enforce`: the leaked-password attack fails and `records-api` still serves requests across at least two credential rotations.
- `secrets=off`: the leaked-password attack succeeds.
- Secrets view shows a credential created within 5 seconds of issue.

#### Integration

- A JWT-SVID from `billing` cannot log in to the `records-api` Vault role.
- ESO-synced secret updates in Kubernetes after a Vault change.

#### Unit

- TTL display computes remaining time and expiry state.

## V6: Who is the user

**Delivers:** R5, R6 (user layer)

**Build plan**

1. Keycloak with realm `clinic`, clients `web` and `records-api`, two test users with different roles.
2. `web` logs in via auth code + PKCE. `records-api` validates the access token (issuer, audience, expiry).
3. Keycloak events adapter and user-level fields in the event model (subject, client).
4. Attack: call `records-api` without a token; call with a token for the wrong audience.
5. Check memory after Keycloak joins. Trim if above the 4 GB target.

**Demo:** Request trace for a user action now shows a user step: subject, client and audience. The no-token attack is stopped by `user`.

**Rests on assumptions:** Q13. If the memory target fails, switch Keycloak to a smaller dev profile or raise the WSL limit.

### Test plan

#### End-to-end

- `user=enforce`: no-token and wrong-audience attacks are stopped by `user`.
- `user=off`: `records-api` trusts a header and the no-token attack succeeds.
- Full stack memory stays under 4 GB at idle.

#### Integration

- Token validation rejects expired, wrong-issuer and wrong-audience tokens.

#### Unit

- Claim extraction maps Keycloak roles to route permissions.

## V7: Defence in depth, end to end

**Delivers:** R0 (complete), R7 (complete), R8 (complete)

**Build plan**

1. cert-manager with a short-lived CA issuer for the TLS edges.
2. Full attack catalogue with expected outcomes in the declarative table.
3. Attack matrix view: every attack against every layer-mode combination, expected versus actual.
4. A guided tour that walks the learner through "turn one layer off at a time" and explains what each result means.
5. Final README: the pattern mapping, what transfers to the real pattern, and where an agent would fit as a workload (link to agent-auth-lab).
6. Final Playwright suite with screenshots for every view in light and dark.

**Demo:** Run the full matrix. A table of attacks against layer combinations fills in, and every cell matches the expected table. The learner turns off `network` and sees which attacks now rely on `mtls` alone.

### Test plan

#### End-to-end

- Matrix run: every cell matches the declared expectation (this is the acceptance test for the whole playground).
- Cold start to full matrix pass in one scripted run.
- Every view renders in light and dark with no console errors, and screenshots are saved.

#### Integration

- cert-manager issues a certificate, and it rotates inside its short lifetime.

#### Unit

- Matrix-diff function reports a mismatch when an expected cell is wrong.

## V8 (stretch): A compromised pod gets killed

**Delivers:** R9

**Build plan**

1. Decide between Falco and a small hand-rolled detector. Choose after checking memory headroom.
2. Rule: unexpected outbound connection or shell in a `clinic` pod.
3. Response: delete the pod, emit a `runtime` event, show it on Topology.
4. Attack: exec a shell into `records-api` and try to dump data.

**Demo:** The shell attack triggers a `runtime` event and the pod restarts with a new identity serial.

### Test plan

#### End-to-end

- The shell attack results in pod deletion within 10 seconds and a visible event.

#### Integration

- The detector ignores normal traffic for 5 minutes (no false kills).

#### Unit

- Rule evaluator flags the intended events and no others.

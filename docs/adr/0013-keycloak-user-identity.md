# ADR-0013: Keycloak signs users in and records-api validates their tokens

- Status: Accepted
- Date: 2026-11-04
- Deciders: user, agent

## Context

V6 adds the user layer. A person signs in, and the clinic decides what they may do from who they are, not only from which service is calling. The spike (AAL-71) ran Keycloak on the k3d cluster, signed in two users, validated their tokens from inside a clinic pod and read the event log. Everything below was measured on the playground cluster unless it says otherwise.

## Decision

**Keycloak 26.8.1 in `start-dev` mode, one pod in namespace `keycloak`.** It is a labelled throwaway like Vault: an embedded database, a fixed admin password, localhost only. A new pod starts with only the `master` realm, so `make keycloak` creates the `clinic` realm from nothing with `kcadm.sh`, and can be run again.

**One realm, `clinic`.** Clients: `web` (public, authorization code with PKCE `S256`, redirect `http://localhost:8081/*`) and `records-api` (bearer only). Roles `clinician` and `receptionist`. Users `aisha` (clinician) and `bob` (receptionist). Access tokens for `web` carry `aud: records-api` through an audience mapper.

**A fixed issuer name.** `KC_HOSTNAME=http://localhost:8180` and `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true`. Every token says `iss: http://localhost:8180/realms/clinic`, whether it was issued to the browser or to a pod. Discovery then points `jwks_uri` at `http://keycloak.keycloak.svc:8080/...`, which pods can reach. `records-api` checks the issuer against the fixed string and fetches keys from the service.

**`records-api` validates with PyJWT** (already in the image): signature (RS256, key from JWKS), issuer, audience `records-api`, expiry. Roles come from `realm_access.roles`.

**Events come from Keycloak's log.** The `jboss-logging` listener writes one line per event. Successes are hidden by default, so the pod sets `KC_SPI_EVENTS_LISTENER__JBOSS_LOGGING__SUCCESS_LEVEL=info`. The observer reads the lines the way it reads the Vault audit log.

## What we measured

| Question | Result |
|---|---|
| Memory | The Keycloak container used 540 MB in the spike and 705 MB after a fresh start with the realm created (cgroup `memory.current`), with the heap capped at 384 MB. Host `MemAvailable` fell from about 3.5 GB to about 2.1 GB when it started, which includes page cache. |
| Issuer from a pod vs from the browser | Both `http://localhost:8180/realms/clinic`. A token requested through the service name still carries the localhost issuer. |
| Token validation in `records-api` | A token for `bob` validated: signature, issuer and audience. A wrong audience raised `InvalidAudienceError`, a wrong issuer `InvalidIssuerError`. |
| Authorization code with PKCE | The login form, code and token exchange worked through a port-forward on 8180. A wrong `code_verifier` returned `invalid_grant: PKCE verification failed`. |
| Events | `LOGIN`, `LOGIN_ERROR` (`invalid_user_credentials`, `cookie_not_found`), `CODE_TO_TOKEN` and `CODE_TO_TOKEN_ERROR` (`pkce_verification_failed`) each logged with `clientId`, `userId` and `error`. Successes appeared only after the level was raised. |
| Restart | The `clinic` realm was gone after a pod restart. |

## Alternatives considered

| Option | Why not |
|---|---|
| Import the realm from a JSON file at start | Survives restarts, but the file is a large generated blob that hides the few settings a learner should read. A script of `kcadm` calls shows each one. Revisit if restarts get annoying. |
| Reuse the Lab IdP from the earlier labs | It is not part of this cluster, and the pattern uses Keycloak. |
| A separate Postgres for Keycloak | It would cost memory for nothing here. |

## Consequences

- The browser must reach Keycloak at `localhost:8180`, so a `make keycloak-ui` target forwards it, and sign-in only works while that forward runs.
- The token `iss` is a string match, not a reachable URL. That is deliberate and a learner may find it odd, so the tutorial says so.
- The user's access token is forwarded unchanged through the agent (AAL-74). That is the simplest path and also the weakest: the agent holds the user's token. V6b (AAL-47) replaces it with an agent identity.
- A failed sign-in with a missing cookie has `userId="null"`, so the Users list must cope with events that have no user.
- PyJWT arrives through another dependency and is not in `pyproject.toml`. AAL-35 adds it explicitly.
- Not measured: Keycloak's start time, the sign-in flow in a real browser, and a token lifetime short enough for the `audit` mode to be worth watching.

## Decisions made while building

- **Sign-in lives in `web`, not the dashboard.** The clinic page offers Sign in and runs authorization code with PKCE. The session is a cookie that scripts cannot read, and the server keeps the tokens in memory, so a restart signs everyone out. `web` refreshes a token that has under 30 seconds left and signs the user out if the refresh fails. `make keycloak-ui` forwards Keycloak to `localhost:8180`.
- **The token travels in a context variable.** Each service reads an `Authorization: Bearer` header on the way in and sends it on the way out, so `web`, `billing`, the agent and `records-mcp` need no per-route code. `web` is the exception: it takes the token from the session cookie only and ignores an `Authorization` header from the browser, so a visitor cannot choose their own token.
- **`records-api` is the only place that decides.** The user layer is one middleware there. `billing` and `records-mcp` pass the token on and decide nothing, so `cross-namespace-billing` still succeeds under `user=enforce`. That is correct for the layer and the catalogue says so.
- **Only clinic roles count.** The check reads `realm_access.roles` and keeps `clinician` and `receptionist`, so Keycloak's default roles do not show up in refusals.
- **A refusal names its layer.** `records-api` answers `{"error": "refused", "layer": "user", "reason": ...}`. `records-mcp` turns that into a tool error with the reason, and the agent returns it as a 403, so the clinic page can say "Refused by the user layer".
- **Two clients exist only for attacks.** `attacker-cli` signs in with a password and gets tokens whose audience is `billing`, so the wrong-audience attack holds a genuine token that `records-api` must still refuse. `billing` is a bearer-only client that only gives the audience a name. Both are labelled weak in `scripts/keycloak-configure.sh`.
- **The injection attack is stopped for a narrow reason.** `agent-prompt-injection` plants its text through the public form on `web`. With the user layer enforced the form needs a signed-in user, and the simulated attacker has none, so the planting step is refused. A signed-in clinician who plants the text, or whose agent reads it, is not stopped, because the agent carries that user's token. The catalogue expects `blocked` only for the anonymous attacker. V6b is meant to close the real gap.
- **Not yet checked on the cluster:** the matrix rows for the user layer. The attack unit tests pass, but the e2e matrix has not run with the new attacks.

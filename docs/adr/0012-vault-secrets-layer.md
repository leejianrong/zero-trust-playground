# ADR-0012: Vault logs workloads in with a JWT-SVID and issues short-lived Postgres users

- Status: Accepted
- Date: 2026-11-04
- Deciders: user, agent

## Context

V5 removes the standing database password. It rests on two assumptions we had not tested: that Vault accepts a SPIRE JWT-SVID as a login (Q11), and that the whole thing fits in the memory we have (Q13). The spike (AAL-64) ran Vault in dev mode on the k3d cluster (Kubernetes v1.35.5+k3s1, one node), logged in from the `records-api` and `billing` pods, and minted a Postgres user. Everything below was measured there.

## What we measured

| Question | Result |
|---|---|
| Does Vault accept a JWT-SVID from py-spiffe? | Yes. `records-api` fetched a JWT-SVID with audience `vault` and logged in to a `jwt` auth role. It got a Vault token with a 120 second TTL. |
| Can Vault use SPIRE's OIDC discovery URL? | Not as is. The SVID's `iss` is `https://oidc-discovery.playground.local`, and that name does not resolve in the cluster. Pointing `oidc_discovery_url` at the in-cluster Service would not match the issuer. We set `jwks_url` to the discovery provider's `/keys` on the Service, `bound_issuer` to the issuer, and `jwks_ca_pem` to SPIRE's CA. |
| Where does the CA come from? | The `x509-svid` keys in the `spire-bundle` ConfigMap, converted to PEM. The bundle holds two of them during a CA overlap. We did not watch a rotation, so a long-running Vault may need the PEM refreshed. |
| Is a login bound to one service? | Yes. The role sets `bound_subject` to the service's SPIFFE ID. A JWT-SVID from `billing` against the `records-api` role was refused with `invalid subject (sub) claim`. |
| Does the database engine issue users? | Yes. A role with `default_ttl=2m` and `max_ttl=2m` created a Postgres user such as `v-jwt-spif-records--...`. The user read 5 rows of `patients` straight away. |
| What happens at expiry? | At 135 seconds a new connection with that user was refused. A connection opened earlier stayed open but got `permission denied for table patients`, because Vault revoked its grants. The Postgres role was gone afterwards. |
| What does it cost? | The Vault process held about 47 MB of resident memory in dev mode. |

## Decision

**Vault in the `vault` namespace, JWT auth, one role per service.** Each role binds one SPIFFE ID with `bound_subject` and a policy that reads only that service's credentials.

**Keys by `jwks_url`, not discovery.** The issuer name does not resolve, so Vault fetches keys from the discovery provider's Service with the SPIRE CA pinned.

**Dev mode for now.** It is in memory, unsealed, with a fixed root token. Restarting the pod loses everything, so the install must be a script that configures Vault from nothing, and it must be safe to run twice. The root token is a throwaway, labelled, and Vault stays localhost-only.

**Image `hashicorp/vault:2.1.2`.** Pinned in `versions.env`. We did not recheck its licence terms against Q12.

## Consequences

- The install card (AAL-65) needs a configure step that can run again, and a way to refresh the SPIRE CA PEM.
- An open connection survives expiry. The credential is useless but the socket is not closed. A client that holds connections must expect `permission denied` and fetch again.
- Vault tokens also last 2 minutes here. We did not test renewal, so the `records-api` card has to.
- The dev-mode manifest in `deploy/vault/vault-dev.yaml` is the spike's. AAL-65 replaces it.

## Decisions made while building

- **Modes follow ADR-0005.** `off` keeps the shared password. `audit` gives `records-api` Vault credentials while the shared password still works. `enforce` also revokes the shared password. Entering `enforce` patches the ConfigMap, waits 3 seconds so the services are already on Vault, then revokes. Leaving it restores the password first.
- **Vault has its own Postgres admin.** The database engine logs in as `vault_admin`, created at install with a random password that goes to Postgres and Vault over stdin. That is what lets the shared `clinic` password be revoked without breaking Vault.
- **A rejected password is attributed by inference.** The attack runner reports a new `auth` phase, and the observer names `secrets (inferred)` when the layer is enforced. A mistyped password would be named the same way.
- **The Secrets view reads Vault's audit log.** The audit device writes to the pod's stdout. The log hashes usernames and passwords and carries no TTL, so the view shows holder and lease, and takes the lifetime from the role (120 seconds, checked by a test).
- **External Secrets uses Kubernetes auth, not the JWT-SVID.** The operator has no SPIFFE socket, so Vault checks its service account token through the Kubernetes API. The Vault role may read one path. Only the controller is installed, without the webhook or cert controller, to save memory.
- **Not changed:** open connections still outlive their credential, Vault token renewal is untested because `records-api` fetches a new login each time, and CA rotation has not been watched.


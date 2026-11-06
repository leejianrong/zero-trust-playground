# Attacks

The attack runner lives in `services/clinic/clinic/attacks/` and runs from the `attacker` pod, or from the pod that an attack's `from` entry in `catalog.json` names. Each attack is listed there with a default outcome and rules that change it for a layer mode. Run one with `make attack A=<name>`. The output names the layer modes, the expected outcome, whether the result matched, and, for a blocked attack, which layer stopped it.

| Name | Title | Runs from | Target | Layers off | mTLS enforced | Network enforced | Secrets enforced | User enforced |
|---|---|---|---|---|---|---|---|---|
| `read-postgres` | Read patient records straight from Postgres | `attacker` | `postgres` | succeeds | succeeds | blocked | blocked | succeeds |
| `postgres-from-billing` | Read patient records from a compromised billing pod | `billing` | `postgres` | succeeds | succeeds | blocked | blocked | succeeds |
| `no-identity-records` | Call records-api with no identity | `attacker` | `records-api` | succeeds | blocked | blocked | succeeds | blocked |
| `cross-namespace-billing` | Reach billing from another namespace | `attacker` | `billing` | succeeds | blocked | blocked | succeeds | succeeds |
| `mcp-no-identity` | Call the MCP server with no identity | `attacker` | `records-mcp` | succeeds | blocked | blocked | succeeds | blocked |
| `forged-identity` | Pretend to be the web app with a forged certificate | `attacker` | `records-api` | succeeds | blocked | blocked | succeeds | blocked |
| `forged-user-header` | Claim to be a clinician with a header | `attacker` | `records-api` | succeeds | blocked | blocked | succeeds | blocked |
| `wrong-audience-token` | Present a real token meant for another service | `attacker` | `records-api` | succeeds | blocked | blocked | succeeds | blocked |
| `agent-prompt-injection` | Let an agent summarise a poisoned record | `attacker` | `records-mcp` | succeeds | succeeds | succeeds | succeeds | blocked |

The matrix test in `web/e2e/matrix.spec.ts` runs every attack at ten settings (all off, mTLS audit, mTLS enforce, network only, mTLS with network, secrets only, user audit, user enforce, and two combinations that enforce the user layer alongside the others) and checks each result against this table. Audit never blocks, so a user audit row expects the same results as everything off.

## Outcomes

An attack ends in one of two outcomes: `succeeds`, meaning the attacker got what it wanted, or `blocked`. Which layer blocked it is worked out by the observer: the runner tags every request with one trace id, and the layer of the first `deny` event with that trace is reported as `stopped by`. A refusal at the TLS handshake has no request and so no event. A dropped connection has none either, so when the network layer is enforced and the attack failed while connecting to a service it covers, the result says `network (inferred)`. A rejected database password with the secrets layer enforced says `secrets (inferred)` for the same reason. The attack's detail records the `phase` that failed: `connect`, `handshake`, `auth` (the database refused the password) or `request`.

## Details

`read-postgres`
: Logs in to Postgres as `clinic` with the shared static password and counts the rows. This is the leaked-password attack: the secrets layer revokes that password, so the attack is blocked when the layer is enforced and succeeds when it is off or in audit.

`postgres-from-billing`
: The same attack, run from inside the `billing` pod, which holds a copy of the leaked password just as the attacker pod does. It stands for an attacker who has code execution in a pod that belongs to the clinic. Only `records-api` is allowed to reach Postgres once the network layer is on. With the secrets layer enforced it fails at the password instead, because the shared password has been revoked.

`no-identity-records`
: Calls `GET /patients` on `records-api` with no credential.

`cross-namespace-billing`
: Calls `GET /invoices` on `billing` from the `attacker` namespace.

`mcp-no-identity`
: Connects to `records-mcp` and calls `list_patients`.

`forged-identity`
: Connects to `records-api` on port 8443 with a self-signed certificate that names itself `spiffe://playground.local/ns/clinic/sa/web`, then asks for every patient. With mTLS off the server asks for no certificate, so the claim is never examined. In `audit` and `enforce` the server checks the certificate against the SPIRE bundle and drops the connection during the handshake. That refusal happens before any request exists, so it has no trace id and no event, and audit mode cannot log it. `make attack` reports it as blocked with no layer named.

`agent-prompt-injection`
: Plants a decoy patient and a poisoned note through the public form, then does what a user does: calls `POST /api/agent/summarise` on `web`, the same call as the **Summarise with AI** button. The web app calls the agent, which reads the records through the MCP tools. It checks whether the decoy was deleted, and removes both. See [Agents and MCP](../agents-and-mcp.md).

`forged-user-header`
: Calls `GET /patients` on `records-api` with no token and an `X-User: aisha` header. With the user layer off, `records-api` believes the header and logs who it claimed to be. In `audit` the header is not believed, and the request is logged as `would_deny`. In `enforce` it gets a 401. See [Turn on the user layer](../the-user-layer.md).

`wrong-audience-token`
: Signs in as `aisha` through `attacker-cli`, a deliberately weak client that accepts a password directly, and sends the token to `records-api`. The token is genuine, but its audience is `billing`, so `records-api` refuses it when the user layer is enforced.

The prompt-injection attack is blocked by the user layer for a narrow reason. The simulated attacker has no account, so under `user=enforce` the form it plants its text through needs a signed-in user and refuses it. A signed-in clinician who plants the same text is not stopped, because the agent passes that clinician's token along unchanged. [Break the user layer](../how-to/break-the-user-layer.md) shows both sides.

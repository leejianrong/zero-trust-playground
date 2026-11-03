# Attacks

The attack runner lives in `services/clinic/clinic/attacks/` and runs from the `attacker` pod. Each attack is listed in `catalog.json` with a default outcome and rules that change it for a layer mode. Run one with `make attack A=<name>`. The output names the layer modes, the expected outcome, whether the result matched, and, for a blocked attack, which layer stopped it.

| Name | Title | Target | Layers off | mTLS enforced |
|---|---|---|---|---|
| `read-postgres` | Read patient records straight from Postgres | `postgres` | succeeds | succeeds |
| `no-identity-records` | Call records-api with no identity | `records-api` | succeeds | blocked |
| `cross-namespace-billing` | Reach billing from another namespace | `billing` | succeeds | blocked |
| `mcp-no-identity` | Call the MCP server with no identity | `records-mcp` | succeeds | blocked |
| `forged-identity` | Pretend to be the web app with a forged certificate | `records-api` | succeeds | blocked |
| `agent-prompt-injection` | Let an agent summarise a poisoned record | `records-mcp` | succeeds | succeeds |

## Outcomes

An attack ends in one of two outcomes: `succeeds`, meaning the attacker got what it wanted, or `blocked`. Which layer blocked it is worked out by the observer: the runner tags every request with one trace id, and the layer of the first `deny` event with that trace is reported as `stopped by`. A refusal at the TLS handshake has no request and so no event.

## Details

`read-postgres`
: Logs in to Postgres as `clinic` with the shared static password and counts the rows.

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

# Attacks

The attack runner lives in `services/clinic/clinic/attacks/` and runs from the `attacker` pod. Each attack is listed in `catalog.json` with the outcome it should have for each combination of layers. So far only the baseline, every layer off, exists.

| Name | Title | Target | With no layers |
|---|---|---|---|
| `read-postgres` | Read patient records straight from Postgres | `postgres` | succeeds |
| `no-identity-records` | Call records-api with no identity | `records-api` | succeeds |
| `cross-namespace-billing` | Reach billing from another namespace | `billing` | succeeds |
| `mcp-no-identity` | Call the MCP server with no identity | `records-mcp` | succeeds |
| `agent-prompt-injection` | Let an agent summarise a poisoned record | `records-mcp` | succeeds |

## Outcomes

An attack ends in one of two outcomes: `succeeds`, meaning the attacker got what it wanted, or `blocked`. Which layer blocked it is worked out from the events and not guessed by the attack.

## Details

`read-postgres`
: Logs in to Postgres as `clinic` with the shared static password and counts the rows.

`no-identity-records`
: Calls `GET /patients` on `records-api` with no credential.

`cross-namespace-billing`
: Calls `GET /invoices` on `billing` from the `attacker` namespace.

`mcp-no-identity`
: Connects to `records-mcp` and calls `list_patients`.

`agent-prompt-injection`
: Plants a decoy patient and a poisoned note through the public form, runs the simulated agent, checks whether the decoy was deleted, and removes both. See [Agents and MCP](../agents-and-mcp.md).

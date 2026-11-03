# ADR-0008: Agents reach the clinic app through an MCP server, driven by a scripted agent

- Status: Accepted
- Date: 2026-11-03
- Deciders: user, agent

## Context

The user wants to show a third kind of client next to browsers and attacker pods: an agent asking the app for information over MCP. This is where layered zero trust gets hard, because an agent acts for a person, reads untrusted text, and can be talked into calling tools it should not. agent-auth-lab already settled how to make agent behaviour testable (its ADR-0005: a deterministic scripted runner by default).

## Decision

- `records-mcp` is an MCP server in the `clinic` namespace using the Python MCP SDK over streamable HTTP. It exposes four tools: `list_patients`, `get_patient`, `update_patient` and `delete_patient`. It calls `records-api` as an ordinary workload, so it appears on the Topology like any other service.
- The `agent` is a separate workload in its own namespace `agents`. It is scripted and deterministic. Its "naive" mode follows any line in a tool result that begins with `ASSISTANT INSTRUCTION:`, which stands in for a model that obeys injected text. This is labelled as a simulation everywhere it appears.
- Because the server speaks standard MCP, a real client (Claude Code, for example) can be pointed at it. That is an optional exercise, not part of the tests.
- Baseline attacks added to the catalogue: `mcp-no-identity` (call the MCP server directly and list every patient) and `agent-prompt-injection` (plant a poisoned record, run the agent, see it delete a decoy).
- Later layers fix them: a SPIFFE ID for `records-mcp` and for the agent (V3), network limits (V4), a delegated user token and per-tool scopes (V6b, mirroring agent-auth-lab labs 07 to 11).

## Alternatives considered

| Option | Why not |
|--------|---------|
| Real LLM agent in the tests | Non-deterministic, costs money, and cannot be asserted in an attack matrix. |
| Agent calls `records-api` directly, no MCP | Misses the thing the user asked about, and the tool-surface problem is specific to MCP. |
| Reuse agent-auth-lab's Lab IdP and agents | ADR-0006 keeps the two projects separate. |

## Consequences

- The naive agent is a model of a failure, not a measurement of any real model. The docs must say so.
- The injection attack is destructive by design, so it only deletes a decoy record it plants itself and cleans up after.
- Two more workloads (`records-mcp`, `agent`) add roughly 150 MB. Memory is re-checked at the end of V2b.

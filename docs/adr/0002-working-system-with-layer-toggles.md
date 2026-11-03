# ADR-0002: A working system you attack, with each security layer switchable

- Status: Accepted
- Date: 2026-11-03
- Deciders: user, agent

## Context

The goal is understanding. Zero trust is defence in depth: each layer exists because another layer can fail. The clearest way to see that is to run the same attack with a layer on and with it off. agent-auth-lab uses starter/solution folders with a deliberate gap per lab. That suits "implement this function" learning and fits conceptual layers badly, because the interesting thing is the interaction between layers, not any one function.

## Decision

The playground ships as a finished, working system. There are no starter/solution pairs and no code to complete. Learning happens through:

1. **Layer modes.** Each layer (workload identity, mTLS authorisation, network policy, secrets, user identity) has a mode of `off`, `audit` or `enforce`. The dashboard flips them (ADR-0005).
2. **Attack scenarios.** A fixed catalogue of named attacks run from the `attacker` pod (or a stolen credential) and report which layer stopped them, or that nothing did.
3. **Break-it experiments.** Short written exercises per slice ("delete this registration entry, predict what `billing` sees, then check").

Each slice adds a layer and its attacks. A slice is done when an attack that succeeded before is stopped, and the dashboard shows why.

## Alternatives considered

| Option | Why not |
|--------|---------|
| agent-auth-lab style starter/solution | Needs a generator and a self-check per lab. Teaches how to write code, not how layers combine. |
| Read-only reference deployment | Nothing to poke. Passive reading is what the pattern's own docs already offer. |
| Everything on from the start | You never see what each layer buys. |

## Consequences

- Every layer needs a real `off` mode that reproduces the vulnerable behaviour. That is extra work per layer and the main cost of this ADR.
- Intentionally weak configurations exist. They are labelled, localhost-only and always paired with the fix, as in agent-auth-lab's ADR-0008.
- Acceptance tests are attack-matrix tests: attack × layer-mode → expected outcome.

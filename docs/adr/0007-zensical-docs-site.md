# ADR-0007: Publish a Zensical tutorial site; supersedes the "no docs site" part of ADR-0006

- Status: Accepted
- Date: 2026-11-03
- Deciders: user, agent

## Context

ADR-0006 and decision Q5 said the docs would be Markdown in the repo with no site. The user has since asked for a Zensical docs page, and the playground is a teaching tool, so a readable tutorial matters as much as the cluster. agent-auth-lab already does this (its ADR-0009), and `dev-playbook` documents the setup.

## Decision

- The tutorial lives in `docs/tutorial/` as Zensical source, with `zensical.toml` at the repo root. `docs/adr/` stays for planning decisions and is not published.
- A GitHub Actions workflow builds on every pull request and deploys to GitHub Pages from `main`.
- Each slice ships its tutorial page in the same pull request as the code. A slice is not done until its page exists and its commands have been run as written.
- Pages follow the Diataxis split from `software-docs-writer`: a tutorial per layer, a how-to for each break-it exercise, one reference page per component, and one explanation page per concept.
- Prose follows `natural-writing`.

## Alternatives considered

| Option | Why not |
|--------|---------|
| README only | Stops working once there are six slices, three dashboards and an agent. |
| mkdocs-material | Zensical is its successor, and agent-auth-lab already uses Zensical. |
| Docs inside the dashboard | Duplicates a docs tool badly, and the docs must be readable without a running cluster. |

## Consequences

- One more thing to keep true. The tutorial's commands drift unless a test runs them, so each tutorial page's commands are covered by the matching slice's end-to-end test where practical.
- Pages for slices V1 and V2 are written retroactively in the V2b slice.

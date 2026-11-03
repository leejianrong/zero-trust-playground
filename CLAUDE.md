# Zero Trust Playground

A k3d cluster plus a toy clinic app and a dashboard, for learning the Layered Zero Trust pattern by attacking it. Read `PLAN.md`, then `docs/adr/`, then `SLICES.md`. `QUESTIONS.md` is the decision register.

## Status

Slices V1 (SPIRE identity), V2 (unprotected clinic app and attacker; attacks run with `make attack`) and V2b (MCP server, simulated agent, Headlamp, Explore view, docs site) are built. V3 (mTLS layers, layer modes, Layers and Architecture views) is built. V4 (network policy) is next. Trust the code over the docs where they disagree, and fix the doc. Board: Pandan `AAL` (epics AAL-E6 to E13).

## Commands

- `make up` / `make down`: create or delete cluster `ztp` with SPIRE
- `make status`: pods and memory
- `make echo`: build and deploy the V1 spike workloads
- `make clinic`: build and deploy web, records-api, billing, postgres and the attacker pod
- `make attack A=<name>`: run an attack from the attacker pod via the observer (no `A` lists them)
- `make web`: port-forward the clinic app to http://localhost:8081 (a real CRUD page: list, add, edit, delete patients)
- `make headlamp` / `make headlamp-ui` / `make headlamp-token`: the cluster dashboard (read-only token; `ROLE=admin` for the contrast). Never print or log the token.
- `make docs` / `make docs-build`: the Zensical tutorial in `docs/tutorial/` (a page per slice ships with the slice; `scripts/check_docs_commands.py` fails on unknown make targets)
- `make observer`: run the observer on :8765 (host process; reads the cluster via kubectl)
- `make test`: no-infra tests, lint, type-check (the pre-push gate; `make hooks` installs it)
- `make e2e`: Playwright against the live cluster (CI only by default)
- Dashboard dev: `cd web && npm run dev` (proxies /events to the observer)

Versions of every chart and image live in `versions.env`.

## Conventions

- Branch per slice off fresh `main`, land by PR after checks pass. No direct pushes to `main` once CI exists.
- Smallest diff that meets the slice's done-condition. Delete what a change supersedes. Report net lines in PR text. Skill: `lean-code`.
- Tests are layered by cost (`dev-playbook`): no-infra tests run locally and in CI, anything needing the cluster runs in CI only.
- Every bug becomes a test. Every denial the playground demonstrates is asserted by an attack-matrix test.
- Python 3.12 + FastAPI + `uv`; Svelte + Vite + TypeScript for the UI (ADR-0004, ADR-0006). Use `frontend-design` for UI work.
- Prose (README, ADRs, handouts): invoke `natural-writing` first.
- Deliberately weak configs (layers off) stay labelled and localhost-only.

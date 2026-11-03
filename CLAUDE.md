# Zero Trust Playground

A k3d cluster plus a toy clinic app and a dashboard, for learning the Layered Zero Trust pattern by attacking it. Read `PLAN.md`, then `docs/adr/`, then `SLICES.md`. `QUESTIONS.md` is the decision register.

## Status

Slice V1 (SPIRE identity + Identity view) is in progress. Trust the code over the docs where they disagree, and fix the doc. Board: Pandan `AAL` (epics AAL-E6 to E13).

## Commands

- `make up` / `make down`: create or delete cluster `ztp` with SPIRE
- `make status`: pods and memory
- `make echo`: build and deploy the V1 spike workloads

Versions of every chart and image live in `versions.env`.

## Conventions

- Branch per slice off fresh `main`, land by PR after checks pass. No direct pushes to `main` once CI exists.
- Smallest diff that meets the slice's done-condition. Delete what a change supersedes. Report net lines in PR text. Skill: `lean-code`.
- Tests are layered by cost (`dev-playbook`): no-infra tests run locally and in CI, anything needing the cluster runs in CI only.
- Every bug becomes a test. Every denial the playground demonstrates is asserted by an attack-matrix test.
- Python 3.12 + FastAPI + `uv`; Svelte + Vite + TypeScript for the UI (ADR-0004, ADR-0006). Use `frontend-design` for UI work.
- Prose (README, ADRs, handouts): invoke `natural-writing` first.
- Deliberately weak configs (layers off) stay labelled and localhost-only.

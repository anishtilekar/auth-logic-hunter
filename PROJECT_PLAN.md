# Neurosymbolic Auth-Logic Hunter — Project Plan

AI-powered tool that finds multi-step and race-condition authorization/business-logic bugs and proves each finding mathematically with Z3, instead of reporting an LLM's guess. Full background: capstone synopsis (Word doc) + the original project brief in this session's memory. This file is the single source of truth for **what phase we're on and what's been built** — read the STATUS block first in any new session, then only dig into the phase detail you need.

---

## STATUS

**Current phase:** Phase 1 — Target app standup (crAPI)
**Last updated:** 2026-09-01
**Repo:** [anishtilekar/auth-logic-hunter](https://github.com/anishtilekar/auth-logic-hunter) (private)

| Phase | Name | Status |
|---|---|---|
| 0 | Project scaffolding & infra | ✅ Done |
| 1 | Target app standup (crAPI) | ⬜ Not started |
| 2 | State-Model Builder (Stage 1) | ⬜ Not started |
| 3 | Backend + frontend skeleton (full-stack vertical slice) | ⬜ Not started |
| 4 | Invariant Extractor (Stage 2) | ⬜ Not started |
| 5 | Hypothesis Generator — sequential (Stage 3) | ⬜ Not started |
| 6 | Symbolic Encoder + Z3 Solver (Stages 4–5) | ⬜ Not started |
| 7 | Race-condition extension | ⬜ Not started |
| 8 | Replay/PoC Engine (Stage 6) | ⬜ Not started |
| 9 | Frontend polish & full dashboard | ⬜ Not started |
| 10 | CLI + GitHub Action wrapper | ⬜ Not started |
| 11 | Evaluation vs. baselines | ⬜ Not started |
| 12 | Writeup, demo, final polish | ⬜ Not started |

**How to update this file:** when a phase finishes, flip its row to ✅, fill in the "What's actually built" note under that phase's section (below), update `Current phase`, and commit this file *in the same commit* as the phase's code. Don't let this file's STATUS block drift from what's actually in the repo — if in doubt, `git log --oneline` and reconcile before trusting old notes here.

---

## Team & Roles

| Person | Owns |
|---|---|
| Anish Tilekar | LLM pipeline — Invariant Extractor (Stage 2), Hypothesis Generator (Stage 3), prompt design |
| Harshada Deshmukh | Code/API analysis — State-Model Builder (Stage 1), target-app integration, replay engine |
| Vijay Talsangi | Formal verification — Symbolic Encoder + Z3 (Stages 4–5), race-condition SMT encoding |
| Sakshi Sharma | Frontend/dashboard, system integration, UI/system design, seeded test targets |

Phases aren't strictly serial per person — e.g. Sakshi can be building the frontend shell in Phase 3 while Anish starts Phase 4 prompts, as long as the API contract between them is agreed first. Each phase's "Depends on" line says what must be *merged* before that phase can finish, not before it can start.

---

## Tech Stack

Chosen for what's current and well-supported as of now. Pin exact versions when you actually scaffold (Phase 0) — take whatever `uv add` / `npm create vite@latest` resolve to at that time rather than hardcoding versions here.

| Layer | Choice | Why |
|---|---|---|
| Backend language | Python 3.12+ | Matches tree-sitter/Joern/z3-solver ecosystem; CPU-only, no GPU dependency anywhere |
| Package manager (Python) | `uv` | Fast, single lockfile, replaces pip+venv+poetry |
| Backend API framework | FastAPI (async) | Native async, WebSocket support for live run progress, pairs with httpx/asyncio already in the stack |
| ORM / DB | SQLAlchemy 2.0 (async) + Alembic migrations, PostgreSQL | Already specified in the brief; stores runs, findings, invariants, hypotheses |
| LLM provider | Claude Sonnet 5 (`claude-sonnet-5`) via Anthropic SDK | Confirmed decision — see memory. Use `strict: true` structured tool output for invariants/hypotheses so they're reliably machine-parseable, not prompted-JSON. Consider Opus 5 specifically for Stage 2 (Invariant Extraction) — proposed, not finalized. |
| Static/code analysis | tree-sitter, Joern | Per brief — parsing crAPI's JS/Python/Java services |
| Symbolic encoding | Custom Python → SMT-LIB | Own code, not a library — this is the core novel contribution |
| Solver | `z3-solver` (Python bindings) | CPU-only, fast |
| Replay client | `httpx` + `asyncio` | Precise timing control needed for race replay |
| CLI | Typer | Nicer DX than raw Click, still Click-compatible under the hood |
| Containerization | Docker + Docker Compose | Postgres + backend services; crAPI brought in as its own vendored compose stack |
| Backend lint/type/test | ruff (lint+format), mypy, pytest + pytest-asyncio | Standard modern Python toolchain |
| **Frontend framework** | React 19 + Vite + TypeScript | SPA is all that's needed (no SSR/SEO requirement) — hits the FastAPI backend directly, runs on localhost |
| UI components | shadcn/ui (Radix + Tailwind CSS) | Fast to build a clean, accessible, modern dashboard without hand-rolling components |
| Styling | Tailwind CSS | Pairs with shadcn/ui |
| Server state / data fetching | TanStack Query v5 | Caching, refetching, run-status polling |
| Routing | React Router v7 | Current standard |
| Live updates | Native WebSocket client → FastAPI WS endpoint | Streams pipeline stage events (model built → invariants → hypothesis queue → SAT/UNSAT → replay result) into the UI live, similar in spirit to Strix's live agent-graph view |
| Charts | Recharts | Severity breakdown, findings-over-time on the dashboard |
| Frontend lint/type/test | `oxlint` (Rust-based, what `create-vite` now scaffolds by default as of this project's setup — faster than ESLint, kept as-is rather than swapped), `tsc -b`, Vitest + React Testing Library (tests not yet added) | Current default tooling |
| CI | GitHub Actions | Separate backend/frontend jobs — lint, type-check, test on every push |

**Running on localhost (end state):** `docker compose up -d` brings up Postgres + the FastAPI backend (+ crAPI's own compose stack for the target app); `npm run dev` in `/frontend` serves the dashboard on Vite's dev server hitting the backend. Documented properly in Phase 9.

---

## Repository Structure (proposed)

```
/backend
  /pipeline
    stage1_state_model/
    stage2_invariants/
    stage3_hypotheses/
    stage4_encoder/
    stage5_solver/
    stage6_replay/
  /api            # FastAPI app, routers, WebSocket endpoint
  /db             # SQLAlchemy models, Alembic migrations
  /cli            # Typer CLI entrypoint
  pyproject.toml
/frontend
  /src
    /pages        # Dashboard, RunDetail, NewRun
    /components
    /lib          # API client, WS hook
  package.json
/targets
  /crapi          # vendored/submoduled OWASP crAPI
  /seeded-race     # custom Spring Boot service(s) with planted race-condition bugs (Phase 7)
/docker
  docker-compose.yml
/.github/workflows
  ci.yml
PROJECT_PLAN.md    # this file
```

---

## Cross-Cutting Conventions

- **Commit convention:** Conventional Commits style — `feat(stage1): extract per-resource state machine from OpenAPI spec`, `chore(infra): scaffold docker-compose`, etc. One commit (or small tight series) per phase, pushed to `main` or merged from a phase branch — team's call, but keep phases as clean, working checkpoints in history.
- **Definition of Done, every phase:** tests pass locally, CI is green, this file's STATUS block and the phase's own notes section are updated, code is committed and pushed to GitHub.
- **Secrets:** `ANTHROPIC_API_KEY` via `.env` (gitignored), never committed. Add `.env.example` with the variable names but no values.
- **Branching:** keep it simple given team size — either commit straight to `main` per phase, or one short-lived branch per phase merged via PR if you want the GitHub Actions checks to gate the merge. Decide in Phase 0 and note it in this file.
- **Token efficiency, always:** every LLM call the pipeline itself makes (Stage 2 Invariant Extraction, Stage 3 Hypothesis Generation, and the counterexample feedback loop) must be designed to use tokens optimally — this is a standing rule for all pipeline code, not a one-time optimization pass. In practice: keep prompts and structured-output schemas terse (output tokens cost 5x input on Sonnet 5, so verbose responses are where the money actually goes — see the per-run cost estimate in project memory); put the large static context (app model, invariants) first and byte-identical across calls within a run so prompt caching actually hits; don't re-send context that's already cached; avoid asking the model to restate input it was just given; and default new prompts to the minimum output verbosity that still satisfies the structured schema. Apply this same discipline to code Claude Code itself generates while building this project — no unnecessary boilerplate, no restating context back to the user in code comments, no verbose scaffolding beyond what a task actually needs.

---

## Open Questions / Risks (resolve early, don't let these silently block a phase)

1. **GitHub repo not yet created.** Need: repo name, visibility (public/private — a private repo is probably right until submission), and which account/org owns it. Resolve at the start of Phase 0.
2. **Scope vs. hours tension:** the original brief scoped the dashboard as "secondary/demo-only, don't over-invest." This plan now includes a full production-quality frontend per your instruction, which is real additional hours on top of the ~450-hour budget the brief assumed (that figure was also computed for a 3-person team before Sakshi's role was confirmed). Recommend tracking actual hours spent from Phase 0 onward and revisiting scope (e.g. trimming the Juice Shop evaluation, or the CI/CD GitHub Action packaging in Phase 10) if the frontend is eating more than expected.
3. **crAPI has no built-in race conditions.** Phase 7 depends on a seeded target (custom Spring Boot service or a modified crAPI) that doesn't exist yet — needs to be built, not just configured.
4. **Sonnet 5 vs. hybrid Opus 5/Sonnet 5 split** for Stage 2 vs. Stage 3 — proposed but not finalized. Decide by Phase 4.
5. **Strix comparison row** was discussed as worth adding to the synopsis's comparison table but hasn't been added yet — separate from this build plan, but don't forget it.

---

## Phase 0 — Project Scaffolding & Infrastructure

**Goal:** empty repo → a running skeleton with CI green, before any pipeline logic exists.
**Depends on:** nothing.
**Owner:** whole team (can be split: Sakshi+Anish do the scaffolding scripts, everyone reviews).

Tasks:
- [x] Resolve Open Question #1 — repo is `anishtilekar/auth-logic-hunter`, private. `git init`, GitHub repo created via `gh repo create`, remote set.
- [x] `.gitignore` (Python, Node, `.env`, Docker volumes, `__pycache__`, `node_modules`, etc.)
- [x] `/backend`: `uv init` (src layout, package `app`), `pyproject.toml` with ruff/mypy/pytest config, minimal FastAPI app (`GET /health`) — verified locally: `uv run pytest`/`ruff check`/`mypy` all pass, server boots and serves `/health`
- [x] `/frontend`: `npm create vite@latest` (React 19 + TS + Vite 8 template), Tailwind v4 + shadcn/ui (Nova preset, radix base) installed, `Dashboard` page that calls `/api/health` through the dev-server proxy — verified end-to-end live (frontend → proxy → backend → `{"status":"ok"}` rendered as a badge)
- [x] `/docker/docker-compose.yml`: Postgres 17 + backend service (with a `Dockerfile` for the backend); frontend stays `npm run dev`, not containerized
- [x] `.github/workflows/ci.yml`: backend job (`uv sync`, `ruff check`, `mypy`, `pytest`), frontend job (`npm ci`, `oxlint`, `vite build` — build runs `tsc -b` first)
- [ ] Pre-commit hooks (ruff, oxlint/prettier) — deferred, not done in Phase 0
- [x] Root `README.md`: project description, link to this plan, quickstart
- [x] Branching convention: committing straight to `main` per phase (small team, CI gates every push anyway) — recorded here since this is where Phase 0 said to record it
- [x] Commit, push — CI status not yet confirmed on GitHub's side (verify the Actions run is green after this commit lands)

**What's actually built:** Full monorepo skeleton exists and is verified working locally: `/backend` (FastAPI on Python 3.14 via `uv`, `/health` endpoint, ruff+mypy+pytest all clean), `/frontend` (React 19/Vite 8/TypeScript, Tailwind v4, shadcn/ui with the Nova preset already themed light+dark, a Dashboard page proving the dev-server proxy reaches the backend live), `/docker/docker-compose.yml` (Postgres + backend, not yet actually run via `docker compose up` since Docker Desktop wasn't running during this phase — config is written but untested end-to-end), and `.github/workflows/ci.yml` covering both sides. One deviation from the original plan: the Vite scaffold defaults to `oxlint` instead of ESLint now — kept it rather than swapping, since it's strictly faster and does the same job. Pre-commit hooks were skipped (optional, CI already gates everything). Not yet done: actually starting Docker Compose to confirm the backend container + Postgres come up together (do this at the start of Phase 1, since crAPI standup needs Docker running anyway).

---

## Phase 1 — Target App Standup (OWASP crAPI)

**Goal:** crAPI running locally via Docker, its OpenAPI spec reachable, state resettable between pipeline runs.
**Depends on:** Phase 0 (docker-compose skeleton exists).
**Owner:** Harshada (+ Vijay for docker help).

Tasks:
- [ ] Vendor crAPI under `/targets/crapi` (git submodule, or a documented pinned-commit copy)
- [ ] Get crAPI's own docker-compose stack running alongside the project's compose file (decide: separate `docker compose -f` invocation vs. merged network — document whichever you pick)
- [ ] Confirm OpenAPI spec is reachable at a known local URL
- [ ] Write a reset script/seed data plan so repeated pipeline runs start from a known state
- [ ] Document exact startup steps in `/targets/crapi/README.md`
- [ ] Commit, push

**What's actually built:** *(fill in when done)*

---

## Phase 2 — State-Model Builder (Stage 1)

**Goal:** given crAPI's source + OpenAPI spec, produce a structured "Application Model" — resources, ownership, endpoints, state transitions — as a typed (Pydantic) artifact.
**Depends on:** Phase 1 (need the target to parse).
**Owner:** Harshada.

Tasks:
- [ ] Define the Application Model schema (Pydantic models: Resource, Endpoint, StateTransition, OwnershipRelation)
- [ ] tree-sitter/Joern-based parsing of crAPI's services (Node.js community service, Python/Flask identity service, Java/Kotlin workshop service)
- [ ] OpenAPI spec parser feeding endpoint/parameter data into the same model
- [ ] Unit tests validating extracted model against crAPI's known real structure (hand-verify a handful of resources/endpoints)
- [ ] `backend/cli`: `authhunter build-model --target ./targets/crapi` → writes the model as JSON
- [ ] Commit, push

**What's actually built:** *(fill in when done)*

---

## Phase 3 — Backend API Skeleton + Frontend Skeleton (full-stack vertical slice)

**Goal:** prove the whole stack end-to-end on the simplest possible slice — frontend triggers a run, backend executes Stage 1, result flows back and renders — before adding pipeline complexity. This is the phase that de-risks integration.
**Depends on:** Phase 2 (Stage 1 must exist to have something to call).
**Owner:** Sakshi (API wiring + frontend), Anish/Vijay define API contract with her.

Tasks:
- [ ] SQLAlchemy models: `Run`, `Finding`, `Invariant`, `Hypothesis` (fields for the later stages can be stubbed now)
- [ ] Alembic migration, wire Postgres via docker-compose
- [ ] FastAPI: `POST /runs` (kicks off a run, currently just Stage 1), `GET /runs/{id}`, `GET /runs`, WebSocket `/runs/{id}/events`
- [ ] Frontend pages: Dashboard (list runs), New Run form, Run Detail (shows live status via WS, renders the Stage 1 model once done)
- [ ] `lib/apiClient.ts` + WS hook in frontend
- [ ] End-to-end manual test: start a run from the UI, watch it hit Stage 1, see the extracted model rendered
- [ ] Commit, push

**What's actually built:** *(fill in when done)*

---

## Phase 4 — Invariant Extractor (Stage 2)

**Goal:** Claude Sonnet 5 reads the state model + relevant source, proposes security invariants, forced into a strict structured schema (not prose).
**Depends on:** Phase 3 (need the run pipeline + a place to display results).
**Owner:** Anish.

Tasks:
- [ ] Anthropic SDK integration, `ANTHROPIC_API_KEY` via `.env`
- [ ] Pydantic `SecurityInvariant` schema (e.g. `∀ order, user: payOrder(user, order) requires user == order.owner`, structured not string)
- [ ] Prompt design using `strict: true` tool schema so output always validates
- [ ] Unit tests with mocked LLM responses (don't spend money in CI); one manual live integration run against crAPI
- [ ] Decide Open Question #4 (Sonnet 5 alone vs. Opus 5 for this stage specifically) and record the decision here
- [ ] Wire into API + frontend: Run Detail shows extracted invariants
- [ ] Commit, push

**What's actually built:** *(fill in when done)*

---

## Phase 5 — Hypothesis Generator, Sequential Only (Stage 3)

**Goal:** first prove the mechanism with one hand-crafted hypothesis (no LLM), then automate sequential BOLA-style hypothesis generation with Claude.
**Depends on:** Phase 4 (need invariants to target).
**Owner:** Anish.

Tasks:
- [ ] `Hypothesis` schema: ordered request sequence, preconditions, target invariant, expected violation
- [ ] Hand-craft one sequential hypothesis manually against crAPI, confirm it can flow through to (stubbed) Stage 4/5 — validates the mechanism before automating it
- [ ] LLM-driven hypothesis generation: given app model + invariants, propose candidate sequential attack chains
- [ ] Wire into API + frontend: Run Detail shows the hypothesis queue
- [ ] Commit, push

**What's actually built:** *(fill in when done)*

---

## Phase 6 — Symbolic Encoder + Z3 Solver (Stages 4–5)

**Goal:** the actual proof engine — translate a hypothesis + its target invariant into SMT-LIB, solve with Z3, interpret SAT (concrete witness) / UNSAT (counterexample). This is the core novel contribution — test heavily.
**Depends on:** Phase 5 (need hypotheses to encode).
**Owner:** Vijay.

Tasks:
- [ ] Python → SMT-LIB translation layer over the Application Model's state transitions
- [ ] Z3 integration: solve, extract concrete witness on SAT, extract counterexample reason on UNSAT
- [ ] Counterexample feedback loop: UNSAT reason feeds back into Stage 3's next hypothesis round
- [ ] Test suite with hand-built cases of known SAT/UNSAT outcome — this is the safety net for the whole project's core claim, don't skimp here
- [ ] Wire into API + frontend: Run Detail shows SAT/UNSAT per hypothesis with the proof trace
- [ ] Commit, push

**What's actually built:** *(fill in when done)*

---

## Phase 7 — Race-Condition Extension

**Goal:** extend the whole pipeline to treat race conditions as a first-class hypothesis type — the project's sharpest novelty claim.
**Depends on:** Phase 6 (sequential proof pipeline must already work).
**Owner:** Vijay + Anish jointly.

Tasks:
- [ ] Extend SMT encoding with an interleaving/ordering variable so the solver checks every interleaving of a concurrent request pair
- [ ] Extend Hypothesis Generator to propose concurrent/race pairs
- [ ] Build the seeded race-condition target (`/targets/seeded-race` — custom Spring Boot service(s) with a planted double-redeem/double-spend bug), since crAPI has none (Open Question #3)
- [ ] Hand-crafted race hypothesis proven end-to-end first, then LLM-driven race hypothesis generation
- [ ] Commit, push

**What's actually built:** *(fill in when done)*

---

## Phase 8 — Replay / PoC Engine (Stage 6)

**Goal:** take a Z3-proven witness and actually fire it against a live target — sequential requests in order, race pairs with precise concurrent timing — to empirically confirm the mathematical proof.
**Depends on:** Phase 7 (need both sequential and race witnesses to replay).
**Owner:** Harshada (+ Vijay).

Tasks:
- [ ] `httpx` + `asyncio` replay client for sequential witnesses
- [ ] Precisely-timed concurrent firing for race witnesses (this is the trickiest part — needs real timing control, not just `asyncio.gather`)
- [ ] Capture request/response evidence per replay
- [ ] Wire into API + frontend: Findings show reproduction steps + captured evidence
- [ ] Commit, push

**What's actually built:** *(fill in when done)*

---

## Phase 9 — Frontend Polish & Full Dashboard

**Goal:** this is where "proper frontend, ready, running on localhost" actually gets finished — not just the functional skeleton from Phase 3.
**Depends on:** Phase 8 (all pipeline stages now produce real data to display).
**Owner:** Sakshi.

Tasks:
- [ ] Dashboard: run history, severity breakdown (Recharts), quick stats
- [ ] Run Detail: live per-stage progress (via WS), findings list with proof traces + replay evidence, expandable hypothesis queue
- [ ] Findings/report export (PDF or shareable HTML)
- [ ] Responsive layout, sensible empty/error/loading states
- [ ] Polish pass against a real UX bar (Strix's dashboard is a reasonable reference point for what "proper" looks like, not to copy but to benchmark against)
- [ ] Update root README with final "how to run this on localhost" steps
- [ ] Commit, push

**What's actually built:** *(fill in when done)*

---

## Phase 10 — CLI + GitHub Action Wrapper

**Goal:** the product-shape requirement from the brief — a CLI and CI-integrated GitHub Action, not just the dashboard.
**Depends on:** Phase 8 (full pipeline must work end-to-end).
**Owner:** Anish/Harshada.

Tasks:
- [ ] Typer CLI: `authhunter scan --target <repo>` runs the full pipeline headlessly
- [ ] Plain-language Markdown/HTML report generator (CLI-only path, no dashboard needed)
- [ ] Package a GitHub Action wrapping the CLI for PR-triggered scans
- [ ] Commit, push

**What's actually built:** *(fill in when done)*

---

## Phase 11 — Evaluation vs. Baselines

**Goal:** the numbers the synopsis/paper actually needs.
**Depends on:** Phase 10 (need the CLI for repeatable, scriptable runs).
**Owner:** whole team.

Tasks:
- [ ] Run against full crAPI + the seeded race-condition target
- [ ] Baseline 1: run NEO (`github.com/columbia/neo`) on the same targets
- [ ] Baseline 2: raw LLM agent, no solver, same bug classes
- [ ] Baseline 3: Semgrep/CodeQL default rules
- [ ] Collect precision/recall/false-positive metrics per tool; the headline number is true multi-step/race findings all three baselines miss, each with a proof + replayed PoC
- [ ] Commit results/scripts, push

**What's actually built:** *(fill in when done)*

---

## Phase 12 — Writeup, Demo, Final Polish

**Goal:** ship it.
**Depends on:** Phase 11.
**Owner:** whole team.

Tasks:
- [ ] Final report/paper writeup using the evaluation numbers
- [ ] Demo script rehearsed against the localhost setup
- [ ] README final pass — a stranger should be able to `git clone`, `docker compose up -d`, `npm run dev`, and see it work
- [ ] Tag a release
- [ ] Final commit, push

**What's actually built:** *(fill in when done)*

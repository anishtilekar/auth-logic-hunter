# Neurosymbolic Auth-Logic Hunter — Project Plan

AI-powered tool that finds multi-step and race-condition authorization/business-logic bugs and proves each finding mathematically with Z3, instead of reporting an LLM's guess. Full background: capstone synopsis (Word doc) + the original project brief in this session's memory. This file is the single source of truth for **what phase we're on and what's been built** — read the STATUS block first in any new session, then only dig into the phase detail you need.

---

## STATUS

**Current phase:** Phase 9 — Frontend Polish & Full Dashboard
**Last updated:** 2026-09-03
**Repo:** [anishtilekar/auth-logic-hunter](https://github.com/anishtilekar/auth-logic-hunter) (private)
**Resolved 2026-09-02 — closes the gap open since Phase 4:** a real live run against crAPI with `LLM_ENV=dev` (OpenRouter's free GLM 5.2) completed in ~11 seconds with 8 invariants and 6 hypotheses, both inspected in full and genuinely high quality — see "First successful live run" after Phase 5 for the details, including a hypothesis structurally identical to the hand-crafted BOLA example from Phase 5 that the model generated independently. Stage 2 and Stage 3's real output quality is no longer a leap of faith. **Still open, lower urgency now:** Together.ai's paid `prod` tier itself hasn't been tested with a real key yet — needed before an actual Phase 11 evaluation run, not before Phase 6.

| Phase | Name | Status |
|---|---|---|
| 0 | Project scaffolding & infra | ✅ Done |
| 1 | Target app standup (crAPI) | ✅ Done |
| 2 | State-Model Builder (Stage 1) | ✅ Done |
| 3 | Backend + frontend skeleton (full-stack vertical slice) | ✅ Done |
| 4 | Invariant Extractor (Stage 2) | ✅ Done (LLM output verified live 2026-09-02) |
| 5 | Hypothesis Generator, Sequential Only (Stage 3) | ✅ Done (LLM output verified live 2026-09-02) |
| 6 | Symbolic Encoder + Z3 Solver (Stages 4–5) | ✅ Done (API/frontend wiring not yet seen live — see Phase 6 note) |
| 7 | Race-condition extension | ✅ Done (seeded target's planted race reproduced live; LLM race generation not yet seen live) |
| 8 | Replay/PoC Engine (Stage 6) | ✅ Done (crAPI auth automation deferred — see note) |
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
| LLM provider | **Superseded 2026-09-02** — see "LLM provider switch" note right after Phase 5 below. Was Claude Sonnet 5 (Opus 5 for Stage 2) via Anthropic SDK; now Together.ai's DeepSeek V4 Pro (prod) / OpenRouter's free GLM 5.2 (dev), both via a shared OpenAI-compatible client using forced tool-calling for structured output. |
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
4. ~~Sonnet 5 vs. hybrid Opus 5/Sonnet 5 split for Stage 2 vs. Stage 3~~ — decided in Phase 4 (Opus 5 for Stage 2), then **fully superseded 2026-09-02**: both stages now use one model per environment (DeepSeek V4 Pro prod / GLM 5.2 free dev) instead of a per-stage Anthropic split. See the "LLM provider switch" note after Phase 5.
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
- [x] Commit, push — confirmed green on GitHub Actions (both `backend` and `frontend` jobs passed on the first push)

**What's actually built:** Full monorepo skeleton exists and is verified working locally: `/backend` (FastAPI on Python 3.14 via `uv`, `/health` endpoint, ruff+mypy+pytest all clean), `/frontend` (React 19/Vite 8/TypeScript, Tailwind v4, shadcn/ui with the Nova preset already themed light+dark, a Dashboard page proving the dev-server proxy reaches the backend live), `/docker/docker-compose.yml` (Postgres + backend, not yet actually run via `docker compose up` since Docker Desktop wasn't running during this phase — config is written but untested end-to-end), and `.github/workflows/ci.yml` covering both sides. One deviation from the original plan: the Vite scaffold defaults to `oxlint` instead of ESLint now — kept it rather than swapping, since it's strictly faster and does the same job. Pre-commit hooks were skipped (optional, CI already gates everything). Not yet done: actually starting Docker Compose to confirm the backend container + Postgres come up together (do this at the start of Phase 1, since crAPI standup needs Docker running anyway). CI confirmed green on GitHub itself, not just locally (both jobs passed on the first push, ~20s each).

---

## Phase 1 — Target App Standup (OWASP crAPI)

**Goal:** crAPI running locally via Docker, its OpenAPI spec reachable, state resettable between pipeline runs.
**Depends on:** Phase 0 (docker-compose skeleton exists).
**Owner:** Harshada (+ Vijay for docker help).

Tasks:
- [x] Vendor crAPI under `/targets/crapi` — git submodule, pinned to release tag `v1.1.6` (not tracking `develop`)
- [x] Get crAPI's own docker-compose stack running alongside the project's compose file — decided: **separate `docker compose -f` invocations**, not merged. Verified both stacks running simultaneously with no port conflicts (crAPI's internal `postgresdb` isn't exposed to the host, so no clash with our own Postgres on 5432).
- [x] Confirm OpenAPI spec is reachable — static file at `targets/crapi/openapi-spec/crapi-openapi-spec.json` (40 endpoints, `servers` already `http://localhost:8888`, zero rewriting needed) **and** live-verified: `curl http://localhost:8888/health` → 200, plus a real `POST /identity/api/auth/signup` call → `{"message":"User registered successfully!...","status":200}`
- [x] Write a reset script/seed data plan — `targets/crapi-reset.sh` (full wipe via `down -v`) for evaluation runs; documented the cheaper "sign up fresh throwaway users" approach for iterative dev in the README. Note: this lives at `targets/` level, *not* inside `targets/crapi/` — that directory is a git submodule (a clean pinned reference to the upstream repo), so our own docs/scripts stay outside it rather than mixed into someone else's tree.
- [x] Document exact startup steps in `/targets/README.md` (not inside the submodule — see note above)
- [x] Commit, push

**What's actually built:** crAPI is vendored, running, and verified working end-to-end via live HTTP calls (not just "containers report healthy"). Also closed out a Phase 0 loose end while Docker was being debugged: our own `docker/docker-compose.yml` (Postgres + backend) is now verified working too — found and fixed a real bug in `backend/Dockerfile` where the `CMD` used `uv run uvicorn ...`, which silently re-triggers `uv sync` *without* `--no-dev` on every container start, reinstalling ruff/mypy/etc. at runtime; fixed by calling `.venv/bin/uvicorn` directly. Both compose stacks (ours + crAPI's) run simultaneously with no conflicts.

Hit a real, non-trivial blocker along the way, worth recording in case it recurs: Docker Desktop crashed on every launch with `initializing Inference manager: listening on unix://...\Docker\run\dockerInference: The file cannot be accessed by the system.` — an orphaned AF_UNIX socket reparse point from an earlier abnormal exit, which Windows' socket driver held in a stuck "busy" state that no user-mode delete (`rm`, PowerShell `Remove-Item`, `cmd del`/`rd`, `fsutil reparsepoint delete`) could clear. Fixed via Docker Desktop's own "Reset to factory defaults" (cost nothing since no images/volumes existed yet on this install). If this recurs on a teammate's machine: factory-reset Docker Desktop, or reboot Windows (which also clears the stuck kernel-level socket reference), before assuming it's a "slow first launch."

---

## Phase 2 — State-Model Builder (Stage 1)

**Goal:** given crAPI's source + OpenAPI spec, produce a structured "Application Model" — resources, ownership, endpoints, state transitions — as a typed (Pydantic) artifact.
**Depends on:** Phase 1 (need the target to parse).
**Owner:** Harshada.

Tasks:
- [x] Define the Application Model schema — `Endpoint`, `Resource`, `StateTransition`, `ApplicationModel` (Pydantic) in `backend/src/app/pipeline/stage1_state_model/schema.py`
- [x] ~~tree-sitter/Joern-based parsing~~ — **scope correction, see note below**: crAPI's real stack is Kotlin/Spring (identity), Go (community), Python/Django (workshop), not the Node/Flask/Java the brief assumed. Used a lightweight regex-based ownership-evidence scanner instead of standing up tree-sitter grammars or Joern for 3 languages in one phase — a deliberate scope cut, not an oversight.
- [x] OpenAPI spec parser (`openapi_parser.py`) — infers resources/endpoints/CRUD-vs-action transitions from the spec via a two-pass heuristic (path-param-adjacent nouns first, then vocabulary matching for paramless endpoints)
- [x] Unit tests validating against crAPI's real structure (`backend/tests/pipeline/`) — 7 tests, all passing, including a regression anchor tied to a real vulnerability (see below)
- [x] `backend/cli`: `uv run authhunter build-model --target ../targets/crapi --out <path>` → writes the model as JSON (Typer; also added a `version` command since Typer collapses a single-command app and silently drops the subcommand name otherwise)
- [x] Commit, push

**What's actually built:** Stage 1 is a real, working pipeline stage — not a stub. `build_from_openapi()` parses crAPI's 40-endpoint spec into 25 resources with CRUD/action-classified transitions; `scan_ownership_evidence()` greps the corresponding service source for each BOLA-relevant resource (video/vehicle/post/order — the ones with a path-param id) and flags lines where the id and an ownership-related keyword appear near each other. `build_application_model()` orchestrates both into one `ApplicationModel`, exposed via `authhunter build-model`.

**Notable finding, not just plumbing:** the source scanner surfaced a genuine, live BOLA vulnerability in crAPI's own code — `workshop/crapi/shop/views.py:122`, `order = Order.objects.get(id=order_id)`, with no ownership filter at all (it later does `user = order.user` instead of checking the requester). This is real validation that Stage 1's signal is useful, not just structurally correct — it's exactly the kind of evidence Stage 2 (Phase 4) needs to hand the LLM. It's now a regression-anchored test (`test_source_scanner.py::test_order_scan_surfaces_the_known_bola_line`) — if this stops showing up, the heuristic broke.

**Two rounds of real bugs found and fixed while validating against actual output** (both by literally reading what the parser produced against known crAPI facts, not by inspection alone): (1) the resource-inference fallback classified every unmatched endpoint as `ACTION` regardless of HTTP verb, misclassifying plain `GET /products` — fixed to still branch on method when resource-matching fails. (2) the ownership-evidence id-param regex included a "stripped suffix" variant (`order_id` → bare `order`) meant to catch loose wording, but it matched Django's `.order_by()` and `OrderedDict` — removed; now matches only the exact id-param name.

**Known limitation, documented rather than silently accepted:** the `vehicle` resource's ownership scan returns 0 hits — the OpenAPI spec's declared path param `vehicleId` doesn't appear as that literal string anywhere in the actual Kotlin source (it likely resolves through a VIN or different internal name). This is an honest precision/recall gap in a regex-only heuristic; Stage 2's LLM is where real semantic matching picks up the slack. Not fixed further here — chasing it would be over-engineering a heuristic that's explicitly meant to be approximate.

Not yet wired: the API/frontend don't call this yet — that's explicitly Phase 3's job, not Phase 2's.

**Follow-up fix after first CI run:** the pipeline tests initially passed locally but errored on GitHub Actions — `actions/checkout` doesn't fetch submodule content by default, so `targets/crapi` existed as an empty directory in CI, and the tests' skip-guard checked directory existence (true even when empty) rather than actual file content. Fixed by adding `submodules: true` to the backend job's checkout step and hardening the guards to check for the real spec file. CI now genuinely runs these tests against real crAPI content, confirmed green.

---

## Phase 3 — Backend API Skeleton + Frontend Skeleton (full-stack vertical slice)

**Goal:** prove the whole stack end-to-end on the simplest possible slice — frontend triggers a run, backend executes Stage 1, result flows back and renders — before adding pipeline complexity. This is the phase that de-risks integration.
**Depends on:** Phase 2 (Stage 1 must exist to have something to call).
**Owner:** Sakshi (API wiring + frontend), Anish/Vijay define API contract with her.

Tasks:
- [x] SQLAlchemy models: `Run` (real fields), `Finding`/`Invariant`/`Hypothesis` (deliberate stubs — just `run_id` + a JSON `data` blob — their real shape lands in Phases 4/5/6)
- [x] Alembic (async) migration, wired against Postgres via docker-compose
- [x] FastAPI: `POST /runs`, `GET /runs`, `GET /runs/{id}`, WebSocket `/runs/{id}/events` — background execution via `BackgroundTasks` + an in-memory per-run event fan-out (single-process, no broker — revisit only if the pipeline ever needs multiple workers)
- [x] Frontend pages: Dashboard (run list + status badges), New Run (form), Run Detail (live status via WS + polling fallback, renders the full Stage 1 model — resources with ownership evidence, transitions)
- [x] `lib/apiClient.ts` (typed) + `useRunEvents` WS hook
- [x] End-to-end manual test — done in a real browser (Claude Browser tooling), not just curl: New Run → Start Run → live navigation to Run Detail → completed status → full model rendered, including the real BOLA evidence line from Phase 2 (`workshop\crapi\shop\views.py:122: order = Order.objects.get(id=order_id)`) actually visible in the UI. Console clean, no errors.
- [x] Commit, push

**What's actually built:** A genuine full-stack vertical slice, verified live end-to-end in a browser, not just unit-tested in isolation. `POST /runs` creates a row and schedules Stage 1 in the background; the frontend either watches it live over WebSocket or falls back to 1s polling (`refetchInterval`) — both paths were exercised and agree. The WS handler correctly handles the case where a run *already finished* by the time a client connects (sends the terminal status immediately and closes) — which is actually the common case here, since Stage 1 completes in milliseconds. Real multi-event live streaming (pending → running → completed as separate WS messages, not just an instant terminal state) will get its first genuine exercise once a slower stage exists (Phase 4's LLM calls).

**Three real environment/infra bugs hit and fixed, not glossed over:**
1. **Postgres port collision:** a native Windows PostgreSQL service was already listening on 5432, and `localhost:5432` was silently connecting to *that* instead of our Docker container — surfaced as a confusing `InvalidPasswordError` during the first Alembic run, not a connection-refused (which would've been obvious). Fixed by moving our compose stack's host-side Postgres port to 5433; container-internal traffic (backend → postgres) was never affected.
2. **Compose project-name collision:** both our `docker/docker-compose.yml` and crAPI's vendored one live in a directory literally named `docker`, so Compose defaulted both to the same project name and started reporting crAPI's containers as "orphans" of our project — one accidental `--remove-orphans` away from deleting an unrelated stack. Fixed by giving our compose file an explicit `name: auth-logic-hunter`.
3. **Stale Docker container shadowing native dev:** the Phase-0-era `backend` container was still running and bound to host port 8000 with an old image, silently intercepting requests meant for a freshly-started native `uv run uvicorn` process — `/health` worked (both builds have it) but `/runs` 404'd, which is what actually exposed it. Lesson recorded in this file: **stop the Docker `backend` service before native dev on the same port**, don't run both.

Also added ruff config fixes for two more idiomatic-but-flagged patterns (`fastapi.Depends`, same class of false-positive as `typer.Option` from Phase 2) and excluded `migrations/versions/*` (autogenerated, not meant for hand-authored style compliance) from linting.

---

## Phase 4 — Invariant Extractor (Stage 2)

**Goal:** Claude Sonnet 5 reads the state model + relevant source, proposes security invariants, forced into a strict structured schema (not prose).
**Depends on:** Phase 3 (need the run pipeline + a place to display results).
**Owner:** Anish.

Tasks:
- [x] Anthropic SDK integration (`anthropic` 1.3.0, httpx2-based) — `ANTHROPIC_API_KEY` via `.env` through `Settings`, same pattern as `DATABASE_URL`
- [x] Pydantic `SecurityInvariant` schema — `resource`, `endpoint_keys`, `kind` (ownership/role_required/state_precondition), `statement`, `rationale`, `confidence`. Structured fields are strict; `statement`/`rationale` stay prose since Phase 6 hasn't defined the SMT-ready predicate form yet — scoped deliberately, not a shortcut.
- [x] **Design deviation from the task wording, same spirit:** used `client.messages.parse(..., output_format=InvariantExtractionResult)` (JSON-schema-constrained structured output, returns an already-validated Pydantic instance) instead of a forced `strict: true` tool call. For pure extraction with no agentic tool loop, this is the more direct, less-boilerplate surface — same guarantee (output always validates), less code to get wrong.
- [x] Unit tests with a mocked client (`tests/pipeline/test_invariant_extractor.py`) — prompt-building and extraction-parsing both covered, no API spend in CI
- [x] **Open Question #4 decided:** Opus 5 for Stage 2 specifically (`settings.invariant_model`), Sonnet 5 stays the default elsewhere — invariant extraction is the highest-stakes reasoning step and runs only a handful of times per app, so the cost delta is negligible
- [x] Wired into API + frontend: `_execute_run` runs Stage 2 after Stage 1, persists `Invariant` rows, publishes a `{"type": "stage", "stage": "invariants"}` WS event while it runs; `GET /runs/{id}` returns them; Run Detail renders an Invariants card (resource, kind badge, confidence %, statement, rationale) plus a live "extracting invariants…" indicator
- [x] Commit, push

**What's actually built:** The prompt (`prompt.py`) deliberately only includes resources with a path-param id — the actual BOLA-relevant ones — keeping token spend down and focus tight on this project's actual novelty claim, rather than dumping the full 25-resource model at the model. System prompt explicitly instructs: infer the invariant that *should* hold even when evidence shows no enforcement, but reflect that gap as *lower confidence* rather than skipping the resource — the missing-enforcement case is exactly what this whole project exists to surface, not a reason to stay silent.

**Verified two different things, honestly kept separate:** (1) the pipeline logic itself, via mocked unit tests (2 pass) — no real API key needed, no cost; (2) the DB/API/frontend *wiring* for invariants, verified live in a browser by manually inserting a test `Invariant` row and confirming `GET /runs/{id}` → SQLAlchemy `selectinload` → Pydantic response → React rendering all round-trip correctly end to end. **Not yet done:** an actual live call to Claude — no `ANTHROPIC_API_KEY` is available in this environment, so the "does the LLM produce good invariants on real crAPI data" question is still open. That's a real gap, not a formality — the prompt could be well-formed and still produce mediocre invariants; someone with a real key needs to run `POST /runs` end-to-end and eyeball the output before trusting this stage.

Caught and fixed one real correctness issue via mypy, not just style: `response.parsed_output` is typed `T | None` by the SDK (e.g. on a refusal) — the first draft assumed it was always present. Now raises a clear error with the `stop_reason` and refusal explanation if the model didn't produce structured output, instead of a bare `AttributeError`.

---

## Phase 5 — Hypothesis Generator, Sequential Only (Stage 3)

**Goal:** first prove the mechanism with one hand-crafted hypothesis (no LLM), then automate sequential BOLA-style hypothesis generation with Claude.
**Depends on:** Phase 4 (need invariants to target).
**Owner:** Anish.

Tasks:
- [x] `Hypothesis` schema — `preconditions`, `steps: list[RequestStep]` (actor, endpoint_key, description, `captures`/`uses` for chaining a response value from one step into a later step's request), `target_invariant_statement`, `expected_violation`, `confidence`
- [x] Hand-crafted hypothesis against a **real** crAPI bug, not a synthetic example — the exact one Phase 2's scanner found (`workshop/crapi/shop/views.py:122`, no ownership filter): victim creates an order and captures `order_id`, attacker fetches it via `GET .../orders/{order_id}` using that captured id. Two tests pin it: round-trips through JSON, and explicitly asserts the actor actually switches between the capturing step and the using step — the structural core of a BOLA chain, not just "the schema parses."
- [x] LLM-driven hypothesis generation (`generator.py`) — same `output_format` pattern as Stage 2, Sonnet 5 per the finalized model split. Prompt only includes OWNERSHIP-kind invariants and instructs prioritizing *lower*-confidence ones (evidence suggested enforcement might already be missing, so a violating chain is more likely to actually succeed) — same "state the gap, don't skip it" philosophy as Stage 2's prompt.
- [x] Wired into API + frontend: `_execute_run` runs Stage 3 after Stage 2, persists `Hypothesis` rows, publishes a `{"stage": "hypotheses"}` WS event; Run Detail renders a Hypotheses card showing each chain's numbered steps with actor badges
- [x] Commit, push

**What's actually built:** Same verification split as Phase 4, kept honest: mocked unit tests for the generation logic (prompt filtering, schema shape) — no API spend, no key needed; DB/API/frontend wiring verified live in a browser via manually-inserted test rows. **Still not done:** an actual live Claude call — same open item as Phase 4, still no `ANTHROPIC_API_KEY` in this environment. Both Stage 2 and Stage 3's real output quality are unverified until someone runs it with a real key.

**One real design bug caught while eyeballing the live-rendered output, not by any automated check:** `RequestStep` originally had both a `method: HTTPMethod` field *and* an `endpoint_key` string already formatted as `"METHOD /path"` — two sources of truth for the same fact, and the UI ended up printing `POST POST /workshop/api/shop/orders`. Worse than a display bug: an LLM-generated step could have set `method` inconsistently with the method embedded in `endpoint_key`, and nothing would have caught it. Removed the redundant field entirely rather than just fixing the display — `endpoint_key` alone is now the single source of truth, matching the convention Stage 1 already uses for its own `Endpoint.key`.

---

### LLM provider switch (2026-09-02, post-Phase-5)

**Decision:** dropped Anthropic (Sonnet 5 / Opus 5) entirely. Both Stage 2 and Stage 3 now go through one shared OpenAI-compatible client (`app/pipeline/llm_client.py`), picking a provider by `LLM_ENV`:

- **`dev` (default):** OpenRouter's free-tier GLM 5.2 (`z-ai/glm-5.2:free`) — genuinely $0, for iteration. Defaulting to this (not prod) means nobody burns real money just by running the app.
- **`nvidia`** (added 2026-09-02): build.nvidia.com's free "prototyping" endpoint for the SAME model as `prod` below (`deepseek-ai/deepseek-v4-pro-0813`) — dev-testing here is directly representative of real production behavior, unlike GLM 5.2 which is a different model. Tool-calling support wasn't confirmed by NVIDIA's docs either way going in. Not for the Phase 11 evaluation numbers even if it works — it's a prototyping tier.
- **`prod`:** Together.ai's DeepSeek V4 Pro (`deepseek-ai/DeepSeek-V4-Pro-0813`, $1.32/1M in, $3.96/1M out) — the real model for actual runs and the Phase 11 evaluation numbers.

**Why the switch:** DeepSeek V4 Pro is ~2.5–3x cheaper than the Sonnet+Opus hybrid for the same work, with a track record (via its V3/R1 lineage) specifically strong on coding/structured-reasoning tasks — a good match for what Stages 2–3 actually do. The free GLM 5.2 dev tier eliminates dev-iteration cost entirely without touching output quality for the parts that were already cost-free anyway (mocked tests).

**Why tool-calling, not each provider's native structured-output helper:** both providers are confirmed (via their docs) to support forced function/tool calling; only GLM 5.2 was confirmed for the stricter JSON-schema `response_format` mode, not DeepSeek V4 Pro. Tool-calling is the one mechanism verified on both, so `llm_client.py` builds on that rather than branching logic per provider.

**Real empirical finding, not just reasoning from docs:** tried to verify the new `call_structured()` abstraction live against local Ollama models (already installed on this machine) before asking for real provider keys. Results were genuinely informative: `llama3:latest` doesn't support tools at all in Ollama; `mistral:latest` crashed the underlying llama-server process outright; `qwen2.5:3b` correctly returned a tool call for a trivial 2-field schema with `tool_choice="auto"`, but silently returned no tool call at all for the real `InvariantExtractionResult` schema (nested list of a 6-field object) — and forced `tool_choice` (the mode this project actually uses) didn't work with this Ollama version regardless of schema complexity. This is real evidence, not just the general reasoning given earlier in the project, for why small local models were ruled out as anything beyond a highly limited dev aid, and why hosted providers are the right call for both the free dev tier and production.

**First real hosted-provider attempt (2026-09-02):** with an `NVIDIA_API_KEY` in place and `LLM_ENV=nvidia`, triggered a real `POST /runs` against crAPI end-to-end. Result: `401 Unauthorized` — but cleanly isolated as a credential problem, not a code problem: reproduced the identical 401 with a raw `curl` request carrying the exact same key, completely independent of our Python code, the OpenAI SDK, and `llm_client.py`. That's actually a useful confirmation — the whole path (config loading from `.env`, request construction, error surfacing into `run.error`, WebSocket failure event) worked correctly on the first real attempt; only the credential itself didn't authenticate. One concrete lead: the key provided is 64 characters and doesn't start with `nvapi-`, the standard prefix for build.nvidia.com personal API keys as of this project's knowledge — possibly the wrong value was copied from the model page. Waiting on a corrected key to retry.

**Still fully unverified:** OpenRouter (`dev`) and Together.ai (`prod`) — no key provided for either yet. `nvidia` was the first one attempted specifically because it's free and uses the exact production model.

**Credential fixed, then a second, more serious bug surfaced by the same live run:** the key was missing its `nvapi-` prefix — corrected, and the retried request got past authentication. But then the run appeared to hang, and a plain `GET /runs/{id}` to our *own* backend also hung — the whole server had frozen, not just the run. Root cause: `_execute_run` is `async def`, scheduled as a FastAPI `BackgroundTasks` job, but `extract_invariants`/`generate_hypotheses` call the *synchronous* `OpenAI` client directly. A blocking network call executed straight inside an async function doesn't yield control — it blocks the entire single-threaded event loop for the LLM round-trip's duration, freezing every other request the server is handling, not just the one that triggered it. Mocked tests never caught this because mocks return instantly, so the blocking duration was always ~0ms in every test that existed. **Fixed** by wrapping both calls in `asyncio.to_thread(...)` at the `_execute_run` call site — `extract_invariants`/`generate_hypotheses` themselves stay correctly synchronous (same functions the CLI calls directly), only the async caller needed to offload them. **Verified the fix directly, not just by inspection:** fired a fresh run, then hit `GET /health` and `GET /runs/{id}` *while the run was actively `running`* — both returned in ~0.3s, proving the server stays responsive during a live LLM call. This is exactly the kind of bug that only shows up under real latency, which is precisely why the "verify with mocks, then verify live" split from Phases 4–5 exists — mocks alone would never have caught it.

**NVIDIA's free tier itself proved too slow/unreliable for practical use, at least at the time of testing:** with the concurrency bug fixed, confirmed via a live open TCP connection (reverse-DNS-matched to `integrate.api.nvidia.com`) that a run genuinely sat waiting 10+ minutes with no response — not a code hang, real server-side latency. Added `extra_body={"chat_template_kwargs": {"thinking": False}}` (matching NVIDIA's own sample code, since DeepSeek V4 Pro is a reasoning model and disabling extended thinking was the obvious first lever) plus an explicit 120s client timeout (previously relying on the SDK's 10-minute default, which is a bad fit for a background job that should fail fast and clearly). Retried: failed cleanly at the 120s mark with `openai.APITimeoutError` — still too slow even with thinking disabled. Two consecutive genuine timeouts is enough to treat this as a real property of the free "prototyping" tier right now, not a fluke — matches the caution already on record that prototyping tiers aren't reliable enough for anything beyond casual dev use. **Decision: deprioritize `nvidia` for now.** The `nvidia` code path stays in place (essentially free to keep, might just need a retry on a less congested day) but isn't the near-term path to a verified run.

### First successful live run — OpenRouter's GLM 5.2, `dev` tier (2026-09-02)

**This closes the verification gap open since Phase 4.** Ran `POST /runs` against crAPI with `LLM_ENV=dev` (GLM 5.2, free). Result: **completed in ~11 seconds** (created 16:33:52, completed 16:34:03) — both Stage 2 and Stage 3 calls combined, consistent with OpenRouter's own reported ~2.72s typical latency for this model and a world apart from NVIDIA's 10+ minute stalls. 8 invariants, 6 hypotheses, both inspected in full, not just "did it return valid JSON":

- **The order invariant Stage 2 extracted (confidence 0.8) names the exact real bug** Phase 2's scanner found — cited `Order.objects.get(id=order_id)` with no ownership comparison, matching the pinned regression test in `test_source_scanner.py` almost verbatim.
- **Real semantic judgment, not just pattern-matching:** correctly classified community-post read/comment endpoints as `state_precondition` rather than `ownership` — reasoning that posts are meant to be shared/public, so no ownership check *should* exist there, unlike the order/video/vehicle cases where the same "no check found" evidence correctly *does* indicate a bug. Also correctly inferred a `role_required` invariant (admin-only video deletion) purely from an `/admin/` path segment.
- **Stage 3's `order` hypothesis (confidence 0.7) is structurally identical to the hand-crafted example from Phase 5** — victim creates an order, attacker fetches/updates it via the captured `order_id`. The model independently generated the same chain shape used as this project's own "proof the schema can express a real attack" reference case.
- **Genuine multi-step reasoning, not shortcut-taking:** the `vehicle` hypothesis realized the vehicle ID isn't returned directly from the add-vehicle call, so it inserted an extra step (victim lists their vehicles to obtain the ID) before the attacker uses it — and the `captures`/`uses` references correctly pointed at `step2` (the actual capturing step), not reflexively `step1`.

**Practical implication:** GLM 5.2 via OpenRouter is not just "good enough to not error out" — on this one real run, output quality was genuinely strong. Worth keeping as the default `dev` tier with real confidence now, not just because it's free. Still keep Together.ai's full-precision paid `prod` tier for the actual Phase 11 numbers (GLM 5.2 here runs at FP4 quantization, per OpenRouter's own listing) — this result de-risks Stage 2/3's design, it doesn't replace the reproducibility case for prod.

**Still open:** Together.ai's `prod` tier itself remains unverified — no key tested yet. Low urgency now that `dev` is confirmed working end-to-end with good output; verify prod whenever a real evaluation run is actually needed.

---

## Phase 6 — Symbolic Encoder + Z3 Solver (Stages 4–5)

**Goal:** the actual proof engine — translate a hypothesis + its target invariant into SMT-LIB, solve with Z3, interpret SAT (concrete witness) / UNSAT (counterexample). This is the core novel contribution — test heavily.
**Depends on:** Phase 5 (need hypotheses to encode).
**Owner:** Vijay.

Tasks:
- [x] Python → SMT-LIB translation layer over the Application Model's state transitions (`stage4_encoder/binding.py` + `encoder.py`)
- [x] Z3 integration: solve, extract concrete witness on SAT, extract counterexample reason on UNSAT (`stage5_solver/solver.py`)
- [x] Counterexample feedback loop: UNSAT reason feeds back into Stage 3's next hypothesis round (`generate_hypotheses(refuted=...)`, bounded by `settings.hypothesis_rounds`, default 2)
- [x] Test suite with hand-built cases of known SAT/UNSAT outcome — 38 new tests across binding, solver, crAPI integration, and the feedback loop
- [x] Wire into API + frontend: Run Detail shows SAT/UNSAT per hypothesis with the proof trace (witness narrative, unsat core, collapsible SMT-LIB)
- [x] Commit, push

**What's actually built:** The formal question Z3 answers is deliberately narrow and stated in `encoder.py`'s docstring: *does there exist an execution of this exact chain, under the application model's transition semantics and assuming the app does NOT enforce the check at the governed endpoint, in which a governed step is performed in a way the invariant forbids?* It's bounded model checking over the chain: per resource instance and per step index, `owner@k : Int` (an actor id) and `exists@k : Bool`; create sets both, delete clears `exists`, read/update/action leave state alone, everything untouched is framed. SAT means the chain *structurally* reaches a violation — the model is the concrete witness (which actor, which instance, introduced at which step, violated at which step) that Stage 6 will replay. UNSAT means no execution can violate it whatever the app does — the unsat core names why (same actor created and accessed; instance deleted before access; no step touches a governed endpoint; a known-enforced endpoint). That split is what makes the loop sound: Z3 filters LLM chains that can't logically violate anything, and the replay engine — not Z3 — is what decides whether the live app actually enforces the check. An `enforced_endpoints` input exists for exactly that hand-off: once replay observes a 403 on an endpoint, marking it enforced makes every future chain through it UNSAT up front, with the core pointing at the enforcement assumption.

**Structural binding happens in Python before anything touches Z3, and it's strict on purpose.** Every `uses` value must be a `stepN.name` reference to an earlier step's capture; every path param must be bound; every endpoint must exist in the model. A chain that fails binding gets verdict `invalid` with the exact error, not a vacuous encoding — the alternative (treating an unresolved id as a free symbolic instance) would make "attacker guesses an order id" trivially SAT and turn the whole check into noise. Three modeling assumptions are stated up front rather than hidden: named actors are distinct principals; a value captured from a read/list made by actor A is an instance owned by A (this is how the crAPI vehicle chain works — the create call returns no id, so the victim lists first); for `role_required`, an actor is privileged iff its name contains "admin", because the invariant text is prose. `state_precondition` invariants return `unsupported` explicitly instead of being faked.

**Tests pin the *why*, not just the verdict.** Beyond SAT/UNSAT on hand-built chains (same-actor, delete-then-access, enforcement flip, ungoverned endpoint, cross-resource body reference, multi-actor attribution to the right step, list-captured ids), two tests guard the proof artifacts themselves: the exported SMT-LIB is re-parsed by Z3 and re-solved to the same verdict (so the trace is faithful, not decorative), and the SAT witness is checked by pinning its actor values into the re-parsed problem (still SAT) and then forcing the attacker to equal the owner (UNSAT) — the ownership mismatch really is what the witness hinges on. A crAPI integration test proves the hand-crafted Phase 5 order BOLA SAT against the *real* Stage 1 model, and its same-actor twin UNSAT.

**Two real bugs the suite caught before commit:** (1) the witness narrative used ownership phrasing for role-required violations because it branched on "has a target instance" instead of on invariant kind; (2) `Solver.to_smt2()` output was textually non-deterministic — Z3's let-binding names are hash-cons ids recycled by the shared default context, so two identical proofs produced different traces. Fixed by translating the assertions into a fresh `z3.Context()` for export; a determinism test now pins it.

**Verified vs. not, kept honest:** backend pytest (51 pass), ruff, mypy strict, frontend lint + build all green. The DB/API/frontend wiring was then verified live in a browser after fixing Docker (see the Docker note below): Postgres up, migrations applied, a run seeded with **real** Stage 1 + Stage 4/5 output (`prove_all` against the actual crAPI model, verdicts `sat` and `unsat`), and Run Detail confirmed rendering the verdict badge, witness narrative, unsat core + reason, and the collapsible SMT-LIB trace with its human-readable label header. `Finding` rows carry `ProofResult` JSON paired to hypotheses by position; the `Finding` table already existed as a stub, so no migration was needed.

**Full pipeline verified live (later on 2026-09-03):** after four attempts failed at Stage 2 on an upstream `429` from OpenRouter's shared free pool (surfaced cleanly into `run.error` as designed), a fifth plain `POST /runs` with `LLM_ENV=dev` completed in ~20 seconds: 5 invariants (including a correctly-identified `role_required` admin-video rule and a correctly *non*-ownership call on community posts), 5 hypotheses, 5 findings — every LLM-generated chain bound to the real crAPI model with zero `invalid`/`unsupported` verdicts, and Z3 proved all five `sat` with concrete witnesses (video read+delete, video update, vehicle location via the list-then-use shape, order read+return, order update). Rendered in the browser with per-hypothesis proof traces. Stage 2 -> 3 -> 4 -> 5 handoff is no longer an open item.

### Docker Desktop startup failure — root-caused and fixed (2026-09-03)

Docker Desktop 4.73 crashed on every start with "starting services: initializing Inference manager: listening on unix://…\Docker\run\dockerInference: remove …: The file cannot be accessed by the system." A factory reset didn't help, and after clearing that one file it simply crashed on the next socket instead (`…\docker-secrets-engine\engine.sock`) — so the specific file was never the problem.

**Actual root cause:** these are AF_UNIX socket files, stored on Windows as reparse points. Leftover socket files from a previously-crashed Docker session stay bound in kernel state, and every subsequent access fails with Windows error 1920 (`ERROR_CANT_ACCESS_FILE`). Confirmed it's not a permissions or antivirus issue: Controlled Folder Access is off, only Defender is installed, and the files resisted `Remove-Item`, `del` via the `\\?\` kernel path, `fsutil reparsepoint delete`, and even `Rename-Item` — while the *parent directory* renamed fine, which is a directory-metadata operation that never opens the file. A freshly created socket was equally undeletable with every Docker process killed, which is what proves the binding is leaked in the kernel rather than held by a live process.

**Fix that worked, no reboot needed:** stop all Docker processes, `wsl --shutdown`, then rename the *containing directories* aside (`%LOCALAPPDATA%\Docker\run` and `%LOCALAPPDATA%\docker-secrets-engine`) rather than trying to delete the sockets. Docker recreates both cleanly on next launch — the daemon came up in ~10 seconds. If it ever recurs, that's the recipe; the leftover `*.stale-*` directories can't be deleted until a reboot clears the kernel bindings, and are harmless until then.

---

## Phase 7 — Race-Condition Extension

**Goal:** extend the whole pipeline to treat race conditions as a first-class hypothesis type — the project's sharpest novelty claim.
**Depends on:** Phase 6 (sequential proof pipeline must already work).
**Owner:** Vijay + Anish jointly.

Tasks:
- [x] Extend SMT encoding with an interleaving/ordering variable so the solver checks every interleaving of a concurrent request pair (`race_group` on steps; per-member check/write event times in `encoder.py`)
- [x] Extend Hypothesis Generator to propose concurrent/race pairs (new `single_use` invariant kind in Stage 2, race instructions + `race_group` in Stage 3's prompt/schema)
- [x] Build the seeded race-condition target (`/targets/seeded-race` — Spring Boot coupon service with a planted double-redeem bug), since crAPI has none (Open Question #3 resolved)
- [x] Hand-crafted race hypothesis proven end-to-end first (SAT against the Stage 1 model of the seeded target; sequential twin UNSAT), and the planted bug reproduced live against the running service. LLM-driven race generation is wired (prompt + schema) but not yet observed in a live run — see below.
- [x] Commit, push

**What's actually built:** Race conditions are a first-class hypothesis shape now, not a special case bolted on. A hypothesis step carries an optional `race_group`; steps sharing a group are fired concurrently and must be consecutive. Stage 2 gained a `single_use` invariant kind with a machine-readable `limit` ("this effect may succeed at most N times per instance" — coupon redeem, vote, token consume, withdraw), which is the invariant class races actually violate. The encoder tracks a per-instance use counter alongside owner/exists. A *sequential* governed use is atomic check-then-act: it succeeds iff the prior count is below the limit, then increments. A *race group* of uses gets, per member, symbolic check and write event times with `check < write` and all events distinct; each member observes only the writes that landed before its own check, and succeeds iff that observation is below the limit. Z3 therefore searches every interleaving of the concurrent requests, and the violation predicate is simply "final count exceeds the limit." The SAT witness includes the interleaving Z3 chose (`Witness.order`, e.g. `check step 2 < check step 3 < write step 2 < write step 3`) — the concrete schedule Stage 6 will try to reproduce.

**The gap between SAT and UNSAT *is* the race condition, and the tests pin exactly that.** The identical chain (create coupon, redeem, redeem) is SAT when the two redeems share a race group and UNSAT when they don't, with the unsat core naming the atomic-use assertions. `limit` behaves: two concurrent uses against limit 2 are UNSAT, three are SAT. A known-atomic endpoint (`enforced_endpoints`) serializes the group and refutes the race, with the core pointing at that assumption — the same hand-off hook Phase 6 gave ownership, ready for Phase 8 replay to feed back "this endpoint turned out to be atomic." Two artifact-level tests guard the encoding itself: the exported SMT-LIB re-solves to the same verdict, and adding a single serializing constraint (`write step 2 < check step 3`) to the re-parsed SAT problem makes it UNSAT — proving the window really is what the witness hinges on. Malformed races (single-member group, non-consecutive members) are `invalid` with a precise reason; ownership semantics still hold inside a race group.

**Seeded target, verified two ways.** `targets/seeded-race` is a minimal Spring Boot 3.3 / Java 17 coupon service (built with the Maven already on this machine, no Docker needed) with one deliberately planted bug: `POST /api/coupons/{code}/redeem` checks `redeemed` then sets it as two unsynchronized steps, with a 50 ms sleep to widen the window. Stage 1 ingests its hand-written OpenAPI spec exactly like crAPI (create → `create`, read → `read`, redeem → `action`). (1) Formally: the hand-crafted double-redeem hypothesis proves SAT against the model Stage 1 builds from that spec, its sequential twin UNSAT. (2) Empirically, against the running jar: two *sequential* redeems return `200` then `409` and the coupon reads back `redemptionCount: 1`; two *concurrent* redeems both return `200` and it reads back `redemptionCount: 2`. That is the solver's SAT/UNSAT split reproduced by the real application — the strongest single piece of evidence so far that the formal model tracks reality.

**Honest scope notes.** The `single_use` limit is modeled per instance (global), not per actor — "each user may redeem once" is a future refinement. Race semantics only affect the use counter; race-group members are treated in declared order for owner/exists. `state_precondition` is still `unsupported`. **Not yet observed live:** GLM 5.2 actually *emitting* a `single_use` invariant and a `race_group` hypothesis for the seeded target — the prompt and tool schema carry both, and unit tests pin the prompt text, but a real `POST /runs {"target_name": "seeded-race"}` hasn't been run through the LLM stages yet. Do that at the start of Phase 8; if the model doesn't produce a race chain unprompted, the hand-crafted one above is the reference case to tune the prompt against.

---

## Phase 8 — Replay / PoC Engine (Stage 6)

**Goal:** take a Z3-proven witness and actually fire it against a live target — sequential requests in order, race pairs with precise concurrent timing — to empirically confirm the mathematical proof.
**Depends on:** Phase 7 (need both sequential and race witnesses to replay).
**Owner:** Harshada (+ Vijay).

Tasks:
- [x] `httpx` + `asyncio` replay client for sequential witnesses (`stage6_replay/replayer.py`)
- [x] Precisely-timed concurrent firing for race witnesses — `asyncio.Barrier` over pre-warmed per-member connections, not bare `asyncio.gather`
- [x] Capture request/response evidence per replay (status, timing, body excerpt, captured values, per-member release offsets)
- [x] Wire into API + frontend: `POST /runs {"replay": true}` runs Stage 6 on every SAT finding; Run Detail shows the outcome badge, reproduction steps and captured evidence under each proof trace
- [x] Commit, push

**What's actually built:** Replay is what turns a proof into a finding. Stage 5 says a chain *can* violate its invariant *if* the app doesn't enforce the check; Stage 6 decides whether this app actually doesn't, and reports one of four outcomes. `confirmed`: the violating step(s) succeeded against the running app, with the request/response evidence attached. `refuted`: the app rejected them, and the endpoints that did the rejecting come back as `enforced_endpoints` and feed straight into the next round's `prove_all`, so the same chain is refuted up front instead of re-proposed — the Phase 6/7 hand-off hook, now actually connected at both ends. `inconclusive`: a setup step failed, so the violating step never got a fair try (deliberately *not* reported as refuted — an attack that never ran is not evidence of enforcement). `error`: the chain didn't even bind.

**Race timing is the part that needed real care.** Members of a race group each get their own client, are connection-warmed with an OPTIONS request first, and then all block on an `asyncio.Barrier` so the release is the only ordering between them. Plain `asyncio.gather` would serialize TCP setup and hide the very window being tested. Each step records its wall-clock offset from the release, so the interleaving that actually occurred is visible rather than assumed — in the live run below both redeems started within 0.2 ms of each other, against a 50 ms window.

**Verified end to end against the running seeded service, both directions.** The concurrent chain: Z3 `sat` with the proven interleaving `check step 2 < check step 3 < write step 2 < write step 3`, then replay `confirmed` — both redeems returned HTTP 200 and the coupon read back `redemptionCount: 2`. The sequential control: Z3 `unsat`, and replay `refuted` with 200 then 409. Rendered in the dashboard with the proof trace and the live HTTP evidence side by side. The test suite covers the same matrix against a purpose-built threaded HTTP server (a real socket server, not a mocked transport — a mock returning instantly would make any implementation look correct) with switchable `atomic` and `enforce_ownership` behaviour, so CI proves both `confirmed` and `refuted` without needing Java.

**Two real bugs the tests caught before commit, both of the "silently discards a finding" kind.** (1) When a capture failed, replay fired the next request with a literal `{order_id}` still in the URL, got a 404, and read that as enforcement — turning a real finding into "refuted". Unresolved path params are now rejected up front as inconclusive. (2) A *governed* step returning 4xx was treated as a failed setup step rather than as the app enforcing the rule; it's now judged, not dismissed. A third subtlety is encoded deliberately: surviving *sequential* repeats of a single-use action never marks the endpoint enforced, because that says nothing about atomicity under concurrency — marking it would suppress exactly the race proof the seeded target exists to demonstrate.

**Honest scope note — crAPI replay auth is not automated.** The replay target registry (`stage6_replay/targets.py`) ships a header strategy, which is all the seeded-race target needs (`X-User: {actor}`), plus a slot for supplied bearer tokens. crAPI's signup + email-OTP + JWT flow is a real piece of work and is deliberately not automated here; without tokens, replay against crAPI reports its 401s honestly rather than pretending the app is vulnerable. Automating that login flow is the natural first task whenever crAPI replay numbers are actually needed (Phase 11).

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

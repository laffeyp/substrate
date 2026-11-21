# Task breakdown — substrate daily driver (2026-08-25)

Derives from `TECH-SPEC-2026-08-25-round6.md` + `ROADMAP-2026-08-25-daily-driver.md`. One row per sprint, sized ≤2 files / one concept per AGENTS.md hard rule 6. Sprint cards live at `substrate/process/sprints/sprint-NNN-*.md`.

## Piece 0 — Sprint-0 Vocabulary Session

Ratification-gated. Nothing downstream dispatches until 204 closes.

| # | Sprint | Scope | Files | Signal contract | Observation contract |
|---|---|---|---|---|---|
| 202 | Substrate-side vocabulary lock | Author `signals/session-vocabulary.md` (Markdown, following swebench-solver-vocabulary.md shape — repo convention for topology vocab, distinct from kernel-JSON 0.1/0.2). Locks eight new session-topology kinds, all PascalCase Structs, all Producer-emitted (no wire events): `SessionStarted`, `UserMessage`, `ModelReply`, `Park`, `SessionEnded`, `SessionEndRequested`, `TranscriptCompacted`, `SessionWarning`. Plus strata + invariants + dual-contract audit. | `substrate/process/signals/session-vocabulary.md` | Emits: none (documentation). Consumes: TECH-SPEC round 6 §3, §3a, §7.3. | Architect reads the doc, ratifies in `BLACKBOARD.md ## Decisions`. |
| 203 | UI-side vocabulary lock + pairing | Author `substrate-ui/signals/versions/0.6.json` with the matching grader tags + `checkSessionBookends` grader shape. Author `0.6-rationale.md` with the dual-contract pairing table (TECH-SPEC §13.5). | `substrate-ui/signals/versions/0.6.json`, `substrate-ui/signals/versions/0.6-rationale.md` | Consumes: sprint 202's `0.6.json`. | Substrate-ui `npm run signals` grades clean against v0.6. |
| 204 | Canonical-home registry + ratification | Add TECH-SPEC §1.6.1 canonical-home registry entries to `WORKING_AGREEMENT.md`. Architect ratifies vocabulary lock + registry in one Decision. | `substrate/process/WORKING_AGREEMENT.md` | — | Architect Decision entry names v0.6 as locked and dispatches piece A. |

## Piece A — Session topology

Dispatches after 204 ratifies. Six sprints.

| # | Sprint | Scope | Files | Signal contract |
|---|---|---|---|---|
| 205 | Session topology skeleton + Structs | Author `topologies/session/__init__.py` with `session_topology(*, driver, driver_name, driver_context_tokens, seed, tools, per_turn, max_turns, turn_max_steps, session_id, workspace_path, parent_session_id, parent_seq_at_call)`; eight event Structs (SessionStarted, UserMessage, ModelReply, Park, SessionEnded, SessionEndRequested, TranscriptCompacted, SessionWarning); five producer kinds (`model`, `tool`, `park`, `session_end`, `session_warning`); Views `results`, `user_turns`, `model_failures`. | `topologies/session/__init__.py`, `topologies/session/views.py` | Emits: eight Structs registered across the five producer_kind calls. |
| 206 | Triggers + termination | Wire `run-tool`, `continue`, `wrap-up`, `park-on-final`, `park-on-model-error`, `resume-on-user`, `end-on-exit`, `end-on-cap`, `end-on-user-end` triggers. Termination: `any_of(pause_await_input(when=Park), threshold_count(SessionEnded, 1))`. Build-time assertion refusing `all_completed`. | `topologies/session/__init__.py` | Emits: triggers fire the four terminal Producers as declared in TECH-SPEC §3. |
| 207 | Transcript renderer + rolling window | Author `topologies/session/transcript.py` — `render_transcript(...)`, `RenderedTranscript`, `_compute_k`, `_group_by_turn`. Cadence rules for `TranscriptCompacted` per TECH-SPEC §3a. | `topologies/session/transcript.py`, `topologies/session/__init__.py` (integrate renderer into model factory) | Emits: `TranscriptCompacted{strategy, dropped_seq_range, kept_seq_start, reason, tokens_before, tokens_after}`. |
| 208 | Driver context lookup + seed-alone-exceeds | Add per-driver context resolution: Ollama `/api/show` scan for `*.context_length` key with 60s TTL cache; CLI config table entry; `DeterministicResponder` = 4096; custom `[[responder]]` from `~/.substrate/config.toml`. Seed-alone-exceeds warning at session open. | `topologies/session/transcript.py`, `adapters/models.py` (small `context_tokens` helper) | Emits: `SessionWarning{kind: "seed_alone_exceeds"}` when threshold hit. |
| 209 | Session topology bundled + CI record | Register `"session"` in `topologies/bundled.py:BUNDLED` with a CI-mode factory (deterministic responder, scripted two-turn fixture). Generate committed `records/ci_mode.record/`. | `topologies/bundled.py`, `topologies/session/records/ci_mode.record/` | Consumes: bundled dispatch. |
| 210 | OBSERVATION — piece A end-to-end | Fire the piece-A observation contract from TECH-SPEC §3: script + expected log substrings + expected runtime signals + expected screenshot. Behavior-touching, no new source; runs the harness. | `tests/test_session_topology_e2e.py`, `tests/fixtures/three_turns.json` | Reads: piece-A output on `records/`. |

## Piece C — Named standing sessions + delegate per-call args

Three sprints. Depends on A.

| # | Sprint | Scope | Files |
|---|---|---|---|
| 211 | SessionRegistry module | Author `substrate-ui/session_registry.py` (or a substrate-side module): name → session_id index at `~/.substrate/sessions/by-name.json` with `fcntl.flock`-atomic create. Manifest at `~/.substrate/sessions/<session_id>/manifest.json`. Boot-scan restore with `_hot_segment` check → `interrupted` status. | `substrate-ui/session_registry.py`, `substrate-ui/server.py` (wire boot scan) |
| 212 | make_delegate per-call args | Add per-call `model`, `child_session_name`, `context`, `baseline` to `delegate.py:187` `make_delegate`. Constructor gains `session_registry`, `parent_session_id`, `parent_record_root`. Return `Tool` schema declares the six-field JSON schema at `delegate.py:274`. | `substrate/src/substrate/topologies/tool_loop/delegate.py` |
| 213 | Delegate four dispatch paths | Implement the four dispatch paths in `Tool.run`: standing-session route, different-driver route, context-slice route, fresh-child route. Provenance both directions (`parent_session_id`, `parent_seq_at_call` on child baseline). | `delegate.py` |

## Piece B — Session-scoped daemon API

Four sprints. Depends on A.

| # | Sprint | Scope | Files |
|---|---|---|---|
| 214 | /api/session/* create + turn + events | New handlers under `/api/session/*` in `server.py`: POST create, POST turn, GET events (SSE via `api.attach`), GET list, GET by-name, DELETE. Per-session `asyncio.Lock` map. | `substrate-ui/server.py` |
| 215 | SessionEndRequested + PATCH + interrupt | POST /end injects `SessionEndRequested{reason: "user_end"}` via `Runtime.resume` (the external-event injection path per `runtime.py:409`). PATCH updates driver/tools/per_turn on `SessionRegistry` + manifest. POST /interrupt cancels current model Producer's task. Graceful daemon SIGTERM handler emits `SessionEnded{reason: "daemon_shutdown"}` for every running session. | `substrate-ui/server.py` |
| 216 | Queue cap + 410 mid-delegate | Per-session queue cap default 4; fifth caller returns `{ok:false, error:"session queue full: 4 turns queued"}`. 410 Gone from POST /turn when session has ended between resolve and post. | `substrate-ui/server.py` |
| 217 | /api/agent backwards-compat adapter | Wrap existing `/api/agent` handler at `server.py:554-687` to create a session on first request under a generated name, route subsequent requests to `POST /api/session/<id>/turn`. One-release deprecation notice on stderr. | `substrate-ui/server.py` |

## Piece D — CLI + REPL + slashes

Five sprints. Depends on A + B (stub daemon enough to start).

| # | Sprint | Scope | Files |
|---|---|---|---|
| 218 | substrate chat verb + config.toml defaults | Add `chat` verb to `cli.py`. Bare `substrate` dispatches to `chat` with defaults from `~/.substrate/config.toml`. Daemon auto-launch (double-fork POSIX). Socket connect + TCP fallback. | `substrate/src/substrate/cli.py` |
| 219 | REPL + SSE streaming | REPL loop reading stdin cooked-mode; background thread reads `/api/session/<id>/events` and prints. Assistant text streams to stdout before `_daemon.turn` returns. | `substrate/src/substrate/cli.py` |
| 220 | Ctrl+C/D/SIGHUP + SUBSTRATE_SESSION env | SIGINT during turn → POST /interrupt; SIGINT idle → hint. EOF → POST /end. SIGHUP → clean CLI exit; session stays parked. `os.environ["SUBSTRATE_SESSION"]` set before every turn call. | `substrate/src/substrate/cli.py` |
| 221 | Slash command router | Route nine slashes per TECH-SPEC §6. `/exit` reaches the model as a UserMessage. Every other slash bypasses via daemon PATCH / GET / local `api.*` call. `/context` stores per-REPL pending state. | `substrate/src/substrate/cli.py` |
| 222 | session/bundle/builder subverbs | `substrate session ls/end/rm/set-name`; `substrate bundle create/ls/show/edit`; `substrate builder` opens `~/.substrate/studio.html`. Every subverb POSTs to daemon or invokes existing `api.*` locally. | `substrate/src/substrate/cli.py` |

## Piece E — Application manifests + registry

Three sprints. Independent of A after 0 ratifies; parallel dispatch OK.

| # | Sprint | Scope | Files |
|---|---|---|---|
| 223 | applications/registry.py + manifest scan | Author `topologies/applications/registry.py`: `load_manifests()` scans `applications/*.manifest.toml` via `importlib.resources.files` + `tomllib`; returns `{name: ApplicationSpec}`. Daemon calls it at boot. | `substrate/src/substrate/topologies/applications/registry.py`, `substrate-ui/server.py` (boot hook) |
| 224 | Four manifests + BUNDLED registration | Write `code_review.manifest.toml`, `best_of_n_verified.manifest.toml`, `research_sweep.manifest.toml`, `daily.manifest.toml`. Register the three existing application topologies plus a `daily` shim in `topologies/bundled.py:BUNDLED` under CI-mode factories. | `topologies/applications/*.manifest.toml`, `topologies/bundled.py` |
| 225 | pair_coding session-composite | Author `topologies/applications/pair_coding_composite.py`: `pair_coding_application(*, builder_driver, reviewer_driver, workspace, daemon_client) -> SessionCompositeSpec`. Daemon opens both sessions; both torn down together on end. `pair_coding.manifest.toml` names `runs = "session_composite"`. | `topologies/applications/pair_coding_composite.py`, `topologies/applications/pair_coding.manifest.toml` |

## Piece F — Substrate toolkit tool wrappers

Three sprints. Depends on A.

| # | Sprint | Scope | Files |
|---|---|---|---|
| 226 | run_topology + run_topology_poll | Author `topologies/tool_loop/substrate_tools.py` with `make_run_topology(daemon_client)` and `make_run_topology_poll`. `baseline=` merges into child's `TopologyBuilder.baseline`. `await_completion=false` returns `{run_id, record_root, status:"running"}`. | `topologies/tool_loop/substrate_tools.py` |
| 227 | inspect_record + progressive disclosure + HMAC cursor | Add `make_inspect_record(records_root)` with filter shape `{kinds, seq_range, producer, application, time_range}`. Budget cap `min(4096, 0.25 * driver_context_tokens)`. HMAC-signed cursor pagination. Progressive-disclosure default `format="summary"`. | `topologies/tool_loop/substrate_tools.py` |
| 228 | list_records/topologies/applications/sessions | Four small `make_list_*` factories. Session-topology tool suite composition folds all seven tools alongside `full_suite` and `delegate`. | `topologies/tool_loop/substrate_tools.py`, `topologies/session/__init__.py` |

## Piece H — Bundles + Mad Lib

Four sprints. Depends on E (default bundles for the shipped apps).

| # | Sprint | Scope | Files |
|---|---|---|---|
| 229 | bundles.py loader + extends resolution | Author `substrate/src/substrate/bundles.py`: `load_bundle(name)`, `assemble_seed(bundle, session_task)`, `resolve_extends(name, seen)`. C3 linearisation; cycle detection with `BundleCycleError`; depth cap 8; `BundleShapeError` on both `methodology.md` and `methodology/` present. | `substrate/src/substrate/bundles.py` |
| 230 | Slot binding + fallback algorithm | `bind_slots(topology_name, caller_bundle_dict)` per TECH-SPEC §9. Reads `[slots]` from `manifest.toml`. `SlotUnfilledError` on missing required. | `substrate/src/substrate/bundles.py`, `topologies/applications/registry.py` |
| 231 | Five default bundles | Populate `topologies/session/bundle/`, `topologies/applications/code_review.bundle/`, `pair_coding.bundle/`, `best_of_n_verified.bundle/`, `research_sweep.bundle/`. Each has `methodology.md`, `personality.md`, `per-turn.md` (or empty), `bundle.toml`. | Five bundle directories under `topologies/` |
| 232 | Mad Lib wizard + templates | `substrate bundle create <name> --wizard` walks a template. Ship six templates under `substrate/src/substrate/templates/bundles/`. ~40-line home-rolled interpolator (no jinja). | `substrate/src/substrate/cli.py` (wizard verb), `substrate/src/substrate/templates/bundles/*.tmpl.md`, `substrate/src/substrate/templates/interpolate.py` |

## Piece G — Substrate-ui two-view (in substrate-ui/sprints/)

Own sprint chain in `substrate-ui/sprints/` continuing at 033. Not enumerated here — belongs to that repo's roadmap document. Named at TECH-SPEC §10 with five UI controls, rail rewrite, signal vocab v0.6 bump, `e2e_session.js` harness, `checkSessionBookends` grader.

## Test coverage summary

Every sprint above ships tests as named in `TECH-SPEC-2026-08-25-round6.md` per-piece Tests block. Total new tests: ~60 across the daily driver's Python surface plus the substrate-ui end-to-end harness.

## What halts each piece

- Piece 0: `vocabulary_change_required` if a proposed kind uses `substrate.*`; `observation_contract_missing` if a behavior kind has no dual-contract pairing (§13.5); `awaiting_architect_decision` for the vocabulary lock itself.
- Piece A: `dual_contract_fail` if `test_session_topology_refuses_all_completed.py` regresses; `observation_contract_missing` if 210 does not run green.
- Piece C: `bridge_mapping_required` if `session_registry.py` grows a new external SDK before its module lands in `WORKING_AGREEMENT.md`.
- Piece D: `observation_contract_missing` if the pty-driver test at 219 does not exist by close.
- Piece E, F, H: `comprehension_failed` if any sprint touches a topology whose `manifest.toml` has not been dispatched in 223.
- Piece G: `observation_contract_missing` — Playwright script + five DOM states from TECH-SPEC §10 required per sprint.

---

*Task breakdown, 2026-08-25. 31 sprints in `substrate/process/sprints/` (202-232). Piece G continues in `substrate-ui/sprints/` from 033. Cards are dispatched by piece; piece 0 first, others gated by the dependency graph in ROADMAP.*

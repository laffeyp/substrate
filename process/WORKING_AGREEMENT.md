# process/WORKING_AGREEMENT.md — Substrate

*Project-specific overrides and additions on top of `sdd-kit-2/AGENTS.md`. The Agent reads AGENTS.md first (the methodology) then this file (the project specifics). This file augments; it never overrides AGENTS.md hard rules. When the two conflict, AGENTS.md wins.*

---

## Project identity

- **Project name:** Substrate
- **Project type:** Python library + CLI (concurrent streaming dataflow runtime)
- **Primary language(s):** Python 3.12+ (CI matrix 3.12, 3.13, 3.14); asyncio
- **Primary build commands:** `uv run pytest` (suite) · `uv run substrate conformance` (release gate) · `uv run mypy --strict` (public-API type gate) · `uv run ruff check`
- **Adopted SDD kit version:** `sdd-kit-2` (read-only canon at `../sdd-kit-2/`)
- **License:** Apache-2.0 (product D-1)

---

## Project class

**Backend / data-pipeline** + **CLI / command-line** + (optional extras) **LLM-integration**. Consult `TECHNIQUES.md` Section 2 → those three subsections during sprint composition. Notable class techniques in play: Wave-0 carry / pre-filled contract files (the public API surface is consumed by many subsystems); N.INT integration sprints at wave boundaries; always-emit-summary + paired-incident; operator-chain category alignment; exit-codes-as-contract; stdout-for-data/stderr-for-narration; flag-driven instrumentation; external-SDK reverse-engineer-first (msgspec, rfc8785).

---

## Project scope (verbatim from BLACKBOARD ## Decisions)

> Substrate is a concurrent streaming dataflow runtime: an importable Python 3.12+ library plus a `substrate` CLI, Apache-2.0. It runs Producers concurrently, coordinates them through one totally-ordered append-only bus, creates new Producers dynamically when predicates over the log are satisfied, and persists every run as a replayable, diffable, provenance-complete record — the record is the product surface. v1.0 is the full build per product spec DRAFT 7 (all eight primitives, both persistence modes, replay Levels 1–3a, composition, the CLI, the inspection API), gated by the 17 conformance checks with R-1..R-3 as integration proofs. Out of scope for v1.0: a UI in-repo (substrate-ui is the separate companion), distributed execution, Windows persistent bus. Corrections folded from 2026-06-27: ALL models are legitimate arms (no local-vs-cloud cost tier — the only surviving distinction is sample size), and running command-line models/agents as Producers is baseline substrate capability, not a cockpit feature.

*(Ratified into `## Decisions` 2026-07-22, recording the Architect's 2026-06-12 verbal endorsement + 2026-06-27 corrections. The same ruling opened `## Decisions` to any writer recording a made decision.)*

---

## Canonical specs (the corpus this project implements)

| Spec | Canonical file | Draft |
|---|---|---|
| Kernel semantics (eight primitives, append cycle, replay) | `docs/specs/kernel_spec/v15.md` | v15 |
| Product (requirements F-*, N-*, conformance §7, reference topologies §8, decisions D-1..D-9) | `docs/specs/product_spec/draft7.md` | DRAFT 7 |
| Technical (byte layout, writer cycle, public API, constants §19) | `docs/specs/technical_spec/draft5.md` | DRAFT 5 |
| Design (API ergonomics, CLI UX, error UX) | `docs/specs/design_spec/draft1.md` | DRAFT 1 |

Superseded drafts under `docs/specs/product_spec/`, `docs/specs/technical_spec/`, `docs/specs/kernel_spec/` are audit-trail history (no deletions, hard rule 12); cite only the canonical drafts above.

**Additive amendments** (govern over the base draft where they conflict; the base draft is preserved): `docs/specs/product_spec/draft7_amendment_A1_replay_3b.md` + `docs/specs/technical_spec/draft5_amendment_A1.md` — 2026-06-13 Ruling 2: Level 3(b) replay deferred (F-RPLY-1 relaxed to SHOULD for v1.0; conformance check 6 = "deferred (spec-amended)"), and the D-8 supplementary-metadata exclusion set enumerated. `docs/specs/product_spec/draft7_amendment_A2_nperf1.md` — 2026-06-13: N-PERF-1 floor recalibrated 100K → 40K appends/sec (the 100K was derived from a prototype that didn't measure the required canonical encoding; measured ~56K). Cite the base draft + its amendments together.

---

## Canonical home registry

*Per AGENTS.md hard rule 7. Seeded from technical spec §16 (public API) + §3 (record format). Firms up as architecture sprints land; add rows as types stabilize. Import root is the package name (B-Q-1, unresolved — placeholder `substrate`).*

| Type / module | Canonical home (planned) | Notes |
|---|---|---|
| `Event`, `BlobRef`, `ProducerRef`, `Subscription` | `substrate/types.py` | Frozen msgspec Structs; the on-disk envelope (tech §3.4). Sole declaration. |
| `Producer`, `View`, `Responder`, `TriggerContext` (Protocols) | `substrate/protocols.py` | `(input) -> AsyncIterable[Event]`; `update`/`value`. |
| `TopologyBuilder`, registry | `substrate/kernel/topology.py` | One builder method per primitive (design §4.1). *(Post-reorg path; the 2026-06-19 subpackage split moved the flat modules under `kernel/ record/ projections/ conformance/`.)* |
| `Runtime`, `RunResult`, the writer loop | `substrate/kernel/runtime.py` | Single writer; run lifecycle + termination (tech §6). |
| The append cycle (`AppendCycle`), admission/control queues | `substrate/kernel/sequencer.py` + `substrate/kernel/runstate.py` | Six-step cycle; bounded inbox; control bypasses admission. |
| Firing policies (`Once`, `PerEvent`, `PerKey`, `WhileTrue`), cooldowns (`Logical`, `WallClock`) | `substrate/kernel/triggers.py` | Tech §10. |
| Standard Views (`BufferView`, `KindBuffer`, `KindCount`, `PerKindLatest`, started/completed counts) | `substrate/kernel/views.py` | F-VIEW-2. |
| Standard policies (`cancel_all_others`, `quiescence`, `threshold_count`, `all_completed`, `pause_await_input`, `any_of`, `all_of`) | `substrate/kernel/policies.py` | F-LIFE-2. *(`let_finish` REMOVED pre-1.0 — dead no-op path, audit #8; `subtree_cancellation` DEFERRED post-1.0 — vocab-blocked; both in the CONTRIBUTING deferral list.)* |
| Composition (`embedded_substrate`, `EmbeddedRunFailed`) | `substrate/kernel/composition.py` | Tech §20; F-COMP. |
| Canonical encoding (RFC 8785 pipeline, type whitelist, `B_hash`/`B_disk`) | `substrate/encoding.py` | Tech §4. |
| Run record on disk (segments, sealing, frame/CRC, manifest, blob store, recovery, locking, sidecars) | `substrate/record/` (`record.py`, `framing.py`, `blobstore.py`, `sealing.py`, `locking.py`, `sidecar.py`) | Tech §3, §5. |
| Replay engine (Levels 1–3b) | `substrate/projections/replay.py` | Tech §12. |
| Live attach (follower) | `substrate/projections/attach.py` | Tech §13. |
| Inspection / provenance / divergence | `substrate/projections/inspect.py` | Tech §14; `explain_producer`, `trace_ancestry`, `view_at`, `decisions_between`, `first_divergence`. |
| Narration + graph projections | `substrate/projections/narrate.py`, `substrate/projections/graph.py` | Wave 14 / Wave 12 prep. |
| Model adapters (`DeterministicResponder`, `OllamaResponder`, `CliResponder`, `ModelUsage`, metered calls) | `substrate/adapters/models.py` | The Responder seam; re-exported via `substrate.reference` for back-compat. |
| Test helpers (`assert_event`, `assert_no_event`, `assert_sequence`) | `substrate/testing.py` | F-API-4 / tech §15. |
| Public API re-exports | `substrate/api.py` | F-API-6: `substrate.cli` may import only this. |
| CLI (`run`, `replay`, `inspect`, `validate`, `tail`, `conformance`, `resume`, `stats`) | `substrate/cli.py` | Click + Rich; public API only. |
| The locked vocabulary | `process/signals/current.json` (symlink → highest committed `process/signals/<version>.json`; today points at `0.3.json`. Older `0.1.json` / `0.2.json` retained as audit trail.) | Sprint 0, evolved to v0.3 (2026-08-27 P-CANCELLED-CAUSE + P-CANCELLED-CALLER on ProducerCancelled). Sprint 239 added the `current.json` pointer (2026-08-28) so downstream readers (substrate-ui `sync-substrate-vocab.ts`, and any consumer) follow one stable path. Version bumps: `ln -sf <new>.json current.json`; loaded, not hand-edited. |
| Shared best-of-N + correction contract: `Draft`, `Candidate`, `Verdict`, `Solved`, `Exhausted` (+ `ModelUsage`) | RECORDS: `substrate/topologies/best_of_n/contracts.py` (NEUTRAL canonical home) | **3-CONSUMER shared contract** (Wave-0 #15) — coding_flow (re-exports for back-compat), the swebench_solver Repairer, and code_evolution all import from here; reused, not re-rolled (review #57 / KIT_DIARY 12). Moved out of coding_flow (review #61) so the shared loop doesn't import its records from a consumer — dependency flows ONE way, no cycle when coding_flow migrates (#43). Sprint 133 / moved 136. |
| Shared best-of-N + correction LOOP BUILDER: `best_of_n_correction(b, ...)` + `seeder_factory` / `select_first_judge_factory` | `substrate/topologies/best_of_n/__init__.py` | The reusable wiring (seeder/drafter/validator/judge + triggers + termination), parameterized by the caller's draft+validate factories (the work), judge (terminal policy), and termination. Sprint 136 (Wave-0). coding_flow keeps its own copy until the #43 migration (≤2 copies, never 3). |
| delegate tool: `make_delegate(...)` (an agent hands a subtask to a child agent, folds the answer back) | `substrate/topologies/tool_loop/delegate.py` | Application-parity W2.1 (sprint 141), the first engine seam. A tool_loop `Tool` the caller composes into a suite (`{**full_suite(root), "delegate": make_delegate(...)}`); the child runs to a FinalAnswer at its OWN record root in a worker thread (sync tool seam, blocks like `bash`), and `child_root` on the ToolResult is the run-granularity provenance link (composition.py §20). Depth + fan-out capped (typed failures). The child is caller-supplied (`child_factory`) — session, named topology, or a deterministic scripted agent for CI. `delegate`'s schema registers in `tools.py` `_TOOL_SCHEMAS` (a tool absent there is invisible to native tool-calling — a real-model walkthrough caught this). Launch: `scripts/run_tool_agent.py --delegate`. |
| Applications: `research_sweep_topology` + `gather` (fan readers over a doc set, critique gaps, synthesize) | `substrate/topologies/applications/research_sweep.py`; records locked in `process/signals/applications-vocabulary.md` (F-17) | Application-parity W1.3 (sprint 139). Map-reduce, AUTHORED from primitives (no whole topology composes for map-over-different-inputs) — seeder-fan (best_of_n shape) + fan-in quorum (code_review shape). Four topology-local Structs (ReadRequest/Finding/Gaps/Synthesis), like code_review's own. Launch: `scripts/run_research_sweep.py`. Closes W1. |
| Applications: `best_of_n_verified_topology` (generate N, verify each, select the survivor) | `substrate/topologies/applications/best_of_n_verified.py` | Application-parity W1.2 (sprint 138). COMPOSES `best_of_n_correction` — a drafter Responder + a caller-supplied verifier (deterministic `check` OR an independent judge Responder, finding #42). No engine change, no new vocabulary (reuses Draft/Candidate/Verdict/Solved/Exhausted). Launch: `scripts/run_best_of_n_verified.py`. |
| Applications: `fanout_review_topology` + `changed_files` (the review panel on a real git diff) | `substrate/topologies/applications/fanout_review.py`; the `ReviewSubject` record locked in `process/signals/applications-vocabulary.md` (S-8) | Application-parity W1.1 (sprint 137). COMPOSES `code_review_topology` fed a real diff — no engine change. Reuses `CritiquePosted`/`VerdictRendered` AND emits one own kind, `ReviewSubject` (the gathered diff on the record, review C-2). The launchable surface is `scripts/run_fanout_review.py`. best_of_n_verified + research_sweep join this package (phase W1). |
| swebench_solver records: `SuspectFiles`, `SuspectElements`, `EditLocations`, `AppliedPatch`, `TestResults`, `SelectedPatch`, `RepairOutcome`, `RepairSummary` | `substrate/topologies/swebench_solver/records.py` | The LOCALIZE + SELECT + terminal-OUTCOME records wrapping the shared loop. Fields locked in `process/signals/swebench-solver-vocabulary.md` (sprint 133; `RepairOutcome`/`RepairSummary` ADDED for `swebench_repair_topology` — the always-emit terminal summary, techniques #51/#53, so the no-patch failure modes are ENUMERATED typed events not reconstructed). `TestResults` is `replayable=False`; the SELECT regression set is repo-derived, NOT the `PASS_TO_PASS` grade field (firewall). |

---

## Canonical home registry — daily driver

*Per AGENTS.md hard rule 7. Seeded from TECH-SPEC-2026-08-25-round6 §1.6.1 (piece 0, sprint 204). Every downstream sprint reads a row here before writing code — new consumers do not re-derive a path. Additions land as new rows before dispatch.*

| Entity | Canonical home | Owner (sprint or module) |
|---|---|---|
| Session record | `~/.substrate/sessions/<session_id>/record/` | kernel `Runtime` (existing) |
| Session manifest | `~/.substrate/sessions/<session_id>/manifest.json` | daemon piece C — sprint 217 |
| Name → session_id index | `~/.substrate/sessions/by-name.json` | daemon piece C — sprint 217 |
| Session workspace (Mode 1) | `~/.substrate/sessions/<session_id>/workspace/` | daemon piece B — sprint 213 |
| Session worktree (Mode 2) | `~/.substrate/sessions/wt/<repo>-<session_id>/` on branch `substrate/<session_id>` | `_session_worktree` at `server.py:173-193` (existing) |
| Delegate child dir | `<parent_workspace>/delegate-runs/d<depth>-c<N>/` | `_unique_child_root` at `delegate.py:174` (existing) |
| Session registry (in-memory) | daemon module `session_registry.py` (lives in substrate-ui) | daemon piece C — sprint 211 |
| Bundle | `~/.substrate/bundles/<name>/` | user (runtime resolution — sprint 226) |
| Bundle assembler | `substrate/src/substrate/bundles.py` | piece H — sprint 226 |
| Application registry (in-memory) | daemon module `topologies/applications/registry.py` | piece E — sprint 222 |
| Application manifest | `substrate/src/substrate/topologies/applications/<name>.manifest.toml` | piece E — sprint 222 |
| Role prompts | `substrate/src/substrate/topologies/session/prompts/<role>.md` | piece A — sprint 205 (default.md); sprint 209 (reviewer/planner/tester/explainer) |
| Substrate config | `~/.substrate/config.toml` | user (runtime resolution — sprint 208) |
| Daemon socket | `~/.substrate/daemon.sock` | daemon boot — sprint 215 |
| Daemon pidfile | `~/.substrate/daemon.pid` | daemon boot — sprint 215 |
| Signal vocabulary — substrate kernel side | topology's own `producer_kind(schemas=[...])` calls; reserved namespace enforced at `topology.py:194` | topology author (existing kernel invariant) |
| Signal vocabulary — substrate-ui grader side | `substrate-ui/signals/versions/current.json` | substrate-ui SDD — v0.6 ratified 2026-08-25 (sprint 203) |
| Topology vocabulary — daily driver (substrate side) | `substrate/process/signals/session-vocabulary.md` (topology-scoped Markdown per repo convention; kernel JSON `0.1.json` / `0.2.json` do not bump for application signals) | Sprint-0 Vocabulary Session — sprint 202 (v0.1 RATIFIED 2026-08-25) |
| Session topology skeleton (Producers + Views + eight Structs) | `substrate/src/substrate/topologies/session/__init__.py` | sprint 205 (skeleton) + sprint 206 (triggers + termination + `all_completed` refusal) |
| Session `model_failures` View (filters `substrate.ProducerFailed` where `producer.kind == "model"`) | `substrate/src/substrate/topologies/session/views.py` | sprint 205 |
| Session role prompts (`default.md` and role variants) | `substrate/src/substrate/topologies/session/prompts/<role>.md` | piece A — sprint 205 (default.md); sprint 209 (reviewer / planner / tester / explainer) |
| Session transcript renderer (`render_transcript`, `RenderedTranscript`, `TranscriptCompacted` Struct — the ONE Python home for the wire name) | `substrate/src/substrate/topologies/session/transcript.py` | sprint 207 |
| Driver context lookup (`resolve_driver_context_tokens`, 60-s TTL cache, CLI-config fallback at 100 000 default, `DeterministicResponder` at 4096 constant) | `substrate/src/substrate/topologies/session/transcript.py` | sprint 208 |
| Driver introspection API (`OllamaResponder.context_tokens()`, typed `ContextTokensUnknown` and `DriverIntrospectionUnavailable` errors) | `substrate/src/substrate/adapters/models.py` | sprint 208 |
| Session `session_warning` producer + seed-alone-exceeds guard (registered on `session_topology`, binds `initial("session_warning", ...)` only when `_est_tokens(seed) + _est_tokens(per_turn) > driver_context_tokens * 0.6`) | `substrate/src/substrate/topologies/session/__init__.py` | sprint 208 |
| SessionRegistry (in-memory name index + per-session `asyncio.Lock` map + boot scan) | `substrate-ui/session_registry.py` | sprint 211 |
| Session name → session_id index (persistent, `fcntl.flock`-atomic writes via `.by-name.lock` sibling; atomic-write via tempfile+rename) | `~/.substrate/sessions/by-name.json` | sprint 211 |
| Session manifest (per-session hint the boot scan reads to rebuild the in-memory catalog; `SessionManifest` msgspec Struct per TECH-SPEC §5; status one of `running`/`parked`/`interrupted`/`ended`) | `~/.substrate/sessions/<session_id>/manifest.json` | sprint 211 |

Every claim in TECH-SPEC-2026-08-25-round6 about where a daily-driver entity lives cites a row above. When a downstream sprint discovers a new entity, it halts on `canonical_home_missing` and adds the row before writing code.

---

## External SDK bridge mappings

*Per AGENTS.md hard rule 10 / technique 46. The first sprint that imports an SDK without a bridge mapping here MUST halt with `bridge_mapping_required`. Reverse-engineer the real API surface before authoring against it. To be completed in a `pass_kind: bridge` sprint before the encoding/record sprints dispatch.*

### msgspec — VERIFIED against installed **0.21.1** (2026-06-13, `.venv/bin/python` introspection)
- **Used for:** Struct definitions, schema validation at the bus boundary, `msgspec.to_builtins()` (input to the JCS pipeline), `msgspec.json.schema()` for `RunStarted` descriptors, pre-built `msgspec.json.Decoder` per (kind, version).
- **Verified surface:**
  - `class X(msgspec.Struct, frozen=True)` — mutating a frozen instance raises **`AttributeError`** (`"immutable type: 'X'"`). (Not a custom exception — catch `AttributeError`.)
  - `msgspec.json.Decoder(Type)` then `.decode(bytes) -> Type`; on validation failure raises **`msgspec.ValidationError`** with a JSON path (e.g. `Expected \`int\`, got \`str\` - at \`$.x\``). Malformed JSON raises `msgspec.DecodeError`.
  - `msgspec.json.encode(obj) -> bytes`; `msgspec.json.Encoder`.
  - `msgspec.to_builtins(obj, *, str_keys=False, builtin_types=None, enc_hook=None, order=None) -> builtins` — returns dict/list/scalars. **Raw `bytes` fields become base64 strings** (confirms tech §4.2: forbid inline variable bytes; use schema-declared hex-`str` fields for `bytes16/20/32`).
  - `msgspec.json.schema(Type) -> dict` (JSON Schema, `$ref` + `$defs`, draft 2020-12 shape); `msgspec.json.schema_components([Types]) -> (schemas, components)` for the multi-kind `RunStarted` manifest.
  - `msgspec.convert(obj, Type)` — builtins→Struct (boundary conversion path for frozen Pydantic → Struct).
  - Errors available: `msgspec.ValidationError`, `msgspec.DecodeError`, `msgspec.EncodeError`.
  - Constrained/fixed types: `typing.Annotated[T, msgspec.Meta(min_length=…, max_length=…, ge=…, le=…)]`. *Status: VERIFIED.*

### rfc8785 — VERIFIED against installed **0.1.4** (2026-06-13)
- **Used for:** RFC 8785 (JCS) canonical JSON encoding — the bytes everything hashes over (`B_hash`).
- **Verified surface:** `rfc8785.dumps(obj) -> bytes` (UTF-8, minimal, sorted keys); `rfc8785.dump(obj, io)` writes to a binary file-like. Accepts dict/list/str/int/float/bool/None (tuples→lists). Raises **`rfc8785.CanonicalizationError`** (or subclass) on failure. **Does NOT coerce non-`str` dict keys** — our type whitelist already mandates str keys, and `substrate/encoding.py` enforces the whitelist (int range, finite floats, str keys) BEFORE calling `dumps`, rather than relying on rfc8785 to reject. Pipeline: `obj → msgspec.to_builtins → whitelist check → rfc8785.dumps → bytes`. CI runs the RFC 8785 conformance vectors every commit (an upgrade that changes any byte fails CI). *Status: VERIFIED.*

### Ollama `/api/show` — VERIFIED live 2026-08-25 against local daemon at `127.0.0.1:11434`
- **Used for:** driver context resolution — `session_topology` asks the responder how many tokens the model's window holds so `render_transcript`'s `_compute_k` can size the transcript. Added by sprint 207.5 (this row) ahead of sprint 208 per TECHNIQUE #46: the bridge mapping lands before the code, not folded into the same sprint.
- **Endpoint:** `POST <OLLAMA_BASE_URL>/api/show` with body `{"name": "<tag>"}`. Same `OLLAMA_BASE_URL` env the responder's `/api/chat` reads (defaults to `http://localhost:11434`; the container test arena points it at `host.docker.internal`).
- **Response shape (top-level `model_info` dict):** exactly one `<family>.context_length` key names the driver's window size. Family names are model-family, not tag. Verified against three tags:
  - `POST /api/show {"name":"huihui_ai/qwen2.5-coder-abliterate:7b"}` → `model_info.qwen2.context_length = 32768`.
  - `POST /api/show {"name":"deepseek-v4-flash:cloud"}` → `model_info.deepseek4.context_length = 1048576`.
  - `POST /api/show {"name":"llama3.2:1b"}` → `model_info.llama.context_length = 131072` (per TECH-SPEC §3a note; not re-verified this run but published there).
- **Read rule:** iterate `model_info.keys()`, take the first key ending in `.context_length`, return its int value. Do not hardcode the family prefix — new models bring new prefixes. A tag with no matching key raises `ContextTokensUnknown` (typed), caller falls back to the `~/.substrate/config.toml` `[driver.<name>].context_tokens` value.
- **Rate class:** local daemon path; no provider rate limit. Cache per tag with a 60-second TTL — the value does not change during a session's lifetime; TTL lets a model reload after config change without a session restart.
- **httpx:** lazy import inside the call site (matches the existing responder pattern; keeps `openai-compat` optional-extra).
- **Failure modes:** connection refused (daemon down) → typed `DriverIntrospectionUnavailable` (fallback to config table); 404 (unknown tag) → typed `ContextTokensUnknown`; malformed body → typed `DriverIntrospectionUnavailable`. *Status: VERIFIED.*

### python-ulid, click, rich
- python-ulid: `run_id` generation. click: CLI parsing. rich: terminal output. Document surfaces before the CLI sprints.

---

## SWE-bench external substrates (boundary-as-producer mapping)

*Added 2026-08-12 by Sprint 162 per the 2026-08-12 halt at `BLACKBOARD ## Surfaced for review` (ratified) and roadmap v2 at `docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md`. Six external non-deterministic substrates sit under the SWE-bench assay. Each has a scheduled producer sprint (S5.1 through S5.6, plus S6 for the topology-level grade). This table is the contract: any new SWE-bench code that touches a boundary listed here goes through the corresponding producer once the producer lands; a boundary interaction from anywhere else halts with `bridge_mapping_required` at the runtime. Producer events land on the record; failures become typed events, not exception-handler strings.*

| # | Boundary | Non-determinism | Current defense | Producer (roadmap v2) | Reason string in `_HARNESS_REASONS` on failure |
|---|---|---|---|---|---|
| B1 | LLM via provider (Ollama Cloud) | model latency, model output | `OllamaResponder` + `ModelUsage` event | S5.1 VERIFIED (Sprint 189): every SWE-bench producer that calls a model uses `call_responder_metered` (`repair.py:74`, `localize.py:74`, `localize_elements.py:130`, `reproduction.py:110`) which returns `(text, ModelUsage)` and emits the `ModelUsage` event onto the cell's record. Every rate-limit failure surfaces as a typed exception (`ProviderRateLimited`) the runner catches and maps to `REASON_RATE_LIMITED` on the cell row. `swebench_repair_topology` declares `ModelUsage` in the localizer producer's schema list at `assemble.py:293`; the shared best-of-N drafter declares it via `best_of_n/__init__.py`. Nothing more to do here. | `harness_error` (adapter exception surfaces as `HarnessError`) |
| B2 | Provider rate limits (Ollama tier, OpenAI RPM, ...) | 429/503 throttling, per-model concurrency caps | `RateLimitedResponder` shim at `adapters/rate_limit.py` | S5.2 — `RateLimitProducer` emitting `RateLimitAttempted` / `Granted` / `Denied` / `Retried` | `rate_limited` |
| B3 | Docker daemon | container start, OOM eviction, kill, exec | `run_swebench_one` subprocess + `docker kill` | S5.3 — `ContainerProducer` emitting `ContainerRequested` / `Started` / `Exited` / `Killed` | `container_crashed`, `docker_error` |
| B4 | Docker image registry | image pull, image 404, digest resolution | `verify_constants` at boundary | S5.4 — `ImageProducer` emitting `ImageRequested` / `Pulled` / `Missing` | `harness_error` (image 404) |
| B5 | GitHub for repo clones | bandwidth throttling, parallel-clone contention | mother-clone cache at `swebench_suite.py:_mother_clone` | S5.5 — `RepoCloneProducer` wrapping the cache with typed events | `git_error` |
| B6 | swebench harness subprocess | pytest execution, report parsing, harness raise | `run_swebench_one` wrapping + wall-clock timeout | S5.6 — `HarnessProducer` emitting `HarnessCallFired` / `Completed` / `Timeout` / `Error` (embeds `ContainerProducer`) | `timed_out`, `harness_error`, `container_crashed` |

### Producer-authorship rules

- Every producer declares a `Budget` (from the S1 kernel change; shipped registration-only at Sprint 164, `Cap` struct amendment at Sprint 166). Two axes: `wall_seconds: Cap | None` (max wall-clock from `ProducerStarted` to any terminal, seconds) and `event_counts: dict[str, Cap] | None` (per-emit cap per event kind, keyed by the event's Struct class name). Each `Cap` carries `limit: int | float` and `reason: str`. Concrete patterns: `ContainerProducer` caps `event_counts={"ContainerRequested": Cap(limit=1, reason="one grade container per instance")}`; `HarnessProducer` caps `wall_seconds=Cap(limit=<per-repo-timeout>, reason="per-instance grade budget")` from `assay/swebench_timeouts.json`; `RateLimitProducer` caps `event_counts={"RateLimitAttempted": Cap(limit=<max_retries>, reason="tier's max retry budget")}`. Runtime enforcement lands in the follow-on kernel sprint (roadmap v2 S1b); overrun emits `substrate.BudgetExceeded` and terminates the factory.
- Every producer's typed events carry payload shapes ratified in `signals/swebench-solver-vocabulary.md` § G (v0.3 additions, S0.75).
- Every producer's failure path raises exactly one typed exception carrying a class-level `reason` attribute from `_HARNESS_REASONS`. Callers catch by type; no string-matching on `repr(exc)`.
- Every producer is testable in isolation against a mocked substrate seam (mock-Docker, mock-Responder, mock-git); the tests survive replay via `assert_replayable` on the recorded events.

### Cross-cutting invariants

- No new SWE-bench code catches `BaseException` around a boundary call; every catch handles a typed exception a producer raises.
- No boundary event fires outside its producer once the producer ships. A boundary interaction from anywhere else halts with `bridge_mapping_required` at the runtime.
- The runner (post-S7) contains zero boundary-specific code; it wires the topology, calls `run_suite`, and reads the record.
- Every producer added here is Substrate-level (`src/substrate/adapters/`), not SWE-bench-specific. Future assays that touch Docker, provider rate limits, subprocess-based graders, or GitHub inherit these producers directly.

---

## Primitive-plus-consumer discipline (Sprint 183, external round-2 R7)

*Round-2 review R7 named a pattern: three sprints in a row (164 Budget, 170 RunUnpublishable, 172 Budget UserWarning) landed substrate primitives whose production paths had zero consumers at close time. Each sprint closed clean because the primitive's tests passed; each left the tree with a primitive that exists and does nothing. Under the pre-Sprint-183 dual-contract shape, "primitive lands; consumer follows in a separate sprint the next day" is permitted; the pattern accumulates dead surface area whose consumer sometimes never dispatches (Sprint 170 shipped and its runner-wire waited five sprints for Sprint 177).*

*Sprint 183 tightens the dual-contract at the sprint-card level: every sprint that lands a substrate primitive (a new public class, a new module under `src/substrate/`, a new API-surface field, a new event kind) must EITHER wire a live production consumer in the same sprint OR name the sprint that will, with a card number filed alongside the primitive's own card.*

**The rule.** A sprint whose `artifact contract → files created` adds a new public type / module / function / event kind must name in `notes` one of:

1. **In-sprint consumer.** The same sprint contains a modification to a non-test source file that consumes the primitive in a production path. The card asserts the consumer exists.
2. **Named next-sprint consumer.** The card names the sprint id + slug that will wire the consumer. That sprint card exists on disk (status: `pending` at minimum) before this primitive-adding sprint closes. The consumer sprint dispatches within one working session of the primitive sprint's close.

**What counts as a consumer.** A production code path (a file under `src/substrate/`, `scripts/`, or elsewhere on the runtime graph) that invokes the primitive under normal operation. Tests do not count. Documentation does not count. A `notes:` mention with no code binding does not count.

**Why the rule.** A primitive without a consumer is unrefuted design. The tree grows surface area whose only proof of correctness is unit tests against invented inputs. When the consumer finally dispatches (if it does), it may reveal the primitive's shape was subtly wrong for the real path; each intervening sprint that touches the primitive under the "tests pass, ship it" discipline accretes error the consumer sprint has to unwind. The primitive-plus-consumer rule catches the mismatch at the earliest possible sprint boundary.

**Grace clause.** A kernel primitive that requires runtime enforcement (Sprint 164's `Budget` needing Sprint 165 runtime enforcement) may split across two sprints when the split is honestly at the ≤2-file boundary AND the enforcement sprint is named on the primitive sprint's card. Sprint 172's UserWarning was the right shape for the interim — the interim carries a build-time observable that names the missing consumer. Any interim exceeding one working session escalates to a halt.

**What Sprint 183 does not change.** Every existing primitive sprint stays closed under its original discipline. The rule applies to sprints dispatching after Sprint 183's ratification.

---

## Vocabulary discipline overrides

- **Validator-extras posture:** **strict.** Payload fields not declared in the schema raise at emit time (emission becomes `substrate.ProducerEmittedInvalidEvent` with reason `non_canonical_value`/`schema_violation`). Rationale: matches the substrate's own product principle 4 — bus-boundary validation is *mandatory and non-configurable*; a documentation-only posture would contradict the product the project ships.
- **View-payload-universal convention:** the substrate has no `view` *category* in the UI sense — Views are runtime projections, not rendered scenes. The dual contract's "view-side counterpart" maps instead to **the run record on disk**: every behavior tag's effect must be reconstructable from the persisted log (replay Level 1/2). The dual-contract audit (BOOTSTRAP Step 9) pairs each behavior tag with a record-observable assertion (a sequenced event + a `view_at`/`decisions_between` reconstruction), not a screen element. Documented in the rationale doc.
- **Reserved namespace:** kernel/control-plane kinds use the `substrate.` prefix (F-OBS-5); Producer-declared kinds MUST NOT collide. The vocabulary JSON marks each tag's namespace.
- **Vocabulary location:** `process/signals/0.2.json` (active locked vocabulary; `process/signals/0.1.json` retained as the v0.1 audit trail, no deletions). Rationale docs: `process/signals/0.2-rationale.md` (+ founding `process/signals/0.1-rationale.md`). Open/ratified proposals: `process/signals/proposals.json`.

---

## Build and verification commands

*The Architect runs these; the Agent does not silently retry failed builds (reports exit code + last 200 lines).*

- **THE DEFAULT GATE (Architect ruling 2026-07-22): `scripts/ci_local.sh`** — the exact CI stack (ruff check, format --check, strict mypy, pytest, lint-imports, conformance --no-perf) across py3.12/3.13/3.14 in isolated envs, locally. Hosted GitHub Actions is unavailable (minutes exhausted) and the verification bar must never depend on a hosted runner: "gates green" = this script exiting 0, watched to conclusion (the finding-33/36 bar, local form). `scripts/ci_local_ubuntu.sh` covers the linux axis via Docker. When Actions returns it becomes a backstop, not the bar.
- **Primary build / test:** `uv run pytest` — expected exit 0
- **Release gate:** `uv run substrate conformance` (the 17 checks) — expected exit 0
- **Type gate (public API):** `uv run mypy --strict` — expected exit 0
- **Lint/format:** `uv run ruff check` / `uv run ruff format --check` — expected exit 0
- **Perf floor (N-PERF-1, as amended by A2.1):** the reference-shape append-rate probe — **≥40K appends/sec** (recalibrated from 100K, which was derived from a prototype that didn't measure the required canonical encoding; measured ~56K, floor at a ~28% margin); ≤20% regression vs previous release tag (conformance check 15)
- **Canonical-encoding stability:** RFC 8785 conformance vectors — byte-identical, every commit

---

## Observation contract environment

*Substrate has no UI/simulator. The "observation" surface is the run record on disk + the CLI reading it. Behavior-touching sprints (writer cycle, replay, record, attach, CLI) declare an observation contract whose driving step runs a topology (or a recorded fixture) and whose assertions are: expected sequenced events in the JSONL trace, expected `assert_event`/`assert_sequence` results, expected exit code, expected `replay --level N` outcome, expected `inspect`/`tail` output substrings. Tools: `pytest`, the CLI subcommands, `assert_event`/`assert_no_event`/`assert_sequence` (tech §15), and a confirmed-good run record as a regression fixture (F-API-4 / technique 38).*

---

## Hand-author authorization log

*Per AGENTS.md hard rule 10. Explicit hand-authorizations logged here.*

- None to date.

---

## Tone canon (CLI / error strings)

The substrate's user-facing strings (CLI output, error messages, `tail`/`inspect` lines) follow the design spec's structured-output discipline:

- **Structured output everywhere; never natural language from the runtime.** `explain_producer` returns a typed `Explanation`, not prose. Errors carry typed fields (`error_kind`, `at_path`, `sequence`).
- **Sequence numbers everywhere identification happens.** "At seq 1247" — never "around the third trigger."
- **Vocabulary discipline (product principle 6 / design §2):** the eight words (Producer, Bus, View, Predicate, Trigger, Route, TerminationPolicy, Topology) and no anthropomorphic synonyms ("agent", "actor", "speaker") and no marketing REFRAMES OF SUBSTRATE'S OWN CONCEPTS (a topology as a "workflow", a firing as a "step", a run as a "task"). This applies to docs, CLI output, log fields, AND code identifiers. (Narrowed 2026-08-07, review S-5, per the C-6 ruling in `## Decisions`: the ENGLISH word "task" for the problem an agent solves is the input domain, not a reframe — it is FINE; only reframing substrate's own primitives is banned.)
- **No emoji** (kit tone canon + design spec). Registration errors follow the design §6.1 shape: where → one-line summary → what's wrong → upstream constraint → inline fix.
- Tonal constraints bind Layer 7 (Evidence) for any payload field carrying user-visible strings.

---

## Custom techniques (project-specific orchestration, layered on top of the kit)

*The Architect mandated maximal use of parallel agent teams and worktree isolation. The kit defers these to TECHNIQUES Section 3 ("compose with any orchestrator"); they are NOT in the kit canon, so they live here as project techniques. They sit ON TOP of the kit discipline and never bypass it: the dual contract, the Rubber Duck Pass, the vocabulary lock, and hard rule 10 (no silent hand-author) still gate every close.*

- **CT-1 — Parallel subagent teams (fan-out → synthesize → adversarially verify).** Decomposable work (research strands; per-subsystem vocabulary drafting; per-dimension review) is fanned out to concurrent subagents, synthesized by the Supervisor hat, then adversarially verified by independent agents before anything lands. Pattern: Workflow `pipeline`/`parallel`. Apply when the work-list is independent and the conclusion (not the file dumps) is what matters.
- **CT-2 — Originals over summaries for every spawned agent (hard rule 11, enforced).** Every subagent prompt transmits *file paths to read* (the kit foundations/grammar/TECHNIQUES, the canonical specs, the locked vocabulary) — never my summary of them. An agent that hasn't read the originals for its slice halts. This is the load-bearing transmission discipline; summary-induced drift is the documented failure mode.
- **CT-3 — Per-sprint git worktree isolation for parallel implementation.** When two or more implementation sprints touch file-disjoint slices and could run concurrently, each runs in its own git worktree (`Agent` `isolation: "worktree"`) so parallel file mutation can't conflict; results merge back via the Architect's integration-manager review (technique 21). Worktrees are EXPENSIVE and only used when agents genuinely mutate files in parallel — NOT for read-only research or for sprints that return structured proposals to the Supervisor (Sprint 0 is the latter: no worktrees needed). Requires git (initialized).
- **CT-4 — Best-of-N for high-stakes architecture sprints.** For architecture-band sprints establishing load-bearing contracts (encoding, writer cycle, record format), generate N independent candidate implementations from different angles, score against the dual contract + conformance checks, synthesize from the winner grafting the best of runners-up. Deferred-in-kit (Section 3); used here because the substrate's contracts are conjunctive and a wrong contract is expensive. Never lands a candidate that fails its dual contract.
- **CT-5 — Conformance-check-as-acceptance-spine.** The 17 conformance checks (product §7) and R-1..R-3 (§8) are the project's integration proofs. Every implementation wave ends with an N.INT sprint asserting the relevant checks pass end-to-end (technique 16). Each conformance check maps to the sprints that satisfy it (tech §21 table is the seed).

---

## Sprint cadence policy

- **Phase 0 (Vocabulary Session):** plan-mode (Architect drives; ratifies the locked vocabulary + rationale).
- **Phase 1+ (implementation):** **auto-within-phase (Architect directive 2026-06-13: "keep going autonomously, parallelize as much as possible, never make stuff up, stop and research if any issues, refer to the original docs").** The Agent dispatches Wave/sprint chains without per-card go-ahead, surfacing to BLACKBOARD only on a genuine halt (spec ambiguity, unverifiable API, dual-contract fail, vocabulary-change-required). Discipline unchanged: author against the locked vocabulary + canonical specs; verify external API surfaces from their real docs before use (bridge-mapping-required halt if undocumented); dual contract + Rubber Duck Pass at every close; never invent vocabulary or APIs.

---

## Project-specific halt conditions

*In addition to AGENTS.md base halts.*

- `spec_ambiguity` — a sprint needs a semantic the canonical specs underspecify (vs. a vocabulary gap). Surface with the exact spec section + the ambiguity. Resume: Architect rules, or cuts a spec revision (specs are revised additively — new draft, prior preserved).
- `conformance_unmapped` — a sprint's artifact is needed by a conformance check but no sprint chain yet covers that check end-to-end. Surface for wave re-planning.

---

*process/WORKING_AGREEMENT.md for Substrate. Project class backend/library + CLI. Strict validator-extras. Orchestration (teams + worktrees + best-of-N) layered on top of the kit as project techniques CT-1..CT-5, never bypassing the dual contract or vocabulary lock. Canonical specs: kernel v15, product DRAFT 7, technical DRAFT 5, design DRAFT 1.*

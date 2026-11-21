# ROADMAP v2 — SWE-bench rebuild: boundaries as producers

*Second version. `ROADMAP-2026-08-12-swebench-rebuild-sprint-chain.md` is v1 on
disk. v2 folds in the design pass named by the 2026-08-12 halt at
`process/BLACKBOARD.md ## Surfaced for review` and ratified by the Architect: every
SWE-bench external boundary becomes a substrate producer emitting typed events on
the record. The halt's diagnosis is that the runner grew to 972 lines because five
external systems each got an `except`-branch instead of a producer; the fix is
not "fold the exception-handlers into helpers" but "productize each boundary so
the exception-handlers disappear." v2 is longer than v1 (14 sprints instead of 10)
because the fix is deeper. It is also cleaner: every failure lands on the record,
`first_divergence` works across runs, `narrate` renders the grade path in
vocabulary, and the runner shrinks to a topology assembler around `run_suite`.*

*Reviewer role. Build side dispatches. Sprint cards in `process/sprints/`.*

*Companion documents:
`docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md` (technical
divergence record without positioning framing),
`AUDIT-2026-08-12-substrate-usage-in-swebench-work.md` (Substrate-primitive
gap analysis), the 2026-08-12 halt (the shim-collapse evidence that made
the design pass unavoidable). Sprint 184 (external round-2 M2) removed
`PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md` from the
authority list — the paper is a position document per its own status note,
retained on disk per hard rule 12 but no longer cited as diagnosis
authority.*

*Date: 2026-08-12. Sprint 161 (v1's Sprint 0) already landed; vocabulary v0.2 is
RATIFIED. This roadmap starts from that clean base.*

---

## What v2 changes from v1

v1's Sprint 6 said: *rewrite the confirmatory runner around `run_suite` and fold
generic pieces into `assay/run.py`*. v1 kept the six external boundaries defended
by exception-handlers, shims, gates, and caches — one per boundary, each grown
sprint-by-sprint when a failure surfaced.

v2 says: every external boundary becomes a substrate producer. The producer's
`start(input) -> AsyncIterable[Event]` yields typed events onto the record.
`ContainerRequested → ContainerStarted → ContainerRunning → ContainerExited`
replaces the `docker run --rm` subprocess plus its `try/except` wrapper.
`RateLimitAttempted → RateLimitGranted | RateLimitDenied → RateLimitRetried`
replaces the semaphore-plus-Retry-After loop that pinned slots and collapsed
throughput at N=300 Pro. The grade itself becomes a producer inside the topology,
emitting `GradeResult(verdict, reason)`; the oracle collapses to a
`LogProjectionOracle` reading one event off the record. `ExternalGraderOracle`
retires from the SWE-bench path.

Consequences:
- The runner drops from 972 lines toward roughly 350–400. Sprint 181 (R4 fold)
  corrects an earlier claim of ~150 lines: an honest line count separates
  boundary except-branches (which producer-authoring absorbs) from env parsing
  (~50 lines), arm building (~140), prep sweep (~90), image pre-pull (~30),
  cases sidecar writer (~30), config fingerprint + preregistration wiring
  (~40), the cell inner function (~90 even without boundary handling), row
  writer + JSONL append + progress printout (~30), the `_run` outer function
  + salvage + batch-grade paths (~80). Roughly 580 lines survive under any
  redesign that keeps the runner's job. The producer-authoring absorbs the
  boundary handling; the ~350–400 target credits that reduction honestly and
  keeps the number defensible against a line count after the redesign lands.
- Every boundary failure lands on the record. `first_divergence` between the
  June 27 run and the current run reads the exact producer where they diverge.
  `attach` / `LiveRecord` can observe rate-limit denials in flight.
  `narrate` renders "Container `substrate-grade-abc123` requested; ImagePulled;
  HarnessCallFired; HarnessCompleted with verdict=FAIL, reason=`` empty" as prose.
- The AUDIT of the grade becomes replayable at Level 1 (record-derivable).
  Sprint 181 (R3 fold) corrects an earlier "grade replayable at L1" claim:
  what becomes L1-replayable is the recorded `GradeResult` event — a reader
  who `read_record()`s the cell reconstructs the verdict deterministically.
  The GRADE ITSELF (pytest inside Docker) remains non-deterministic; two
  identical patches graded twice may still produce different `report.json`
  outcomes on rare pytest-side flake. The genuine win is post-hoc audit:
  `explain_producer` walks a `GradeResult` back through the `HarnessProducer`
  events and pinpoints WHERE the divergence lives (repro test flake, harness
  timeout, container OOM), which was invisible under the pre-producer
  external-grader shape. Roadmap v2 markets audit-replay, not grade-replay.
- Every future assay that touches Docker, provider APIs, or subprocess-based
  graders inherits these producers. The work is Substrate-level, not
  SWE-bench-specific.

v2 keeps every preserved contract from v1's keep-list (the applier, the firewall
parser, the mother-clone cache, the pre-registration hashes, the tests). The
mother-clone cache stays as a data structure the `RepoCloneProducer` reads;
the tiered-match applier stays exactly. The evolution is at the boundary layer.

---

## The dependency graph (v2)

```
S0 vocab v0.2 (LANDED) ──── S0.5 bridge mapping ──── S0.75 vocab v0.3 (boundary events)
                                                            │
                                                            └── S1 producer_kind Budget primitive
                                                                    │
                                    ┌───────────────────────────────┼─────────────────────┐
                                    │                               │                     │
                                    S2 topology dual-mode +         S5.1 LLM (already      │
                                    bundled.py + CI record          productized; verify)   │
                                            │                               │              │
                                            S3 embedded_substrate           S5.2 RateLimit  │
                                            best-of-N sub-topology          Producer        │
                                                    │                               │       │
                                                    S4 repair nests sub                     │
                                                                                    S5.3 Container Producer
                                                                                            │
                                                                                    S5.4 Image Producer
                                                                                            │
                                                                                    S5.5 RepoClone Producer
                                                                                            │
                                                                                    S5.6 Harness Producer
                                                                                            │
                                                                                    S6 Grade as producer +
                                                                                    LogProjectionOracle
                                                                                            │
                                                                                    S7 runner shrinks around
                                                                                    run_suite
                                                                                            │
                                                                                    S8 per-cell budget
                                                                                            │
                                                                                    S9 wire-check N=300 Lite
                                                                                            │
                                                                                    S10 Verified pass 1
```

S0.5, S0.75, S1 gate the whole chain. S2 gates S3. S3 gates S4. S5.1-S5.6 run in
parallel once S0.75 + S1 land. S6 gates S7. S7 gates S8. S8 gates S9. S9 gates S10.

**Total: 14 sprints.** At SDD pace (mechanical sprints half-day; architectural
sprints one day), roughly 10-12 working days.

---

## Sprint 0 — Vocabulary v0.2 consolidation (LANDED 2026-08-12)

`process/signals/swebench-solver-vocabulary.md` flipped to `RATIFIED — v0.2`;
§ E adds Verdict enum + `_HARNESS_REASONS` closed set; § F carries signatures.
Sprint 161 card at `process/sprints/sprint-161-swebench-vocabulary-v02-ratification.md`.
Architect ratification pending in `## Decisions`.

---

## Sprint 0.5 — Bridge mapping for the six external boundaries

**Duration.** One hour.

**Rule.** AGENTS.md § "bridge_mapping_required" — every external substrate the
project touches at runtime appears in `WORKING_AGREEMENT.md`, with defense
status and scheduled work.

**Files touched.**

- `process/WORKING_AGREEMENT.md` — add "SWE-bench external substrates" section.

**Content — six boundaries.** For each, name: shape of non-determinism;
current defense; scheduled producer sprint; failure mode → typed event on
the record; reason-string mapping to `_HARNESS_REASONS`.

| # | Boundary | Current defense | Producer sprint |
|---|---|---|---|
| B1 | LLM via provider (Ollama Cloud) | `OllamaResponder` + `ModelUsage` event | S5.1 (verify) |
| B2 | Provider rate limits | `RateLimitedResponder` shim | S5.2 (recast as producer) |
| B3 | Docker daemon | `run_swebench_one` subprocess + `docker kill` | S5.3 |
| B4 | Docker image registry | `verify_constants` at boundary | S5.4 |
| B5 | GitHub for repo clones | mother-clone cache | S5.5 |
| B6 | swebench harness subprocess | `run_swebench_one` timeout enforcement | S5.6 |

**Observation contract.** Every external boundary the runner touches at
runtime appears in this section; every unshipped producer has its S5.x sprint
number here.

---

## Sprint 0.75 — Vocabulary v0.3 (boundary events)

**Duration.** Half a day.

**Rule.** grammar/BOOTSTRAP.md § "Layer 1 (Lexical) — name the tags per entity"
applied to the six boundaries as new entities.

**Files produced or modified.**

- `process/signals/swebench-solver-vocabulary.md` — modify. Add § G (v0.3
  additions: boundary event tags).

**Tags to lock — per boundary.**

| Boundary | Tags | Payload shape (canonical) |
|---|---|---|
| B2 rate limits | `RateLimitAttempted`, `RateLimitGranted`, `RateLimitDenied`, `RateLimitRetried` | provider, model, wait_ms, attempt_n, retry_after_ms |
| B3 Docker container | `ContainerRequested`, `ContainerStarted`, `ContainerExited`, `ContainerKilled` | container_name, image, cmd, exit_code, wall_ms |
| B4 image | `ImageRequested`, `ImagePulled`, `ImageMissing` | image, digest, wall_ms |
| B5 repo clone | `RepoCloneRequested`, `RepoCloned`, `RepoCloneCached` | repo, base_commit, cache_hit, wall_ms |
| B6 harness | `HarnessCallFired`, `HarnessReportRead`, `HarnessCompleted`, `HarnessTimeout`, `HarnessError` | instance_id, wall_ms, report_path, verdict, reason |
| Grade (topology-level) | `GradeResult` | verdict: `PASS \| FAIL \| NO_VERDICT`, reason: str from `_HARNESS_REASONS` |

**Vocabulary invariants.**

- Every `HarnessCallFired` precedes exactly one of `HarnessCompleted`,
  `HarnessTimeout`, `HarnessError` on the same record.
- Every `ContainerRequested` precedes exactly one of `ContainerStarted` or a
  `ContainerKilled` / `DockerDaemonError`.
- `RateLimitGranted` follows zero or more `RateLimitDenied` + `RateLimitRetried`
  pairs, terminating at `RateLimitGranted` or `ProviderRateLimited` (exception,
  retries exhausted).
- Exactly one `GradeResult` per cell record after the `SelectedPatch`.

**Signal contract.** No runtime emits from the vocabulary sprint itself.

**Observation contract.** Every planned producer at S5.x has its declared
events named here with payload shapes matching what the producer at S5.x will
emit. Grep-verifiable.

**Dispatches after Sprint 0.5's bridge mapping ratifies** (so the boundary
scope is signed off before the events are named).

---

## Sprint 1 — Kernel: `producer_kind` `Budget` primitive

**Duration.** One sprint.

**Files touched.**

- `src/substrate/kernel/topology.py` — add optional `budget: Budget` kwarg.
- `src/substrate/api.py` — export `Budget`, `BudgetExceeded`.

**Contract.** `Budget(docker_containers=(2, "reason"), wall_seconds=(600, ...),
model_calls=(6, ...))`. Runtime enforces at run time; overrun emits typed
`substrate.BudgetExceeded` and terminates the producer factory. Existing
producers without a `budget` behave identically.

Every S5.x producer sprint declares its budget. `ContainerProducer` declares
`docker_containers=(1, "per-instance grade")`. `HarnessProducer` declares
`wall_seconds` from the per-repo timeout table. `RateLimitProducer` declares
`model_calls` based on the tier.

---

## Sprint 2 — Repair topology: dual-mode + `bundled.py` + CI record

Unchanged from v1. Half a day. Fills the four gaps between
`swebench_repair_topology` at `assemble.py:257` and a correct topology per
`adding-a-topology.md`: dual-mode default responder, `bundled.py` registration,
committed CI record, substance test asserting `SelectedPatch` and
`assert_replayable`.

---

## Sprint 3 — `embedded_substrate` best-of-N + correction sub-topology

Unchanged from v1. One to two days. `topologies/best_of_n_with_correction/`
factored once, consumed by `swebench_solver`, `coding_flow`, `code_evolution`.

---

## Sprint 4 — Repair topology nests the sub-topology

Unchanged from v1. One sprint. `swebench_repair_topology` replaces inline
drafter/validator/judge/selector wiring with an `embedded_substrate` call.

---

## Sprint 5.1 — B1 (LLM) — verify existing productization

**Duration.** One hour.

**Rule.** B1 is already a producer via `OllamaResponder` + `ModelUsage` event.
This sprint verifies the shape matches v2's discipline, adds nothing.

**Files touched.**

- `docs/review/AUDIT-2026-08-12-substrate-usage-in-swebench-work.md` — modify.
  Add a note under § 1.1 confirming B1's producer status.

**Verification.** Grep the topology's record for `ModelUsage` events; assert
one per model call. No new code.

---

## Sprint 5.2 — B2 (rate limits) — RateLimitProducer

**Duration.** Two sprints (one full day).

**Rule.** The 2026-08-12 N=300 Pro halt evidence: `RateLimitedResponder` at
`adapters/rate_limit.py` acquires the semaphore around the entire retry loop,
pinning the slot during 429 sleeps and producing positive-feedback throughput
collapse. The fix moves the retry-and-back-off logic OUT of a `Responder`
wrapper and INTO a substrate producer that emits typed events, with the
semaphore held only during the actual in-flight call.

**Files touched.**

**Sprint 5.2a — the producer.**
- `src/substrate/adapters/rate_limit_producer.py` — new (~200 lines). Defines
  `RateLimitProducer` implementing the `Producer` protocol. Its `start(input)`
  yields `RateLimitAttempted` → (optionally) `RateLimitDenied` +
  `RateLimitRetried` → `RateLimitGranted`, then delegates to the wrapped inner
  `Responder`. Semaphore is acquired only around the inner call, released
  during retry sleeps.
- `tests/test_rate_limit_producer.py` — new. Substance tests:
  (a) three-worker pileup no longer collapses to 1/3 throughput under sustained
  429; (b) `Retry-After` header honored; (c) `ProviderRateLimited` raised typed
  after retry exhaustion; (d) the emitted events survive replay.

**Sprint 5.2b — the migration.**
- `src/substrate/adapters/__init__.py` — modify. Export the producer alongside
  the legacy `RateLimitedResponder`.
- `src/substrate/assay/swebench_matrix.py` — modify. Every arm's responder
  construction wraps in the producer, not the shim.
- `src/substrate/adapters/rate_limit.py` — modify. Deprecation notice at
  module top; body preserved for the audit trail per hard rule 12.

**Signal contract.** Emits `RateLimitAttempted`, `RateLimitGranted`,
`RateLimitDenied`, `RateLimitRetried` per event surface at S0.75.

**Observation contract.** Live smoke against Ollama Pro at N=30: throughput
holds at ≥3 in-flight requests per model; event stream shows the retry
choreography; slot no longer pinned during 429 sleep. Compare to the
2026-08-10 baseline (N=30 wire-check that masked the collapse).

**Preserved.** The `OllamaQuota` classmethods (`free`, `pro`, `max_tier`,
`local`) stay — data descriptors for the tier limits, reused by the producer.

**Removed.** Nothing yet; deprecation lands S7.

---

## Sprint 5.3 — B3 (Docker daemon) — ContainerProducer

**Duration.** One sprint.

**Files touched.**

- `src/substrate/adapters/docker_producer.py` — new. `ContainerProducer(image,
  cmd, timeout)` implementing `Producer`. `start(input)` yields
  `ContainerRequested` → `ContainerStarted` → (waits) → `ContainerExited(exit_code)`
  or `ContainerKilled(reason)`. Owns container lifecycle via `subprocess.run(...,
  timeout=T)` + `docker kill` on `TimeoutExpired`.
- `tests/test_docker_producer.py` — new. Mock-Docker tests for start/exit/kill;
  live smoke against a running daemon.

**Signal contract.** Emits `ContainerRequested`, `ContainerStarted`,
`ContainerExited`, `ContainerKilled` per S0.75 schemas.

**Observation contract.** Every SWE-bench grade call goes through this
producer post-S6; every container spawn appears on the record; `docker ps`
shows no orphaned containers after any run terminates.

---

## Sprint 5.4 — B4 (image registry) — ImageProducer

**Duration.** Half a sprint.

**Files touched.**

- `src/substrate/adapters/image_producer.py` — new. `ImageProducer(image)`
  yields `ImageRequested` → `ImagePulled(digest)` or `ImageMissing(status)`.
- `tests/test_image_producer.py` — new.

**Signal contract.** Emits `ImageRequested`, `ImagePulled`, `ImageMissing`.

**Observation contract.** Runner pre-flight now uses this producer to verify
every declared instance image before Sprint 6 dispatches. Missing images halt
with typed events on the record, not string-match log parsing.

---

## Sprint 5.5 — B5 (GitHub clones) — RepoCloneProducer

**Duration.** Half a sprint.

**Files touched.**

- `src/substrate/adapters/repo_clone_producer.py` — new. Wraps the existing
  mother-clone cache at `assay/swebench_suite.py:_mother_clone`. Yields
  `RepoCloneRequested` → `RepoCloned(path)` or `RepoCloneCached(path)`.
- `tests/test_repo_clone_producer.py` — new.

**Signal contract.** Emits `RepoCloneRequested`, `RepoCloned`,
`RepoCloneCached`.

**Preserved.** The `_mother_clone` cache stays exactly. The producer wraps
around it; the cache stays a data structure the producer reads.

---

## Sprint 5.6 — B6 (swebench harness) — HarnessProducer

**Duration.** One sprint.

**Files touched.**

- `src/substrate/adapters/harness_producer.py` — new. `HarnessProducer(instance_id,
  patch, image, timeout)`. `start(input)` yields `HarnessCallFired` → (waits) →
  `HarnessCompleted(verdict, reason)` or `HarnessTimeout` or
  `HarnessError(exc_class)`. Uses `ContainerProducer` internally as an
  `embedded_substrate` — the harness call IS a container run plus a report read.
- `tests/test_harness_producer.py` — new. Substance tests: gold patch produces
  `HarnessCompleted(verdict=PASS)`; empty patch produces
  `HarnessCompleted(verdict=FAIL)`; missing image produces
  `HarnessError(reason="harness_error")`; timeout produces `HarnessTimeout`.

**Signal contract.** Emits `HarnessCallFired`, `HarnessReportRead`,
`HarnessCompleted`, `HarnessTimeout`, `HarnessError`.

**Observation contract.** Every grade call goes through this producer post-S6;
the gold-differential test at `tests/test_assay_swebench_harness_binding.py`
verifies it produces the same result as the pre-S6 `run_swebench_one` call.

---

## Sprint 6 — Grade as producer + LogProjectionOracle

**Duration.** One sprint (architectural).

**Rule.** With every boundary productized, the grade lives inside the topology
as one more producer. The oracle reads a single event off the record.

**Files touched.**

- `src/substrate/topologies/swebench_solver/assemble.py` — modify. A new
  `swebench_solve_and_grade_topology` wraps `swebench_repair_topology` and
  adds a `HarnessProducer`-triggering trigger on `SelectedPatch`. Emits one
  `GradeResult` per cell.
- `src/substrate/assay/swebench.py` — modify. Add
  `swebench_log_projection_oracle` returning `LogProjectionOracle` that reads
  `GradeResult` off the record. `SwebenchRecordOracle` at line 380 marked
  deprecated (retires with the runner rewrite at S7).

**Signal contract.** Emits `GradeResult` per S0.75 schema.

**Observation contract.** Runs of the same instance produce byte-identical
records at L1/L2 (the grade is now derivable from the record;
`assert_replayable` passes). `explain_producer` on `GradeResult` walks back
to the harness producer, to the container producer, to the patch.

**Preserved.** Every SWE-bench boundary defense at the file level;
`_HARNESS_REASONS` closed set exactly. The oracle taxonomy at `assay/oracle.py`
gains one more `LogProjectionOracle` consumer.

**Removed.** Nothing yet; `SwebenchRecordOracle` and `ExternalGraderOracle`
usage from the SWE-bench path retires at S7.

---

## Sprint 7 — Runner rewrite around `run_suite`

**Duration.** Two sprints.

**Rule.** With every boundary as a producer and grade as record projection,
the runner has almost nothing to do.

**Files touched.**

**Sprint 7a — extend `assay/run.py`.**
- `src/substrate/assay/run.py` — modify. Add `run_suite_with_salvage`,
  `PerCellBudget`, sidecar-writer plumbing. `CellSource` enum unified.

**Sprint 7b — rewrite the runner.**
- `scripts/assay_swebench_confirmatory.py` — replace. Roughly 350–400 lines around
  a `run_suite_with_salvage` call. Every env flag preserved. The 972-line
  version moves to `scripts/_deprecated/` with a KIT_DIARY entry per hard rule
  12.
- `tests/test_assay_swebench_runner_thin.py` — new. Asserts runner is under
  200 lines and every branch delegates to a `run_suite` helper or a
  SWE-bench-specific module.

**Signal contract.** No new emits at the runner level.

**Observation contract.** The runner script's line count drops below 200.
Every current env flag preserved. The CI record for a Lite-3 dry run matches
the pre-rewrite output shape at the cell-row level.

**Preserved.** Every current env flag; every current cell-row field name;
every current arm output.

**Removed.** The 665 lines of runner-as-exception-handler. `SwebenchRecordOracle`
and `ExternalGraderOracle` usage from the SWE-bench path.
`RateLimitedResponder` (superseded by `RateLimitProducer`; body retained under
`_deprecated/` per hard rule 12).

---

## Sprint 8 — Unify three timeout regimes into one per-cell budget

Unchanged from v1. Half a sprint. `PerCellBudget` derived from the per-repo
timeout table, applied at one enforcement point in `run_arm_on_case`. Every
boundary producer inherits the budget via the `Budget` primitive from S1.

---

## Sprint 9 — Wire-check on Lite at N=300, observation contract per H-4

Unchanged from v1 in shape; the observation contract gets tighter because now
it can name boundary events by tag.

**Duration.** Wall-clock several hours.

**Observation contract additions on top of v1's.**

- Every cell record contains: one `SelectedPatch`, one `HarnessCallFired`,
  one `HarnessCompleted`, one `GradeResult`. Absence of any halts with typed
  reason.
- `RateLimitDenied` count per cell logged; no cell should have >10
  `RateLimitDenied` events (a signal the tier is overloaded).
- `ContainerKilled` count = 0 (no orphaned containers).
- **Sustained rate-limit bound (Sprint 174, external F12 fold).** Rolling
  `RateLimitDenied` rate over any 30-minute window during the sweep must not
  exceed 20 percent of the provider's declared tier capacity — i.e.,
  `RateLimitDenied / total_RateLimitAttempted < 0.20` in every 30-minute
  slice. A run that crosses the threshold triggers the publish-refusal
  branch (Sprint 170) and dumps a per-model-per-minute denial curve to the
  report for the postmortem's starting fixture. This bound complements the
  per-cell `>10 RateLimitDenied` alarm above — a per-cell alarm catches one
  wedged cell; the sustained bound catches the tier-saturation pattern
  KIT_DIARY 39 named (300 cells × 10 denials × ~30 minutes ≈ 100 denials
  per minute, the exact 82-percent-throttle shape the 2026-08-10 halt
  described). The bound is a numeric floor the observation contract reads
  directly from the recorded events; no separate telemetry pipeline needed.

---

## Sprint 10 — Verified pass 1, ensemble arm only

Unchanged from v1 in scale (500 instances × 1 trial × 1 arm). Sprint 185
(external round-2 R5 fold) tightens the pre-registration's statistical
specification before this sprint dispatches.

**Statistical spec the pre-reg must pin before S10 dispatches (R5 fold).**
Design v3 waved at "three-trial McNemar" without naming the pairing unit
or the exact test statistic. The user's memory item at
`project-benchmarking-power-reality` names the class of trap:
"bit-collapse+McNemar is conservative not inflated; pass^k vs pass@k trap."
S10's pre-registration must therefore pin:

- **Pairing unit.** Instance-level, not trial-level. For each of the 500
  instances, the ensemble arm's pass^k-collapsed outcome (cell) pairs with
  the compute-matched baseline arm's cell on the same instance. b = control
  passed, arm failed; c = control failed, arm passed; discordant pairs
  drive the statistic. Same shape as `assay/report.py:build_report`'s
  paired-McNemar branch (line ~407).
- **Test statistic.** McNemar's exact binomial on (b, c) — the two-sided
  probability that under the null (b ~ Binomial(b+c, 0.5)) the observed
  discordance is at least as extreme. Preferred over the χ² approximation
  at the sample sizes Verified produces (500 instances → discordant pair
  count likely <100). `assay/report.py::exact_mcnemar_p` at line 34 is the
  shipped implementation; S10 uses it verbatim.
- **Primary endpoint currency.** Δ-pass^k with k=1 (pass@1 collapse). The
  currency lives on `ArmReport.delta_pass_k`; the CI + equivalence verdict
  come from the paired two-level bootstrap at
  `assay/stats.py::bootstrap_delta_pass_k`, seed pinned in the pre-reg.
  McNemar's p is a secondary cross-check; the primary claim runs off the
  bootstrap's TOST verdict + BH-FDR across the arm matrix.
- **What Pass 1 does not test.** Trial-level variance decomposition
  (pass^k vs pass@k) is out of scope for Pass 1. Pass 2's trial structure
  (matrix arms + 3 trials at N=500 in the original v3 shape) is where the
  variance decomposition lives; the pre-reg for Pass 2 names it there.
- **Grace clause for zero discordant.** `assay/stats.py::equivalence_verdict`
  already falls back to `zero_discordant` (see the Sprint 150 note in the
  close-the-loop roadmap round 3); Pass 1's pre-reg inherits that fallback
  verbatim.

Before S10 dispatches, `docs/preregistrations/2026-08-swebench-verified.preg.json`
(new file for Pass 1) carries a `statistical_spec` block naming every value
above with a citation to the code line the runner reads. The pre-registration
gate at `assay/preregistration.py::load_preregistration` refuses to admit
a pre-reg missing the block (a follow-on to Sprint 170's `graded_rate_floor`
gate; same shape).

---

## What each producer costs

A rough size estimate per producer, from precedent (existing adapters +
similar-shape producers in `topologies/`):

| Producer | Est. lines | Key primitives |
|---|---|---|
| RateLimitProducer | ~250 | asyncio.Semaphore + Retry-After parser + typed events |
| ContainerProducer | ~200 | subprocess.run + docker kill + typed events |
| ImageProducer | ~120 | docker manifest inspect + typed events |
| RepoCloneProducer | ~100 | wraps existing _mother_clone + typed events |
| HarnessProducer | ~200 | subprocess.run + report parse + typed events + uses ContainerProducer as embedded_substrate |

Total ~870 lines of new producer code plus tests. Replaces ~665 lines of
runner-as-exception-handler plus 200 lines of `RateLimitedResponder` plus 90
lines of `run_swebench_one`. Net roughly break-even on line count, and every
line is on the record instead of off it.

The Substrate under any future assay that uses Docker or a rate-limited
provider inherits five of these producers directly. The cost is amortized
across every future application.

---

## Design gaps surfaced during dispatch (need conversation before further sprint work)

- **S3/S4 (embedded_substrate sub-topology + swebench_repair migration).** `best_of_n_correction` at `topologies/best_of_n/__init__.py` is a BUILDER (adds producer kinds to the caller's builder). `swebench_repair_topology` currently reuses `seeder_factory` + `select_first_judge_factory` inline; the swebench-solver-design comments explicitly note that `best_of_n_correction`'s all-in-one shape doesn't model swebench's pre/post phases (LOCALIZE + EMIT). Full migration to `embedded_substrate` requires ExportMap wiring across LOCALIZE → sub-substrate → EMIT boundaries — real design conversation, not a mechanical refactor. Not blocking anything; the shared factories work today.
- **S5.3/S5.4/S5.5/S5.6 (boundary-as-producer for Docker/image/repo-clone/harness).** The roadmap named "wraps X with typed events" for each. Real question glossed: WHERE do those typed events land? `_mother_clone` runs in the prep phase, before any substrate topology has started; `run_swebench_one` runs at grade time, after the cell's topology has finalized. Neither has a natural substrate run to emit onto. Two paths to resolve: (a) add a prep-phase / grade-phase substrate topology that wraps each cell; (b) accept that these boundaries get "typed function + structured logging" rather than full substrate producers. The choice governs S5.x's whole shape. Not blocking S5.1 (LLM boundary, already productized).

## Deferred notes from external reviews (not blockers)

These items came out of external reviews as findings; each is a real caveat, none is a halt. They live here so a reader sees them without them each getting a sprint card. When a real code-change need surfaces for any of them, a real sprint gets filed at that time.

- **Equivalence comparator is externally-produced (round-2 R2).** The pre-registration pins Agentless + GPT-4o = 27.8% resolve on Lite (Xia et al. 2024) as the equivalence comparator. Substrate has never run Agentless on this codebase / harness pin / environment; environmental drift between the Xia paper's run and substrate's is a confound the equivalence math cannot see. Two paths a future sprint may take: run Agentless on this substrate for a like-to-like comparator, OR drop the external comparator and frame the arms as within-substrate comparisons only. Not blocking Pass 1; a real decision when the equivalence claim needs the tighter framing. (Sprint 186 was filed as a halt for this finding and retired on 2026-08-13 as over-ceremonial; card preserved under `process/sprints/_deprecated/`.)

- **Paper positioning (round-2 M2).** `docs/review/PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md` reads as adoption argument, not audit. Status note on the paper itself flags this; no doc cites the paper as authority. A future rewrite as technical postmortem would land as a new dated file. Not queued.

- **"External review" ceremony (round-2 M6).** Blackboard entries called the reviewer's own findings "external review" and thereby raised the close-count reflex. KIT_DIARY 42 records the lesson; blackboard entries after 2026-08-12 should not use the "external" label for same-session reviewer output.

- **Linter-level review pattern (round-2 M1).** Round 1 pitched every finding at the level a smarter linter would reach; round 2 caught it. KIT_DIARY 41 records the transferable lesson. Not a fix; a discipline note for future reviewer passes.

---

## What v2 preserves from v1

Every keep-list entry from v1's Section 4 stays. The topology at
`assemble.py:257`, the applier, the firewall parser, the mother-clone cache,
the pre-registration files, the tests, the `container_arm` (F8), the
`assay/swebench_errors.py` typed hierarchy, the `assay/swebench_suite.py`
Adapter, the `swebench-solver-vocabulary.md` doc (now RATIFIED v0.2 via
Sprint 161), the ratified `Verdict` enum, the ratified `_HARNESS_REASONS`
closed set, the pre-registration and preregistration gates.

The `_HARNESS_REASONS` closed set stays *exactly*. Producer events carry the
same wire strings on their `reason` payloads. One vocabulary, one lexicon,
from H-3 forward.

---

## What the Architect needs to ratify before dispatch

Four items. All go through `## Decisions`.

**H-A (routine).** `signals/swebench-solver-vocabulary.md` § E consolidation
from Sprint 161. Reads § E.1 against `oracle.py:36-105`; reads § E.2 against
`swebench.py:55-85` + `swebench_errors.py`. Ratifies the header flip to
RATIFIED. Sign-off in `## Decisions`. Sprint 161 closes.

**H-B (architectural — v0.3 vocab).** The six-boundary event set at
Sprint 0.75. Reviews the table under S0.75 § "Tags to lock." Approves the
tag names, payload shapes, and invariants. Ratifies as v0.3.

**H-C (architectural — Budget primitive).** The kernel change at Sprint 1.
Reviews the `Budget` API shape and the additive-only compatibility promise.
Non-trivial because it touches `producer_kind`.

**H-D (operational — deprecation policy).** Which retired code moves to
`_deprecated/` versus stays alive in-tree with a deprecation notice. Applies
to `RateLimitedResponder` (S5.2b), `SwebenchRecordOracle` + `ExternalGraderOracle`
(S7), the 972-line runner (S7b). Ratifies the pattern; individual sprints
inherit.

Nothing else requires ratification. Every other sprint runs under existing
working-agreement dispatch rules.

---

## The shape v2 lands

At v2's landing, one SWE-bench cell's record contains, in order:

```
substrate.RunStarted
  → SuspectFiles, EditLocations
  → n × (Draft → Candidate → Verdict → AppliedPatch?) [embedded_substrate: best_of_n_with_correction]
  → SelectedPatch, RepairSummary
  → RepoCloneRequested → RepoCloneCached
  → ImageRequested → ImagePulled
  → ContainerRequested → ContainerStarted
  → HarnessCallFired
  → (RateLimitAttempted → RateLimitGranted)* [model calls during harness]
  → HarnessReportRead
  → HarnessCompleted(verdict, reason)
  → ContainerExited
  → GradeResult(verdict, reason)
substrate.RunFinalised
```

`assert_replayable` on this record passes at L1 for the AUDIT of the grade
(the `GradeResult` event is a deterministic projection of prior events on
the record; the pytest run inside the container that produced `report.json`
is not itself deterministic — see the Consequences section above for the
audit-replay vs grade-replay distinction). `first_divergence` between this
record and June 27's shows the
exact producer where they diverge, if they do. `narrate` renders the whole
sequence as prose. `attach` + `LiveRecord` observes the sequence unfold in a
browser pane while the run is in flight.

The runner is a topology assembler around `run_suite`. The exception-handler
classifier disappears — the boundary producers emit typed events; the
`_HARNESS_REASONS` strings ride on those events; the report reads them by
counting event kinds, not by parsing strings from log lines.

The 972-line runner shrinks to roughly 350–400 lines. The 200-line shim moves
into a 250-line producer where the retry loop no longer holds the slot. The
90-line `run_swebench_one` moves into a producer with typed events.
`SwebenchRecordOracle` and `ExternalGraderOracle` retire from the SWE-bench
path — the grade is a `LogProjectionOracle` projecting one event.

Every substrate producer added is available to every future assay that
touches Docker, provider APIs, subprocess-based graders, or GitHub. The
five producers together are the Substrate-level shape for external-grader
assays generally.

---

## One paragraph

v2 folds the halt's design pass into v1's roadmap. Fourteen sprints instead
of ten. The added four sprints (S0.75, S5.2 through S5.6, S6) recast every
SWE-bench external boundary as a substrate producer emitting typed events on
the record. The runner shrinks from 972 lines to 150 not by hiding logic in
helpers but by moving it into producers where it belongs. The oracle
collapses to a one-line `LogProjectionOracle` because the grade is now
projectable from the record. Every future Substrate assay touching Docker or
a rate-limited provider inherits these producers directly. Sprint 161's
vocabulary v0.2 consolidation already landed; v0.3 (boundary events) is
S0.75. The Budget primitive at S1 gates enforcement across every boundary
producer. Ten to twelve working days at SDD pace. The number the confirmatory
produces at S9's wire-check reads back off a record whose every failure has
a typed home.

---

*Sources: `docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md` (technical
divergence record), `AUDIT-2026-08-12-substrate-usage-in-swebench-work.md`
(Substrate-primitive gap analysis),
`ROADMAP-2026-08-12-swebench-rebuild-sprint-chain.md` (v1, superseded on
completion of v2 chain), `process/BLACKBOARD.md` (the 2026-08-12 halt at
`## Surfaced for review`), `sdd-kit-2/AGENTS.md`,
`sdd-kit-2/grammar/PRINCIPLES.md`, `sdd-kit-2/grammar/BOOTSTRAP.md`,
`src/substrate/api.py`, `src/substrate/kernel/composition.py`,
`src/substrate/topologies/swebench_solver/assemble.py`,
`src/substrate/assay/*.py`, `scripts/assay_swebench_confirmatory.py`,
`scripts/bench_coding.py`, `docs/adding-a-topology.md`. Sprint 184 removed
`PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md` from this list
per external round-2 M2; the paper is retained on disk per hard rule 12 as
a position document, not as authority.*

# ROADMAP — SWE-bench rebuild sprint chain

*Companion to `PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md`
(diagnosis) and `AUDIT-2026-08-12-substrate-usage-in-swebench-work.md`
(specification). This document is the sprint-by-sprint plan the build side
dispatches from.*

*Purpose: turn the diagnosis and specification into a concrete, dependency-
ordered chain of ≤2-file sprints per `sdd-kit-2/AGENTS.md` hard rule 6.
Every sprint carries a signal contract, an observation contract per hard
rule 9, files touched, preserved contracts, removed code, and a duration
estimate.*

*Non-goals. This roadmap does not dispatch. The build side reads it,
files each sprint's card in `process/sprints/`, and executes. This roadmap
does not edit code. Reviewer role.*

*Halts before Sprint 0 dispatches: three, listed at the end.*

*Date: 2026-08-12.*

---

## The dependency graph

```
S0 vocab session ──┬── S1 kernel budget primitive
                   │
                   ├── S2 topology dual-mode + bundled + CI record
                   │       │
                   │       └── S3 embedded_substrate sub-topology
                   │                │
                   │                └── S4 repair topology nests sub-topology
                   │
                   ├── S5 oracle: one path, delete extract-only
                   │       │
                   │       └── S6 runner rewrite around run_suite
                   │                │
                   │                ├── S7 unify three timeout regimes
                   │                │
                   │                └── S8 daemon-health + image-manifest gates
                   │                         │
                   │                         └── S9 wire-check N=300 Lite
                   │                                  │
                   │                                  └── S10 Verified pass 1
                   │
                   └── S0.5 bridge mapping (parallel to S1-S8)
```

S0 and S0.5 gate everything. S1 gates S2. S2 gates S3. S3 gates S4. S5
gates S6. S6 gates S7 and S8. S8 gates S9. S9 gates S10.

Total: 11 sprints. At SDD pace (one ≤2-file sprint per half-day for
mechanical work, one per day for architectural work), roughly 8-10 working
days.

---

## Sprint 0 — Vocabulary session for the SWE-bench sub-topology

**Duration.** Half a day.

**Rule.** `sdd-kit-2/grammar/BOOTSTRAP.md` twelve-step procedure. Architect
+ Agent produce a locked vocabulary extension.

**Files produced.**

- `process/signals/0.2.json` — new. Extends `signals/0.1.json` (the kernel
  vocabulary) with the SWE-bench sub-topology tags.
- `docs/vocabulary-0.2-rationale.md` — new. Names every tag added between
  sprint 133 and today with its category, payload schema, invariants, and
  dual observable per rule 25.

**Tags to lock** (from the current sub-topology + the two grade states):

| Tag | Category | Dual observable |
|---|---|---|
| `SuspectFiles` | LOCALIZE | `recall_at_k` against gold patch files |
| `SuspectElements` | LOCALIZE | element-level recall |
| `EditLocations` | LOCALIZE | localizer's downstream trim shape |
| `Draft` | REPAIR | one Draft per slot per round |
| `Candidate` | REPAIR | one Candidate per Draft |
| `Verdict` | REPAIR | apply pass/fail with reason |
| `AppliedPatch` | REPAIR | git diff on successful apply |
| `Solved` | REPAIR | judge's terminal signal |
| `Exhausted` | REPAIR | judge's out-of-rounds signal |
| `ReproductionTest` | (optional) | reproduction generator's output |
| `TestResults` | (optional) | in-topology test execution (retire path) |
| `SelectedPatch` | EMIT | exactly one per case |
| `RepairSummary` | EMIT | always-emit terminal for termination |
| `ModelUsage` | METERING | one per model call |

**Oracle-verdict closed set** (already ratified as H-1): `PASS`, `FAIL`,
`NO_VERDICT`. Reason strings for `NO_VERDICT`: `timed_out`,
`container_crashed`, `docker_error`, `harness_error`, `git_error`,
`firewall_violation`, `rate_limited`.

**Vocabulary invariants** to lock:

- `SelectedPatch` fires exactly once per case.
- Every `SelectedPatch` follows an `AppliedPatch` with the same slot.
- `SuspectFiles` precedes every `AppliedPatch`.
- `RepairSummary` fires exactly once per case as the terminal event.
- Every `Verdict` carries a slot matching one of the round's `Candidate`s.

**Signal contract.** No runtime emit — this sprint produces a JSON
artifact and a doc.

**Observation contract.** Architect reviews `signals/0.2.json` against
the code that emits each tag; every emit site's payload matches the locked
schema; every declared tag has a producer.

**Dispatches only after H-halt-1** (routine vocab evolution ratification
in `## Decisions`).

---

## Sprint 0.5 — Bridge mapping for the six external boundaries

**Duration.** One hour.

**Rule.** `sdd-kit-2/AGENTS.md` hard rule 12 halt-condition
`bridge_mapping_required`; the section belongs in `WORKING_AGREEMENT.md`.

**Files touched.**

- `process/WORKING_AGREEMENT.md` — modify. Add a "SWE-bench external
  substrates" section.

**Content.** For each of B1-B6 (from
`PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md` § "The six
external boundaries"):

- Boundary name and shape of non-determinism.
- Substrate seam that admits it.
- Current defense status (shipped, partial, scheduled, absent).
- Sprint that ships the defense (if not yet shipped).
- Failure mode → typed exception → cell-row reason string.

**Signal contract.** No runtime emit.

**Observation contract.** Every external boundary the runner touches at
runtime appears in the section; every unshipped defense has a scheduled
sprint number in this roadmap.

**Dispatches in parallel with S1 through S8** — a doc sprint, no code
dependency.

---

## Sprint 1 — Kernel: `producer_kind` resource budget primitive

**Duration.** One sprint (roughly one day).

**Rule.** The missing rule the postmortem's own prevention section
requested at
`docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md` § "Discipline for
prevention", currently deferred.

**Files touched.**

- `src/substrate/kernel/topology.py` — modify. `producer_kind` grows an
  optional `budget: Budget` kwarg.
- `src/substrate/api.py` — modify. Export `Budget`, `BudgetExceeded`.

**Contract.**

```python
class Budget(msgspec.Struct, frozen=True):
    docker_containers: tuple[int, str] | None = None
    wall_seconds: tuple[float, str] | None = None
    model_calls: tuple[int, str] | None = None
```

The runtime enforces at run time: exceeding a cap emits a typed
`substrate.BudgetExceeded` event on the record and terminates the
producer's factory. The topology's watchdog catches the termination.

**Signal contract.** `substrate.BudgetExceeded` emit at every enforcement
site.

**Observation contract.** A unit test in `tests/test_kernel_budget.py`
constructs a producer with a `docker_containers=(2, "test cap")` budget,
runs a factory that spawns three containers, asserts the third emits
`BudgetExceeded` and the run's record contains one such event.

**Preserved.** Existing producers without a `budget` kwarg behave
identically. Additive change.

**Removed.** Nothing.

---

## Sprint 2 — Repair topology: dual-mode + `bundled.py` + CI record

**Duration.** Half a day.

**Rule.** `docs/adding-a-topology.md` § "Make it dual-mode" and § "Add it
to the catalogue".

**Files touched.**

- `src/substrate/topologies/swebench_solver/assemble.py` — modify.
  `swebench_repair_topology` grows `responders: list[Responder] | None =
  None`; when `None`, defaults to
  `[DeterministicResponder(seed=i) for i in range(n)]` for CI. Signature
  parity with `code_review`'s dual-mode pattern.
- `src/substrate/topologies/bundled.py` — modify. Registers
  `swebench_repair` in the `BUNDLED` dict.

**Adjacent artifact.** Generate the CI record via
`scripts/gen_topology_records.py` and commit
`src/substrate/topologies/swebench_solver/records/ci_mode.record`.

**Signal contract.** In CI mode, the emit sequence is: `SuspectFiles` →
`EditLocations` → n × (`Draft` → `Candidate` → `Verdict`) → optional
`AppliedPatch` → `SelectedPatch` → `RepairSummary`.

**Observation contract.** A test in `tests/test_swebench_repair_topology.py`
runs the topology with the CI-default responder and asserts
`assert_event(rec, "SelectedPatch")`; asserts the record's model_patch is
the deterministic stub form (`stub[0]:<hash>`); asserts
`assert_replayable(rec)` passes.

**Preserved.** Every non-CI caller passing an explicit `responders` list
behaves identically.

**Removed.** Nothing.

---

## Sprint 3 — Best-of-N + correction as `embedded_substrate` sub-topology

**Duration.** One sprint (one to two days — architectural).

**Rule.** `docs/swebench/swebench-solver-design.md:82-86` — factor once, three
consumers.

**Files touched.**

- `src/substrate/topologies/best_of_n_with_correction/__init__.py` — new.
  Defines the sub-topology function
  `best_of_n_with_correction(b: TopologyBuilder, *, n, max_rounds,
  drafter_factory, validator_factory) -> None`.
- `tests/test_best_of_n_with_correction.py` — new. Substance test with
  `DeterministicResponder`.

**Contract.** The sub-topology emits `Candidate`, `Verdict`,
`AppliedPatch`, `Solved`, `Exhausted`, `Draft` per the locked vocabulary
from Sprint 0. Consumers wire drafter_factory and validator_factory
specific to their domain (SEARCH/REPLACE for SWE-bench, test-driven
correction for coding_flow, mutation for code_evolution).

**Signal contract.** Emits `Candidate`, `Verdict`, `AppliedPatch`,
`Solved`, `Exhausted`, `Draft`, `ModelUsage`.

**Observation contract.** Unit test runs the sub-topology with a
deterministic drafter that emits three candidates in fixed order; asserts
three `Candidate` events, three `Verdict` events, one `Solved` event when
the first candidate applies clean.

**Preserved.** The stand-alone `swebench_repair_topology` at line 257
remains callable for the current wire path until Sprint 4 lands.

**Removed.** Nothing yet.

---

## Sprint 4 — Repair topology nests the sub-topology via `embedded_substrate`

**Duration.** One sprint.

**Rule.** `AGENTS.md` hard rule 6 (≤2 files, one concept — the concept is
the substitution).

**Files touched.**

- `src/substrate/topologies/swebench_solver/assemble.py` — modify.
  `swebench_repair_topology` replaces its inline drafter + validator +
  judge + selector wiring with an `embedded_substrate` call producing
  `best_of_n_with_correction` as the REPAIR stage.
- `tests/test_swebench_repair_topology.py` — modify. Update assertions to
  reflect the nested topology's event source (unchanged in shape, but the
  producer_kinds list gains the embedded record's kinds).

**Signal contract.** Unchanged from Sprint 2 — the topology still emits
`SuspectFiles`, `EditLocations`, `SelectedPatch`, `RepairSummary` at the
outer level; the sub-topology's events appear on the nested record.

**Observation contract.** Byte-stable CI record match against Sprint 2's
committed `ci_mode.record` (same producer sequence, same terminal, same
`stub[0]:<hash>` shape).

**Preserved.** External arm-helper API unchanged. Every arm continues to
call `swebench_repair_arm(name, role, models, n, max_rounds)`.

**Removed.** The inline drafter, validator, judge, and selector producer
kinds from `assemble.py`. Replaced by the embedded call.

---

## Sprint 5 — Oracle: one grade path, delete extract-only

**Duration.** Ten minutes.

**Rule.** Move 8 finish from the holistic review.

**Files touched.**

- `src/substrate/assay/swebench.py` — modify. Delete
  `SwebenchExtractOnlyOracle` at line 515 and `batch_grade_from_records`
  at line 835.
- `tests/test_assay_swebench.py` — modify. Delete tests for the deleted
  classes.

**Signal contract.** No emit changes.

**Observation contract.** `pytest tests/test_assay_swebench.py` runs
clean; the inline `SwebenchRecordOracle.grade` path is the only grader
path exercised.

**Preserved.** `SwebenchRecordOracle` and its inline grade path.

**Removed.** Two classes plus the `SWEBENCH_BATCH_GRADE` env plumbing
(which was already default-off at commit `b5f5961`).

---

## Sprint 6 — Runner rewrite around `run_suite`

**Duration.** Two sprints (three to four days).

**Rule.** Move 3 from the holistic review. Largest structural rebuild.

**Files touched.**

**Sprint 6a — extend `assay/run.py` with the generic pieces.**
- `src/substrate/assay/run.py` — modify. Add:
  - `run_suite_with_salvage(suite, roots, salvage_root=None)`.
  - `PerCellBudget(topology_watchdog_s, grade_timeout_s, margin_s)` type
    and enforcement inside `run_arm_on_case`.
  - Optional `sidecar_writer: SidecarWriter | None` argument that writes
    typed cell rows per assay-specific taxonomy.
  - `CellSource` enum unified with the assay-specific runner enums.
- `tests/test_assay_run.py` — modify. Add tests for salvage, per-cell
  budget, sidecar writer.

**Sprint 6b — rewrite the confirmatory runner.**
- `scripts/assay_swebench_confirmatory.py` — replace. Roughly 200 lines
  around a `run_suite_with_salvage` call, importing the SWE-bench-specific
  helpers from `assay/run.py`, `assay/swebench.py`, `assay/swebench_errors.py`,
  `adapters/rate_limit.py`. Preserves every current env flag
  (`SWEBENCH_MODELS`, `SWEBENCH_N`, `SWEBENCH_TRIALS`, `SWEBENCH_LIMIT`,
  `SWEBENCH_CONCURRENCY`, `SWEBENCH_OLLAMA_TIER`, `SWEBENCH_ARMS`, ...).
- `tests/test_assay_swebench_runner_thin.py` — new. Asserts the runner is
  under 250 lines and every branch delegates to `run_suite_with_salvage`
  or a named helper.

**Signal contract.** No new emits.

**Observation contract.** The runner script's line count drops below 250.
`bench_coding.py` and `assay_swebench_confirmatory.py` use the same
underlying loop (grep-verifiable). The CI record for a Lite-3 dry run
matches the pre-rewrite output shape byte-for-byte at the cell-row level.

**Preserved.** Every current env flag, every current cell-row field name,
every current arm output.

**Removed.** Roughly 600 lines of the current runner's bespoke outer
loop, salvage handling, resume handling, sidecar writing, tier verification,
error classification — all folded into `assay/run.py` as generic assay
concerns.

---

## Sprint 7 — Unify three timeout regimes into one per-cell budget

**Duration.** Half a sprint.

**Rule.** Move 7 from the holistic review.

**Files touched.**

- `src/substrate/assay/run.py` — modify. `PerCellBudget` derived from
  `read_swebench_timeouts()` per-repo table + a small margin. Applied at
  one enforcement point in `run_arm_on_case`.
- `src/substrate/topologies/swebench_solver/assemble.py` — modify.
  `swebench_repair_topology`'s `watchdog_seconds` default changes to
  `None` (meaning "derive from caller's budget"); the arm helper passes
  the value from `PerCellBudget` at build time.

**Signal contract.** No new emits. `substrate.BudgetExceeded` (from
Sprint 1) fires when a cell's budget is breached.

**Observation contract.** A test constructs a `PerCellBudget` with a
1-second grade timeout, runs a slow-mock grader, asserts the cell row
lands with `reason="timed_out"` and the `substrate.BudgetExceeded` event
on the record.

**Preserved.** Every current per-repo timeout number in
`swebench_timeouts.json`.

**Removed.** `SWEBENCH_RUN_TIMEOUT` env plumbing (subsumed by
`PerCellBudget`).

---

## Sprint 8 — B3 daemon-health pre-flight + B4 image-manifest check

**Duration.** Half a sprint each; one sprint together.

**Rule.** Section 4 of `PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md`.

**Files touched.**

- `src/substrate/assay/swebench.py` — modify. Add
  `docker_daemon_ping()` and `image_manifest_check(instance_ids)` at the
  runner boundary. Both raise typed exceptions from
  `assay/swebench_errors.py` on failure.
- `scripts/assay_swebench_confirmatory.py` — modify. Both checks fire at
  runner startup, alongside the model pre-flight from commit `4fb4eaf`.
- `tests/test_assay_swebench.py` — modify. Add tests for both checks with
  mocked Docker responses.

**Signal contract.** No runtime emits; both are startup gates.

**Observation contract.** Test verifies daemon-down and image-404 both
halt the runner before any cell fires. Live smoke against a running
daemon verifies success path.

**Preserved.** Model pre-flight from `4fb4eaf`.

**Removed.** Nothing.

---

## Sprint 9 — Wire-check on Lite at N=300, observation contract per H-4

**Duration.** Wall-clock several hours; sprint-work is writing the
observation contract, then running it.

**Rule.** H-4 ratified 2026-08-10.

**Files touched.**

- `process/sprints/sprint-N-wire-check.md` — new. Card carries the full
  observation contract:
  - Input fixture: 300 SWE-bench Lite instance IDs (pinned in the sprint
    card by ID list).
  - Expected verdict distribution: `n_drafts_repair_ensemble` produces
    108 ± Wilson-CI (~5.4pp) resolved cells; ≤5 grade errors.
  - Expected log substrings: `RepairSummary` count = 300;
    `SelectedPatch` count between 240 and 290; zero unclassified halts.
  - Expected runtime signals: `substrate.BudgetExceeded` count = 0.
  - Publish threshold: ≥80 percent graded rate per arm.

**Signal contract.** No new code emits.

**Observation contract.** The card's own contract.

**Preserved.** Everything before Sprint 9.

**Removed.** Nothing.

**Halt on breach.** If any expectation fails, halt with
`dual_contract_fail`; the diff from June 27's shape goes to a follow-up
postmortem; no subsequent sprint dispatches until the halt resolves.

---

## Sprint 10 — Verified pass 1, ensemble arm only

**Duration.** Wall-clock ~9-15 hours (500 cells at CONCURRENCY=8-12,
average 5-10 min per cell).

**Rule.** v3 design's step 6.

**Files touched.**

- `docs/preregistrations/2026-08-swebench-verified.preg.json` — new.
  Adapted from the Lite pre-reg with Verified comparator, models, and
  arms hash. Frozen before the run fires.
- `process/sprints/sprint-N-verified-pass-1.md` — new. Observation
  contract:
  - Fires only after Sprint 9's observation contract passed clean.
  - Runs 500 instances × 1 trial × ensemble arm = 500 cells.
  - Expected result: mechanism claim's evidence in verdict counts and
    resolve rate.
  - Publish threshold from the pre-reg.

**Signal contract.** No new code emits.

**Observation contract.** Runner exits clean; report emits three-number
headline; `RUN_UNPUBLISHABLE` fires only if graded rate under threshold.

**Preserved.** Everything.

**Removed.** Nothing.

---

## The keep/remove file inventory

Same as `AUDIT-2026-08-12-substrate-usage-in-swebench-work.md` Section 4;
reproduced here for the build side's convenience.

**Preserve as-is.**
- `src/substrate/topologies/swebench_solver/assemble.py` — through S2, S4.
- `src/substrate/topologies/swebench_solver/applier.py`.
- `src/substrate/topologies/swebench_solver/localize.py`.
- `src/substrate/topologies/swebench_solver/localize_elements.py`.
- `src/substrate/topologies/swebench_solver/records.py`.
- `src/substrate/topologies/swebench_solver/repair.py` — through S3, S4.
- `src/substrate/assay/swebench.py` — through S5, S7, S8.
- `src/substrate/assay/swebench_suite.py`.
- `src/substrate/assay/swebench_errors.py`.
- `src/substrate/assay/swebench_matrix.py` post-Move 2.
- `src/substrate/assay/oracle.py`.
- `src/substrate/adapters/rate_limit.py`.
- `src/substrate/adapters/ensemble.py`.
- `src/substrate/assay/swebench_timeouts.json`.
- All `tests/test_assay_swebench*`, `tests/test_swebench_*`,
  `tests/test_rate_limit.py`, `tests/test_adapters_ensemble.py`.

**Move to `topologies/swebench_solver/_deprecated/` with a KIT_DIARY
entry.**
- `src/substrate/topologies/swebench_solver/select_exec.py` — verify
  unwired first.
- `src/substrate/topologies/swebench_solver/select_docker.py` — verify
  unwired first.
- `src/substrate/topologies/swebench_solver/select_regression.py` —
  verify unwired first.
- `src/substrate/topologies/swebench_solver/repro_base_validate.py` —
  verify unwired first.
- `src/substrate/topologies/swebench_solver/reproduction.py` — verify
  unwired first.

**Delete (S5).**
- `SwebenchExtractOnlyOracle` class from `assay/swebench.py`.
- `batch_grade_from_records` function from `assay/swebench.py`.

**Rewrite (S6).**
- `scripts/assay_swebench_confirmatory.py` — from 837 lines to under
  250, with the outer loop delegated to `run_suite_with_salvage` in
  `assay/run.py`.

**Extend (S1, S6, S7, S8).**
- `src/substrate/kernel/topology.py` — S1 `Budget` primitive.
- `src/substrate/api.py` — S1 export.
- `src/substrate/assay/run.py` — S6, S7 helpers.

**Add.**
- `src/substrate/topologies/best_of_n_with_correction/__init__.py` — S3.
- `src/substrate/topologies/swebench_solver/records/ci_mode.record` — S2.
- `process/signals/0.2.json` — S0.
- Multiple new tests per sprint.

---

## What the build side needs from the Architect before Sprint 0 dispatches

Three halts, per SDD hard rule 4.

**H-1 (routine, expected fast ratification).** `signals/0.2.json`
vocabulary lock. Architect reviews the Sprint 0 output (the JSON file
plus the rationale doc). Sign-off in `## Decisions`. Then S1-S10
dispatch.

**H-2 (architectural, needs discussion).** `producer_kind` `Budget`
primitive lands in the kernel. Non-trivial kernel change. Architect
reviews the API shape at S1's sprint card; ratifies the additive-only
design (existing producers without `budget` behave identically). Once
ratified, S1 dispatches.

**H-3 (operational).** The heavy-topology satellite files
(`select_exec.py`, `select_docker.py`, `select_regression.py`,
`repro_base_validate.py`, `reproduction.py`) move to `_deprecated/`
rather than being deleted, per hard rule 12. Architect ratifies the
"move to `_deprecated/` with KIT_DIARY entry" approach in `## Decisions`
before S5 dispatches. Alternative: promote the deletion carve-out from
the roadmap to a kit-level ADDENDUM under `sdd-kit-2/ADDENDUMS.md`.

Nothing else requires Architect ratification. Every other sprint runs
under the working agreement's existing dispatch rules.

---

## What this roadmap does not do

- Does not dispatch. Build side files each sprint card in
  `process/sprints/`.
- Does not edit code. Reviewer role.
- Does not schedule against calendar time. Sprint durations are
  estimates; the Architect sets the pace.
- Does not supersede
  `docs/swebench/swebench-close-the-loop-roadmap.md` (round 3). That document
  reflects the pre-rebuild plan and stays on disk as the audit trail per
  hard rule 12. The relationship:
  - Close-the-loop round 3 targets the current heavy-topology architecture.
  - This roadmap targets the rebuild that follows from the paper's
    diagnosis.
  - When Sprint 0 through Sprint 10 land, close-the-loop round 3 is
    marked "superseded — see ROADMAP-2026-08-12" in its own header.

---

## One-paragraph summary

Ten sprints plus one vocabulary session and one bridge-mapping session
close the gap between the current SWE-bench work and a build that uses
Substrate to the depth Substrate ships. Sprint 0 locks the vocabulary
that grew sprint-by-sprint through July. Sprint 0.5 names the six
external boundaries and their defenses. Sprint 1 adds the producer_kind
resource budget primitive the postmortem's own prevention section
requested. Sprints 2-4 make the topology dual-mode, register it in
`bundled.py`, and factor the best-of-N + correction sub-topology via
`embedded_substrate` shared with `coding_flow` and `code_evolution`.
Sprint 5 collapses the two grading paths. Sprint 6 rewrites the runner
around `run_suite`. Sprint 7 unifies the three timeout regimes. Sprint 8
adds the last two boundary defenses. Sprint 9 fires the observation
contract at N=300 Lite. Sprint 10 fires Verified pass 1. Roughly eight
to ten working days at SDD pace. Every sprint carries a signal contract,
an observation contract, and a keep/remove call. The build side
dispatches; this reviewer stops here.

---

*Sources: `PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md`,
`AUDIT-2026-08-12-substrate-usage-in-swebench-work.md`,
`sdd-kit-2/AGENTS.md`, `sdd-kit-2/grammar/BOOTSTRAP.md`,
`docs/adding-a-topology.md`,
`docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md`,
`docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v3.md`,
`docs/swebench/swebench-close-the-loop-roadmap.md` (round 3, superseded on
completion of this chain), all files cited in the two companion
documents above.*

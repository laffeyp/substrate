# DESIGN — SWE-bench confirmatory, corrected shape (2026-08-10, v3)

*Third version. `DESIGN-2026-08-10-swebench-confirmatory-revert.md` is v1 on disk;
`DESIGN-2026-08-10-swebench-confirmatory-revert-v2.md` is v2. This v3 folds the
sixteen findings in `docs/review/REVIEW-2026-08-10-swebench-confirmatory-revert-v2.md`
and names four halts that land in BLACKBOARD before any code moves.*

Companions:
- `docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md` — what broke and why.
- `docs/review/REVIEW-2026-08-10-swebench-confirmatory-revert-v2.md` — the review
  this version answers.
- `sdd-kit-2/AGENTS.md` — the discipline the four halts respect.

---

## The four halts

The design routes through four halt-and-articulate items in
`process/BLACKBOARD.md ## Surfaced for review` before any code lands. Each is a
load-bearing choice the Architect ratifies in `## Decisions`.

**H-1 — `assay.Verdict` enum is a `vocabulary_change_required` proposal, not a
struct-field append.** `assay/oracle.py:35`'s `Result` is the shared oracle
contract every assay in the tree reads. Adding a load-bearing three-state enum
is exactly the AGENTS.md hard rule 2 case (never invent tags; halt with
`vocabulary_change_required`; propose under one of the eight evolution types in
`grammar/PRINCIPLES.md`). The evolution type here is `NEW_TAG_PROPOSED` for the
enum values (`PASS`, `FAIL`, `NO_VERDICT`) and `PAYLOAD_FIELD_PROPOSED` for the
`Result.verdict` field. Names, source citation (the review at
`docs/review/REVIEW-2026-08-10-swebench-confirmatory-revert-v2.md` findings 2
and 5), one-sentence rationale, layer (Layer 1 lexical + Layer 2 payload) —
recorded in `process/BLACKBOARD.md ## Surfaced for review` and awaiting `##
Decisions` sign-off.

**H-2 — `passed` becomes a derived `@property` of `verdict`, not a parallel
field.** Two fields carrying one fact drift the first time a caller forgets.
The choice: `passed` returns `self.verdict is Verdict.PASS`; every existing
reader keeps working; no in-code invariant to maintain by convention. Architect
ratifies this shape (versus dropping `passed` entirely) in `## Decisions`
before the enum lands.

**H-3 — one closed set of failure-reason strings, shared by oracle and runner.**
Current design has two lexicons: oracle uses `harness_timeout`,
`container_crash`, `docker_error`, `harness_error:<class>`; runner's `source`
column uses `timed_out`, `docker_error`, `git_error`, `firewall_violation`,
`run`, `salvage`. The overlap (`docker_error`) differs; the timeout has two
names. Halt: define one enum-shape closed set at the oracle boundary, use its
values verbatim in the runner rows. Architect ratifies the merged list.

**H-4 — Step 5 wire-check is written as an AGENTS.md hard-rule-9 observation
contract at N=300 Lite.** Not a smoke test at N=20. The observation contract
declares the input fixture (300 SWE-bench Lite instance IDs, pinned), the
expected verdict distribution matching the June 27 shape (108/300 = 36%
resolved ± Wilson interval, ≤5 grade errors), the expected log substrings
(`RepairSummary` count = 300, `SelectedPatch` count between 240 and 290), and
the publish threshold. Below the observation contract's pass criteria, Verified
does not fire.

---

## The claim to measure

Pass 1 measures whether the ensemble mechanism — several free small models under
orchestration — produces patches that resolve real Verified issues at a
nontrivial rate. Pass 2 puts the number in equivalence form against a
compute-matched single strong model baseline, under Benjamini-Hochberg FDR
across the five-arm matrix. The pre-registration file at
`docs/preregistrations/2026-08-swebench-lite.preg.json` pins the comparator
(Agentless + GPT-4o = 27.8% resolve on Lite); the Verified equivalent lands in
an amended pre-reg before pass 2 fires.

The number the confirmatory produces is credible when every layer under it
produces its own well-defined outcome, always, in bounded time. Every contract
below is written to that standard.

---

## The topology contract

**Name:** `swebench_repair_topology` at `topologies/swebench_solver/assemble.py:257`.
Already implemented, already tested, ran clean on 300 Lite instances (KIT_DIARY
entry 26, commit `0aab945`).

**Input:** a `PreparedPayload` (typed dict at `assay/swebench_suite.py:44`) plus
a responder list. The payload carries `base_checkout`, `repo_skeleton`,
`known_files`, `issue`, and the regression-set spec. Responder list is one
Responder per draft slot; length is `n`.

**Output:** exactly one `SelectedPatch` event per run. Its `model_patch` field
is a unified git diff against the base commit. Its `slot` and `reason` fields
carry the best-of-N provenance.

**Stages:**

1. **LOCALIZE.** One model call over the repo skeleton picks suspect files.
   Emits `SuspectFiles`, `SuspectElements` (one per Python suspect file, capped
   at 20 elements per file to keep the payload under `BLOB_THRESHOLD_BYTES`),
   `EditLocations`. Bound: one model call, one prompt at the configured cap.

2. **REPAIR.** N drafters each write SEARCH/REPLACE edits against the localized
   files. A validator clones the base checkout per candidate, applies the edits
   via `applier.py:apply_candidate`, emits `Verdict` and — on success —
   `AppliedPatch`. Max rounds configurable; pass 1 uses `max_rounds=2`.
   Correction rounds feed each round's failures to the next round's drafters.
   Bound: `n × max_rounds` model calls.

3. **EMIT.** `_first_patch_selector_factory` at `assemble.py:198` picks the
   first candidate whose validator returned `passed=True`. The topology emits
   one `SelectedPatch` and terminates on `RepairSummary` (the always-emit
   summary event at `records.py:139`).

**No Docker inside the topology.** The applier runs `git apply` against a temp
clone; the validator runs no tests. The topology's whole job is to produce a
git diff and hand it off. Testing the diff is the grader's job.

**Watchdog.** `swebench_repair_topology`'s signature at `assemble.py:267` sets
`watchdog_seconds: float = 60.0`. The arm helper this design specifies passes
`watchdog_seconds=900` explicitly at build time; pass 1's pre-registration pins
the number. The 60-second default in the topology signature stays for
short-topology callers; the confirmatory arm overrides.

**The heavy topology stays available under a renamed door.**
`swebench_solver_topology` at `assemble.py:438` gets renamed
`swebench_solver_topology_with_test_selection` in the same commit that lands
the matrix rewiring. `_build_solver_arm_from_payload` grows an
`include_test_selection: bool = False` kwarg; the default and every arm
factory build the light topology. Rename plus explicit kwarg makes the heavy
topology impossible to rewire silently.

## The oracle contract

**Vocabulary change (routes through H-1).** `assay/oracle.py:35`'s `Result`
grows a `verdict` field typed `Verdict`; the enum has three values,
`PASS | FAIL | NO_VERDICT`. Naming: `PASS`/`FAIL` (not `RESOLVED`/`NOT_RESOLVED`)
because `Result` is a general assay contract, not SWE-bench-specific; the same
enum reads correctly for coding assays, replay assays, and any future oracle.

**One field, one fact (routes through H-2).** `passed: bool` becomes a
`@property` returning `self.verdict is Verdict.PASS`. Every existing reader
that touches `.passed` keeps working; no invariant to maintain by convention.

**Grade contract.** For every `(record, ground_truth)` pair, `.grade()` returns
exactly one `Result` with a typed `verdict`. Every call returns; the runner
never sees a raise from the oracle. Every one of the three states is a
definite outcome.

**Verdict-mapping table (routes through H-3 for the reason strings).** One
closed set of `reason` strings lives at
`assay/swebench.py:_HARNESS_REASONS` and is imported by the runner:

| Harness state | verdict | reason string |
|---|---|---|
| `report.json` exists, `resolved: true` | `PASS` | `` (empty) |
| `report.json` exists, `resolved: false` | `FAIL` | `` (empty) |
| Missing report after wall-clock deadline | `NO_VERDICT` | `timed_out` |
| Container exited non-zero before report | `NO_VERDICT` | `container_crashed` |
| Docker daemon error | `NO_VERDICT` | `docker_error` |
| Harness raised (import, image 404) | `NO_VERDICT` | `harness_error` |

Runner-side cell rows use the same `reason` strings verbatim on any row where
the oracle returned `NO_VERDICT`. Additional runner-only reasons (`git_error`,
`firewall_violation`) come from cell-level exceptions the oracle never sees;
they use their own strings from the same closed set. One lexicon, one
translation table.

**The extract-only oracle exits the light-topology path.** With the light
topology, per-cell inline grade is tractable (one bounded harness call, one
container). `SwebenchExtractOnlyOracle` at `swebench.py:515` stays in the
codebase for the day someone wants a two-phase runner with an in-topology
selector; the light-topology arms dispatch `SwebenchRecordOracle` inline and
skip the extract-defer-batch dance. Batch grade is a runner-level knob for
when it's needed; it is not part of the light-topology's default shape.

## The grader contract

**One function owns the harness call:** `run_swebench_one(instance_id, patch,
image, timeout_seconds) -> HarnessOutcome`. Where `HarnessOutcome` is a Struct
with `verdict: Verdict` and `reason: str`. The function guarantees:

- Exactly one Docker container spawned per call. The container name pins
  `substrate-grade-{cell_id}-{ulid}` so `docker ps` names show what run owns
  what container.
- A wall-clock deadline enforced by `subprocess.run(..., timeout=T)` around
  the harness subprocess call, with `docker kill <container_name>` in the
  `except subprocess.TimeoutExpired` block. The primitive is
  subprocess-timeout + external-kill, deterministic under `ThreadPoolExecutor`
  workers.
- On deadline: kill the container, wait for exit, return
  `HarnessOutcome(verdict=NO_VERDICT, reason="timed_out")`.
- On subprocess non-zero exit before a report writes: return
  `HarnessOutcome(verdict=NO_VERDICT, reason="container_crashed")` with the
  exit code and last 400 bytes of stderr recorded in `Result.detail`.
- On harness exception (import failure, docker daemon down, image 404):
  return `HarnessOutcome(verdict=NO_VERDICT, reason="harness_error")` with the
  exception class in `Result.detail`.
- On completion: parse `report.json`, return `PASS` or `FAIL`.

**Per-instance timeout is data.** The default table lives at
`assay/swebench_timeouts.json` — one number per repo, derived from a one-time
measurement pass (base-only, empty patch, record wall-clock). sympy gets 90
min; matplotlib gets 30 min; small repos get 10 min. The default when a repo
is unknown is 60 min. Callers may override per-call. The pre-registration for
the confirmatory pins the table's sha256 so a change trips the pre-reg gate.

**No orphaned containers.** Every container spawned inside `run_swebench_one`
is killed by the same call before it returns. A test in
`tests/test_assay_swebench.py` asserts that after a controlled
`run_swebench_one` invocation `docker ps` shows no container with the
substrate prefix.

## The runner contract

**Per-cell wall-clock budget.** Each cell has a hard budget covering the
topology run AND the grade call. Pass 1 sets this to the topology's watchdog
(900s = 15 min) plus the per-repo grade timeout (10-90 min) plus a small
margin (5 min). Every cell completes or fails within that budget.

**Every cell writes exactly one typed row to cells.jsonl.** The row's `source`
field takes one of the shared closed set from H-3; `verdict` takes one of
`pass`, `fail`, `no_verdict`; `passed` (derived) is `verdict == "pass"`;
`reason` (when `verdict == "no_verdict"`) takes one of the same strings the
oracle emits.

**`_classify_cell_error` at `scripts/assay_swebench_confirmatory.py:146` is the
right shape.** Line 179 returns `(_ERROR_UNCLASSIFIED, True)` — halt. The
design extends the closed set as new failure modes appear; every unclassified
raise still halts the sweep. The firewall_violation flake (line 175 comment,
2026-08-09) stays a flake for the Verified run because Verified is
human-curated; a runner-end report counts firewall_violation rows separately
so the flake never hides a real data bug.

**Batch grade is a knob, default off.** Runner reads
`SWEBENCH_BATCH_GRADE=0` by default. `scripts/assay_swebench_confirmatory.py:223`
flips from `"1"` to `"0"` in the runner-change commit. When someone opts in
with `SWEBENCH_BATCH_GRADE=1`, the batch path is a loop over
`run_swebench_one` under a thread pool of `CONCURRENCY` workers; each worker
owns its container and its deadline.

## The report contract

**Every headline reads as three numbers:** N attempted, M graded, K resolved.
Resolve rate = K/M. The K/N number appears with a `(M/N graded)` qualifier
attached. Both are always present.

**Verdict counts appear per arm.** `pass`, `fail`, `no_verdict`, plus the
per-cell error taxonomy counts (`timed_out`, `container_crashed`,
`docker_error`, `harness_error`, `git_error`, `firewall_violation`). A reader
sees where the run spent its cells without opening a shell.

**The report refuses to publish "confirmatory" if graded_rate below
threshold.** Pre-reg pins the threshold. When `M/N < threshold`, the report
emits a `RUN_UNPUBLISHABLE` verdict block with the completion gap named. The
pre-registration also pins the per-arm graded-rate floor.

## The five-arm matrix

Every arm builds `swebench_repair_topology` with the same shape (finding 8
gate: `include_test_selection=False` explicit at build time; matrix test
asserts producer_kinds do not include `select_exec`).

- `single_draft_baseline` — one responder, n=1, max_rounds=1. Floor.
- `n_drafts_no_correction` — one responder, n=N, max_rounds=1. Best-of-N,
  no correction.
- `n_drafts_repair` — one responder, n=N, max_rounds=2. Best-of-N + correction.
- `n_drafts_repair_ensemble` — N responders (heterogeneous), n=N (one per
  model), max_rounds=2. The mechanism claim.
- `baseline_matched_compute` — one responder, n=K, max_rounds=1. K = median
  model_calls the ensemble consumed per case in Pass 1 Lite calibration.

Every arm dispatches the same topology; per-cell wall is comparable across
arms; the DELTA between arms measures the mechanism, holding the topology
constant.

---

## Pass 1 shape

**500 instances × 1 trial × 1 ensemble arm = 500 cells.** Finding 14 collapses
the earlier 500 × 3 × 1 = 1500. Three-trial McNemar on Pass 1 alone reads as
belt-and-braces given Pass 2 runs the whole matrix with its own trial
structure. Trial-level variance for the ensemble arm gets estimated from the
Lite calibration pass (Step 5, N=300, 5 arms) — 1500 Lite cells is plenty to
observe cross-run variance without spending Verified cells on it. Pass 1's job
is the ensemble's Verified resolve rate; N=500 × 1 gives that number with
Wilson CI ~ ±4 points at 30% resolve.

---

## The files that change

Ordered by dependency.

**`src/substrate/assay/oracle.py`** (~50 lines). Add `Verdict` enum. Add
`verdict: Verdict` field with default `NO_VERDICT`. Make `passed` a `@property`
returning `self.verdict is Verdict.PASS`. This is the H-1 landing; it happens
only after Architect sign-off on the vocabulary proposal.

**`src/substrate/assay/swebench.py`** (~150 lines). Add the shared
`_HARNESS_REASONS` closed set. Refactor `SwebenchRecordOracle.grade` at line
415 to return typed `Verdict`. Add `run_swebench_one` — the per-instance
grader that owns container lifecycle and wall-clock via `subprocess.run(...,
timeout=T)` + `docker kill` in `except subprocess.TimeoutExpired`. Refactor
`batch_grade_from_records` to loop over `run_swebench_one` under a thread pool.
Add `read_swebench_timeouts()`.

**`src/substrate/assay/swebench_matrix.py`** (~60 lines). Change
`_build_solver_arm_from_payload` to build `swebench_repair_topology`
explicitly. Add `include_test_selection: bool = False` kwarg; every arm
factory passes False. Pass `watchdog_seconds=900` at build time.

**`src/substrate/topologies/swebench_solver/assemble.py`** (~10 lines).
Rename `swebench_solver_topology` at line 438 to
`swebench_solver_topology_with_test_selection`; every current caller updates
in the same commit. The light `swebench_repair_topology` at line 257 stays
untouched.

**`scripts/assay_swebench_confirmatory.py`** (~200 lines). Every cell row
gains `verdict` and `reason` fields. Cell writer enforces "exactly one row
per cell." Per-cell wall-clock budget matches the design. Flip
`SWEBENCH_BATCH_GRADE` default at line 223 from `"1"` to `"0"`. Batch grade
loops over `run_swebench_one`. Runner reads shared reason strings from
`assay/swebench._HARNESS_REASONS`.

**`src/substrate/assay/report.py`** (~50 lines). Three-number headline (N/M/K)
per arm. Verdict-count breakdown per arm using the shared closed set.
Publish-refusal branch when graded_rate under threshold.

**`assay/swebench_timeouts.json`** (new, ~15 lines). Per-repo timeout map.

**`tests/test_assay_oracle.py`** (~40 lines). Verdict enum round-trip;
`passed` property equivalence.

**`tests/test_assay_swebench.py`** (~80 lines). Six harness-state → verdict
mappings; no-orphan-container invariant; `run_swebench_one` subprocess-timeout
+ docker-kill behavior.

**`tests/test_assay_swebench_matrix.py`** (~40 lines). Every arm factory
produces a topology whose producer_kinds omit `select_exec`.

Total: ~700 lines across 6 source files, 3 test files, 1 JSON. One commit per
step keeps the confirmatory bisectable.

## The seven landing steps

**1. File the four halts to BLACKBOARD.** H-1, H-2, H-3, H-4. Await Architect
sign-off in `## Decisions` before landing code.

**2. Land the vocabulary change (H-1, H-2 ratified).** `oracle.py` gets
`Verdict` + `passed` as `@property`. One commit.

**3. Land the shared reason lexicon (H-3 ratified).** `swebench.py` gets
`_HARNESS_REASONS`, refactored oracle, `run_swebench_one`. One commit.

**4. Land the matrix routing + heavy-topology rename.**
`swebench_matrix.py` builds `swebench_repair_topology`;
`swebench_solver_topology` renamed to
`swebench_solver_topology_with_test_selection`. One commit.

**5. Land the runner + report changes.**
`assay_swebench_confirmatory.py` enforces per-cell contracts;
`report.py` reads verdicts and enforces publish threshold;
`SWEBENCH_BATCH_GRADE` default flips to "0". One commit.

**6. Fire the wire-check on Lite (H-4 observation contract).** N=300 SWE-bench
Lite instances (IDs pinned in the pre-registration), five matrix arms.
Expected: `n_drafts_repair_ensemble` produces 108/300 ± Wilson interval
resolved, ≤5 grade errors, `SelectedPatch` count on every completed cell,
zero unclassified halts. When the observation contract's expectations hold,
Verified fires. When they don't, the diff from June 27 lands in a follow-up
postmortem before code moves.

**7. Fire pass 1 on Verified.** Ensemble arm only, 500 instances × 1 trial.
Number produced is the mechanism claim's evidence.

**8. Freeze pass 2 pre-registration.** With pass 1's observed K, update the
pre-reg, commit, freeze. Fire pass 2. Five-arm matrix produces the
equivalence-form claim substrate goes public with.

---

## Discipline for prevention

**Every confirmatory arm has a runs-300-Lite wire-check gate before Verified
fires.** June 27's 108/300 on Lite is the shape a working confirmatory
produces. Any drift from that shape on Lite blocks the Verified spend. This
design's Step 6 encodes the discipline; the pre-registration binds it. The
`firewall_violation` flake demoted at
`scripts/assay_swebench_confirmatory.py:175` is compensated by the
report's per-arm `firewall_violation` count — a run whose flake count exceeds
5% of cells falls under the publish-refusal branch.

**On any regression from a working shape, grep the git history before writing
code.** The 517 silent-fail count on the 2026-08-09 run was a regression from
June 27's 5-out-of-300. The first move on such a drift is `git log` on the
touched files. The postmortem is what happens when this step is skipped.

**Every topology stage declares a resource budget.** Docker calls per cell,
wall-clock per Docker call, model calls per stage — each named in the
topology's registration, each enforced by the runtime, each visible in the
topology's manifest. `select_exec`'s unbounded Docker load in the heavy
topology is what made the 2026-08-09 confirmatory hang; a declarative budget
per producer_kind catches it at build time. This is a follow-on kernel change
(declarative budgets per producer_kind) owned by the substrate kernel workstream,
targeted for the next kernel sprint after the confirmatory result lands. Named
here so the rule has a landing schedule.

---

## The one-line summary

The confirmatory returns to its working shape when the vocabulary under it is
stable (three named verdicts), the strings under it are shared (one closed
lexicon at the oracle boundary), the reader can tell one state from four, the
topology every arm dispatches is bounded (`swebench_repair_topology`), the
grader owns its containers (`run_swebench_one` with subprocess-timeout +
docker-kill), the runner writes exactly one typed row per cell, and the Verified
spend fires only after N=300 Lite matches the June 27 shape.

*Sources this version answers to:
`docs/review/REVIEW-2026-08-10-swebench-confirmatory-revert-v2.md`,
`docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md`,
`docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v2.md` (v2 on disk),
KIT_DIARY entry 26 (commit `0aab945`), sdd-kit-2 AGENTS.md, code cited at
verified current-HEAD line numbers.*

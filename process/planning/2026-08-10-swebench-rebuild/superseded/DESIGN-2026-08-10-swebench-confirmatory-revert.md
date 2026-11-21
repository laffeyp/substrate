# DESIGN — SWE-bench confirmatory, corrected shape (2026-08-10)

*Companion to `docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md`. The postmortem
names what broke and why; this doc specifies the fix at every layer — the topology,
the oracle, the grader, the runner, the report, and the five-arm matrix. When this
design lands the confirmatory produces the shape of the June 27 result on Verified.*

Source of truth for the working shape: KIT_DIARY entry 26, commit `0aab945`
(2026-06-27). 300/300 ran, 108 resolved (36%), 5 grade errors traceable to one
upstream cause, zero topology-side failures.

---

## The claim to measure

Pass 1 measures whether the ensemble mechanism — several free small models under
orchestration — produces patches that resolve real Verified issues at a nontrivial
rate. Pass 2 puts the number in equivalence form against a compute-matched single
strong model baseline, under Benjamini-Hochberg FDR across the five-arm matrix. The
pre-registration file at `docs/preregistrations/2026-08-swebench-lite.preg.json`
pins the comparator (Agentless + GPT-4o = 27.8% resolve on Lite; the Verified
equivalent lands in an amended pre-reg before pass 2 fires).

The number the confirmatory produces is credible when every layer under it produces
its own well-defined outcome, always, in bounded time. This doc specifies each of
those layers.

---

## The topology contract

**Name:** `swebench_repair_topology` at `topologies/swebench_solver/assemble.py:217`.
Already implemented. Already tested.

**Input:** a `PreparedPayload` (typed dict at `assay/swebench_suite.py:44`) plus a
responder list. The payload carries `base_checkout`, `repo_skeleton`, `known_files`,
`issue`, and the regression-set spec. The responder list is one Responder per draft
slot; length is `n`.

**Output:** exactly one `SelectedPatch` event per run. Its `model_patch` field is a
unified git diff against the base commit. Its `slot` and `reason` fields carry the
best-of-N provenance.

**Stages (three, ordered, bounded):**

1. **LOCALIZE.** One model call (`responders[0]`) reads the issue and the repo
   skeleton, returns the top-k suspect files. Emits `SuspectFiles`, `EditLocations`.
   Bound: one model call, ceiling on prompt at `element_localizer_factory`'s
   `_ELEMENTS_PER_FILE_CAP`.

2. **REPAIR.** N drafters (`responders[i]` for `i in 0..n`) each write
   SEARCH/REPLACE edits against the localized files. A validator clones the base
   checkout per candidate, applies the edits with the local applier at
   `applier.py:apply_candidate`, and emits `Verdict` + on success `AppliedPatch`.
   Max rounds = configurable (2 for pass 1). Correction rounds feed each round's
   failures to the next round's drafters. Bound: `n × max_rounds` model calls, each
   with a wall-clock ceiling per call.

3. **EMIT.** The first candidate whose validator returned passed=True becomes
   `SelectedPatch`. This is the June 27 `_first_patch_selector_factory` behavior
   at `assemble.py:158`. The topology emits one `SelectedPatch` and terminates on
   `RepairSummary` (the always-emit summary event at `records.py:139`).

**No Docker inside the topology.** The applier uses `git apply` locally against a
temp clone; the validator runs no tests. The topology's whole job is to produce a
git diff and hand it off. Testing the diff is the grader's job.

**Watchdog:** the topology's `termination` uses
`api.any_of(threshold_count("RepairSummary", 1), quiescence_with_watchdog(seconds=W))`.
Pass 1 sets W = 900s (15 min). No cell exceeds this wall-clock in the topology.

**Removed from the current heavy topology when this design lands:**
`swebench_solver_topology` at `assemble.py:398` and its stages `repro_gen`,
`repro_base_validate`, `select_exec`, `selector` stay in the codebase for
research use. They are not what the confirmatory arms dispatch. A future
experiment that measures the value of in-topology test-based selection uses that
topology explicitly.

## The oracle contract

**Name:** `SwebenchRecordOracle` at `assay/swebench.py:380`, revised to a
three-state grade.

**Result vocabulary gains a `status` field.** `Result` at `assay/oracle.py:35` adds:

```python
class Verdict(enum.Enum):
    RESOLVED = "resolved"
    NOT_RESOLVED = "not_resolved"
    NO_VERDICT = "no_verdict"

class Result(Struct, frozen=True):
    passed: bool           # True iff verdict == RESOLVED
    verdict: Verdict       # NEW — the honest three-state outcome
    detail: str            # carries reason when verdict == NO_VERDICT
    ...  # existing fields unchanged
```

`passed` remains for backward compat; every existing consumer keeps working.
`verdict` is the new load-bearing field. `NO_VERDICT` is the honest third state
covering harness timeout, container crash, missing report, harness exception.

**Grade contract:** for every `(record, ground_truth)` pair, `.grade()` returns
exactly one `Result` with a typed `verdict`. Every call returns; the runner never
sees a raise from the oracle. Every one of the three states is a definite outcome.

**Verdict-mapping rules (a closed table):**

| Harness state | verdict |
|---|---|
| `report.json` exists, `resolved: true` | `RESOLVED` |
| `report.json` exists, `resolved: false` | `NOT_RESOLVED` |
| `report.json` missing (harness timed out) | `NO_VERDICT` (reason=`harness_timeout`) |
| Container crashed (non-zero exit before report) | `NO_VERDICT` (reason=`container_crash`) |
| Docker daemon error | `NO_VERDICT` (reason=`docker_error`) |
| Harness raised (import, image 404) | `NO_VERDICT` (reason=`harness_error:<class>`) |

Silence at the harness becomes a typed outcome at the oracle. The runner rolls
none of these into `not_resolved`.

## The grader contract

**One function owns the harness call:** `run_swebench_one(instance_id, patch,
image, timeout) -> HarnessOutcome`. The outcome is one of the harness states above.
The function guarantees:

- Exactly one Docker container spawned per call, with a name the function tracks.
- A wall-clock deadline enforced by the function itself, not by the harness.
- On deadline: the function `docker kill`s the container it spawned and returns
  `HarnessOutcome(state="timeout", reason="deadline_at_{T}s")`.
- On any exception from the harness: the function catches it, cleans up, and
  returns `HarnessOutcome(state="harness_error", detail=repr(exc))`.
- On completion: parses the report.json, returns
  `HarnessOutcome(state="resolved" | "not_resolved", ...)`.

**Per-instance timeout is data, not a magic constant.** The default table lives at
`assay/swebench_timeouts.json` — one number per repo, derived from a one-time
measurement pass (base-only, empty patch, record wall-clock). sympy gets 90 min;
matplotlib gets 30 min; small repos get 10 min. The default when a repo is unknown
is 60 min. Callers may override per-call. The pre-registration for the confirmatory
pins the table's hash so a change to the table trips the pre-reg gate.

**Batch grade is a loop over `run_swebench_one`.** Not a single opaque
`run_swebench(all_predictions)` call. Sequential loop with a thread pool at
`max_workers=CONCURRENCY`, one instance at a time from each worker's perspective.
Each worker's `run_swebench_one` call owns its own container and its own wall-clock.
No worker leaks a container.

**No orphaned containers exist at any point.** Every container spawned inside
`run_swebench_one` is killed by the same call before it returns. The confirmatory
runner exits and Docker's `ps` shows no containers with our image tag.

## The runner contract

**Per-cell wall-clock budget.** Each cell has a hard budget covering the topology
run AND the grade call. Pass 1 sets this to the topology's watchdog (15 min) plus
the per-repo grade timeout (10-90 min) plus a small margin (5 min). Every cell
completes or fails within that budget.

**Every cell writes exactly one typed row to cells.jsonl.** The row's `source`
field takes one of a closed set: `run`, `salvage`, `timed_out`, `docker_error`,
`git_error`, `firewall_violation`. `verdict` field takes one of `resolved`,
`not_resolved`, `no_verdict`. `passed` is `verdict == "resolved"`.

**No cell exits without a row.** A cell that raises an unclassified exception
halts the sweep (the current typed error taxonomy at
`scripts/assay_swebench_confirmatory.py:_classify_cell_error` is the shape;
extend the closed set as new failure modes appear, do not silently swallow).

**Batch grade is optional and off by default.** With the bounded repair topology,
per-cell inline grade takes ~1-5 min per cell (one harness call, one container,
bounded). The June 27 shape ran inline; wall-clock was tractable. Batch grade
stays available as `SWEBENCH_BATCH_GRADE=1` for larger runs where the deferred
grade wins on wall-clock; the batch is a loop over `run_swebench_one` (per the
grader contract), not one opaque `run_swebench` call.

## The report contract

**Every headline reads as three numbers:** N attempted, M graded, K resolved.
Resolve rate = K/M. The K/N number appears with a `(M/N graded)` qualifier
attached. Both are always present; neither is presented alone.

**Verdict counts appear per arm.** `resolved`, `not_resolved`, `no_verdict`,
plus the per-cell error taxonomy counts (`timed_out`, `docker_error`,
`git_error`, `firewall_violation`). A reader sees where the run spent its cells
without opening a shell.

**The report refuses to publish "confirmatory" if graded_rate below threshold.**
Pre-reg pins the threshold. When `M/N < threshold`, the report emits a
`RUN_UNPUBLISHABLE` verdict block with the completion gap named. The
pre-registration also pins the per-arm graded-rate floor — a matrix arm with
80% graded and another with 40% graded is not a fair comparison; the report
refuses to compute a delta until both meet the floor.

## The five-arm matrix, revisited

Every arm builds `swebench_repair_topology` with the same shape. The arms differ
only in the responders passed in and the correction discipline (n, max_rounds).

- `single_draft_baseline` — one responder, n=1, max_rounds=1. The floor.
- `n_drafts_no_correction` — one responder, n=N, max_rounds=1. Best-of-N with
  no correction.
- `n_drafts_repair` — one responder, n=N, max_rounds=2. Best-of-N with the
  correction round.
- `n_drafts_repair_ensemble` — N responders (heterogeneous), n=N (one per model),
  max_rounds=2. The mechanism claim.
- `baseline_matched_compute` — one responder, n=K, max_rounds=1. K = median
  model_calls the ensemble arm consumed per case in pass 1. The compute-matched
  control.

Because every arm dispatches the same topology, per-cell wall is comparable
across arms. The DELTA between arms measures the mechanism, holding the topology
constant.

The current matrix code at `assay/swebench_matrix.py:88-130` routes every arm
through `_build_solver_arm_from_payload` → `solver_topology_from_payload` (the
heavy topology). This design changes that helper to build
`swebench_repair_topology` instead. The heavy topology stays in the codebase for
research; the arm helper stops dispatching it.

---

## The files that change

Ordered by dependency.

**`src/substrate/assay/oracle.py`** (~30 lines added). Add `Verdict` enum. Add
`verdict: Verdict` field to `Result` (default `NO_VERDICT` for backward compat).
Existing consumers of `passed` unchanged; new consumers read `verdict`.

**`src/substrate/assay/swebench.py`** (~100 lines changed). Refactor
`SwebenchRecordOracle.grade` and `SwebenchExtractOnlyOracle.grade` to return
typed `Verdict`. Add `run_swebench_one` — the per-instance grader that owns
container lifecycle and wall-clock. Refactor `batch_grade_from_records` to be a
loop over `run_swebench_one` under a thread pool. Add `read_swebench_timeouts()`
that reads `assay/swebench_timeouts.json` and returns the per-repo timeout map.

**`src/substrate/assay/swebench_matrix.py`** (~50 lines changed). Change
`_build_solver_arm_from_payload` to build `swebench_repair_topology` instead of
`swebench_solver_topology`. All five arm factories inherit the change.

**`src/substrate/topologies/swebench_solver/assemble.py`** (no change required
for the revert — `swebench_repair_topology` already exists at line 217 and works).
The heavy `swebench_solver_topology` at line 398 stays in place for future
research use.

**`scripts/assay_swebench_confirmatory.py`** (~150 lines changed). Every cell
row gains a `verdict` field. The runner's `cell()` writes rows with typed
verdicts from the oracle. Per-cell wall-clock budget = topology watchdog +
per-repo grade timeout + margin. Batch grade is a loop over `run_swebench_one`.
The row-writing path enforces "exactly one row per cell." Report reads verdict
counts and refuses to emit a confirmatory number when `M/N` falls under the
pre-reg threshold.

**`src/substrate/assay/report.py`** (~40 lines added). Three-number headline
(N/M/K) per arm. Verdict-count breakdown per arm. Publish-refusal branch when
graded_rate under threshold.

**`assay/swebench_timeouts.json`** (new file, ~15 lines). Per-repo timeout map.
Initial values from a one-time measurement pass.

**`tests/test_assay_oracle.py`** (~30 lines added). Round-trip tests for the
new `Verdict` field. Every existing test continues to pass — the change is
additive.

**`tests/test_assay_swebench.py`** (~60 lines added). Tests for the
three-state grade. Test each of the six harness-state → verdict mappings.

**`tests/test_assay_swebench_matrix.py`** (~20 lines changed). Update assertions
that the matrix arms build `swebench_repair_topology`.

Total: ~500 lines of code changed across 6 source files + 3 test files, plus one
new JSON.

## The verification gate before Verified fires

**Wire-check on Lite before firing on Verified.** After this design lands, the
confirmatory runner fires against SWE-bench Lite at n=20 instances first. The
number produced must fall within the June 27 shape: >30% resolved on the
graded subset, <5% NO_VERDICT, zero unclassified halts. When those hold, Verified
fires. When they do not hold, the diff from the last-working shape lands in a
follow-up postmortem, and the design revisits.

**Per-arm calibration on Lite before pass 2.** Each of the five matrix arms
runs against N=20 Lite instances to observe per-arm K (median model_calls per
case), per-arm wall, per-arm verdict distribution. The K value from
`n_drafts_repair_ensemble` becomes the `baseline_matched_compute` arm's K
parameter. The pre-registration is updated with the observed K and the arm hashes
land in `docs/preregistrations/`. Pass 2 fires after the pre-reg is committed.

## The next moves

**1. Land the vocabulary change.** `oracle.py` gets `Verdict`. Tests pass. One
commit.

**2. Land the grader refactor.** `swebench.py` gets `run_swebench_one` and the
loop-based `batch_grade_from_records`. Tests pass. One commit.

**3. Land the matrix routing change.** `swebench_matrix.py`'s
`_build_solver_arm_from_payload` builds `swebench_repair_topology`. Existing
matrix tests continue to pass with updated assertions. One commit.

**4. Land the runner + report changes.** `assay_swebench_confirmatory.py`
enforces per-cell contracts; `report.py` reads verdicts and enforces publish
threshold. Tests pass. One commit.

**5. Wire-check on Lite (N=20).** Fire the confirmatory. Read the numbers.
When they match the June 27 shape, proceed.

**6. Fire pass 1 on Verified.** Ensemble arm only, all 500 instances, 3 trials.
The number produced is the mechanism claim's evidence.

**7. Freeze the pass 2 pre-registration.** With pass 1's observed K, update the
pre-reg, commit, freeze. Fire pass 2. The five-arm matrix produces the
equivalence-form claim substrate goes public with.

---

## Discipline for prevention

Three rules the postmortem's contributing factors imply.

**Every confirmatory arm has a "runs 300 Lite" wire-check gate before Verified
fires.** June 27's 108/300 on Lite is the shape a working confirmatory produces.
Any drift from that shape on Lite blocks the Verified spend. This design's
step 5 encodes the discipline; the pre-registration binds it.

**On any regression from a working shape, grep the git history before writing
code.** The 517 silent-fail count on this week's run was a regression from June
27's 5-out-of-300. The first move on such a drift is `git log` on the touched
files, not a design proposal. The postmortem records what happens when this
step is skipped.

**Every topology stage declares a resource budget.** Docker calls per cell,
wall-clock per Docker call, model calls per stage — each named in the topology's
registration, each enforced by the runtime, each visible in the topology's
manifest. `select_exec`'s unbounded Docker load in the heavy topology is what
made this week's confirmatory hang; a bound would have caught it at build time.
This is a follow-on kernel change (declarative budgets per producer_kind) and
lands in a separate design doc.

---

## One-line summary

The confirmatory returns to its working shape by using the topology that already
works (`swebench_repair_topology`), an oracle that names its third state
(`NO_VERDICT`), a grader that owns its containers, a runner that guarantees one
typed row per cell, and a report that shows three numbers instead of one — a
day of coding across six source files, gated behind a Lite wire-check that
proves the shape holds before the Verified spend fires.

*Companions: `docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md` (what broke
and why); KIT_DIARY entry 26 (commit `0aab945`) as the working-shape reference;
`docs/NORTH-STAR-2026-08-10-v5.md` (product vision this measurement serves).*

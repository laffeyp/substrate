# POSTMORTEM — the SWE-bench topology got heavy and the confirmatory broke (2026-08-10)

*The confirmatory pass 1 on SWE-bench Verified ran the wrong topology. What was a
bounded, working shape on June 27 (300 Lite instances, 108 resolved, 5 grade
errors — all one cause) is now an unbounded shape that spawns eight or more Docker
containers per cell, hangs on hard test cases, and rolls silence into
`resolved=false` at the grader. This postmortem names what happened, when, why, and
what returns the system to working.*

---

## The working shape — June 27, 2026

Commit `0aab945` closed a full-set run on SWE-bench Lite:

- **Topology:** `swebench_repair_topology` at `topologies/swebench_solver/assemble.py:217`.
  It does three things: (1) LOCALIZE — one model call over the repo skeleton picks
  suspect files; (2) REPAIR — best-of-N SEARCH/REPLACE drafts from the model, each
  applied to a fresh clone via `git apply`; (3) EMIT — the first patch that applies
  cleanly is `SelectedPatch`. Docker inside the topology: **zero.**
- **Grade:** one `run_swebench` harness call per instance. Docker per grade: **one.**
- **Runner:** `scripts/assay_full_run.py` (created in commit `2af99eb`, deleted in
  commit `2a1ba59` on 2026-08-08). Simple loop over instances, per-instance
  try/except, checkpointed to `results.jsonl`, resumable.
- **Model:** qwen3-coder:480b-cloud, single strong model.
- **Result:** 300/300 ran. 108 resolved (36%). 5 errors, all one upstream cause
  (missing SWE-bench eval image on sympy — a 404, diagnosable in minutes from the
  harness log). Zero topology-side failures.

Total Docker containers per instance: **one**. Grade at the end, on the emitted patch.

## The drift — July 2026 through August 8, 2026

The `swebench_solver_topology` at `assemble.py:398` was built alongside the repair
topology to add "richer" selection logic. It has these additional stages:

- **REPRO_GEN** — a model call generates a Python script that reproduces the issue.
- **REPRO_BASE_VALIDATE** — one Docker run of the repro script against the unmodified
  base, to check that the repro discriminates (see `repro_base_validate_factory`,
  sprint 155).
- **SELECT_EXEC** — for every applied candidate patch, ONE Docker run to execute the
  repro script + a proximity regression set. Up to `n × max_rounds` Docker runs per
  cell — six with n=3, max_rounds=2 (see `_select_exec_factory` at assemble.py:97).
- **SELECTOR** — a deterministic rerank over the recorded TestResults.

The intent was Agentless-style rigor: the topology picks the best patch of N drafts
using tests, rather than the first-applied heuristic. Sprints 155, 157, 158, 159 all
built out this shape. The five-arm matrix in `assay/swebench_matrix.py:171` (sprint
159) wired every matrix arm through `_build_solver_arm_from_payload`, which routes
to `solver_topology_from_payload`, which builds `swebench_solver_topology`.

At sprint 159 the confirmatory infrastructure landed a new runner
(`scripts/assay_swebench_confirmatory.py`) that used the matrix arms exclusively.
The June 27 `assay_full_run.py` was deleted in the same commit (`2a1ba59`,
2026-08-08). Nothing in the codebase now dispatches `swebench_repair_topology`.

Total Docker containers per cell after the drift: **up to seven** (1 base repro + up
to 6 select_exec) inside the topology, plus **one** at grade time = up to eight per
cell.

## The current break — August 9-10, 2026

The Verified pass 1 sweep ran 1500 cells (500 instances × 3 trials × 1 ensemble
arm) through `swebench_solver_topology`. What happened:

1. **Per-cell Docker load exploded.** Each cell fired up to 7 in-topology Docker
   runs plus 1 grade Docker run. sympy and django cells routinely spawned 4-6
   containers each; the `select_exec` phase's per-candidate regression run took 20+
   minutes on sympy; some hung longer.

2. **Batch grade doubled the Docker work.** Commit `7e34feb` added a deferred grade
   that fires one big `run_swebench(preds, max_workers=8)` call at end of sweep.
   The batch grade re-ran the SAME test files inside the SAME container image the
   `select_exec` phase had already been running for its own selection logic. Grade
   duplicated topology work.

3. **The harness's own per-instance timeout (30 min) killed 517 grades before they
   wrote report.json.** The current `SwebenchExtractOnlyOracle` at
   `assay/swebench.py:405` falls back to `resolved=False` when the report file is
   missing. Silence became "not resolved." Charged as fails. 517 of 854
   patches got no grade at all.

4. **The final resolve number is a mixture.** 118 resolved out of 337 grades that
   completed = 35%. 118 out of 1500 cells = 7.9%. 118 out of 854 non-empty patches
   = 13.8%. Three different numbers, all reported, all misleading in isolation, and
   the run took ~11 hours to produce them.

Contrast June 27: 300 instances, 108 resolved, 5 grade errors, all diagnosable to
one upstream cause, ~1 Docker per instance, clean.

---

## Root causes

**RC1. The topology grew a duplicate of the harness.** `select_exec` inside the
topology runs the same class of Docker test execution that the swebench harness
runs at grade time. Both apply the patch, both spin the eval image, both run
pytest, both parse test outcomes. The topology's version exists to pick the best-of-N
candidate; the harness's version exists to grade. Doing both means every cell pays
Docker cost twice. On slow-test repos (sympy, django, matplotlib) the topology's
select_exec hangs at the same places the harness would; the topology times out;
the grade times out; the number lies.

**RC2. The matrix arms cut off the working topology.** The five-arm matrix at
`swebench_matrix.py:88-130` funnels every arm through
`_build_solver_arm_from_payload` → `solver_topology_from_payload` → the heavy
topology. `swebench_repair_topology` (the June 27 shape) is still defined in
`assemble.py:217` but nothing in the current runner path dispatches it. The
architectural choice at sprint 159 was to make the matrix arms all-solver, all the
time — no repair-only arm survived the sprint.

**RC3. The oracle rolls harness silence into `resolved=false`.**
`SwebenchExtractOnlyOracle.grade` at `assay/swebench.py:405` and
`SwebenchRecordOracle.grade` at `assay/swebench.py:415` both fall back to False on
FileNotFoundError. That is where the 517 silent fails come from. The vocabulary
admits two outcomes when the harness admits three (resolved, not_resolved, no
verdict). The lack of a third state at the oracle layer converts every harness
timeout, container crash, and daemon hiccup into a false negative.

Ordered by consequence: RC1 is the largest — the heavy topology creates the Docker
load that causes the hangs that cause the silences. RC2 is the enabler — the working
topology exists but no arm calls it. RC3 is the amplifier — silence becomes visible
fails instead of visible incompletes.

---

## Contributing factors — this week

**CF1. I optimized against the wrong bottleneck.** The 5-day wall-clock projection
that motivated batch grade was for the heavy topology. Reverting to the light
topology would have cut wall directly. Instead I added grade batching on top of a
topology that was already doing 8× too much Docker.

**CF2. I killed orphan containers thinking they were leaks.** The 23 sympy
containers "up 3 hours" I flagged at ~09:30 local were not leaks. They were the
batch grade's own in-flight work; the batch grade finished cleanly at 05:09 local,
four hours before I checked. The containers were leftover artifacts of grades that
had already returned False via the missing-report fallback. My kill affected
nothing because the process had already exited.

**CF3. I proposed band-aids.** First a longer timeout; then a three-state
vocabulary; then a five-state vocabulary. Each proposal accepted the topology-as-heavy
frame and worked around one symptom. None asked the question "why is the topology
running full pytest inside itself." The answer was in the codebase all along —
`swebench_repair_topology` right next to the heavy one, tested, proven, June 27.

**CF4. The last working confirmatory run and its script both got deleted in one
commit** (`2a1ba59`, 2026-08-08). The deletion left no runnable path to the June
27 shape. I did not re-read the git history when the current pass produced 8%
resolve; I diagnosed the timeout as if the heavy topology were the intended shape.

---

## What working looks like from here

The June 27 shape is one commit away.

1. **Reinstate a repair-only arm.** Add a factory in `assay/swebench_matrix.py` (or
   restore the `swebench_solver_arm` shape) that builds `swebench_repair_topology`
   instead of `swebench_solver_topology`. Same `PreparedPayload`, same responders,
   same n and max_rounds — the topology emits `SelectedPatch` as before, and the
   oracle grades it at the harness.

2. **Route the ensemble arm through the repair-only topology.** For pass 1's
   purpose (measuring whether the ensemble mechanism produces valid patches), the
   in-topology test execution was never needed. Best-of-N drafts + first-applied
   is what the June 27 run used to produce 36% resolve on Lite. The ensemble
   version fits the same shape.

3. **Grade once per instance at the end.** Batch grade is fine, and it is
   compatible with the light topology — the batch just gets clean patches to grade
   without duplicating the topology's own test runs. Or grade inline per cell,
   like June 27 — either shape works when the topology is bounded.

4. **The oracle records three outcomes, not two.** `RESOLVED`, `NOT_RESOLVED`,
   `NO_VERDICT` — the third named honestly. `NO_VERDICT` gets its own count in the
   report. Resolve rate is K/M where M = graded cells; the K/N number carries a
   qualifier. This is a small change and it makes future runs self-diagnosing.

5. **Delete the heavy topology from the arm matrix, or make it explicitly
   opt-in.** Keep `swebench_solver_topology` in the codebase for the day someone
   wants to measure the value of in-topology test-based selection specifically.
   Do not make it the default that every matrix arm silently uses.

---

## Discipline for prevention

Three rules from SDD apply directly here.

**Every station has a bounded contract.** The `swebench_solver_topology`'s
`select_exec` stage runs an unbounded number of Docker calls (up to n ×
max_rounds), each with an unbounded timeout (only capped by the topology's own
watchdog at 40 min). This is a topology-level poka-yoke gap. Every stage in the
topology should declare a hard resource budget; a stage that wants to run Docker
should declare "at most K containers, at most T seconds each, on failure ->
typed event." The current select_exec has none of these.

**One artifact per stage.** The topology emits `SelectedPatch` — the git diff —
and that is what the grader consumes. Everything the topology does INSIDE (repro,
select_exec, verdict) is upstream of that one artifact. If the internal work is
redundant with the grader's, cut it. If it is not, the ONE artifact still leaves
the topology, and the internal detail lives on the record for audit. The current
shape lets internal Docker work drag the whole cell's wall-clock past the grade's
own budget.

**A wire-check for regressions.** The June 27 run's numbers (300/300 ran, 108
resolved, 5 errors from one cause) are the shape a working confirmatory should
produce. Any run whose shape drifts from that (say, 517/854 no verdict) is a
regression, not a hard problem. The first move on such a drift is to grep the git
history for the last-working shape and diff. I skipped that step this week; the
postmortem is what happens next time I skip it.

---

## One-line summary

The topology I have been running does eight Docker containers per cell where the
working shape did one; that ratio, applied across 1500 cells, is the whole story
of the eleven hours, the 517 silent fails, and the number that means nothing.

*Sources: `git log` on `src/substrate/topologies/swebench_solver/assemble.py`,
`src/substrate/assay/swebench_matrix.py`, `scripts/assay_swebench_confirmatory.py`;
KIT_DIARY entry 26 (commit `0aab945`); commits `e13f095` (created
`swebench_repair_topology`), `2af99eb` (created `scripts/assay_full_run.py`),
`2a1ba59` (deleted `assay_full_run.py`, wired the five-arm matrix through
`solver_topology_from_payload`), `7e34feb` (added batch grade on top of the heavy
topology).*

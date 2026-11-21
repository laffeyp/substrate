# PLAN — repo cleanup for public release (DEEP survey; supersedes the earlier plan)

**Author:** Claude session 2026-08-31.
**Supersedes:** `PLAN-2026-08-31-repo-cleanup-for-public-release.md` (that pass called `process/` "done" against sibling `dev/` — it is not; sibling `dev/` is far more organized). This document is the full comparison, file by file, with the concrete target layout and the move list.

**Ground truth surveys run at open** (with tracked-file counts, sizes, and gitignore status).

---

## 1. Substrate root — every item classified

| Item | Type | Kind | Verdict |
|---|---|---|---|
| `src/` | dir | product code | keep |
| `tests/` | dir | product tests | keep |
| `docs/` | dir | product docs (mostly) — MIS-SHELVES 12 process artifacts | keep, but purge (see §3) |
| `scripts/` | dir | operator scripts | keep |
| `.github/` | dir | CI + issue templates | keep |
| `pyproject.toml` | file | build config | keep |
| `uv.lock` | file | dep lock | keep |
| `README.md` | file | first-page | keep, apply dellm |
| `CHANGELOG.md` | file | release notes | keep, apply dellm |
| `CONTRIBUTING.md` | file | contribution guide | keep, apply dellm |
| `SECURITY.md` | file | security policy | keep |
| `LICENSE` | file | Apache-2.0 | keep |
| `Dockerfile.arena` | file | discovery harness image | keep (belongs at root — Docker convention) |
| `demo.sh` | file | one-line demo | keep |
| `conftest.py` | file | pytest hooks | keep (root conftest is standard) |
| `process/` | dir | SDD ledger + everything | keep + massive reorganize (§2) |
| `.gitignore` | file | ignore rules | keep, expand (§4) |
| `.githooks/` | dir | pre-commit gate | keep |
| **`substrate-coding-flow*.json`** | 1,046 files, 4.1 MB | assay artifacts | **gitignored already; delete from disk** |
| **`substrate-test.s199d-e2e.json`** | 1 file, 476 B | orphan e2e output | **delete or move to process/runs/** |
| **`userinsights/`** | dir, 1 file | user-guide prose (`how-i-drive-the-session.md`) | **move to docs/user-guides/** |
| **`dist/`** | dir | build artifacts | gitignored; **delete from disk** (regenerable) |
| **`logs/`** | dir, 159 MB | eval-harness logs | gitignored already; **delete from disk** |
| `.venv/, .*_cache, __pycache__/` | dirs | tool caches | gitignored; no action |

**Root-level cleanup summary:** 1,048 files to delete from disk (1,046 root JSONs + 1 test artifact + 1 empty demo file). 3 folders to delete or move (`userinsights/`, `dist/`, `logs/`).

After cleanup, `ls substrate/` shows ~20 items instead of ~1,066.

---

## 2. Substrate `process/` — every item classified

Current shape: 27 subdirectories + 19 loose files at root. That is *not* the sibling's `dev/` organized shape. Substrate has kept every SDD artifact under `process/` but never grouped them by purpose.

### 2a. Kit-standard artifacts (stay at process/ root — SDD `AGENTS.md` and `WORKING_AGREEMENT.md` expect them there)

- `BLACKBOARD.md` — 548 KB, kit-canonical location.
- `KIT_DIARY.md` — 183 KB, kit-canonical.
- `WORKING_AGREEMENT.md` — 41 KB, kit-canonical.

Substrate does not ship an `ADDENDUMS.md` (only sdd-kit-2 has one). Not a gap; the kit's ADDENDUMS lives at the kit level, not per-project.

### 2b. Process artifacts CURRENTLY loose at process/ root — MOVE

**Ten REVIEW-*.md files** (238 KB total) currently at process/ root. Sibling has `dev/reviews/`. Substrate needs `process/reviews/`:

- REVIEW-2026-08-25-piece-a-work-in-progress.md
- REVIEW-2026-08-26-piece-b-closure-fold.md
- REVIEW-2026-08-26-piece-b-closure.md
- REVIEW-2026-08-26-piece-b-fold-and-215-216-red-team.md
- REVIEW-2026-08-26-piece-c-closure.md
- REVIEW-2026-08-26-sprint-210-piece-a-closure.md
- REVIEW-2026-08-28-code-quality.md
- REVIEW-2026-08-28-piece-b-red-team-close.md
- REVIEW-2026-08-28-un-reviewed-sprints-217-through-232b.md
- REVIEW-2026-08-31-session-topology-vs-specs.md

**Four planning docs** at process/ root — group as `process/planning/`:

- PHASE2.md — Phase-2 plan
- RESEARCH.md — accumulating research findings (50 KB)
- ROADMAP-2026-08-25-daily-driver.md
- TASK-BREAKDOWN-2026-08-25-daily-driver.md

**One raw fixture at process/ root:** `swebench-lite-full-qwen3coder480b-20260627.jsonl` (67 KB). Move to `process/runs/fixtures/` or delete if ephemeral.

### 2c. Run/results directories — GROUP under process/runs/

Substrate has **twenty-three (23)** loose top-level directories at process/ root that all hold run outputs. They fall into three families:

**Assay runs** (19 dirs, ~9.4 GB, 24,309 tracked files):

| Dir | Files | Size | Tracked |
|---|---|---|---|
| assay_lite_n300_6arm_2026-08-10 | 3,582 | 59 MB | 3,582 |
| assay_lite_n300_6arm_v2_2026-08-11 | 3,543 | 48 MB | 3,543 |
| assay_lite_n300_6arm_shim_2026-08-11 | 1,491 | 42 MB | 1,491 |
| assay_lite_n300_6arm_local_2026-08-11 | 1,084 | 33 MB | 1,084 |
| assay_shim_check_n30_pro_2026-08-11 | 968 | 32 MB | 968 |
| assay_wire_check_n300_2026-08-10 | 7,307 | 301 MB | 7,307 |
| assay_wire_check_n10_2026-08-10 | 41 | 1.4 MB | 41 |
| assay_wire_check_2026-08-10 | 15 | 620 KB | 15 |
| assay_full | 292 | 1.2 MB | 292 |
| assay_matrix | 4 | 16 KB | 4 |
| assay_repair | 2 | 8 KB | 2 |
| assay_container | 3 | 12 KB | 3 |
| assay_smoke | 1 | 4 KB | 0 (gitignored) |
| assay_host | 4 | 16 KB | 0 (gitignored) |
| assay_ws_gate | 1 | 4 KB | 0 (gitignored) |
| assay_confirmatory_swebench_lite_2026-08 | 2,837 | 9.1 GB | 0 (gitignored) |
| assay_confirmatory_swebench_verified_2026-08 | 7,735 | 379 MB | 0 (gitignored) |

**Bench + agency runs** (2 dirs):
- bench_results/ (4 files, 2.5 MB, 2 tracked — gitignored)
- agency_results/ (3 files, 12 KB, 3 tracked)

**Smoke + solve runs** (3 dirs):
- flask_solve/ (1 file, 4 KB, gitignored)
- solve_runs/ (2 files, 8 KB, gitignored)
- swebench_smoke/ (1 file, 4 KB, gitignored)

**Tracked-file total across the twenty-three run dirs: ~18,340 files.** Nearly all of those are committed to git and inflate the public-facing repo.

### 2d. Legitimate process/ subfolders (stay)

- `sprints/` — 145 files. Kit-standard.
- `signals/` — 12 files. Vocabulary locks + rationale + proposals. Load-bearing.
- `refactor-reviews/` — 3 files. Created 2026-08-28.
- `archive/` — 1,810 files, 35 MB, 1 tracked (README). Explicit archive folder. Content is gitignored.

### 2e. Cleanup at process/

- `.DS_Store` — gitignored (grep confirmed) but present on disk. Delete.

---

## 3. Substrate `docs/` — 12 process artifacts mis-shelved as docs

The following files under `docs/` are actually process artifacts and belong under `process/reviews/` or `process/planning/`:

**Reviews mis-shelved as docs (9 files):**
- REVIEW-2026-08-07-python-config-linting.md
- REVIEW-2026-08-08-swebench-solver.md
- REVIEW-2026-08-09-sdd-conformance-swebench-additions.md
- REVIEW-2026-08-09-swebench-runner-shape-and-walltime.md
- REVIEW-2026-08-10-swebench-confirmatory-revert-v2.md
- REVIEW-2026-08-10-swebench-holistic.md
- REVIEW-2026-08-11-swebench-re-review.md
- REVIEW-2026-08-12-round2-what-round1-missed.md
- REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md

**Planning docs mis-shelved as docs (3+ files):**
- ROADMAP-2026-08-12-swebench-rebuild-sprint-chain.md
- ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md
- POSTMORTEM-2026-08-10-swebench-topology-drift.md
- AUDIT-2026-08-12-substrate-usage-in-swebench-work.md
- PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md
- DESIGN-2026-08-10-swebench-confirmatory-revert.md
- DESIGN-2026-08-10-swebench-confirmatory-revert-v2.md
- DESIGN-2026-08-10-swebench-confirmatory-revert-v3.md
- DESIGN-2026-08-11-responder-rate-limit-shim.md

Nineteen files total. Move to `process/reviews/` (the REVIEW ones) and `process/planning/` (the ROADMAP/POSTMORTEM/AUDIT/PAPER/DESIGN ones).

What stays under `docs/` after the purge: product-facing docs — the how-to catalogue, API reference, walkthroughs, benchmarking design, tutorials, specs. Sample:
- adding-a-topology.md, api.md, applications.md, application-catalogue.md
- interactive-agent.md, tool-loop-*.md, output-conformance-design.md
- benchmarking-*.md, cockpit-design-round1.md, director-framing-round1.md
- swebench-*.md (roadmap, bridge-mapping, solver-design — arguable, but currently long-form design)
- replay.md, tutorial.md, README.md, three-way-intersection.md
- proof/, review/, preregistrations/, walkthroughs/, specs/, cradle-x-substrate/

---

## 4. Sibling `dev/` shape vs proposed substrate `process/` shape

**Sibling's dev/ (per source doc):**
```
dev/
├── BLACKBOARD.md
├── KIT_DIARY.md
├── WORKING_AGREEMENT.md
├── ADDENDUMS.md
├── sprints/
├── signal-reports/
├── sdd-kit-2/                         (vendored)
├── persona-reviews/
└── reviews/
```

**Proposed substrate process/ (target):**
```
process/
├── BLACKBOARD.md                       # kit-canonical, stays
├── KIT_DIARY.md                        # kit-canonical, stays
├── WORKING_AGREEMENT.md                # kit-canonical, stays
├── sprints/                            # 145 files, kit-canonical
├── signals/                            # 12 files, vocab locks
├── reviews/                            # NEW — group 10 root REVIEWs + 9 docs/REVIEWs
├── refactor-reviews/                   # keep as-is (3 files)
├── planning/                           # NEW — PHASE2, ROADMAP, TASK-BREAKDOWN,
│                                       #   RESEARCH, POSTMORTEM, AUDIT, PAPER, DESIGN,
│                                       #   plus swebench-* ROADMAPs from docs/
├── runs/                               # NEW — group every _run/results/assay dir
│   ├── assays/                         # 19 assay_* dirs
│   ├── benches/                        # bench_results/, agency_results/
│   ├── smokes/                         # flask_solve/, solve_runs/, swebench_smoke/
│   └── fixtures/                       # the loose swebench-lite-*.jsonl at process/ root
├── archive/                            # keep as-is (gitignored contents)
└── (no other loose files)
```

**Differences from sibling to note:**
- Substrate does not vendor `sdd-kit-2` — it lives one level UP at project root, shared with substrate-ui. Do not move.
- Substrate does not ship `signal-reports/` — the sibling project's per-sprint output-report pattern is not in use here.
- Substrate does not ship persona-reviews.
- Substrate ships `signals/` (vocabulary locks) — sibling probably does too under a different name.
- Substrate ships `runs/` — sibling's shape does not name a runs folder (its project's outputs live elsewhere).

---

## 5. Execution — sprint chain in order

Sequence per the source doc: docs first (dellm + ledger backfill), moves last. Gates between every step. `git mv` for every folder rename so `git log --follow` walks history.

### Sprint 245 — root-level cleanup (delete debris + move userinsights)

1. Delete 1,046 `substrate-coding-flow*.json` files at root (gitignored; regenerable).
2. Delete `substrate-test.s199d-e2e.json` at root.
3. Delete `dist/` from disk (gitignored; regenerable).
4. Delete `logs/` from disk (gitignored; 159 MB; regenerable).
5. `git mv userinsights docs/user-guides` (or `docs/user_guides` — pick one convention).
6. Delete `process/.DS_Store` and `docs/.DS_Store` where present.
7. Add `substrate-test.*.json` and any missed patterns to `.gitignore`.

Gates: `uv run python -m pytest tests/ -q --timeout=90` still green; `git status` shows only the expected deletions + one move; `ls substrate/` shows ≤ 25 items.

Estimated: 30 minutes.

### Sprint 246 — process/reviews/ + process/planning/ + process/runs/ scaffolding

1. `mkdir process/reviews process/planning process/runs process/runs/assays process/runs/benches process/runs/smokes process/runs/fixtures`.
2. Blast-radius grep for hard-coded paths pointing at any of the 23 run directories currently at process/ root:
   ```bash
   grep -rIn --include='*.py' --include='*.toml' --include='*.md' --include='*.sh' \
     --exclude-dir=.venv --exclude-dir=process \
     -E 'process/(agency_results|assay_|bench_results|flask_solve|solve_runs|swebench_smoke)' .
   ```
   Every hit needs the path updated in the same commit as the move.
3. Do not move yet — this sprint just scaffolds + does the grep.

Gates: greps produce a list of files to touch in sprint 247.

Estimated: 30 minutes.

### Sprint 246a — ROOT-CAUSE the output paths that create this mess

This is the sprint the earlier plan missed. Moving files without fixing the scripts that write them means the next run recreates the old layout at process/ root, and the next SWE-bench eval dumps another 100 JSON files at repo root. The reorg leaks unless the sources land at the new paths.

**Source 1 — 11 scripts hardcode `process/<subdir>/` defaults.** Every one either overrides via env var or wires the path inline. Files + lines:

| Script | Line | Current default | New default (after sprint 248) |
|---|---|---|---|
| scripts/assay_container_run.py | 65 | `process/assay_container` | `process/runs/assays/container` |
| scripts/assay_swebench_confirmatory.py | 22-23, 168-169 | `process/assay_smoke/*` (env-overridable) | `process/runs/assays/smoke/*` |
| scripts/assay_swebench_run.py | 56 | `process/assay_run` | `process/runs/assays/run` |
| scripts/agency_assay.py | 187 | `process/agency_results` (env-overridable) | `process/runs/benches/agency` |
| scripts/assay_repair_topology_verify.py | 31 | `process/assay_repair` | `process/runs/assays/repair` |
| scripts/assay_host_run.py | 64 | `process/assay_host` | `process/runs/assays/host` |
| scripts/assay_workspace_gate.py | 49 | `process/assay_ws_gate` | `process/runs/assays/ws_gate` |
| scripts/assay_matrix_run.py | 47 | `process/assay_matrix` | `process/runs/assays/matrix` |
| scripts/flask_solve.py | 166 | `process/flask_solve` | `process/runs/smokes/flask` |
| scripts/bench_coding.py | 50 | `process/bench_results/coding_cells.jsonl` (env-overridable) | `process/runs/benches/coding/coding_cells.jsonl` |
| scripts/solve_instance.py | 158 | `process/solve_runs` | `process/runs/smokes/solves` |

Each is a one-line default swap plus an env-var name (where present) that a downstream doc references. Order these edits alongside sprint 248's git-mv so the source and destination move in one commit.

**Source 2 — the 1,046 root-level `substrate-coding-flow*.json` files.** Root cause: `swebench.harness.run_evaluation` (upstream lib) writes a `<model_name>.<run_id>.json` at `Path.cwd()` regardless of the `report_dir` argument. `src/substrate/assay/swebench.py:401-406` documents the behavior and reads from both locations at retrieval time:

```python
# "the report.json may land in CWD regardless of `report_dir`. So SEARCH the known
# candidate roots"
for cand in (rdir / report_name, Path.cwd() / report_name):
    if cand.exists():
        return read_run_report(cand)
```

Substrate today `.gitignore`s the pattern (`substrate-*.json` + `substrate-coding-flow.*.json`) but nothing stops the physical write. The fix at root cause: wrap every `run_evaluation.main(...)` call site in a `contextlib.chdir(report_dir)` block so the harness writes into the controlled directory, not repo root.

Call sites in `src/substrate/assay/swebench.py`:
- Line ~381: the single-cell path via `write_predictions(...)`.
- Line 1185: the batch `run_evaluation.main(...)` call inside `_run_batch_via_harness_map`.

Two edits, one file. Sketch:

```python
import contextlib, os
# ... at each call site:
with contextlib.chdir(report_dir):
    run_evaluation.main(
        ...,
        report_dir=str(report_dir),   # harness's own arg
        ...
    )
```

Belt-and-braces addition: after each call, sweep `Path.cwd().glob(f"{model_name}*.json")` — every unexpected drop into the wrong dir moves into `report_dir` before return. Costs three lines; catches an upstream regression the chdir might not.

**Source 3 — orphan `substrate-test.s199d-e2e.json` at root.** Find the test/script that writes it. Grep returns zero hits under `.py` files, so this is a one-shot artifact from a manual run. Delete + gitignore the pattern (`substrate-test.*.json`) so a future test that echoes to root does not commit.

**Verification — every source under test, not a proxy.**

Every script whose default path changed gets an actual run. Every `run_evaluation` call site with a chdir wrap gets an actual invocation. Every gitignore addition gets a synthetic file at that pattern to prove it holds. The check is not "one smoke run." The check is "the source cannot leak."

Per-source observation contract:

**Every one of the 11 scripts, each invoked live.** Baseline output count at each new path before invocation, invoke with the smallest legitimate input the script accepts, assert the new path grew and no old path saw a write. Concretely (one row per script):

| Script | Invocation | Assert new path grew | Assert old path did NOT grow | Assert repo root did NOT grow |
|---|---|---|---|---|
| assay_container_run.py | one-instance dry-run | `process/runs/assays/container/` file count went up | `process/assay_container/` unchanged | `ls substrate/*.json` unchanged |
| assay_swebench_confirmatory.py | env-unset invocation | `process/runs/assays/smoke/` grew | `process/assay_smoke/` unchanged | root unchanged |
| assay_swebench_run.py | one-instance | `process/runs/assays/run/` grew | `process/assay_run/` unchanged | root unchanged |
| agency_assay.py | env-unset invocation | `process/runs/benches/agency/` grew | `process/agency_results/` unchanged | root unchanged |
| assay_repair_topology_verify.py | one-instance | `process/runs/assays/repair/` grew | `process/assay_repair/` unchanged | root unchanged |
| assay_host_run.py | one-instance | `process/runs/assays/host/` grew | `process/assay_host/` unchanged | root unchanged |
| assay_workspace_gate.py | invocation | `process/runs/assays/ws_gate/` grew | `process/assay_ws_gate/` unchanged | root unchanged |
| assay_matrix_run.py | invocation | `process/runs/assays/matrix/` grew | `process/assay_matrix/` unchanged | root unchanged |
| flask_solve.py | invocation | `process/runs/smokes/flask/` grew | `process/flask_solve/` unchanged | root unchanged |
| bench_coding.py | env-unset invocation | `process/runs/benches/coding/coding_cells.jsonl` written | `process/bench_results/` unchanged | root unchanged |
| solve_instance.py | one-instance | `process/runs/smokes/solves/` grew | `process/solve_runs/` unchanged | root unchanged |

**Every `run_evaluation.main` call site under the chdir wrap:** invoke the single-cell path (`swebench.py:381`) with one prediction. Invoke the batch path (`swebench.py:1185`) with two predictions. Both invocations run against a real (or hermetic-stub) SWE-bench instance, or against a mocked `run_evaluation.main` that writes to `Path.cwd()` the way the real one does. After each: `ls substrate/*.json | wc -l` returns 0. Repeat 3× consecutively to catch a race.

**Every gitignore addition tested by placing a synthetic file and running `git status`:** touch `substrate-test.sample.json`; `git status | grep substrate-test`; if the pattern was added correctly the file is untracked-and-ignored. Delete after.

**Every gitignore removal tested by removing the entry, touching the pattern, and confirming git NOW sees it — then re-adding the entry.** Regression protection for the ignore.

**Every moved directory's downstream readers verified:** grep for readers of each old path (`process/assay_*/`, `process/bench_results/`, etc.). Every hit is either a script we already updated (sprint 246a) or a doc that references the path (sprint 247's sed sweep). No hit outside those two classes.

**Full-suite pytest:** `uv run python -m pytest tests/ -q --timeout=120` green. Non-negotiable.

**Repo state:** `ls substrate/*.json 2>/dev/null | wc -l` returns 0. `git status` shows only the expected diff. `git ls-files | grep -E 'process/assay_' | wc -l` returns 0 (the moves closed the old paths in the tree).

Halt if any script's live run writes to an old path or to repo root. Halt if any chdir-wrapped `run_evaluation.main` invocation drops a JSON at repo root. Halt if the full suite fails. Halt if the gitignore synthetic-file check fails.

Estimated: 3-5 hours (11 script live runs + 2 chdir invocations × 3 reps + gitignore synthetic-file tests + full suite). Dispatches BEFORE sprint 248 so the moves land against a corrected output path, not the old one.

### Sprint 247 — move REVIEW + PLAN docs (10 root + 9 docs/ files)

1. `git mv process/REVIEW-*.md process/reviews/` (10 files).
2. `git mv docs/REVIEW-2026-08-*.md process/reviews/` (9 files).
3. `git mv process/PHASE2.md process/planning/`.
4. `git mv process/RESEARCH.md process/planning/`.
5. `git mv process/ROADMAP-*.md process/planning/`.
6. `git mv process/TASK-BREAKDOWN-*.md process/planning/`.
7. `git mv docs/ROADMAP-*.md docs/POSTMORTEM-*.md docs/AUDIT-*.md docs/PAPER-*.md docs/DESIGN-2026-08-*.md process/planning/`.
8. sed-sweep any doc that references these paths inline. Anchor patterns: `` ` ``, `(`, ` ` (per source-doc guidance).
9. Verify no `dev/dev/` or `process/process/` double-slash bugs.

Gates: `uv run python -m pytest tests/ -q --timeout=90` green; every internal link resolves.

Estimated: 1 hour.

### Sprint 248 — move the 23 run directories under process/runs/

1. `git mv` the 17 tracked assay directories to `process/runs/assays/` (rename to drop the `assay_` prefix optionally — `runs/assays/lite_n300_6arm_2026-08-10/` reads cleaner than `runs/assays/assay_lite_n300_6arm_2026-08-10/`).
2. `git mv process/bench_results process/runs/benches/coding` (and similar for agency_results).
3. Update `.gitignore` for every renamed path:
   - `process/bench_results/` → `process/runs/benches/`
   - `/process/assay_smoke/` → `/process/runs/assays/smoke/`
   - `/process/assay_ws_gate/` → `/process/runs/assays/ws_gate/`
   - `/process/assay_host/` → `/process/runs/assays/host/`
   - `/process/assay_run/` → `/process/runs/assays/run/` (currently referenced but not on disk)
   - `/process/flask_solve/` → `/process/runs/smokes/flask/`
   - `/process/solve_runs/` → `/process/runs/smokes/solves/`
   - `process/swebench_smoke/` → `process/runs/smokes/swebench/`
   - `process/archive/root-debris-20260722/` → unchanged (still under archive/)
   - `process/assay_confirmatory_swebench_lite_2026-08/` → `process/runs/assays/confirmatory_lite_2026-08/`
   - `process/assay_confirmatory_swebench_verified_2026-08/` → `process/runs/assays/confirmatory_verified_2026-08/`
4. `git mv process/swebench-lite-*.jsonl process/runs/fixtures/`.
5. sed-sweep every script under `scripts/` that writes to or reads from these paths.
6. Verify `scripts/agency_assay.py`, `scripts/assay_container_run.py`, etc. still resolve their output roots.

Gates: full pytest green; a smoke assay run writes to the new location (do NOT run a real assay — check the destination-path logic instead via dry-run or a targeted unit test).

Estimated: 2 hours. High blast radius; every script that touches these paths needs verification.

Optional deferral: leave the two `assay_confirmatory_*` dirs alone — they hold 9.5 GB of gitignored data and represent finished research. Rename in place if the reader benefits; do not disturb the content.

### Sprint 249 — BLACKBOARD backfill for sprints 240-244

Prepend one entry per sprint to `## Built`:
- **Sprint 240:** SessionStarted instrument wired on RunStarted. Closes REVIEW-2026-08-28-piece-g-full SDD-1. Files: `topologies/session/__init__.py`. Test: `test_session_started_instrument.py`.
- **Sprint 241:** Regenerated 18 bundled CI records post-240 fingerprint bump; fixed the kind-set assertion at `test_session_topology_e2e.py:97`.
- **Sprint 242:** HMAC cursor delimiter bug fix. Root cause: signature contained 0x2E ~12% of the time; `split(b'.', 1)` cut the signature short. Fix: fixed 32-byte prefix. Regression test at 200 round-trips.
- **Sprint 243:** Three failure-mode E2E tests. `park-on-model-error`, `park-on-interrupt`, `end-on-cap`. All green post-244.
- **Sprint 244:** Session model producer awaits `driver.arespond`. Unblocks `cancel_producer` during a slow model call. `DeterministicResponder.arespond` added (delegates to sync `respond` — CI record byte-identical). Closes TECH-SPEC §11's Ctrl+C promise.

Gates: `grep 'Sprint 24[0-4]' process/BLACKBOARD.md` returns five hits.

Estimated: 30 minutes.

### Sprint 250 — ledger backfill diff (fold-in-place, per source doc)

1. Diff every sprint file's id against ## Built + ## Sprint tail coverage.
2. For each id not covered by either a per-sprint entry or an explicit rollup range, either add a per-sprint entry or extend the closest rollup range.
3. Source of truth is the sprint file bodies.

Gates: `ls process/sprints/ | grep -oE 'sprint-[0-9]{3}[a-z]?' | sort -u | wc -l` matches the count of unique ids covered in ## Built / ## Sprint tail.

Estimated: 1 hour (based on sibling's 5 sprints backfilled; substrate may have a similar-scale gap).

### Sprint 251 — dellm on README + CONTRIBUTING + SECURITY

Run the `dellm` skill on each. Verify each rewrite does not change a fact against the code (numeric claims especially — the sibling caught two content errors this way).

Gates: `wc -w` before/after; word-count delta 5-40% cuts expected; no changed claim.

Estimated: 1-2 hours.

### Sprint 252-256 — dellm on docs/ how-to cluster

Five sprints, one per doc cluster:
- 252: api.md + applications.md + application-catalogue.md
- 253: adding-a-topology.md + tutorial.md + demo.md
- 254: interactive-agent.md + tool-loop-*.md (four files)
- 255: benchmarking-*.md + output-conformance-design.md
- 256: swebench-*.md + cockpit-design-round1.md + director-framing-round1.md

Estimated: 1-2 hours per sprint, 5-10 hours total.

### Sprint 257 — repo-cleanup close-out doc

Author a sibling to `repo-cleanup-for-public-release.md` at project root or substrate root: `substrate-cleanup-notes-2026-08-31.md`. Names what applied, what did not (no sdd-kit vendoring, no signal-reports pattern), the sprint chain the substrate side actually ran, and what stayed on disk vs went into `.gitignore`.

Estimated: 30 minutes.

---

## 6. Totals

- **13 sprints** (245-257), ~15-20 hours of Architect + Agent time.
- **1,048 files deleted** from disk at root.
- **19 files moved** from process/root and docs/root into process/reviews/ or process/planning/.
- **23 directories moved** from process/root into process/runs/ subgroups.
- **~18,340 tracked files** re-parented under process/runs/ (git-tracked rename).
- **`ls substrate/` before:** ~1,066 items. **After:** ~20.
- **`ls process/` before:** 46 items. **After:** ~10 (3 kit-canonical + 5 grouped subfolders + 2 legitimate legacy — sprints, signals, refactor-reviews, reviews, planning, runs, archive).

---

## 7. Sequencing across all 14 sprints

Per source doc: rewrites first (docs are still in their old paths at that point), moves last. Root-cause script fixes land BETWEEN scaffolding and physical moves so the moves land against corrected paths.

1. **Sprint 249** — BLACKBOARD backfill for 240-244 (30 min).
2. **Sprint 250** — ledger diff pass (1 hr).
3. **Sprint 251** — dellm README + CONTRIBUTING + SECURITY (1-2 hrs).
4. **Sprints 252-256** — dellm docs/ cluster (5-10 hrs).
5. **Sprint 245** — root debris deletion (30 min).
6. **Sprint 246** — process/ subfolder scaffolding + blast-radius grep (30 min).
7. **Sprint 246a** — ROOT-CAUSE the output paths (2-3 hrs). Every source that writes the old paths gets updated: 11 script defaults + `contextlib.chdir` wrap around 2 `run_evaluation.main` call sites + delete-and-gitignore the orphan root artifact. Verify one live invocation writes to the new location.
8. **Sprint 247** — move REVIEW + PLAN docs (1 hr).
9. **Sprint 248** — move the 23 run directories (2 hrs). Now safe because 246a already updated the scripts that write them.
10. **Sprint 257** — close-out doc (30 min).

Total: 15-22 hours. Break into 2-3 working sessions.

Gates between every sprint: `pytest tests/ --timeout=90` green; `git status` shows only expected changes; `ls` at root and process/ produce the expected surface count.

---

## 8. What this plan does not do

- Does not move `sdd-kit-2/` — it lives at project-root level (`Agent Orchestration/sdd-kit-2/`), shared with substrate-ui. Substrate does not vendor it.
- Does not rewrite closed sprint cards, BLACKBOARD paragraphs, KIT_DIARY entries — rule 12 preserves the audit trail.
- Does not touch `substrate-ui/` — that repo needs its own parallel plan.
- Does not force-push or rewrite history to purge the 18,340 tracked assay files. That is a git-filter-repo operation, high-risk, and beyond the "cleanup for public release" scope this plan targets. Reader sees them in the git tree; that is acceptable for a research-project public release, provided the current-state layout reads clean.

---

*PLAN-2026-08-31-repo-cleanup-DEEP.md. Real substrate-vs-sibling comparison. 1,048 root files to delete, 19 process artifacts to move out of docs/ and process/root, 23 run directories to group under process/runs/. Thirteen sprints, 13-19 hours. Author: Claude session 2026-08-31.*

# CLOSEOUT — substrate repository organization

*2026-11-20. What the repository-organization work moved and added, with a map from old paths to new. The guide behind it is `docs/document-organization-guide-2026-10-30/GUIDE-2026-10-30-reorganizing-files-and-folders-r3.md`. Names did not change on any move, so a document that still cites an old path resolves with `find . -name <file>`; this map lists the moves a document is most likely to cite.*

## What the 2026-08-31 cleanup moved (sprints 245–248)

Planned in `superseded/PLAN-2026-08-31-repo-cleanup-DEEP.md` and run that day:

- The ~1,046 `substrate-coding-flow*.json` and the orphan `substrate-test.*.json` at the repository root were deleted from disk and gitignored.
- The 23 run directories at `process/` root moved under `process/runs/`, grouped into `assays/`, `benches/`, `smokes/`, `fixtures/`; the 11 scripts that write them were repointed to the new defaults, and `.gitignore` was updated.
- 19 reviews and designs mis-shelved under `docs/` moved to `process/reviews/` (the `REVIEW-*`) and `process/planning/` (the `ROADMAP-`, `DESIGN-`, `POSTMORTEM-`, `AUDIT-`, `PAPER-`).

Path map for the 2026-08-31 moves:

| Old path | New path |
|---|---|
| `process/assay_<run>/` (e.g. `assay_lite_n300_6arm_2026-08-10/`) | `process/runs/assays/<run>/` (prefix `assay_` dropped) |
| `process/bench_results/` | `process/runs/benches/coding/` |
| `process/agency_results/` | `process/runs/benches/agency/` |
| `process/flask_solve/`, `process/solve_runs/`, `process/swebench_smoke/` | `process/runs/smokes/{flask,solves,swebench}/` |
| `docs/REVIEW-2026-08-*.md` | `process/reviews/` |
| `docs/{ROADMAP,DESIGN,POSTMORTEM,AUDIT,PAPER}-2026-08-*.md` | `process/planning/` (grouped into pieces on 2026-11-20, below) |

## What 2026-11-20 moved

- 81 loose documents at `process/planning/` root grouped into 16 pieces of work, each `YYYY-MM-DD-subject/` with earlier rounds in its `superseded/`. The full row-by-row map is `../2026-11-20-planning-reorganization/move-table.txt`.
- `process/planning/RESEARCH.md` → `process/RESEARCH.md` (its own title and the BLACKBOARD already named it there).
- `process/refactor-reviews/PLAN-2026-08-31-repo-cleanup-DEEP.md` and `-for-public-release.md` → `process/planning/2026-11-20-repo-organization/superseded/`.

| Old path | New path |
|---|---|
| `process/planning/<TYPE>-<date>-<subject>.md` | `process/planning/<piece>/[superseded/]<same name>` (see `2026-11-20-planning-reorganization/move-table.txt`) |
| `process/planning/RESEARCH.md` | `process/RESEARCH.md` |
| `process/refactor-reviews/PLAN-2026-08-31-repo-cleanup-DEEP.md` | `process/planning/2026-11-20-repo-organization/superseded/PLAN-2026-08-31-repo-cleanup-DEEP.md` |
| `process/refactor-reviews/PLAN-2026-08-31-repo-cleanup-for-public-release.md` | `process/planning/2026-11-20-repo-organization/superseded/PLAN-2026-08-31-repo-cleanup-for-public-release.md` |

## What 2026-11-20 added

- `process/planning/README.md` — the planning index, one row per piece of work with its status.
- `RUNBOOK-2026-11-20-substrate-r2.md` — the repository runbook (round 1 superseded the same day; it is in `../substrate-boundary-and-runbook-2026-11-09/superseded/`).
- `process/reviews/README.md`, `process/sprints/README.md`, `process/runs/README.md`, `process/runs/assays/README.md`, `process/signals/README.md` — the five folder indexes.
- `process/WORKING_AGREEMENT.md` `## Documents` — the four document kinds and their change rules.
- `process/BLACKBOARD.md` reordered into one newest-last append-only stream; the sectioned original is `process/archive/BLACKBOARD-to-2026-11-20.md`.
- This piece's research, plan and this close-out.

## What was left undone, on purpose

- `BACKLOG.md` is not added; the `## Deferred` and `## Open questions` content of the BLACKBOARD holds that material.
- `OPEN-ITEMS` is deferred to the boundary refactor's first epic, where the rolling-wave planning uses it.
- The 18,336 tracked assay records are not un-tracked; the guide does not reach git weight, and the 2026-08-31 plan chose to keep them tracked. They are already grouped under `process/runs/assays/` and indexed.

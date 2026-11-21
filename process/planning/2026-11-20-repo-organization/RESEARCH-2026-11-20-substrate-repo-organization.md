# RESEARCH — applying the file-organization guide to the whole substrate repository

*2026-11-20. The task is to bring all of `substrate/` to `docs/document-organization-guide-2026-10-30/GUIDE-2026-10-30-reorganizing-files-and-folders-r3.md`, not only `process/planning/`, which was done earlier today. This document surveys the repository as it stands, measures it against the guide's rules and its worked-example layout, states what prior work already did, names what remains, says what programs read so it does not move, and settles the approach. One item is a decision for the owner. A plan follows this research.*

Sources read in full: the file-organization guide r3; the three prior cleanup documents in `process/refactor-reviews/` (`PLAN-2026-08-31-repo-cleanup-DEEP.md`, `PLAN-2026-08-31-repo-cleanup-for-public-release.md`, `PLAN-2026-08-28-hygiene-splits.md`); `process/archive/README.md`. Measurements taken at open: `git ls-files` counts per directory, `.gitignore`, the BLACKBOARD section structure, the READMEs present under `process/`, and the readers of `process/runs/assays`.

---

## What is already done

The guide's largest moves are behind us. Two passes did them.

**The 2026-08-31 cleanup.** `PLAN-2026-08-31-repo-cleanup-DEEP.md` surveyed the whole repository and ran its sprints 245–248. The `.gitignore` comment dated 2026-08-31 records the result: "every process/ run/output directory now lives under `process/runs/{assays,benches,smokes,fixtures}/`." Measured now against that plan's targets:

- Root is 13 tracked files (`.gitignore`, `CHANGELOG.md`, `CLAUDE.md`, `conftest.py`, `CONTRIBUTING.md`, `demo.sh`, `Dockerfile.arena`, `LICENSE`, `pyproject.toml`, `README.md`, `RUNBOOK-2026-11-20-substrate-r1.md`, `SECURITY.md`, `uv.lock`). The 1,046 root assay JSONs the plan named are gone; the orphan `substrate-test.*.json` and the `substrate-coding-flow.*.json` pattern are gitignored.
- `docs/` holds only product-facing documents at its top (`adding-a-topology.md`, `api.md`, `application-catalogue.md`, `applications.md`, `compaction.md`, `demo.md`, `README.md`, `replay.md`, `schema-evolution.md`, `tutorial.md`) plus organized subfolders (`specs/`, `walkthroughs/`, `design/`, `swebench/`, `language/`, `tool-loop/`, `benchmarking/`, `research/`, `cradle-x-substrate/`, `user-guides/`). The 19 reviews and designs the plan named as mis-shelved under `docs/` are now in `process/reviews/` and `process/planning/`.
- `process/runs/` holds the run corpus: `assays/` (18,336 tracked files across 19 run directories), `benches/`, `smokes/`, `fixtures/`. The 11 scripts write there by default.

**The planning folder, today.** 81 loose documents under `process/planning/` became 16 pieces of work with an index (`process/planning/README.md`); `RESEARCH.md` was restored to `process/RESEARCH.md`. Commit `fb8def12`.

**The runbook, today.** `RUNBOOK-2026-11-20-substrate-r1.md` at the repository top. Commit `b820c3ad`.

So root hygiene, the `docs/` purge, the run-directory grouping, the review grouping, the planning grouping, and the runbook — the guide's steps 7 through 9 and its worked-example top-level and `process/` shape — are in place. What follows is the delta against the guide's finer rules.

---

## The guide's worked-example layout, measured against substrate

The guide's worked example is one shape, not a mandate; rule 8 keeps a folder that already means something. The mapping, with substrate's name where it differs:

| Guide element | Substrate | State |
|---|---|---|
| `README.md`, runbook, `AGENTS.md`-equivalent, `WORKING_AGREEMENT.md`, `LICENSE`, build config at root | all present (`CLAUDE.md` is the method shim; runbook added today) | conforms |
| `LOG.md` (append-only, newest last) | `process/BLACKBOARD.md` (sectioned, sdd-kit-2 shape) | gap — see Finding 1 |
| `LESSONS.md` | `process/KIT_DIARY.md` | conforms (same role, kit name) |
| `process/tasks/` (task cards) | `process/sprints/` (272 cards) | conforms (kit name; rule 8) |
| `process/planning/` with `README.md` index and pieces of work | present, indexed today | conforms |
| `process/reviews/` | present (21 reviews), no index | gap — see Finding 2 |
| `process/reports/` (one report per run or task close) | none; run outputs live under `process/runs/`, closes in the BLACKBOARD | conforms by substitution |
| `process/archive/` | present, indexed | conforms |
| `_deprecated/` (retired code and records) | `scripts/_deprecated/` (retired scripts) + `process/archive/` (retired specs and records) | conforms by substitution |
| `OPEN-ITEMS-YYYY-MM-DD.md` in planning | none | optional — see Finding 6 |
| `BACKLOG.md` | none | optional — see Finding 6 |
| Every multi-item folder has an index (rule 12) | `archive/`, `planning/`, `refactor-reviews/` have one; `reviews/`, `sprints/`, `runs/`, `runs/assays/`, `signals/` do not | gap — see Finding 2 |
| `WORKING_AGREEMENT.md` `## Documents` section (the four document kinds and their change rules) | absent | gap — see Finding 3 |
| Top-of-collection map from every old path to new | none for the 2026-08-31 moves | gap — see Finding 5 |

The code tree (`src/`, `tests/`, `scripts/`), the specs (`docs/specs/` with its archive), and the state directory are already in the shape the guide and the project's own conventions want; they are not revisited here.

---

## Findings

### Finding 1 — the BLACKBOARD is sectioned, not a single newest-last stream. This is the owner's decision.

`process/BLACKBOARD.md` is 1,366 lines in the sdd-kit-2 shape: seven sections (`## Surfaced for review`, `## Decisions`, `## Built`, `## Deferred`, `## Open questions`, `## Drift watchlist`, `## Sprint tail`) and a `## Single-writer-per-section discipline` table, with the recent `built` entries running newest-last after it. The guide's rule 10 and step 10 want one append-only stream, newest entry last, so that `tail` reaches the recent record; its reason is that a file grown by sections leaves old entries at the end of each section and strands the recent record in the middle. sdd-kit-3 made exactly this change to its own BLACKBOARD on 2026-10-29 ("one append-only stream, newest entry at the bottom... the seven sections became seven kinds of entry").

The grounds pull both ways. The guide and the kit's own 2026-10-29 conversion argue for the stream. Substrate's working agreement documents the single-writer-per-section discipline as a deliberate choice, and the `## Decisions` section is marked Architect-only; converting to one stream dissolves that structure and changes how the project's primary record is written from here on. The guide ships a content-preserving reorder (`docs/document-organization-guide-2026-10-30/tools/reorder_log.py`) whose check compares the sorted non-blank lines of the old and new files and proves no line was added or lost, so the move itself is safe to verify. The risk is not loss; it is that the restructure is to the project's load-bearing record and is the owner's to weigh.

Recommendation: convert to the single newest-last stream, because the kit's own method moved there and the sectioned board is the exact shape the guide names as the failure mode. Hold this step until the owner rules; the rest of the work does not depend on it.

### Finding 2 — five folders hold many files and no index (rule 12)

Rule 12: every folder holding more than one thing has an index. Missing:

- `process/reviews/` — 21 reviews, no `README.md`. An index gives one row per review: date, subject, what it reviewed, and where its findings were applied.
- `process/sprints/` — 272 cards, no `README.md`. The cards are numbered and their status is in their frontmatter; an index here is a thin pointer (the range, how a card is named and numbered, where the roadmap that groups them lives), not a row per card.
- `process/runs/` — four run families, no `README.md`. An index names each family (`assays/`, `benches/`, `smokes/`, `fixtures/`), what writes it, and that the content is generated.
- `process/runs/assays/` — 19 run directories, no `README.md`. An index gives one row per run: the run's name, its date, its arm count and instance count, and whether it is tracked or gitignored.
- `process/signals/` — 15 files, no `README.md`. An index names `current.json`, the version it tracks, the rationale docs, and `proposals.json`.

These are additive writes; they move nothing.

### Finding 3 — WORKING_AGREEMENT has no `## Documents` section

The guide's worked example puts in `WORKING_AGREEMENT.md` a short `## Documents` section stating the rules for the four document kinds — records (append-only: BLACKBOARD, RESEARCH, KIT_DIARY), reference files (one copy, dated, edited in place: README, CLAUDE.md, WORKING_AGREEMENT, the runbook), working documents (one round per file, never edited: everything under `process/planning/<piece>/`), and task cards (the status field changes, the rest does not) — plus the naming rule and the files a session reads. Substrate's working agreement carries the discipline in scattered form (the vocabulary overrides, the canonical-home registry, the tone canon) but not this section. The runbook written today states these rules in its Conventions and Session-startup sections; the working agreement is their canonical home. Add the section; it is six lines of rules, with the reasons left in the plan that introduces them.

### Finding 4 — refactor-reviews holds two repo-cleanup plans that are not refactor reviews and are partly superseded

`process/refactor-reviews/` is defined by its README as "refactor plans and reviews of oversized or misshapen modules." Two of its three files fit that (`PLAN-2026-08-28-hygiene-splits.md`, the module splits). The two `PLAN-2026-08-31-repo-cleanup-*.md` files are repository-hygiene plans, not module-refactor reviews, and their sprints 245–248 ran, so they are history, not live plans. They belong with the repository-organization work, and their status belongs in an index. Two moves settle it: the two cleanup plans move to this piece of work's folder (`process/planning/2026-11-20-repo-organization/superseded/`, since they are the prior rounds of this same task), and `refactor-reviews/` keeps the module-split plan under its stated purpose. The hygiene-splits plan stays where it is; it describes `src/` and `substrate-ui/` module shape, a different subject still open.

### Finding 5 — no map records the 2026-08-31 moves

The DEEP plan's own sprint 257 (a cleanup close-out naming what moved) was not written; no file exists. The guide (step 12, step 14) wants the top of the collection to carry a map from every old path to its new one, and the record to name what moved. A document in a prior cleanup still citing `docs/REVIEW-2026-08-12-*.md` or `process/assay_lite_n300_6arm_2026-08-10/` resolves today only because names did not change and `find` locates them; a written map makes the move legible without the search. A close-out for the 2026-08-31 moves and for today's planning and runbook work, with the path map, closes this.

### Finding 6 — BACKLOG and OPEN-ITEMS are absent; adopt them for the refactor's rolling-wave planning

The guide's worked example carries `process/BACKLOG.md` (ideas not yet a piece of work) and `OPEN-ITEMS-YYYY-MM-DD.md` (the list current work is drawn from) inside a piece of work. Substrate has neither; the backlog lives in the BLACKBOARD's `## Open questions` and `## Deferred` sections, and the current work is named in the planning index. The boundary refactor about to start is a fourteen-stage, rolling-wave effort whose breakdown (`RESEARCH-2026-11-09-refactor-breakdown-workflow.md`) plans the near epic in detail and leaves the rest coarse — the exact case an `OPEN-ITEMS` list and a `BACKLOG` serve. Adopting them is a judgment call, not a guide rule. Recommendation: add `OPEN-ITEMS` to the boundary-refactor piece when its first epic starts, and leave `BACKLOG` to the `## Deferred`/`## Open questions` sections unless the owner wants a separate file.

### Finding 7 — the assay corpus is already guide-conforming; its git weight is out of the guide's scope

`process/runs/assays/` holds 18,336 tracked files, 97% of the repository's tracked files. The mass is six August SWE-bench runs (`wire_check_n300_2026-08-10` 7,307 files; `lite_n300_6arm_*` 3,582 + 3,543 + 1,491 + 1,084; `shim_check_n30_pro` 968). Only three tests read anything under `process/runs/assays` (`test_language_lines_308.py`, `test_language_windows_306.py`, `test_language_measures_304.py`), and they read the small `length_drift_2026-10-12*` directories (two files each), not the mass. The August runs are historical evidence nothing reads.

Against the file-organization guide, this corpus conforms: it is grouped by run under `runs/assays/<run>/`, which is where run outputs belong (the guide's `runs/` holds "logs of end-to-end runs, one folder per run"). The guide governs where files live and how they are found, not whether generated data is git-tracked. The question of un-tracking 18,000 files to shrink a clone is a release-hygiene question the guide does not reach; the DEEP plan weighed it (§8) and chose to keep them tracked, calling the git tree's size acceptable for a research project. This research does not reopen that, and proposes no history rewrite. The only guide item the corpus owes is the `runs/assays/` index in Finding 2.

### Finding 8 — the small items, resolved

- `scripts/_deprecated/` (two retired smokes and a README) and `process/archive/` (prior spec drafts, retired records) together serve the guide's `_deprecated/` role, split by kind. Keep both (rule 8). No top-level `_deprecated/` is needed.
- `.DS_Store` at root and under `process/` is gitignored and not tracked. No action but a disk sweep if desired.
- `conftest.py`, `demo.sh` and `Dockerfile.arena` sit at root by convention (pytest root hooks, the one-line demo, the Docker image). The DEEP plan verified this; programs read them there. They stay.
- `.substrate/memory/` (20 tracked files) is the project's agent-memory index, a reference kept current. It is correctly placed and named. No action.

---

## What programs read, and therefore does not move

- The 11 assay and bench scripts write to `process/runs/{assays,benches,smokes}/` by default (the `.gitignore` comment lists them). None of the remaining work moves a run directory, so none of these paths change.
- Three language tests read `process/runs/assays/length_drift_2026-10-12*`. Those directories do not move.
- `conftest.py` at root, the `.githooks/` pre-commit gate, the sdist include-list in `pyproject.toml`, and the two import-linter contracts all name paths in `src/`, `tests/` and the root; none of the remaining work touches those trees.
- No program parses the BLACKBOARD's section structure. The runbook and a session's own reads use `tail` and a `sed` range; both survive a reorder into one stream. The guide's `reorder_log.py` changes order and form only, and its check proves every line is kept.

The remaining work moves two documents (the two cleanup plans, Finding 4), writes five indexes and one working-agreement section and one close-out (Findings 2, 3, 5), and, if the owner rules for it, reorders one record (Finding 1). It authors no code and changes no path a program reads.

---

## The approach the plan will take

Additive, low-risk work first; the one restructure last and only on the owner's ruling. Each step is one commit with a check.

1. Write the five folder indexes (Finding 2): `process/reviews/README.md`, `process/sprints/README.md`, `process/runs/README.md`, `process/runs/assays/README.md`, `process/signals/README.md`.
2. Add the `## Documents` section to `process/WORKING_AGREEMENT.md` (Finding 3).
3. Move the two repo-cleanup plans into this piece's `superseded/` and record their status (Finding 4).
4. Write the repository-organization close-out with the old-to-new path map for the 2026-08-31 moves and today's work (Finding 5).
5. Hold: the BLACKBOARD reorder (Finding 1), pending the owner's ruling. If taken, it runs with the guide's `reorder_log.py`, writes a new file, passes the line-preserving check, then replaces the old file in one commit.

`OPEN-ITEMS` (Finding 6) is deferred to the boundary refactor's first epic, where it belongs. The assay corpus (Finding 7) needs only its index, already in step 1.

## The one decision for the owner

Whether to reorder `process/BLACKBOARD.md` from the sectioned sdd-kit-2 shape into the single newest-last stream the guide and sdd-kit-3 use (Finding 1). The recommendation is to reorder, with the content-preserving script and its line-preserving check. The rest of the plan proceeds either way.

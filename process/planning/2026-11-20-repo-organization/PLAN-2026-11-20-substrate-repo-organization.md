# PLAN — bring the whole substrate repository to the file-organization guide

*2026-11-20, round 1. Executes the findings of `RESEARCH-2026-11-20-substrate-repo-organization.md`. The research established that the guide's large moves are done (root hygiene, the `docs/` purge, the run-directory grouping, the review grouping, the planning grouping, the runbook) and that six items remain. This plan is the steps for the five settled items; the sixth, the BLACKBOARD reorder, is held for the owner's ruling and specified so it can run the moment that ruling lands. Each step is one commit with a check. The plan authors five indexes, one working-agreement section and one close-out, moves two documents, and changes no code and no path a program reads.*

Written before any change, as the guide requires.

## The rules this applies

- Rule 12: every folder holding more than one thing has an index, and the moves are recorded in a map.
- Rule 10: a log puts its newest entry last (Finding 1, held).
- Rule 1 and rule 4: group by the real thing; earlier rounds sit in `superseded/`.
- Rule 8: a folder that already means something keeps its name.
- Rule 9: nothing is deleted.

## What stays, and why

The code tree, the specs, the state directory, the assay corpus, `scripts/_deprecated/`, `process/archive/`, and the root reference files stay where they are; the research found each conforming or out of the guide's scope. No program's read path changes.

---

## Step 1 — five folder indexes (Finding 2)

Write one `README.md` in each folder that holds many files and lacks an index. Each is a reference file, dated on its first line, edited in place thereafter.

- **`process/reviews/README.md`** — one row per review: date, subject, what it reviewed, where its findings were applied. 21 rows. A header line states that reviews tied to a piece of work live in that work's planning folder, and standalone reviews and audits live here.
- **`process/sprints/README.md`** — a thin pointer, not a row per card: the card-naming rule (`sprint-NNN-subject.md`, numbers never reused), the current range (through sprint 357), the frontmatter `status` values, and that the roadmap grouping a run of cards lives in the matching `process/planning/<piece>/`.
- **`process/runs/README.md`** — one row per family: `assays/`, `benches/`, `smokes/`, `fixtures/`; what writes each (the named scripts); that the content is generated run data, grouped by run, and partly gitignored.
- **`process/runs/assays/README.md`** — one row per run directory: name, date, arm count and instance count where known, and tracked-or-gitignored. 19 rows, from the directory names and the `.gitignore`.
- **`process/signals/README.md`** — names `current.json` and the version it tracks, the numbered locks `0.1`–`0.4` and their rationale docs as the audit trail, `applications-vocabulary.md` and `session-vocabulary.md`, and `proposals.json`.

Check: each file exists; `process/reviews/README.md` lists 21 reviews; `process/runs/assays/README.md` lists 19 runs; `git status` shows five additions and nothing else.

## Step 2 — the `## Documents` section in WORKING_AGREEMENT (Finding 3)

Append a `## Documents` section to `process/WORKING_AGREEMENT.md` stating the four kinds and their change rules:

- **Records** — `BLACKBOARD.md`, `RESEARCH.md`, `KIT_DIARY.md`: append-only; a correction is a new entry naming the one it corrects.
- **Reference files** — `README.md`, `CLAUDE.md`, `WORKING_AGREEMENT.md`, the runbook: one copy, dated on the first line, edited in place; a large change puts the prior version in `process/archive/` under a dated name; the runbook is the exception, replaced by a new round with the old round moved to its planning folder's `superseded/`.
- **Working documents** — everything under `process/planning/<piece>/`: one round per file, never edited; a new round names the file it supersedes and the old round moves to `superseded/`.
- **Task cards** — `process/sprints/sprint-NNN-*.md`: the `status` field changes, the rest of a closed card does not.

Plus the naming rule (`TYPE-YYYY-MM-DD-subject.md`, a later round adds `-rN`) and the files a session reads (named in the runbook's Session-startup section). Six lines of rules; the reasons stay in this plan.

Check: `grep -n '^## Documents' process/WORKING_AGREEMENT.md` returns one line; the four kinds are named under it.

## Step 3 — reclassify the two repo-cleanup plans (Finding 4)

The two `PLAN-2026-08-31-repo-cleanup-*.md` files are the prior rounds of this same repository-organization work; their sprints 245–248 ran. Move them to this piece's `superseded/`, and leave `process/refactor-reviews/` holding the module-split plan under its stated purpose.

```
git mv process/refactor-reviews/PLAN-2026-08-31-repo-cleanup-DEEP.md \
       process/planning/2026-11-20-repo-organization/superseded/
git mv process/refactor-reviews/PLAN-2026-08-31-repo-cleanup-for-public-release.md \
       process/planning/2026-11-20-repo-organization/superseded/
```

Edit `process/refactor-reviews/README.md` to drop the two moved files from its "On file" list and name where they went. The planning index row for this piece names the two plans as the superseded prior rounds.

Check: `ls process/refactor-reviews/` shows `PLAN-2026-08-28-hygiene-splits.md` and `README.md` only; the two plans are under this piece's `superseded/`; `git log --follow` walks each one's history across the move.

## Step 4 — the repository-organization close-out and path map (Finding 5)

Write `process/planning/2026-11-20-repo-organization/CLOSEOUT-2026-11-20-repo-organization.md`: what the 2026-08-31 cleanup moved (root JSONs deleted and gitignored; the 23 run directories to `process/runs/`; the 19 reviews and designs out of `docs/`), what today's work moved (the 81 planning documents; `RESEARCH.md` up to `process/`; the two cleanup plans to this piece's `superseded/`), and what today's work added (the planning index, the runbook, the five folder indexes, the working-agreement section). A table maps each old path to its new one for the moves whose old path a document might still cite. The close-out names that names were unchanged, so `find` resolves any old citation the map does not list.

Check: the file exists and its map covers the run-directory family and the `docs/`-to-`process/` moves; a spot-check of three old paths resolves by `find`.

## Step 5 — the BLACKBOARD reorder (Finding 1) — HELD for the owner's ruling

Not run until the owner rules on whether `process/BLACKBOARD.md` moves from the sectioned shape to the single newest-last stream. If ruled for:

```
python3 docs/document-organization-guide-2026-10-30/tools/reorder_log.py \
        process/BLACKBOARD.md process/BLACKBOARD.new.md
diff <(grep -v '^\s*$' process/BLACKBOARD.md | grep -vE '^(## |---$)' | sort) \
     <(grep -v '^\s*$' process/BLACKBOARD.new.md | sort) && echo "no line lost or added"
mv process/BLACKBOARD.new.md process/BLACKBOARD.md
```

Then update the working agreement's record-of-the-log line and the runbook's read commands if the section-range `sed` no longer applies, and record the reorder in the BLACKBOARD's new tail. The `## Single-writer-per-section discipline` table becomes a statement of the entry kinds, matching sdd-kit-3's 2026-10-29 form.

Check: the `diff` prints nothing but `no line lost or added`; `tail -n 1 process/BLACKBOARD.md` is the newest entry; `grep -c '^- \*\*' process/BLACKBOARD.md` is unchanged from before the reorder.

---

## Sequence and totals

Steps 1 through 4 run in order, each its own commit, independent of the ruling. Step 5 runs last and only on the ruling. The work writes seven files (five indexes, the working-agreement section, the close-out), moves two, and — if ruled — reorders one. No code changes. The gate after each step is `git status` showing only the expected change; no test run is needed, because nothing a program reads moves. Estimated: one working session for steps 1–4.

## What this plan does not do

- No history rewrite of the 18,336 tracked assay files (Finding 7); the guide does not reach git weight and the 2026-08-31 plan chose to keep them tracked.
- No `BACKLOG.md`; the `## Deferred` and `## Open questions` sections hold it (Finding 6).
- No `OPEN-ITEMS` here; it is deferred to the boundary refactor's first epic.
- No touch to `src/`, `tests/`, `scripts/`, the specs, or any path a program reads.
- No edit to a closed sprint card, a BLACKBOARD entry's text, or a KIT_DIARY entry; the reorder in step 5 changes order and form only and is proven line-preserving.

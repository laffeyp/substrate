# PLAN — repo cleanup for substrate public release

**Author:** Claude session 2026-08-31.
**Source doc:** `/Users/peterlaffey/Documents/Claude/Projects/Agent Orchestration/repo-cleanup-for-public-release.md`. Written after the sibling project ran the process. Names three moves and the sequence.
**This plan:** maps those three moves onto substrate's actual shape. Names what applies, what is already done, what does not translate, and the size of each remaining pass.

**Ground truth survey run at review open.**

- Substrate root has **1,047 JSON files totaling 4.1 MB** (`substrate-coding-flow.assay-*.json`, `substrate-coding-flow--n_drafts_*.batch-run-*.json`). A first-time visitor sees these before `README.md`, `src/`, `docs/`.
- SDD process files (BLACKBOARD, KIT_DIARY, ADDENDUMS, WORKING_AGREEMENT, RESEARCH, PHASE2, sprints/, review docs, refactor-reviews/, plan docs, assay run dirs) already live under `process/`. Substrate's `process/` is the equivalent of the source doc's `dev/`. That move is done.
- `sdd-kit-2/` lives one directory UP (project root, shared with substrate-ui). Substrate does not vendor it; the source-doc project did. Move-in-place does not apply.
- `docs/` holds 52 markdown files — the product-facing catalogue (topology walkthroughs, benchmarking design, POSTMORTEM, DESIGN, api.md, applications.md).
- Root markdown: `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`. Standard shape.
- The `dellm` skill is installed at `~/.claude/skills/dellm/SKILL.md`.

Findings organized by the source doc's three moves.

---

## Move 1 — the dellm pass

### Applies

Yes, selectively. The source doc's project cut 20-40% off scaffolded docs, 2% off fact-dense ones. Substrate's docs have a similar distribution:

- **High-value dellm targets** (prose-heavy, likely LLM-register drift): `docs/adding-a-topology.md`, `docs/api.md`, `docs/applications.md`, `docs/design/interactive-agent.md`, `docs/design/output-conformance-design.md`, `docs/tool-loop/tool-loop-agent.md`, `docs/tool-loop/tool-loop-futures.md`, older `docs/benchmarking-*.md` design rounds. Also `README.md` and `CONTRIBUTING.md` — first-impression surfaces.
- **Low-value dellm targets** (already fact-dense per prior reviews + user's plain-register discipline): most process/REVIEW-*.md and process/PLAN-*.md docs (recent authoring already in Orwell/White register per the plain-output-style hook). `process/BLACKBOARD.md` and `process/KIT_DIARY.md` — accumulated audit trails that must not be edited per rule 12; skip. Sprint cards — same reason.
- **Deferred candidates** (large docs, high value but expensive): `process/RESEARCH.md`, `docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md`. Both are historical records; low ROI for the release surface.

### Sequence for this move

The `dellm` skill takes a single draft. Run one pass per file. Reject any pass that changes a fact — the point is register, not content. Verify each output against the pre-pass file to catch factual drift.

Ordering by public-facing visibility:
1. `README.md` (first page a visitor sees).
2. `CONTRIBUTING.md`, `SECURITY.md`.
3. `docs/api.md`, `docs/applications.md`, `docs/adding-a-topology.md` — the how-to surface.
4. `docs/design/interactive-agent.md`, `docs/tool-loop-*.md` — application-level docs.
5. `docs/benchmarking-*.md` — research-adjacent.

Estimated 12-15 files, 1-2 hours per file for a careful pass, 15-30 hours total. Break into 3-5 sprints, one per doc cluster (README+CONTRIBUTING+SECURITY, api+applications+adding-a-topology, etc.).

### Not applicable

The source doc found factual errors under the register pass ("fifteen durability proofs" vs 14 actual). Substrate has the equivalent surfaces to check — grep for numeric claims in the docs against the code. Include this as an every-pass sub-step, not a separate move.

---

## Move 2 — ledger backfill

### Applies, but likely trivial

Substrate has **140 sprint files** under `process/sprints/`. BLACKBOARD `## Built` section holds 169 lines — heavy on rollup paragraphs per phase/piece (piece 0, piece A, piece B, piece C, piece G, DAILY-DRIVER ARC entries). That is the pattern the source doc calls "fine" (rollups cover ranges of sprints).

Per-sprint coverage inside those rollups is the check. A quick sample:

- Piece B's "SPRINT 214a LANDED" through "SPRINT 216 LANDED" are per-sprint entries.
- Piece C's "DAILY-DRIVER ARC pieces 0 + A + C — sprints 202-213b" is a rollup naming the range explicitly.
- Piece G's substrate-ui-side arc has its own BLACKBOARD entries on that side.
- Recent sprints (240, 241, 242, 243, 244) just landed 2026-08-28/2026-08-31 — the surfacing/built entries need writing before the fold-into-tail rollup.

### Sequence for this move

One careful diff:

```bash
cd substrate
ls process/sprints/ | grep -oE 'sprint-[0-9]{3}[a-z]?' | sort -u > /tmp/on-disk.txt
grep -oE 'sprint-[0-9]{3}[a-z]?|sprint [0-9]{3}[a-z]?|Sprint [0-9]{3}[a-z]?' process/BLACKBOARD.md | sort -u > /tmp/mentioned.txt
```

Then compare. Rollup paragraphs naming a range ("sprints 214a-216" or "202-213b") should be expanded during the diff to cover each id in the range. Any sprint on disk that appears in neither a per-entry nor a rollup range needs an entry.

The recent 240-244 arc I just closed today definitely does not have per-sprint ## Built entries yet — that alone is one BLACKBOARD update.

Estimated 30-60 minutes. Not a sprint; a fold-in-place edit on the BLACKBOARD.

### Not applicable

The source doc also checked `## Sprint tail`. Substrate's tail is well-maintained; recent entries land as compressed paragraphs and older ones fold into ## Built. No known gap.

---

## Move 3 — folder reorganization

### Two parts. First is done; second is the load-bearing win.

**Part A — SDD process artifacts under one folder.** Already done. Substrate's `process/` holds every SDD artifact: sprints/, BLACKBOARD.md, KIT_DIARY.md, ADDENDUMS.md (absent — substrate uses in-repo ADDENDUMS/kit-diary shape), WORKING_AGREEMENT.md, RESEARCH.md, PHASE2.md, ROADMAP-*.md, PLAN-*.md, REVIEW-*.md, TASK-BREAKDOWN-*.md, plus the `refactor-reviews/` subfolder. The source doc's "move everything into `dev/`" step is what substrate did months ago naming the folder `process/`. Root already reads as a Python project on the SDD-artifact axis.

**Part B — 1,047 root-level JSON artifacts move under process/ (or a dedicated home).** THIS is the load-bearing cleanup. Root layout at review open:

```
substrate/
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── SECURITY.md
├── conftest.py
├── demo.sh
├── Dockerfile.arena
├── docs/                     ← 52 md files (product-facing catalogue)
├── logs/                     ← gitignored
├── process/                  ← every SDD artifact
├── pyproject.toml
├── scripts/
├── src/                      ← the code
├── substrate-coding-flow--n_drafts_repair_ensemble__astropy_1776_astropy-12907__t2.batch-run-1786323961.json      ← the offender
├── substrate-coding-flow.assay-astropy__astropy-12907-0e91425d78.json                                              ← the offender
├── substrate-coding-flow.assay-astropy__astropy-12907-61ea0282a3.json                                              ← the offender
├── ... 1,044 more of the same ...
├── tests/
├── userinsights/
└── uv.lock
```

A visitor at `github.com/laffeyp/substrate` scrolls past 1,000+ opaque JSON filenames before reaching `tests/`. Not sloppy; corrosive to first impression.

Suggested destination: `process/assay_artifacts/` (or `process/assay_outputs/` — pick one naming). Under `process/` because these are outputs of assay runs, and assay runs are already a process concern. Do not name it `runs/` — that collides with the record-directory semantics substrate uses internally.

Blast radius check before moving:

```bash
cd substrate
grep -rIn --include='*.py' --include='*.toml' --include='*.md' \
  --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=process \
  'substrate-coding-flow' .
```

Zero hits = the code does not read these as data; safe to move. Non-zero hits = the code path that writes or reads these needs updating alongside the move.

The move itself: `git mv` each file (or `git mv` the pattern in one shell loop to preserve rename tracking).

### Sequence for this move

1. Blast-radius grep. If any code reads or writes to a path under `substrate/*.json` at repo root, catch it now and update the path.
2. `mkdir process/assay_artifacts`.
3. `git mv substrate-coding-flow*.json process/assay_artifacts/`.
4. Update `.gitignore` (if any pattern reference), scripts (if any generate to root by default), CI (if any consumes from root).
5. Verify: `ls | wc -l` at root drops from ~20 visible items to ~15; the JSON count moves to `process/assay_artifacts/`.
6. Full-suite `pytest` still green (proves the code was not depending on the root layout).

Rough estimate: 30-45 minutes including verification. One sprint card.

Optional extension: some of the 1,047 files may be gitignored-worthy debris rather than kept artifacts. Sample one to check whether it is genuinely a record of a canonical run or scratch output from an ad-hoc invocation.

### Sequence across all three moves

Source doc says: "Do the moves last." Same order here:

1. Fold-in-place BLACKBOARD updates for the 240-244 sprints (30 min).
2. Ledger-diff pass for any silent gap in ## Built coverage (30 min).
3. dellm pass on README + CONTRIBUTING + SECURITY (1-2 hours).
4. dellm pass on the docs/ how-to cluster (5-8 hours across several sessions).
5. Blast-radius grep on `substrate-coding-flow*.json` (5 min).
6. Sprint card + move (30-45 min).
7. Update `.gitignore`, verify pytest suite green (15 min).

Gates between every step: `uv run python -m pytest tests/ -q --timeout=60`, `npx tsc --noEmit` (for substrate-ui side if any move crosses), and the substrate `check:vocab-parity` equivalent.

Total: 10-15 hours across 3-5 sessions. Not one sprint; a small chain.

## What this plan does not do

- Does not move `sdd-kit-2/`. It lives at the project-root level shared with substrate-ui, not vendored inside substrate. The source-doc project had the kit vendored; substrate does not.
- Does not touch substrate-ui. That repo has its own layout, its own review corpus (`substrate-ui/process/REVIEW-*.md`), its own `web/` tree. A parallel cleanup plan for substrate-ui is a separate document.
- Does not reformat `process/BLACKBOARD.md`'s existing content. Rule 12 preserves the audit trail; new entries append, existing paragraphs stay.
- Does not rewrite closed sprint cards. Their body is history; new sprint cards from tomorrow onward can adopt any register the Architect wants.

---

## Estimated payoff

The three moves close three legibility gaps that the SDD dual contract does not measure. Every one is checkable:

- **Root layout.** `ls` at `substrate/` shows ~20 items instead of ~1,050. First-impression test passes.
- **Doc register.** A busy expert scanning the README + docs/ recognizes the register as hand-written, not measured.
- **Ledger.** Every sprint on disk has coverage in `## Built` (via per-entry or a named rollup).

None of these were the daily-driver v1 build's job. All three fit the "phase-close ritual" the source doc names at the end.

---

*PLAN-2026-08-31-repo-cleanup-for-public-release.md. Substrate's shape against the sibling project's cleanup arc: SDD-artifact folder already done under `process/`; root pollution is 1,047 assay JSON files needing one move sprint; dellm pass applies selectively to ~12-15 public-facing docs; ledger backfill is a 30-minute fold-in-place edit for the 240-244 window. Author: Claude session 2026-08-31.*

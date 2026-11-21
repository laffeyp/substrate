# PLAN — reorganize process/planning into pieces of work

*2026-11-20, round 1. Applies `docs/document-organization-guide-2026-10-30/GUIDE-2026-10-30-reorganizing-files-and-folders-r3.md` to `substrate/process/planning/`. The folder held 81 loose documents named by type and date, grouped by nothing, with one piece-of-work folder (`substrate-boundary-and-runbook-2026-11-09/`) and no index. A session that tails the folder cannot tell which research round is current, which arc a roadmap belongs to, or which work is closed. This plan groups every document by the piece of work it belongs to, puts earlier rounds in each piece's `superseded/`, moves one misfiled reference file up to `process/`, and adds the index. It changes no file's content and no file's name.*

Written before any move, as the guide requires. The move table below is the record of every change; the checks after each step prove it.

---

## The rules this applies

From the guide, the rules that bear here:

1. **Group by the real thing an item belongs to.** A proposal, its research, its design, its roadmap, its postmortem and its review are one piece of work and get one folder, named by the date the work began and its subject.
2. **No folder repeats what names already say.** The documents carry type and date in their names; the folders carry subject, not type.
4. **Old versions of one thing sit together.** Earlier rounds of a document go in a `superseded/` folder inside their piece of work.
7. **What programs read stays where they read it.** Two source comments cite planning documents by path; those paths are followed up in the step that moves their targets.
8. **Names never change.** Every move keeps the file's name, so a citation by name resolves by `find` after the move.
9. **Nothing is deleted.** Voided and abandoned work stays on disk; its status is written in the index.
11. **Status is one word from a closed list,** with the fact that set it on the same line, in the index.
12. **The folder that holds the pieces gets an index, and the moves are recorded.**

## What stays, and why

- `substrate-boundary-and-runbook-2026-11-09/` keeps its name and contents. It is already a piece-of-work folder and already means something to its readers (rule 8). Its name is subject-then-date where new folders are date-then-subject; the name does not change.
- `process/BLACKBOARD.md`, `process/WORKING_AGREEMENT.md`, `process/KIT_DIARY.md` stay. They are the project's records and reference files, not planning documents.
- `process/reviews/`, `process/refactor-reviews/`, `process/archive/`, `process/sprints/`, `process/runs/`, `process/signals/` stay. Each already holds one kind of thing.

## One misfiled reference file

`process/planning/RESEARCH.md` is not a planning document. Its own title is `# process/RESEARCH.md — Substrate research log`, and `process/BLACKBOARD.md`'s header cites it at `process/RESEARCH.md`. It is the append-only empirical research log, a reference file kept current. It moves up one level to `process/RESEARCH.md`, where its title and the citation already place it.

## Two source comments that cite moved files

`src/substrate/topologies/runs/__init__.py` lines 5–6 cite `process/planning/RESEARCH-2026-10-14-core-topologies-r9.md` and `process/planning/ROADMAP-2026-10-14-core-topologies-r3.md`. Nothing imports these; they are documentation comments, so the build does not break. The files keep their names, so `find` resolves them. The two comment paths are updated to the new paths in the same commit as the move, because a comment that names an exact path should name the right one.

## The pieces of work after the change

Sixteen folders, one per piece of work. The index at `process/planning/README.md` carries each one's status.

- `2026-06-18-phase-2-applications/` — the Phase 2 summary (`PHASE2.md`). Closed; a past phase.
- `2026-08-10-swebench-rebuild/` — the SWE-bench topology drift, its confirmatory-revert design (v3 current, v1–v2 superseded), the responder rate-limit design, and the rebuild sprint-chain roadmap (v2 current, v1 superseded).
- `2026-08-25-daily-driver/` — the daily-driver roadmap and its task breakdown.
- `2026-10-09-session-topology-structure/` — the session-topology-structure research (round4 current, earlier rounds superseded) and its roadmap.
- `2026-10-10-default-guidance/` — the default-guidance research (r7 current, r1–r6 superseded) and its roadmap.
- `2026-10-10-guidance-controls/` — the guidance-controls research (r4 current, r1–r3 superseded).
- `2026-10-10-guidance-levels/` — the guidance-levels comparison and its roadmap.
- `2026-10-10-how-substrate-presents-tools/` — the tool-presentation research (r2 current, r1 superseded).
- `2026-10-10-harness-tool-calls/` — the harness-tool-calls roadmap (r2 current, r1 superseded).
- `2026-10-10-language-measurement/` — the language-metrics research (r5 current, r1–r4 superseded) and the language-measurement roadmap (r3 current, r1–r2 superseded).
- `2026-10-11-compaction/` — the compaction research and roadmap.
- `2026-10-12-mid-session-changes/` — the controls-mid-session research (r2 current), the arrive-late postmortem (r3 current), the changes-on-time roadmap (r2 current) and the length-drift experiment (r3 current), each with its earlier rounds superseded.
- `2026-10-12-error-messages/` — the error-message research.
- `2026-10-13-core-topologies/` — the topology audit, the core-topologies research (r1–r17), its roadmaps (r3 current) and its r12 review. Closed and superseded by `substrate-boundary-and-runbook-2026-11-09/`; research rounds 11–17 are void per `process/BLACKBOARD.md` 2026-10-27; round 10 is the last authoritative design.
- `2026-10-14-create-topology/` — the create-topology research and roadmap and the without-substrate postmortem (r2 current, r1 superseded). Closed; the build was reverted.
- `substrate-boundary-and-runbook-2026-11-09/` — unchanged. The live work.

## The move table

Every loose document, old name to new path. Names are unchanged; only the folder changes.

| From `process/planning/` | To |
|---|---|
| `PHASE2.md` | `2026-06-18-phase-2-applications/` |
| `POSTMORTEM-2026-08-10-swebench-topology-drift.md` | `2026-08-10-swebench-rebuild/` |
| `DESIGN-2026-08-10-swebench-confirmatory-revert.md` | `2026-08-10-swebench-rebuild/superseded/` |
| `DESIGN-2026-08-10-swebench-confirmatory-revert-v2.md` | `2026-08-10-swebench-rebuild/superseded/` |
| `DESIGN-2026-08-10-swebench-confirmatory-revert-v3.md` | `2026-08-10-swebench-rebuild/` |
| `DESIGN-2026-08-11-responder-rate-limit-shim.md` | `2026-08-10-swebench-rebuild/` |
| `ROADMAP-2026-08-12-swebench-rebuild-sprint-chain.md` | `2026-08-10-swebench-rebuild/superseded/` |
| `ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md` | `2026-08-10-swebench-rebuild/` |
| `ROADMAP-2026-08-25-daily-driver.md` | `2026-08-25-daily-driver/` |
| `TASK-BREAKDOWN-2026-08-25-daily-driver.md` | `2026-08-25-daily-driver/` |
| `RESEARCH-2026-10-09-session-topology-structure.md` | `2026-10-09-session-topology-structure/superseded/` |
| `RESEARCH-2026-10-09-session-topology-structure-round2.md` | `2026-10-09-session-topology-structure/superseded/` |
| `RESEARCH-2026-10-09-session-topology-structure-round3.md` | `2026-10-09-session-topology-structure/superseded/` |
| `RESEARCH-2026-10-09-session-topology-structure-round4.md` | `2026-10-09-session-topology-structure/` |
| `ROADMAP-2026-10-09-session-topology-structure.md` | `2026-10-09-session-topology-structure/` |
| `RESEARCH-2026-10-10-substrate-default-guidance.md` | `2026-10-10-default-guidance/superseded/` |
| `RESEARCH-2026-10-10-substrate-default-guidance-r2.md` … `-r6.md` | `2026-10-10-default-guidance/superseded/` |
| `RESEARCH-2026-10-10-substrate-default-guidance-r7.md` | `2026-10-10-default-guidance/` |
| `ROADMAP-2026-10-10-default-guidance.md` | `2026-10-10-default-guidance/` |
| `RESEARCH-2026-10-10-guidance-controls.md`, `-r2`, `-r3` | `2026-10-10-guidance-controls/superseded/` |
| `RESEARCH-2026-10-10-guidance-controls-r4.md` | `2026-10-10-guidance-controls/` |
| `GUIDANCE-LEVELS-COMPARED-2026-10-10.md` | `2026-10-10-guidance-levels/` |
| `ROADMAP-2026-10-10-guidance-levels.md` | `2026-10-10-guidance-levels/` |
| `RESEARCH-2026-10-10-how-substrate-presents-tools.md` | `2026-10-10-how-substrate-presents-tools/superseded/` |
| `RESEARCH-2026-10-10-how-substrate-presents-tools-r2.md` | `2026-10-10-how-substrate-presents-tools/` |
| `ROADMAP-2026-10-10-harness-tool-calls.md` | `2026-10-10-harness-tool-calls/superseded/` |
| `ROADMAP-2026-10-10-harness-tool-calls-r2.md` | `2026-10-10-harness-tool-calls/` |
| `RESEARCH-2026-10-10-language-metrics.md`, `-r2`, `-r3`, `-r4` | `2026-10-10-language-measurement/superseded/` |
| `RESEARCH-2026-10-13-language-metrics-r5.md` | `2026-10-10-language-measurement/` |
| `ROADMAP-2026-10-12-language-measurement.md`, `-r2` | `2026-10-10-language-measurement/superseded/` |
| `ROADMAP-2026-10-12-language-measurement-r3.md` | `2026-10-10-language-measurement/` |
| `RESEARCH-2026-10-11-compaction.md` | `2026-10-11-compaction/` |
| `ROADMAP-2026-10-11-compaction.md` | `2026-10-11-compaction/` |
| `RESEARCH-2026-10-12-controls-mid-session.md` | `2026-10-12-mid-session-changes/superseded/` |
| `RESEARCH-2026-10-12-controls-mid-session-r2.md` | `2026-10-12-mid-session-changes/` |
| `POSTMORTEM-2026-10-12-mid-session-changes-arrive-late.md`, `-r2` | `2026-10-12-mid-session-changes/superseded/` |
| `POSTMORTEM-2026-10-12-mid-session-changes-arrive-late-r3.md` | `2026-10-12-mid-session-changes/` |
| `ROADMAP-2026-10-12-changes-on-time.md` | `2026-10-12-mid-session-changes/superseded/` |
| `ROADMAP-2026-10-12-changes-on-time-r2.md` | `2026-10-12-mid-session-changes/` |
| `RESEARCH-2026-10-12-length-drift.md`, `-r2` | `2026-10-12-mid-session-changes/superseded/` |
| `RESEARCH-2026-10-12-length-drift-r3.md` | `2026-10-12-mid-session-changes/` |
| `RESEARCH-2026-10-12-error-messages.md` | `2026-10-12-error-messages/` |
| `AUDIT-2026-10-11-topologies.md` | `2026-10-13-core-topologies/` |
| `RESEARCH-2026-10-13-core-topologies.md` … `-r8.md` | `2026-10-13-core-topologies/superseded/` |
| `RESEARCH-2026-10-14-core-topologies-r9.md` | `2026-10-13-core-topologies/superseded/` |
| `RESEARCH-2026-10-25-core-topologies-r10.md` | `2026-10-13-core-topologies/superseded/` |
| `RESEARCH-2026-10-27-core-topologies-r11.md` … `-r16.md` | `2026-10-13-core-topologies/superseded/` |
| `RESEARCH-2026-10-27-core-topologies-r17.md` | `2026-10-13-core-topologies/` |
| `ROADMAP-2026-10-13-core-topologies.md`, `-r2` | `2026-10-13-core-topologies/superseded/` |
| `ROADMAP-2026-10-14-core-topologies-r3.md` | `2026-10-13-core-topologies/` |
| `REVIEW-2026-10-27-core-topologies-r12.md` | `2026-10-13-core-topologies/` |
| `RESEARCH-2026-10-14-create-topology.md` | `2026-10-14-create-topology/` |
| `ROADMAP-2026-10-14-create-topology.md` | `2026-10-14-create-topology/` |
| `POSTMORTEM-2026-10-14-create-topology-without-substrate.md` | `2026-10-14-create-topology/superseded/` |
| `POSTMORTEM-2026-10-14-create-topology-without-substrate-r2.md` | `2026-10-14-create-topology/` |
| `RESEARCH.md` | `process/RESEARCH.md` (up out of planning) |

The full 81-row machine form is in `move-table.txt` beside this plan.

## The steps, each with its check

1. **Manifest before.** `shasum -a 256` over every file in `process/planning/`, sorted. Saved as `manifest-before.txt`. Check: 99 files listed.
2. **Create the sixteen folders and their `superseded/` subfolders.** Check: `find … -type d` lists them.
3. **`git mv` every loose document per the table.** Names unchanged. Check: `ls process/planning/*.md` lists only files that do not exist (none); every row's target exists.
4. **`git mv process/planning/RESEARCH.md process/RESEARCH.md`.** Check: `process/RESEARCH.md` exists; `process/planning/RESEARCH.md` does not.
5. **Update the two comment paths** in `src/substrate/topologies/runs/__init__.py`. Check: the comment names the new path; `uv run ruff check src/substrate/topologies/runs/__init__.py` returns 0.
6. **Write `process/planning/README.md`,** one row per piece of work with its status and the fact that set it.
7. **Record the move** in `process/BLACKBOARD.md`: one entry naming what moved, where the map is, and the commit.
8. **Manifest after,** compared by content without paths. Check: `diff` of the sorted checksum columns is empty but for the files edited on purpose (the index, this plan, the two comment lines, the BLACKBOARD entry), each with its own check.

## What this does not touch

`process/BLACKBOARD.md` is a sectioned record in the sdd-kit-2 shape, not the single newest-last stream the guide's step 10 describes. Reordering a 709 KB log into one stream is a separate change with its own risk; it is not in this plan, and the runbook's session-start commands (`tail`, the decision grep) already read it as it stands. The reorganization here is the planning folder only.

# process/planning — index

*Current as of 2026-11-20. One folder per piece of work, named by the date the work began and its subject. Each folder holds its documents, with earlier rounds of each in its `superseded/`. The current round of anything is the one at the folder top; this index carries the status. A new piece of work gets a folder and a row on the day its first document is written; its status changes when its closing document is written.*

*History is opened only when a current document points to it. The live work is `substrate-boundary-and-runbook-2026-11-09/`.*

The folder was reorganized on 2026-11-20 from 81 loose documents into the pieces below; the plan, the full old-path-to-new-path map and the before-manifest are in `2026-11-20-planning-reorganization/`. Names were not changed, so a citation that names a moved file still resolves with `find process/planning -name <file>`.

| Folder | Piece of work | Status | The fact that set it |
|---|---|---|---|
| `substrate-boundary-and-runbook-2026-11-09/` | The substrate/substrate-ui boundary refactor and the substrate runbook: the design-and-boundary paper (r3), the fourteen-stage sequence, the epic/wave/card breakdown, the two round-2 reviews, and the topology-value evidence | active | The live work; its sequence orders fourteen stages not yet run |
| `2026-11-20-repo-organization/` | Applying the file-organization guide to the whole repository: the research, the plan, the close-out path map, and the 2026-08-31 cleanup plans as its superseded prior rounds | closed | All steps done 2026-11-20: the BLACKBOARD stream, five folder indexes, the working-agreement Documents section, the two cleanup plans moved, the close-out map; BACKLOG/OPEN-ITEMS deferred by design |
| `2026-11-20-planning-reorganization/` | The planning-folder slice of the repository organization: the plan, the move map, the before-manifest | closed | The moves landed and the after-manifest matched by content, 2026-11-20 |
| `2026-10-14-create-topology/` | The create-topology tool: research, roadmap, and the without-substrate postmortem (r2 current) | reverted | The postmortem records U188 and the build reverted at `3b2ed96`, zeroed out |
| `2026-10-13-core-topologies/` | The core topologies the session can reach: the 2026-10-11 audit, research r1–r17, roadmaps (r3 current), the r12 review | superseded | Superseded by the boundary refactor; research r11–r17 are void per `process/BLACKBOARD.md` 2026-10-27; round 10 is the last authoritative design |
| `2026-10-12-error-messages/` | What an error names: the standard, applied to resumed-session failures | closed | A one-off research note; no open roadmap |
| `2026-10-12-mid-session-changes/` | A mid-session guidance, length or tone change reaching the model on its turn: the controls research (r2), the arrive-late postmortem (r3), the changes-on-time roadmap (r2), the length-drift experiment (r3) | closed | The fix shipped on kernel `6d2d5114` as K299/K300, checked by U167's gate (length-drift r3) |
| `2026-10-11-compaction/` | How a session's history is compacted: the research and the roadmap | closed | Compaction shipped; the recent record runs its § S compaction (`process/BLACKBOARD.md` tail) |
| `2026-10-10-language-measurement/` | Measuring language without judging it: the metrics research (r5), the measurement roadmap (r3) | closed | The instruments were built and tested, sprints 302–306, `src/substrate/language/`, library 0.2.0 (metrics r5) |
| `2026-10-10-harness-tool-calls/` | A harness driver's tool calls on the record (roadmap r2) | closed | `HarnessToolCall` and `HarnessToolResult` are on the record (`process/BLACKBOARD.md` tail) |
| `2026-10-10-how-substrate-presents-tools/` | How Substrate presents tools to each driver (r2) | closed | Research that fed the default-guidance work; no open roadmap |
| `2026-10-10-guidance-levels/` | The three guidance levels compared, and their roadmap | closed | The levels shipped in `src/substrate/topologies/session/bundles/` (the comparison's own subtitle) |
| `2026-10-10-guidance-controls/` | What the section under the model can set (r4) | closed | Research that fed the guidance levels and the mid-session controls; no open roadmap |
| `2026-10-10-default-guidance/` | Substrate's default guidance for every driver (r7), and its roadmap | closed | The `standard` bundle and the levels shipped under `bundles/` |
| `2026-10-09-session-topology-structure/` | The session topology made plain: its structure and a naming plan (round4), and the roadmap | closed | The decisions of 2026-10-09 landed; the turn's end is `Returned`, `FinalAnswer` was dropped |
| `2026-08-25-daily-driver/` | The substrate daily driver: roadmap and task breakdown | closed-partial | Pieces 0, A and C closed (sprints 202–213b, `process/BLACKBOARD.md` 2026-08-25/26); the later pieces ran as the session topology |
| `2026-08-10-swebench-rebuild/` | The SWE-bench rebuild: the topology-drift postmortem, the confirmatory-revert design (v3), the rate-limit design, the rebuild roadmap (v2) | superseded | The August rebuild; later SWE-bench solver work carries the current plan |
| `2026-06-18-phase-2-applications/` | The Phase 2 (applications and visibility) summary | closed | A past phase; its detail is in `process/sprints/` |

*Reviews that belong to a piece of work sit in that work's folder. Standalone reviews and audits are in `process/reviews/`. The decision log is `process/BLACKBOARD.md`; the empirical research log is `process/RESEARCH.md`.*

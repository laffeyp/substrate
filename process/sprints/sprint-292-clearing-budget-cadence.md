# Sprint 292 — Clearing, budget, cadence

```yaml
---
id: 292
status: closed
closed_at: 2026-10-11
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-11-compaction.md
asked: 2026-10-11 (Architect)
---
```

## scope

- In `transcript.py` and the model step: clear tool-output bodies beyond the newest K behind a placeholder; keep user messages and final replies; drop whole turns only when those exceed the budget; apply the rule inside the current turn; scale the estimate by the driver's recorded usage ratio; set CLI windows per model; clear in batches; record an event only when the cut changes. First confirm whether a session's model can read its own record by seq through `inspect_record`; the placeholder names a read-back path only if one works.

## checks

- Unit tests for the plan; replaying a recorded session gives byte-identical prompts; replanning `s_b8dab6b0cfd443cdba9bc8b3` keeps all four user messages and replies inside the budget.

## result

- **Built.**
  - `transcript.py`: `result_lines` gives a result's whole line and its placeholder (§ S.3); `output_savings` prices clearing each result; `plan_history` clears old outputs first, moving the boundary only when the history passes the budget and then until it fits within half, and drops whole turns only once nothing more can clear; `measured_scale` (§ S.5). `_render_turns` and `compose_model_prompt` take `cleared_through`.
  - `views.py`: `TurnHistory` also keeps each turn's savings, the record's last cut, and the driver's measured scale (it now reads `PromptComposed` too). Its value is a `HistoryState`. No new view, so the bundled records' view list is unchanged.
  - `__init__.py`: the trigger plans the cut; the ticket carries the boundary, the estimates, the scale and whether the cut changed; the model step renders with the boundary and records `TranscriptCompacted` only on a change, with `tool_output_cleared` or `rolling_window`. Harness drivers use a scale of 1.0.
- **Rule amended (§ S.7).** Replanning the codex session showed that keeping the newest 3 results of the whole history whole let one finished turn's three file reads (about 57,000 estimated tokens) push out every earlier turn. Only the current turn's newest 3 stay whole now.
- **The codex session, replanned** (`s_b8dab6b0cfd443cdba9bc8b3`, each turn's prompt from its user message): every prompt keeps every turn. Turns 1–4 start at 15,348, 30,844, 45,924 and 46,147 estimated tokens; before, turns 2–4 started with turns 0 and 1 dropped. The boundary held at seq 113 across turns 2–4.
- **Tests.** `test_compaction_clearing_292.py`, 8 of 8: under budget nothing changes; clearing to half the budget; the cut holds still; the current turn's newest 3 stay whole; a finished turn's outputs all clear; turns drop only after clearing is exhausted; the codex shape keeps every turn; an 8-turn scripted session keeps every request, shows placeholders, records one event per change with a boundary that only moves forward, and its prompts rebuild from their tickets. Session-area tests: 365 passed, 7 skipped. `mypy --strict`: clean. The `daily` and `session` bundled records were regenerated for the new schema; the other 16 were not stale and were left alone.
- **Not done: CLI windows per model.** Every CLI driver still gets 100,000 tokens. Setting each model's window needs its verified size from its maker's documentation; none was checked in this sprint. Halted for the Architect: which source to take each CLI model's window from.
- **The placeholder names no read-back path.** `inspect_record` takes a record path, and the session's model is not given its own; a read-back hint would point at nothing. Giving the model its record path is a separate change.

# Sprint 351 — The continued conversation enters as history

```yaml
---
id: 351
status: pending
phase: continuing a session (substrate-ui roadmap 2026-11-12-continue-a-session r3, E9)
pass_kind: functional
depends_on: [350]
plan: ../substrate-ui/process/planning/2026-11-12-continue-a-session/ROADMAP-2026-11-14-continue-a-session-r3.md
---
```

## scope

The continued conversation entered as opening prompt text (`continued_session`, § AD), which every prompt carries and compaction never touches. It enters instead as the session's earliest turns in its record, the events the history renders, written at session open before the first live message; compaction then clears their tool output and drops their oldest turns like any other. Writing them starts no model call. One verifiable property: a continued session's record holds the imported turns as history events, and once new turns pass the budget, a `TranscriptCompacted` drops imported turns first.

## context_files

- `src/substrate/topologies/session/__init__.py` (session open, the triggers on `UserMessage`), `session_prompt_producer.py` (§ AD's source)
- `src/substrate/topologies/session/transcript.py` (`_group_by_turn`, `TURN_EVENT_KINDS`, `plan_history`), `views.py` (the history view)
- `process/signals/session-vocabulary.md` (§ AD, § S)

## signal contract

### Emits

- The imported turns as history events, marked so no trigger starts the model on them; § AD amended (v0.21).

### Invariants

- A session that continues nothing writes what it wrote before.

## artifact contract

Set when the card is written in full, after sprint 350.

## observation contract

A continued session with more imported history than the window holds: its first prompt carries the newest imported turns that fit, and the record holds a `TranscriptCompacted` dropping the oldest.

## done criteria

The continued conversation ages out of the window as the session goes on.

## self-review checklist

- [ ] Written in full after sprint 350 closes.

# Sprint 351 — The continued conversation enters as history

```yaml
---
id: 351
status: active
phase: continuing a session (substrate-ui roadmap 2026-11-12-continue-a-session r3, E9)
pass_kind: functional
depends_on: [350]
plan: ../substrate-ui/process/planning/2026-11-12-continue-a-session/ROADMAP-2026-11-14-continue-a-session-r3.md
---
```

## scope

The continued conversation entered as opening prompt text (`continued_session`, § AD), which every prompt carries and compaction never touches (1,422,933 characters on every turn of the 2026-11-14 session). It enters instead as the session's earliest turns, in its record. At session open the `session_prompt` producer, which the first live message already waits for (`TRIGGER_ID_FIRST_MESSAGE_ON_SESSION_PROMPT`), writes the given turns as the events the history renders: `UserMessage`, `ModelReply`, `HarnessToolCall`, `HarnessToolResult`. Each imported `UserMessage` carries `slash_source` `continued` (session vocabulary v0.21, § AD amended). Every place that acts on a `UserMessage` passes over a continued one:

- the five triggers on `UserMessage`: the model (`TRIGGER_ID_MODEL_ON_USER_MESSAGE`), the change run, the skill, end-on-exit, the turn cap;
- the `user_turns` view (`api.KindCount(USER_MESSAGE)`), which the first message's trigger needs at 0 and `_turn_index` counts;
- `_next_turn_index_from_record` (the registry's turn numbering).

The history (`TURN_EVENT_KINDS`, `_group_by_turn`, `_render_turns`, `TurnHistory`, `plan_history`) reads them as turns, so compaction clears their tool output and drops their oldest turns like any others. The fragment form of § AD is retired. One verifiable property: a continued session's first prompt holds the newest imported turns that fit; with more than fits, its record holds a `TranscriptCompacted` dropping the oldest; no model call runs on an imported message.

## context_files

- `src/substrate/topologies/session/__init__.py` (the `user_turns` view line 1304, `_turn_index` line 1071, the `UserMessage` triggers, the opening order at lines 1340–1402)
- `src/substrate/topologies/session/session_prompt_producer.py` (`continued_session_fragments`, the producer's schemas)
- `src/substrate/topologies/session/transcript.py`, `views.py`, `vocabulary.py` (`DRIVER_SLASH_SOURCE` and its kin, line 570)
- `src/substrate/topologies/session_registry.py` (`_next_turn_index_from_record`)
- `process/signals/session-vocabulary.md` (§ AD, § S)

## signal contract

### Emits

- At session open, the imported turns as `UserMessage` (`slash_source` `continued`), `ModelReply`, `HarnessToolCall`, `HarnessToolResult`; no `PromptFragment` of source `continued_session`.

### Invariants

- A session that continues nothing writes what it wrote before.
- No model call, skill, change run or session end starts on an imported message; the turn cap counts live messages only.
- The first live message is turn 0 of the live session's count; imported turns carry their own indices from the source.

## artifact contract

### Files modified

- `session/__init__.py`, `session_prompt_producer.py`, `vocabulary.py`, `session_registry.py`, `session-vocabulary.md` (v0.21)

### Files created

- `tests/test_continued_as_history_351.py`

### Command exit codes

- The new test, sprints 346–347 and 350's tests (amended where they pinned the fragment), and the session topology's tests return 0.

## observation contract

Through the registry: a session continued from imported turns larger than its window, on a stand-in harness. Its record opens with the imported events, then the live message; no `ModelReply` between them; the first `PromptComposed` holds the newest imported turns and a `TranscriptCompacted` drops the oldest; `user_turns` reads 1 after the first live turn. A session that continues nothing: its record is byte-identical in kinds to before.

## done criteria

The continued conversation ages out as the session goes on.

## notes

Five files for one concept: the marker and everything that must honour it. Primitive-plus-consumer: the server's `continue_from` (substrate-ui sprint 494) is the consumer, unchanged.

## self-review checklist

- [x] Written in full after sprint 350.
- [x] Every reader of `UserMessage` named.
- [x] Observation contract present.

# Sprint 351 — The continued conversation enters as history

```yaml
---
id: 351
status: closed
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

## close

`session_prompt_producer.py`: `continued_session_events` turns the given turns into `UserMessage` (`slash_source` `continued`, `turn_index` -N..-1), `ModelReply` (usage `estimated`), `HarnessToolCall` and `HarnessToolResult`; `session_prompt` yields them after the session-open fragments, at open only; the fragment builder and its precedence are gone. `session/__init__.py`: the producer declares the four kinds; `_continued` guards model-on-user-message, the change run, end-on-exit and the turn cap; `user_turns` is `LiveUserTurns`. `views.py`: `LiveUserTurns` counts live messages. `vocabulary.py`: `CONTINUED_SLASH_SOURCE`. Session vocabulary v0.21, § AF (amends § AD; §§ A–AE byte-preserved).

Two of the card's named readers needed no change, by the numbering: `_next_turn_index_from_record` takes the highest index plus one, which -N..-1 leave at 0; skill-on-user-message needs a `skill:` source. Return-on-reply and language-on-reply fire on `ModelReply`, which has no marker; they need an open turn (`returned_turns < user_turns`), and `user_turns` is 0 until the first live message, which waits for `session_prompt`. `session_registry.py` is therefore unmodified and `views.py` is modified in its place.

- `tests/test_continued_as_history_351.py`: 4 passed. The events and their indices; through the registry, 30 imported turns in a 3,000-token window: imported events before the live message, one `PromptComposed` and one `Returned`, both after it, the newest imported turn in the prompt and the oldest dropped by `TranscriptCompacted`, the next index 1 in the live registry and in a restarted one; a 2-turn continuation whole in the first prompt and not imported again on the second turn; a session continuing nothing writes turn 0 alone.
- Amended: `test_continued_session_source.py` (346: the source is read, never written; open yields fragments, then the conversation; a change run imports nothing), `test_session_continued_347.py` (the record holds the imported message and reply). substrate-ui `tests/test_continue_from_494.py`: the server's deterministic driver has a fixed 4,096-token window, so its first turn drops the imported turns, oldest first, keeping the live message; 8 passed.
- Committed records regenerated for `session` and `daily`, whose fingerprint changed at `RunStarted`; the other 16 differed only in `run_id` and were restored. `test_bundled_topologies.py`, `test_session_topology_bundled.py`: 44 passed.
- Wider run (1,732 tests): 1,714 passed, 14 skipped, 4 failed: the three stale records above, and `test_realmodel_demos.py::test_ensemble_real_disagreement_and_cancel`, which imports no session code and needs three temperature-0.9 draws from `llama3.2:1b` to differ.
- Mutants: `LiveUserTurns` counting imported messages, and the model trigger without `_continued`: each fails 3 tests.
- ruff clean; `mypy --strict` on the four source files clean.

Rubber Duck Pass: at session open, after the `PromptFragment`s, the record holds `UserMessage` (`slash_source` `continued`, negative `turn_index`), `HarnessToolCall`, `HarnessToolResult` and `ModelReply` (usage `estimated`) for each imported turn, and no `continued_session` fragment. Then the live `UserMessage` at turn 0, `TranscriptCompacted` when the window is exceeded, `PromptComposed`, the live `ModelReply`, `Returned` at turn 0. Every declared emit fired; the invariants hold in the tests above. Observation: payload anomaly, an imported `HarnessToolResult` carries no `turn_index`; the live ones carry none either, so the history groups it by order, as it does live results. resolved-here, no change.

# Sprint 353 — A conversation brought in before v0.21 becomes the session's history

```yaml
---
id: 353
status: pending
phase: continuing a session (substrate-ui roadmap 2026-11-12-continue-a-session r4, E11)
pass_kind: functional
depends_on: [352]
plan: ../substrate-ui/process/planning/2026-11-12-continue-a-session/ROADMAP-2026-11-14-continue-a-session-r4.md
---
```

## scope

A session continued under v0.19–v0.20 holds the conversation it continues as one `continued_session` fragment, which every prompt carries and compaction never drops: 1,422,933 characters in `s_52bd6e73d1224d5cb6d04830`. Its turns are in the session's `continued_session.json`, which the topology already receives (`continued_session`). In such a record the history window leaves the fragment out of the head and plans the turns as the session's oldest history: the same events § AF writes, numbered by the window from -M to -1 in seq as their turns are from -N to -1 in `turn_index`. `plan_history` then treats them as it treats any turns (§ S): their tool output clears first, oldest first, then their whole turns drop, oldest first. The model step renders the kept ones before the live turns. One verifiable property: the session's next prompt counts under the window, holds the newest imported turns that fit and all its own, and its `TranscriptCompacted` names the cut in negative seqs.

## context_files

- `src/substrate/topologies/session/__init__.py` (`_prompt_input`, the model step's history read)
- `src/substrate/topologies/session/transcript.py` (`plan_history`, `_render_turns`, `output_savings`)
- `src/substrate/topologies/session/session_prompt_producer.py` (`continued_session_events`)
- `process/signals/session-vocabulary.md` (§ S, § AD, § AF, § AG)

## signal contract

### Emits

- `TranscriptCompacted` whose `cleared_through_seq`, `dropped_seq_range` or `kept_seq_start` is negative when the cut falls in the imported turns.
- `PromptComposed.fragment_seqs` without the `continued_session` fragment's seq.

### Invariants

- A record with no `continued_session` fragment plans as before.
- The fragment's record is unchanged: the window reads it, never rewrites it.
- The plan is the same live and on replay: every input is the record and the turns file the manifest names.

## artifact contract

### Files modified

- `session/__init__.py`, `session-vocabulary.md` (v0.23, § AH)

### Files created

- `tests/test_old_continuation_as_history_353.py`

### Command exit codes

- The new test, the 346–352 tests and the session, history and compaction tests return 0; ruff and `mypy --strict` clean.

## observation contract

A copy of `s_52bd6e73d1224d5cb6d04830`'s record, resumed with this code on a stand-in Claude Code: the prompt counts under the window, holds all 26 of its own turns, the oldest imported turns dropped, and the reply arrives.

## done criteria

The conversation brought in on 2026-11-12 ages out of the old session's prompts like any history.

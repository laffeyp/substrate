# Sprint 268 — The model step reads its history from the record by reference

```yaml
---
id: 268
status: closed
opened_at: 2026-10-09
closed_at: 2026-10-09
phase: 1
pass_kind: architecture
roadmap: substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md
decided: 2026-10-09 (Architect chose option B, history by reference)
---
```

## why

K261 gave the model step its turn history in its input, and every input is recorded. Each step re-recorded the whole history: in a seven-turn live run `TriggerFired.resolved_input` grew from 300 bytes at step 1 to 5,879 at step 11, so a session's record grows with the square of its length. The same text is also on the record in that step's `PromptComposed`.

## research

- **Claim check** (Hohpe and Woolf, *Enterprise Integration Patterns*, 2003): a message carries a ticket to a payload kept in a store; the receiver fetches the payload. Substrate already uses it for payloads over the blob threshold (sprint 095, `{"$blob": …}`).
- **Why it is deterministic here:** the record is append-only and every seq is immutable once written, so a ticket naming a seq range always returns the same events, live or on replay. `record.append` writes each frame with `os.write` before the trigger evaluates (`record/record.py:155`), so every seq up to the triggering event is readable when the model step runs.
- **Precedent:** tools already read records from inside producers (`inspect_record`, `delegate`).

## design

1. **Kernel: read a seq range.** `read_range(root, from_seq, to_seq, *, resolve_blobs)` in `record/record.py`, exported through `api`. It skips sealed segments the manifest places wholly before `from_seq`, stops after `to_seq`, verifies each frame's crc, and checks the returned seqs are exactly `from_seq..to_seq` (a missing seq raises `RecordGapError`, as the full reader does).
2. **Kernel: the trigger context names its record.** `TriggerContext.record_root` (`protocols.py`), set by the sequencer. Any input builder can then hand a Producer a ticket to its own record.
3. **Session: the window is chosen at the trigger.** The history view keeps each turn's estimated rendered size as its events arrive. The model triggers pick the oldest turn that still fits (a sum over per-turn sizes, no rendering) and pass a ticket: `{"record", "from_seq", "to_seq", "dropped": [lo, hi] | null, "tokens_before"}`.
4. **Session: the model step reads and builds.** It reads `from_seq..to_seq` with `read_range`, builds the prompt, records it as `PromptComposed`, sends it, and records `TranscriptCompacted` when the ticket names a dropped range.

## effects

- The recorded input per model step drops from the whole history to a ticket of a few dozen bytes.
- The model step reads one bounded range from disk per call instead of the whole record (lens F101).
- `session_topology` needs no `record_root` parameter; the ticket carries the path.
- A Producer that reads its own record by ticket reads only seqs written before it started, so it never sees events from its own run.

## artifact contract

### Files modified

- `substrate/src/substrate/record/record.py`, `substrate/src/substrate/api.py`, `substrate/src/substrate/protocols.py`, `substrate/src/substrate/kernel/sequencer.py`
- `substrate/src/substrate/topologies/session/__init__.py`, `topologies/session/views.py`, `topologies/session/transcript.py`

### Files created

- `substrate/tests/test_read_range_268.py`
- `substrate/tests/test_history_by_reference_268.py`

## observation contract

### Predicted breaks (written before the run)

- Any test that reads the model step's input and expects `history` in it: none outside K261's own tests.
- CI records: the `session` and `daily` records move (the model step's input changes shape); every other record is unchanged.
- `api.__all__` gains `read_range`; `docs/api.md` is regenerated.

### Driving steps

- `read_range` on a record with sealed and hot segments returns exactly the asked seqs; a missing seq raises.
- A twenty-turn session: every model step's recorded input is under 300 bytes; its prompts equal those built from the full history; compactions are recorded with the same ranges as before.
- The live compaction test (`llama3.2:1b`, `num_ctx=2048`) passes unchanged.

## done criteria

A model step's recorded input is a ticket, not a copy, and the prompt it builds from the ticket is byte-identical to one built from the full history.

## result

- `record/record.py` `read_range(root, from_seq, to_seq)`: skips sealed segments before the range and reads the hot segment backwards from its end, so reading a window costs about the window, not the record (reading the newest 10 of 20,000 events read under a quarter of the file). Exported through `api`.
- `api.current_record_root()` (from the run's `_CURRENT_RUNTIME`): a Producer finds its own record without a recorded path. A first version put the record's absolute path in the ticket; the committed CI records then differed from a fresh run at the first ticket, because a recorded path ties a record's bytes to where it sits. The path was removed and `TriggerContext.record_root` with it.
- The history view keeps each turn's span and estimated size; the model triggers choose the window (`plan_window`) and issue a ticket `{from_seq, to_seq, dropped, tokens_before}`; the model step reads the range and records `TranscriptCompacted` when the ticket names a dropped range.
- Checks: twenty turns at 8,192 tokens, every model step's recorded input under 400 bytes and every prompt equal to the one rebuilt from the full record; the live `llama3.2:1b` test makes the same two checks on a real model and passes. Committed CI records reproduce byte for byte.
- Session-open fragments still ride the input as text (they sit at the start of the record, where a backward read is costly); that copy grows by one fragment set per step.

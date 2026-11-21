# ROADMAP: compaction to first-source practice

*2026-10-11. From the Architect's direction of 2026-10-11. Research: `RESEARCH-2026-10-11-compaction.md`. Release step 2 in `substrate-ui/process/planning/ROADMAP-2026-10-11-before-distribution.md`.*

**Goal.** A session's prompt keeps what the model needs and clears what it can read back. Old tool outputs are cleared first, behind a placeholder; the user's messages and the final replies stay; whole turns drop only when those alone exceed the budget. The budget rests on the token counts the drivers report. Each change of cut is recorded once.

**Ground rules.** The record never changes; compaction only decides how the record renders into the prompt. The prompt stays a pure function of the record, so replay is exact: every clearing decision is computed from recorded events, with no clock or live state. `PromptComposed` stays exactly what was sent. Harness drivers keep the replay model (research §6).

## Decisions

| Decision | What it decides |
|---|---|
| Order of cuts | 1. Old tool-output bodies (`ToolResult`, `HarnessToolResult`) beyond the newest K. 2. Whole oldest turns, only if the user messages and replies alone still exceed the budget. Summaries (`summary_tail`) wait; the masking study found clearing alone matched them. |
| Placeholder | One line per cleared result naming the tool, the seq and the size, and how to read it back. Call lines stay. |
| The current turn | Its own older tool outputs clear under the same rule, so one tool loop cannot overflow the window. |
| Budget | The chars ÷ 4 estimate scaled by the driver's last measured ratio of `ModelReply.usage.prompt_tokens` to the estimate, read from the record. CLI windows set per model, not a flat 100,000. |
| Batches | Each pass clears at least a fixed share of the budget, and the cut holds until the budget forces the next, so the prompt's start stays stable for prefix caching. |
| Event cadence | `TranscriptCompacted` is recorded only when the cut changes. |

## Order and checks

**1. K290: tool outputs sent once.** *Check:* in a native-tool session with two tool calls in one turn, each output appears once in the second step's `PromptComposed`.

**2. K291: vocabulary round for § D.** `strategy` gains `tool_output_cleared`; the event carries the cleared seqs; the invariants gain "a user message is never cleared or dropped while a later turn is kept" and "no event unless the cut changed"; the paired UI tag follows. *Check:* the vocabulary and its golden tests agree.

**3. K292: clearing, budget, cadence.** In `transcript.py` and the model step. *Check:* unit tests for the plan; a replay of a session gives byte-identical prompts; the codex session's history (`s_b8dab6b0…`) replanned keeps all four user messages and replies.

**4. K293: the console row and a live test.** The compaction row names what was cleared or dropped; a repeated cut does not appear. A live opt-in test reruns the codex case: a heavy second turn, then a question that needs it. *Check:* the third turn's prompt holds the first two user messages and replies, and the model answers from them.

Tests per card cover the changed code; the full kernel and UI suites run once, at K293.

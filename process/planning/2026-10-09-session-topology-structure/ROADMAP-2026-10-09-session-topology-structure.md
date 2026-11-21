# ROADMAP: the session topology, made plain

*2026-10-09.*

**Input.** `RESEARCH-2026-10-09-session-topology-structure-round4.md` (findings F1–F9, proposals P1–P6, decisions of 2026-10-09).

**Goal.** Each fact about a turn is on the record once, under a name that says what it is. The record holds the exact prompt the model read.

## Decisions taken for this roadmap

| Decision | Source | What it decides |
|---|---|---|
| `Returned` replaces `Park` | Architect, 2026-10-09 | The turn's end is `Returned{turn_index, reason, detail}`; `reason` is `replied` \| `model_error` \| `interrupted`. |
| The session stops writing `FinalAnswer` in one step | Architect, 2026-10-09 | No transition release. Only Substrate's own readers count. |
| `ModelReply` is one per model call | Research P1 | Fields `text`, `stop_reason` (`end_turn` \| `tool_use` \| `wrap_up`), `usage`, `turn_index`, `step`. |
| tool_loop keeps `FinalAnswer` | Research F2 | Benchmarks grade a final answer; `agency.py` and `delegate.py:170` read tool_loop records and keep reading it. |
| Readers change before writers | Research P6 | Records on disk keep `Park` and `FinalAnswer`. Every reader accepts both shapes before the session writes the new one. |

## Lens-audit rows this roadmap closes

Eighteen rows of the 2026-10-08 ledger concern the session topology; the ledger names these sprints for them.

| Rows | Sprint |
|---|---|
| F098, F100, F101, F107, F108, F469 | K261 |
| F093, F094, F097, F099 | K262 |
| F106 | K263 |
| F096, F103, F104 | K264 |
| F095, F102, F105, F109 | K266 |

## Order and checks

Each step's check runs against the installed Substrate.app where the step changes behavior.

**1. K259: session vocabulary v0.3 (document).**
- *Work:* a new lettered section in `process/signals/session-vocabulary.md` locks `ModelReply` v2, `Returned`, the producer names (P4) and the trigger names (P5). It retires `Park`, and `FinalAnswer` in sessions.
- *Check:* every name used by K260–K266 appears in the new section.

**2. K260: kernel readers accept both shapes.**
- *Work:* `vocabulary.py` gets `RETURNED` and a legacy table, and these readers move onto it:
  - `transcript.py`;
  - `delegate.py:504`, `:806`;
  - `cli.py:1002`;
  - `ci.py`.
- *Check:* the committed CI record and a synthetic new-shape record each render the same transcript, delegate answer and CLI lines.

**3. U119: UI readers accept both shapes.**
- *Work:* these accept both shapes:
  - `envelope_kinds.gen.ts`;
  - `session_controller.ts`;
  - `reveal_component.ts` (stream rows, lanes, the model/external lifelines).
- *Check:* an Electron gate on the installed app attaches an old record and a new-shape record; both show one reply per turn and the turn's end.

**3a. K267: a Producer's input is its own copy of the recorded input.** (Added 2026-10-09; ratified by the Architect.)
- *Work:* the kernel hands each Producer a fresh decode of the canonical bytes it already hashes and records, in place of `seal()`'s read-only mappings and tuples. The four sealed-input fixes (sprints 049, 052, 053, K261's `unseal`) go. F-PROD-3 and §8.3 are amended to isolation by copy.
- *Check:* a Producer's input equals the decode of its recorded input; a Producer's change to its input is invisible to views and other Producers; values with no canonical form still never start a Producer; committed CI records unchanged.

**3b. K268: the model step reads its history from the record by reference.** (Added 2026-10-09.)
- *Work:* a seq-range reader in the kernel; the model step's recorded input is a ticket to the kept range of its own record, not a copy of the history.
- *Check:* recorded inputs stay small as a session grows; prompts built from the ticket equal those built from the full record.

**4. K261: the prompt is built once and recorded exactly.**
- *Work:* one builder. `PromptComposed.text` is the bytes the driver reads. Order: seed and session fragments, then kept history, then the current message, once. `assembled_prompt` and the `user_message` fragment go. The window is sized from the rendered estimate, and the record is not re-read in full per firing.
- *Check:* the capture-responder probe of the research (F4) shows the user's text once, after the seed, and equal to `PromptComposed.text`. A real `claude` turn and a real Ollama turn answer.

**5. K262: one reply event per model call; `Returned` ends the turn.**
- *Work:*
  - `ModelReply` is written on every model call, including one that calls a tool, with `stop_reason` and `usage` filled from the responder.
  - The session writes no `FinalAnswer`.
  - Producer `park` becomes `return`, with triggers `return-on-reply`, `return-on-model-error` and `return-on-interrupt`. Termination pauses on `Returned`.
  - A hard interrupt during a tool call ends the turn with `reason=interrupted` (F093).
- *Check:*
  - A plain turn holds one `ModelReply` and one `Returned`, and no `FinalAnswer`.
  - A tool turn holds a `ModelReply(tool_use)` per call.
  - `usage` has non-zero tokens on Ollama.
  - Interrupting a slow `bash` ends the turn.

**6. K263: fewer producers.**
- *Work:*
  - one `session_prompt` producer replaces the five session-open fragment producers, reusing delegate's slice extractor instead of a copy (F106);
  - `prompt_composer` fires on `UserMessage` and the per-turn chain goes;
  - `warning` replaces the two warning producers;
  - `session_open` becomes `first_message`.
- *Check:* envelopes per plain turn are measured before and after (20 today); the session-open fragments still carry their `source`.

**7. K264: one trigger naming rule.**
- *Work:*
  - The remaining triggers take the form `<what it starts>-on-<event>`.
  - `end-on-cap` becomes `end-on-turn-cap`, with `reason=turn_cap`.
  - The kind and producer literals (F096, F103, F104) give way to constants.
  - The CI records are regenerated.
- *Check:* the structure view lists only names from K259; grep finds no raw kind or producer literal in the session package.

**8. K265: why session-open fragments re-fire after a resume.**
- *Work:* trace the re-emission seen on `s_9eee1b3a4d094346bb30039c` seq 13–20; fix or record the reason.
- *Check:* a resumed session's turn writes no session-open fragment, or the card records why it must.

**9. K266: documents match the code.**
- *Work:* `docs/api.md`, module docstrings and the counts in `vocabulary.py`, `ci.py`, `composer.py` and `__init__.py` (F095, F102, F105, F109).
- *Check:* every count stated in a docstring matches the code.

## Sprint cards

| Sprint | Repo | Card |
|---|---|---|
| K259–K269 | substrate | `substrate/process/sprints/sprint-259…269-*.md` |
| U119 | substrate-ui | `substrate-ui/process/sprints/sprint-119-ui-reads-both-session-shapes.md` |

**Queued: K269, a parallel test suite** (`sprint-269-parallel-suite.md`): pytest-xdist; each real-model test on a model that can do its task, its timeout measured, a failed run retried once.

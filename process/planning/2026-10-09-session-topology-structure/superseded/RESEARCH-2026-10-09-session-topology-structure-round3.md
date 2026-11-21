# RESEARCH — the session topology's structure, where it came from, and a plan to make it plain (round 3)

Round 3. Changes from round 2: the Architect's three decisions of 2026-10-09 are settled (section 6).
- The turn's end is `Returned`.
- The session stops writing `FinalAnswer` in one step, with no transition release.
- sdd-kit-2 keeps its past-tense rule; that rule governs the kit's signal vocabulary, not Substrate's code names.

Round 1 introduced the findings and the plan; round 2 dropped the past-tense naming.

Date: 2026-10-09. Status: decisions settled 2026-10-09; vocabulary lock (R0) next. No code changes until ratified (sdd-kit-2 `grammar/PRINCIPLES.md` commitment 3: a worker proposes vocabulary, the Architect ratifies).

Scope: the whole `session_topology` (`substrate/src/substrate/topologies/session/`) in Substrate's own terms — its producer kinds, triggers, views, initials, instrument, event kinds and termination policy. Not one event pair.

## 1. What the topology is today

Measured from `session/__init__.py` and the structure view of a live session.

- **Producer kinds: 17 registered** (15 always; `role_fragment` and `parent_context_fragment` only when the session has a role or parent context). One more, `driver_stepper`, belongs to the CI wrapper in `ci.py`.
  - Turn work: `model`, `tool`, `park`, `session_end`.
  - Session open: `session_started` (an instrument on `substrate.RunStarted`), `session_open` (emits the first `UserMessage`), five session-open prompt sources (`role_fragment`, `bundle_methodology_fragment`, `bundle_personality_fragment`, `tools_suite_fragment`, `parent_context_fragment`).
  - Per-turn prompt: `per_turn_fragment`, `user_message_fragment`, `interrupt_fragment`, `prompt_composer`.
  - Warnings: `session_warning`, `fragment_error_warning` (both emit `SessionWarning`).
- **Triggers: 16 registered plus the instrument**, so the structure view lists 17.
- **Views: 6** — `results`, `user_turns`, `model_failures`, `fragment_cohort`, `latest_user_message`, `latest_composed`.
- **Event kinds the topology writes: 15** — `SessionStarted`, `UserMessage`, `PromptFragment`, `PromptComposed`, `ModelReply`, `FinalAnswer`, `ToolCall`, `ToolResult`, `Park`, `TranscriptCompacted`, `BackgroundTaskEnded`, `SessionWarning`, `SessionEnded`, plus the injected `SessionEndRequested` and `InterruptRequested`. `ToolCall`, `ToolResult` and `FinalAnswer` are borrowed from `tool_loop`.
- **Termination:** `any_of(pause_await_input(on Park, resume on UserMessage), finalise_on(SessionEnded))`.

**One plain chat turn, measured** on session `s_9eee1b3a4d094346bb30039c`, seq 63–82: 20 envelopes. Fourteen are kernel bookkeeping (`substrate.TriggerFired`, `ProducerStarted`, `ProducerCompleted`); six are session events: `UserMessage`, `PromptFragment`, `PromptComposed`, `ModelReply`, `FinalAnswer`, `Park`.

## 2. Where it came from

The topology grew in five layers; each was sound for its own sprint, and none revisited the layers below it.

1. **tool_loop (before August).** A benchmark agent loop: `model` emits `ToolCall` or `FinalAnswer`; `tool` emits `ToolResult`; triggers `run-tool`, `continue`, `wrap-up`. In a benchmark, "final answer" is the right name: the assay oracle (`assay/oracle.py`) grades it.
2. **Tech spec round 6 §3 (2026-08-25).** The daily-driver session is "run_topology's shape … with one addition: on FinalAnswer, a Trigger fires a Producer that calls pause_await_input". That one addition is `Park`, named after the kernel's pause mechanism. The spec also added `ModelReply`: "one per model firing", carrying `model_usage` (tokens, time), and placed one before each tool call: `ModelReply → (ToolCall → ToolResult → ModelReply)* → FinalAnswer`.
3. **Session vocabulary v0.1 (sprint 202, ratified 2026-08-25)** locked eight kinds including `ModelReply` and `Park`, and the invariant "exactly one `Park` after each `FinalAnswer`".
4. **Sprint 209a** wired the producer bodies. It never built ModelReply's intended job: no ModelReply before a tool call, `model_usage` always `{}`. It emits `ModelReply(text)` and then `FinalAnswer(text)` with the same string on all four exit paths (`__init__.py:496-497`, `:528-529`, `:553-554`, `:559-560`).
5. **Prompt-composition arc, v0.2 (sprints 058–068, 2026-09-01/02)** rebuilt prompt assembly as producers so every prompt part rides the record: eight fragment producers, a composer, a three-link per-turn chain. Phase 8 added the interrupt fragment; UI sprint 104 added `BackgroundTaskEnded`.

The 2026-08-31 review (`process/reviews/REVIEW-2026-08-31-session-topology-vs-specs.md`) checked the code against the specs and called it correct. It checked conformance, not design: where the spec itself carried a duplicate, the review counted the duplicate as conformance.

## 3. Findings

### F1 — Every reply is written twice

A turn that answers writes `ModelReply(text)` then `FinalAnswer(text)`, same text (measured: equal on `s_9eee…` seq 63–82; `model_usage: {}`). Three places now work around it: the window controller hides a FinalAnswer that repeats the last reply (`substrate-ui/web/vm/session_controller.ts:1012`), sprint 116 dropped it from the prompt (`transcript.py`), and the stream view still shows both rows. `composer.py:30` says the driver's usage "lands separately on `ModelReply.model_usage`"; it does not.

In sdd-kit-2 terms this is a `TAG_MERGE_PROPOSED` case (`PRINCIPLES.md:82`): two tags denote one event.

### F2 — "FinalAnswer" names a judgment the session does not make

In a session, the text that ends a turn is the model's reply for that turn, not a final answer: the user replies, and the session goes on. The name came from tool_loop, where an oracle grades it. The same surface term means two events in two contexts — the kit's `TAG_SPLIT_PROPOSED` case (`PRINCIPLES.md:81`, "the DDD bounded-context move"). tool_loop keeps `FinalAnswer`; the session should not borrow it.

### F3 — "Park" names the mechanism, not the event

`Park` is the kernel's pause (`pause_await_input`) leaking into the domain vocabulary. The kit separates domain grammar ("what the system means") from runtime grammar ("what the system computed", Layer 6) (`PRINCIPLES.md:98-105`). What happened, in domain terms: the turn is over and control is back with the user.

### F4 — The user's message reaches the model twice, after the seed

Captured on a real session run (deterministic capture responder, `first_turn_user_message="UNIQUE-HELLO-42"`, seed `"SEED"`), the model's whole prompt was:

```
UNIQUE-HELLO-42
SEED
[transcript: turns 0..0]
USER: UNIQUE-HELLO-42
```

The composed prompt (fragments, ending with the user's message) is prepended to the rendered transcript (seed, then every kept turn including the current one) in `_model_factory` (`__init__.py:433-434`). So the user's ask comes before the session's seed and then again at the end. On the record, the user's line is stored three times per turn (`UserMessage.text`, `UserMessage.assembled_prompt`, the `user_message` `PromptFragment`) and a fourth time inside `PromptComposed.text`.

### F5 — `PromptComposed` is not what the model reads

Vocabulary §I locks `PromptComposed.text` as "the assembled prompt the model receives. Bytes-identical to what the driver reads." The model producer then adds the rendered transcript, background-task notices, the tool list (text-only drivers), "Tool results so far", and the JSON tool-call or wrap-up directive (`__init__.py:420-555`). The record carries a prompt the model never saw, and the prompt it did see is nowhere on the record. That breaks the reason the v0.2 arc exists: "Replay cannot reconstruct which fragment came from where."

### F6 — Prompt plumbing outweighs the turn

Each producer activation costs three bookkeeping envelopes (TriggerFired, ProducerStarted, ProducerCompleted).
- Per turn, three activations run in series before the model: `per_turn_fragment` → `user_message_fragment` → `prompt_composer`. Each link subscribes to the previous one's `ProducerCompleted` or `ProducerFailed`, so the turn's order is held by kernel bookkeeping rather than by the events themselves.
- At session open, five producers each emit one fragment.
- On `s_9eee…` seq 10–36, a resumed turn re-emitted the session-open fragments (seq 13–20) after the first `UserMessage`. The cause is not yet traced.

### F7 — Duplicate and clashing producer names

- `session_started` emits `SessionStarted`, while `session_open` emits the first `UserMessage`. The name doesn't say what the producer does.
- `session_warning` and `fragment_error_warning` are two producers that emit one kind.

### F8 — Trigger names follow five different patterns

| Pattern | Triggers |
|---|---|
| Bare verb | `continue`, `wrap-up`, `run-tool` |
| Mechanism word for what it starts | `resume-on-composed` (it starts the model; nothing resumes) |
| `emit-<thing>` | `emit-per-turn-fragment`, `emit-user-message-fragment`, `emit-interrupt-fragment` |
| `<verb>-on-<event>` | `park-on-final`, `park-on-model-error`, `park-on-interrupt`, `compose-on-cohort-complete`, `compose-on-interrupt-tool-result`, `warn-on-fragment-error`, `end-on-exit`, `end-on-cap`, `end-on-user-end` |
| Name of its producer | `session_started` (the instrument) |

`end-on-cap` ends the session with `reason="timeout"`, but the cap counts turns, not time.

### F9 — Stale counts in the code's own docs

- `vocabulary.py:3` says "the eight kind strings"; the file names eleven.
- `__init__.py:13-14` says "ten triggers"; there are sixteen.
- Vocabulary §C says ModelReply comes "zero or more per turn (tool-loop may fire model multiple times)". The code writes exactly one per answering turn, and none on a tool call.

### Outside practice

| Source (genre) | How the end of a turn is signalled |
|---|---|
| Anthropic Messages API, `platform.claude.com/docs/en/api/handling-stop-reasons` (vendor API reference) | `stop_reason` on the one response: `end_turn` ends the turn, `tool_use` asks for a tool. The text is not repeated. |
| OpenAI Agents SDK, `openai.github.io/openai-agents-python/running_agents/` (vendor SDK docs) | "final output" is a classification of the last model response ("text output with the desired type, and there are no tool calls"), not a separate item. |
| AG-UI events, `docs.ag-ui.com/concepts/events` (open protocol docs) | `TextMessageEnd` closes a message and "does not repeat the message content"; `RunFinished` / `RunError` end a run. |
| OpenTelemetry GenAI semantic conventions (standards draft, status "Development") | One inference span per model call carries `gen_ai.response.finish_reasons`, `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`. |

All four put "why the model stopped" and the token counts on the model's one response. None writes the text twice. These are vendor and draft-standard documents, not independent studies. They agree on the shape, and the shape is also what the session vocabulary itself first asked for in v0.1.

## 4. Proposal (for ratification)

### Naming principle

A name says plainly what the thing is, in words a person reading the stream would use.
- **No mechanism words.** `Park` names the kernel's pause, not what the user sees.
- **No judgment words.** `FinalAnswer` claims a verdict the session never makes.
- **Asks say "Request".** `SessionEndRequested` and `InterruptRequested` mark something asked for, which may still be refused. Everything else on the record is something that happened.

**Tense is free.** sdd-kit-2's past-tense rule (`grammar/BOOTSTRAP.md:84`, `PRINCIPLES.md:21`) governs the kit's own signal vocabulary, and it stays there unchanged. It comes from event sourcing (Greg Young; Vaughn Vernon, *Implementing Domain-Driven Design* — practitioner books, not studies), where a log mixes commands ("PlaceOrder") with facts ("OrderPlaced") and tense tells them apart. Substrate's producer, trigger and event names are ordinary software names, and round 1 was wrong to apply the rule to them. A Substrate record is append-only and holds only what happened, so the one distinction tense would carry — ask versus fact — is carried by the word "Request". Anthropic's stream (`message_start`, `message_stop`) and AG-UI (`TextMessageStart`, `ToolCallResult`) name things the same way.

The proposal follows the Architect's decisions of 2026-10-09: `Returned` for Park, and the session's FinalAnswer goes in one step.

### P1 — One event per model call: `ModelReply`

`ModelReply` stays the name and becomes what v0.1 meant it to be: one per model call. The session stops writing `FinalAnswer`; `stop_reason` carries what FinalAnswer signalled.

| Field | Meaning |
|---|---|
| `text` | what the model said (empty on a bare tool call) |
| `stop_reason` | `end_turn` \| `tool_use` \| `wrap_up` (budget or repeated tool failure forced a plain answer) |
| `usage` | input tokens, output tokens, wall ms, model — the job ModelReply was given in v0.1 |
| `turn_index`, `step` | as today |

tool_loop keeps `FinalAnswer` for benchmarks (F2's split).

### P2 — `Returned` replaces `Park`

`Returned{turn_index, reason, detail}` means the turn is over and control is back with the user. `reason` is `replied` \| `model_error` \| `interrupted`; `detail` is as today. The termination policy pauses on `Returned`. Settled 2026-10-09.

### P3 — The record carries the exact prompt, once

- One builder makes the whole prompt, and `PromptComposed.text` is exactly what the driver reads, with no additions afterwards.
- Order: seed and session-open fragments, then the kept history, then the current message, once.
- The user's line is stored once on the record (`UserMessage.text`). `assembled_prompt` and the `user_message` fragment go.

### P4 — Fewer producers, each named for what it does

| Today | Proposed |
|---|---|
| `role_fragment`, `bundle_methodology_fragment`, `bundle_personality_fragment`, `tools_suite_fragment`, `parent_context_fragment` | `session_prompt`: one producer at session open, one `PromptFragment` per source (the `source` field keeps the provenance) |
| `per_turn_fragment` → `user_message_fragment` → `prompt_composer` | `prompt_composer` fires on `UserMessage` and reads the per-turn text itself; the chain goes |
| `park` | `return` |
| `session_open` | `first_message` |
| `session_warning`, `fragment_error_warning` | `warning` |

Kept: `model`, `tool`, `session_end`, `interrupt_fragment`, the `session_started` instrument.

Effect on a plain turn: two fewer activations (six envelopes) and no `FinalAnswer`. From 20 envelopes to 13, to be measured after the change.

### P5 — One trigger naming rule: `<what it starts>-on-<event>`

| Today | Proposed |
|---|---|
| `run-tool` | `tool-on-tool-call` |
| `continue` | `model-on-tool-result` |
| `wrap-up` | `model-wrap-up-on-tool-result` |
| `resume-on-composed` | `model-on-prompt-composed` |
| `park-on-final` / `-model-error` / `-interrupt` | `return-on-reply` / `return-on-model-error` / `return-on-interrupt` (`return-on-reply` fires on a `ModelReply` whose `stop_reason` is not `tool_use`) |
| `end-on-cap` (`reason=timeout`) | `end-on-turn-cap` (`reason=turn_cap`) |
| `end-on-user-end` | `end-on-end-request` |
| `emit-*`, `compose-*` | gone with P4 |

### P6 — Old records stay readable

Records are append-only and immutable. Records already on disk — the Architect's own sessions — keep `FinalAnswer` and `Park`, and still open. Every reader — the window controller, the transcript renderer, the stream view, replay and the delegate's answer read — maps them through one table in `vocabulary.py`: an old `Park` reads as `Returned`, and an old session `FinalAnswer` that repeats the `ModelReply` before it is dropped. An old `ModelReply` with no `stop_reason` reads as `end_turn` when a FinalAnswer follows it. The committed CI records are regenerated, since the topology fingerprint changes.

## 5. Roadmap

Each step is one sprint card under sdd-kit-2, with an observation contract run against the installed Substrate.app.

| # | Sprint | Depends on | Blast radius (files using the names today) |
|---|---|---|---|
| R0 | Session vocabulary v0.3: `ModelReply` fields (P1), `Returned` (P2), trigger names (P5); rationale; `TAG_MERGE` (ModelReply+FinalAnswer), `TAG_SPLIT` (FinalAnswer stays in tool_loop), `Park` deprecation; Document only. | decisions of 2026-10-09 | `process/signals/session-vocabulary.md` (new lettered section) |
| R1 | Readers accept old and new records (P6), before anything writes the new shape | R0 | `Park` readers; `FinalAnswer`: 14 kernel src, 3 UI src |
| R2 | Prompt truth (P3): one builder, exact bytes on `PromptComposed`, user line once, seed first. Behavior change; real-model check on Ollama and `claude`. | R0 | `__init__.py`, `transcript.py`, `composer.py`, fragment producers |
| R3 | `ModelReply` once per model call with `stop_reason` and `usage`; the session stops writing `FinalAnswer` in this sprint, with no transition release; `Returned` replaces `Park` (P1, P2) | R1 | `__init__.py`, `vocabulary.py`, `session_registry.py`, `cli.py`, `delegate.py`, UI controller and reveal shell; `FinalAnswer` in 22 kernel and 3 UI test files |
| R4 | Producer consolidation (P4); measure envelopes per plain turn | R2 | session package; CI records |
| R5 | Trigger renames (P5); CI records regenerated | R3, R4 | `vocabulary.py`, `__init__.py`, `ci.py`, CI records |
| R6 | Trace why session-open fragments re-fire after a resume (F6) | — | to be found |
| R7 | Docs: vocabulary doc, `docs/api.md`, module docstrings (F9) | R5 | docs |

## 6. Decisions (settled 2026-10-09)

1. The turn's end is `Returned`.
2. The session stops writing `FinalAnswer` in one step (R3). Only Substrate's own readers matter, and R1 updates all of them first.
3. sdd-kit-2 keeps its past-tense rule for its signal vocabulary. Substrate's code names follow section 4's naming principle.

`UserMessage`, `ToolCall` and `ToolResult` keep their names: each already says plainly what it is.

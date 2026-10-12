# Sprint 299 — A change reaches the prompt for the next message

```yaml
---
id: 299
status: closed
closed_at: 2026-10-12
phase: 1
pass_kind: functional
roadmap: process/planning/ROADMAP-2026-10-12-changes-on-time-r2.md
postmortem: process/planning/POSTMORTEM-2026-10-12-mid-session-changes-arrive-late-r2.md
asked: 2026-10-12 (Architect: the first message after a change is answered under the new setting)
context_files:
  - src/substrate/topologies/session/__init__.py
  - src/substrate/topologies/session/session_prompt_producer.py
  - src/substrate/topologies/session/vocabulary.py
  - process/signals/session-vocabulary.md
---
```

## scope

*Revised before any code, after the roadmap's round-2 pressure test.*

- **Vocabulary v0.10 § V.** `SessionChanged` is written by the session-prompt producer, not the model; the prompt for the message on which a change is recorded carries the new text; the turn's record reads message, change(s), rewritten fragments, prompt, reply. Triggers `session-prompt-on-user-message-change` and `model-on-session-prompt-change` added; `session-prompt-on-session-changed` removed.
- **One detection helper** compares the `SessionSettings` view with the turn's settings; `model-on-user-message` fires only when nothing changed.
- **The session-prompt producer**, started with the changes, records each `SessionChanged` and writes the rewritten sources in one run (generation: the message's seq).
- **Its completion starts the model** when the turn's first model step has not run.
- The model step's step-0 detection block goes.
- A skill message after a change: the change's run, then the skill fragment, then the model.

## observation contract

Kernel tests (written in K300 first): for bundle, per_turn, length, tone, and length with tone together, a session run on a capture driver, changed between two messages, records the order above, and the `PromptComposed` for the message after the change holds the new text and not the old; the capture driver is called once for that message.

## checks

K300's tests red, then green; kernel suite; ruff, mypy --strict, lint-imports; vocabulary signed.

## result

- **Built.** `vocabulary.py`: `SESSION_CHANGE_FIELDS`; triggers `session-prompt-on-user-message-change`, `model-on-session-prompt-change`, `skill-fragment-on-session-prompt-change` added, `session-prompt-on-session-changed` removed. `__init__.py`: `_pending_changes` (the `session_settings` view against the turn's settings); `_turn_message` over a new `user_messages` view; `model-on-user-message` and `skill-fragment-on-user-message` fire only with no change; the model step's step-0 detection, its `settings` input and `current_settings` parameter removed; `session_prompt` registered in every session and listing `SessionChanged` in its schemas (the model no longer does). `session_prompt_producer.py`: a change run records each `SessionChanged`, then writes exactly the sources in `only` (none for a driver or date change).
- **Tests.** K300's 7 and the updated K274, K296, K298 tests pass. Three tests encoding K263's "no source, no session_prompt" now assert the producer is present (`test_fewer_producers_263` ×2, `test_render_seed_alone_exceeds`). The `daily` and `session` bundled records regenerated (the other 16 restored). Kernel suite 1,532 passed, 13 skipped; ruff, mypy --strict (139 files), lint-imports (2 kept).
- **Vocabulary** § V (v0.10) signed. Postmortem round 3 corrects RC2: K274's test asserted the delay.
- **Rubber Duck Pass.** A message arrives with tone changed: `session-prompt-on-user-message-change` starts `session_prompt` with `[{"field": "tone", ...}]` and `only: ["control"]`; it records `SessionChanged(tone)` and the new `control` fragment (generation: the message's seq); its completion fires `model-on-session-prompt-change`; the model's `_prompt_input` reads the cohort with the new fragment, and the history draws "tone changed" beside the message.

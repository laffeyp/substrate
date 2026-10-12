# Sprint 299 — A change reaches the prompt for the next message

```yaml
---
id: 299
status: open
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

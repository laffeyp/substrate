# Sprint 299 — A change reaches the prompt for the next message

```yaml
---
id: 299
status: open
phase: 1
pass_kind: functional
roadmap: process/planning/ROADMAP-2026-10-12-changes-on-time.md
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

- **Vocabulary v0.10 § V.** The prompt for the message on which a `SessionChanged` is recorded carries the rewritten sources; the record's order for that turn is the message, the change(s), the rewritten fragments, the prompt.
- **The model step stops after recording a change with rewritten text.** On step 0, when any changed field is in `_REWRITTEN_ON_CHANGE`, it yields the `SessionChanged` events and completes without composing a prompt or calling the driver.
- **One rewrite per step.** The session-prompt rewrite covers every field changed that step (today each `SessionChanged` starts its own producer), so the model starts once.
- **A new trigger** starts the model on that rewrite's completion, with the turn's input (as `model-on-skill-fragment` does for skills).
- Date and driver changes, which rewrite no text, keep today's path.

## observation contract

Kernel tests (written in K300 first): for bundle, per_turn, length, tone, and length with tone together, a session run on a capture driver, changed between two messages, records the order above, and the `PromptComposed` for the message after the change holds the new text and not the old; the capture driver is called once for that message.

## checks

K300's tests red, then green; kernel suite; ruff, mypy --strict, lint-imports; vocabulary signed.

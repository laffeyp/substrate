# Sprint 324 — How readily a session hands work to a topology

```yaml
---
id: 324
status: closed
closed_at: 2026-10-13
phase: 3
pass_kind: functional
depends_on: [323]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies-r2.md
---
```

## scope

A session setting beside length and tone for how readily the model hands work to a topology (delegate, review, build) rather than doing it itself (r8 § 5): positions, a default, the text each writes into the session prompt, changeable mid-session the way length and tone are, on the vocabulary first. Its effect is read from the record: topology calls per turn, by setting and by model.

## observation contract

The position reaches the manifest, `SessionStarted` and the prompt of the message after a change; `substrate` reads topology calls per turn from a record; a scripted check shows the prompt text for each position.

## result

- **Vocabulary first.** v0.13 § Y ratified: the control `handoff`, positions `rare`, `normal` (default), `eager`; the texts; `SessionStarted.handoff`; `SessionChanged.field` adds `handoff`; the measure.
- **Built.** `vocabulary.py`: `Control.HANDOFF`, `HandoffPosition`, `HANDOFF_DEFAULT`, `HANDOFF_TEXTS`, `HANDOFF_TOOLS` (built from the tool names, now each defined once in `tool_loop/tools.py`: `TOOL_NAME_DELEGATE`, `TOOL_NAME_REVIEW`, `TOOL_NAME_BUILD`, `TOOL_NAME_RUN`, imported by review, build, hold and delegate), and `CONTROL_DEFAULTS`. The control flows through `control_fragments`, `session_prompt_sources`, `session_topology(handoff=)`, `SessionStarted`, the registry (manifest, create, `set_controls`, validation, persistence), delegate children (inherited) and the app server (create, PATCH, the manifest responses, the topology). `session/handoff.py` `handoff_calls(events)` and `substrate handoff <record>`: per turn, its position, model, topology calls and their tools; a change recorded after its turn's message applies to that turn.
- **Found by the prompt assertion.** Three hand-written lists of the controls each lacked the new one: `SESSION_CHANGE_FIELDS` (so no change was recorded), the field-to-source map (so the `control` source was not rewritten), and the settings view's opening defaults. Each is now derived from `Control` or `CONTROL_DEFAULTS`. The committed session and daily CI records were regenerated for the new `SessionStarted` field; the other 16 were restored.
- **Tests.** `tests/test_handoff_control_324.py`, 5: each position's text, none at the default, an unknown one refused; the registry keeps, persists and refuses positions; a session opens with its position, and a change from `rare` to `eager` reaches the next message's prompt with its environment line, recorded as `SessionChanged`; calls per turn with the position; the command's line. Session, vocabulary, language, control and prompt tests: 372 pass.

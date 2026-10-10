# Sprint 259 — Session vocabulary v0.3

```yaml
---
id: 259
status: closed
opened_at: 2026-10-09
closed_at: 2026-10-09
phase: 1
pass_kind: docs
roadmap: substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md
---
```

## why

Research round 4 (F1–F3, P1, P2, P4, P5) and the Architect's decisions of 2026-10-09 change the session's names and the reply shape. The vocabulary is locked before code (sdd-kit-2 hard rule 12), so K260–K266 cite one document.

## scope

Add section K, v0.3, to `session-vocabulary.md`. It locks:
- `ModelReply` v2: `text`, `stop_reason` (`end_turn` | `tool_use` | `wrap_up`), `usage` (`input_tokens`, `output_tokens`, `wall_ms`, `model`), `turn_index`, `step` — one per model call.
- `Returned{turn_index, reason, detail}` with `reason` `replied` | `model_error` | `interrupted`.
- The producer names (`return`, `session_prompt`, `prompt_composer`, `warning`, `first_message`) and trigger names (`tool-on-tool-call`, `model-on-tool-result`, `model-wrap-up-on-tool-result`, `model-on-prompt-composed`, `return-on-reply`, `return-on-model-error`, `return-on-interrupt`, `end-on-exit`, `end-on-turn-cap`, `end-on-end-request`).
- The retirement of `Park`, and of `FinalAnswer` on session records.
- The rule that readers accept the retired kinds on records already on disk.
- The invariants of section F rewritten for `Returned`.

Sections A–J stay byte-preserved.

## prerequisites

- none

## context_files

- `sdd-kit-2/AGENTS.md`
- `substrate/process/planning/RESEARCH-2026-10-09-session-topology-structure-round4.md`
- `substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md`
- `substrate/process/signals/session-vocabulary.md`
- `substrate/process/BLACKBOARD.md`


## signal contract

### Emits

None (document only).

### Invariants

- Sections A–J are byte-identical to before.
- tool_loop's `FinalAnswer` is unchanged.

## artifact contract

### Files created

- none

### Files modified

- `substrate/process/signals/session-vocabulary.md`

### Content assertions

- Section K names every producer, trigger and kind that K260–K266 use.
- The status header reads `RATIFIED — v0.3`.
- `git diff` shows additions only above section A's line and after section J.

### Command exit codes

- `git diff --stat` touches one file.

## observation contract

None required (`docs`). The Architect reads section K before K260 dispatches.

## done criteria

The session vocabulary v0.3 is locked and names everything the next seven sprints change.

## result

- `process/signals/session-vocabulary.md` gains a v0.3 status line and section K. K covers: K.1 `ModelReply` v2, K.2 `Returned`, K.3 retired kinds and how old records read, K.4 producer names, K.5 trigger names, K.6 termination, K.7 invariants.
- Sections A–J are byte-identical to the file before the sprint (diffed against a copy taken first).
- K.5 names four triggers the roadmap's list left implicit: `prompt_composer-on-user-message`, `prompt_composer-on-interrupt`, `interrupt_fragment-on-interrupt-request` and `warning-on-fragment-error`. K263 and K264 use them.
- `usage` carries `estimated: bool` for responders that report no counts (a CLI driver).

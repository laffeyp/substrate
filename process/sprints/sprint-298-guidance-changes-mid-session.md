# Sprint 298 — Guidance changes mid-session, and its history line names the level

```yaml
---
id: 298
status: closed
closed_at: 2026-10-12
phase: 1
pass_kind: functional
asked: 2026-10-12 (Architect: guidance, length and tone shown in the pane and changed mid-session; "let's make it happen")
research: process/planning/RESEARCH-2026-10-12-controls-mid-session-r2.md
vocabulary: process/signals/session-vocabulary.md § U (v0.9)
context_files:
  - src/substrate/topologies/session/transcript.py
  - src/substrate/topologies/session/model_class.py
  - src/substrate/bundles.py
---
```

## scope

A mid-session change of length, tone or bundle is already recorded as `SessionChanged`, rewrites the system text (§ P.4, § T.3) and is drawn in the history at its place (`session_changed_line`). Guidance is the bundle (§ R.1), so it changes through the same path; but its history line reads `bundle changed from standard to standard-low`. After: a change between two level bundles reads `guidance changed from high to low` (§ U.2).

## signal contract

No new kind or field; `session_changed_line`'s text for a `bundle` change between level bundles.

## observation contract

`tests/test_guidance_mid_session_298.py`: the line for `standard` → `standard-low` names high → low; a legacy name (`standard-small`) names low; a non-level bundle keeps the bundle line; length and tone lines unchanged. A session run on the deterministic driver, its bundle changed mid-session with `set_bundle`, writes `SessionChanged {field: bundle}` (with a `per_turn` change, since each level carries its own reminder line), and the next prompt's history carries the guidance line beside that turn's message (§ P.4).

## checks

- Test red, then green; kernel suite; ruff, mypy --strict, lint-imports.

## result

- **Built** (`transcript.py`): `session_changed_line` maps both sides of a `bundle` change through `LEGACY_BUNDLE_NAMES` and the inverse of `LEVEL_BUNDLES`; two levels give `Environment update: guidance changed from high to low.`
- **Tests** `tests/test_guidance_mid_session_298.py`, 3: red on the old code (the line read `bundle changed from standard to standard-low`), green after. The session and prompt tests (362 passed, 5 skipped) and K296's pass; ruff, mypy --strict (139 files), lint-imports clean.
- **Vocabulary** § U (v0.9), signed as decided by the Architect, recorded by the Agent.
- **Rubber Duck Pass.** A `SessionChanged` of `bundle` at a turn's first step: the session-prompt producer writes the level's sources again (§ P.4), and the composer draws the line beside that turn's message; no kind or field moved.

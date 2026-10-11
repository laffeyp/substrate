# Sprint 270 — Session vocabulary v0.4: default guidance

```yaml
---
id: 270
status: closed
closed_at: 2026-10-10
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-default-guidance.md
asked: 2026-10-10 (Architect)
---
```

## why

The default-guidance roadmap adds sources, Structs, a field and two renames. SDD puts the vocabulary first.

## scope

- Section P of `process/signals/session-vocabulary.md`: `style` (renamed from `personality`, stacking per link), `harness` (renamed from `session`), `PromptSource` `baseline`, `skill`, `memory`; `SYSTEM_SOURCES`; `PromptComposed.system`; `SessionChanged{field, old, new}`; `SkillRequested{name}`; precedence 5 for every methodology link; `PER_TURN` in the session-open set; legacy tables for `bundle_personality` and the bundle name `session`.

## checks

- Every name used by K271–K280 and U120–U122 appears in section P.

## result

- Section P of `process/signals/session-vocabulary.md`, v0.4: P.1 renames and their legacy tables; P.2 the sources `bundle_style`, `baseline`, `memory`, `skill` and the moved `per_turn`, with scope, precedence and channel; P.3 `PromptComposed.system` and the `cache_layout` layout; P.4 `SessionChanged` and `SkillRequested`; P.5 `skill_fragment` and its trigger; P.6 the `skill` tool; P.7 the shipped bundle, role, skill and class names.
- Check: every name the roadmap's K271–K280 and U120–U122 use appears in section P. §§ A–O unchanged.

# Sprint 288 — Medium and low levels; the level follows the model

```yaml
---
id: 288
status: closed
closed_at: 2026-10-10
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-guidance-levels.md
asked: 2026-10-10 (Architect)
---
```

## result

- **Bundles.**
  - `standard-medium` is new. Every rule of high is stated once, without examples: 1,218 tokens.
  - `standard-small` became `standard-low` (`git mv`; the text was already generic), 562 tokens. The old name resolves through `LEGACY_BUNDLE_NAMES`.
  - High (`standard`) is 2,995 tokens, and the harness level 291.
- **Classes.** `classify` has four. `small` is under 14B (was 30B), `medium` 14B to under 70B, and `large` 70B or more, or of unreported size.
- **Levels.** `GuidanceLevel` (`harness`, `low`, `medium`, `high`), `LEVEL_BUNDLES`, `guidance_level(model_class)` and `guidance_bundle(level)`. `class_variant` now only picks the small role prompt and skill.
- **Vocabulary.** § R.
- **Tests.**
  - `test_model_classes_278.py` covers the four classes at their boundaries and each class's default level.
  - Two tests are new. The levels' heads grow in size from default to high, with medium under 2,000 tokens. The old low name still loads.
  - The golden heads gain `standard-medium` and `standard-low`.
  - Kernel guidance tests: 60 passed.
- **Not yet.** The daemon still maps `standard` by class on every turn (`server.py:723`). U132 moves the choice to session creation and adds the control.

# Sprint 278 — Model classes

```yaml
---
id: 278
status: closed
closed_at: 2026-10-10
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-default-guidance.md
asked: 2026-10-10 (Architect)
---
```

## why

The full texts take a third of `llama3:8b`'s 8,192-token window.

## scope

- The classifier: CLI adapter = harness agent; Ollama under 30B parameters (`/api/show`, both report forms) = small; else large.
- `standard-small` (extends `harness`), `default-small`, `dellm-small`.
- `SessionStarted` records the class.

## checks

- `llama3:8b` opens on the small set within 800 tokens.
- `kimi-k2.6:cloud` opens on `standard`.

## result

- **Built.**
  - `topologies/session/model_class.py`: `parameter_count` reads both Ollama forms (`"8.0B"`, `"1042000000000"`, and `M`/`K`/`T` suffixes); `classify` returns `harness_agent` for a CLI, `small` below 30B, else `large`, including when the size is unknown; `class_variant`.
  - `SessionStarted.model_class`.
  - The daemon's `_model_class` probes `/api/show` and caches the result per model. For a small model it opens the session on `standard-small` in place of `standard`, `default-small` in place of `default`, and the `skill` tool and fragment read `dellm-small`. The manifest keeps the bundle that was asked for.
  - Live probe: `llama3:8b` and `qwen2.5:7b-instruct` small, `kimi-k2.6:cloud` large, `claude` a harness agent.
- **The texts.** `standard-small` (`extends = ["harness"]`), `default-small` and `dellm-small` keep each rule as one short line, 2,575 B together. With the harness, a small session's head is at most 800 tokens, which the test pins. `dellm-small` keeps the four passes and the word and structure lists, without sources or reasons.
- **Tests.**
  - `test_model_classes_278.py`, 5 tests: parsing, the three classes and the 30B line, `class_variant`, the small head within 800 tokens, and `dellm-small` resolving for the small class only, under a third of the full skill's length, and not listed separately.
  - The golden heads gained `standard-small`.
  - `substrate-ui/tests/test_model_class_278_daemon.py`: a small model's session records `standard-small`, `default-small` and `small`.
- **Checks** (targeted): 15 kernel and 5 UI tests passed.

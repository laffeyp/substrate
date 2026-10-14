# Sprint 311 — The app's sessions measure live

```yaml
---
id: 311
status: closed
closed_at: 2026-10-13
phase: 1
pass_kind: functional
depends_on: [310]
repos: [substrate, substrate-ui]
vocabulary: process/signals/session-vocabulary.md § W.6
---
```

## scope

The app's server (`substrate-ui/server.py`, where every app session's topology is built) opens sessions with `language=True`. The UI regenerates `envelope_kinds.gen.ts` and classes `LanguageProfile` and `LanguageDrift` as not shown (what the app shows is a later step).

## observation contract

A session in the installed app, with a real model, two turns: its record holds the language events in § W.5's order, and `substrate language <record>` gives the same values for the same texts. The UI's generated-kinds test and its gates pass.

## result

- **Built** (substrate-ui): `server.py` passes `language=True`; `scripts/gen_kinds.py` builds its reference session with it, so `envelope_kinds.gen.ts` gains `LanguageProfile` and `LanguageDrift`; the controller classes both `ignored`; the graph colours them as plumbing and its app view hides them (`LOW`), as `PromptComposed` is. The full view shows them in the `language` lane. What the app shows of them is the next step's design.
- **Live, in the installed app** (signed build, kernel `8aad1cec`, server on its own port): session `s_3de1000b91cb4d5eaa09efd9`, glm-5.2:cloud, two turns. Each turn's record: `ModelReply` (end_turn), `language-on-reply`, `LanguageProfile` user, model, relation final, relation turn, `return-on-language`, `Returned`. All 8 live profiles equal `substrate language`'s values for the same texts. The measurement took 44.4 ms on the first turn (lexicons loading) and 17.9 ms on the second, from the final reply to `return-on-language`.
- **Checks.** UI: typecheck, lint (two warnings in generated files this change leaves untouched), 37 unit tests, 250 Python tests (the generated-kinds test among them), and all 37 `gates:electron` commands pass. Notarization was skipped (no credentials set); the build is signed and verifies.

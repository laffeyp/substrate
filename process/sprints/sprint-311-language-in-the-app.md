# Sprint 311 — The app's sessions measure live

```yaml
---
id: 311
status: open
phase: 1
pass_kind: functional
depends_on: [310]
repos: [substrate, substrate-ui]
vocabulary: process/signals/session-vocabulary.md § W.6
---
```

## scope

`SessionRegistry` opens sessions with `language=True`. The UI regenerates `envelope_kinds.gen.ts` and classes `LanguageProfile` and `LanguageDrift` as not shown (what the app shows is a later step).

## observation contract

A session in the installed app, with a real model, two turns: its record holds the language events in § W.5's order, and `substrate language <record>` gives the same values for the same texts. The UI's generated-kinds test and its gates pass.

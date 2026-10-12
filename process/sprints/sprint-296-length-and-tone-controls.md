# Sprint 296 — Length and Tone: two controls a session opens with

```yaml
---
id: 296
status: closed
closed_at: 2026-10-11
phase: 1
pass_kind: functional
roadmap: substrate-ui/process/planning/ROADMAP-2026-10-11-before-distribution.md (step 10; OPEN-ITEMS 16)
asked: 2026-10-11 (Architect)
pairs_with: substrate-ui sprint 143 (the rows in the workspace bar)
---
```

## scope

Source: `process/planning/RESEARCH-2026-10-10-guidance-controls-r4.md` §7 (size and tone), §9 (moments), §10 (composition). No measurement is built; the rows are checked by reading replies (OPEN-ITEMS 16, 17).

- **Vocabulary round, v0.8 § T.** Two controls, each a typed set of positions. **Length:** `terse`, `normal`, `full`. **Tone:** `blunt`, `neutral`, `formal`, `dry`. Warm stays out: a study in round 4 §5 found warmth tuning raised agreement with wrong beliefs. An unknown position is refused at creation.
- **A new prompt source, `control`**, session-open (§10): one `PromptFragment` per control that is not at its default, its `provenance` naming the control and the position. `normal` and `neutral` are the defaults and write nothing, so a session that picks neither reads exactly as today.
- **Composition: the base text wins** (§10, design 1). A position narrows within the guidance level's rules and never overrides them; `full` means complete, not padded.
- **The texts**, one or two sentences each, the same on every driver:
  - `terse` — "Keep replies short: the answer and the facts it rests on. Leave out background, restatement and offers of more."
  - `full` — "Give complete replies: the reasoning, the alternatives you weighed, and what you left out. Complete is not padded; every sentence still carries a fact."
  - `blunt` — "Be blunt: state judgements plainly and name problems directly. Do not soften criticism, and hedge only where the evidence is uncertain."
  - `formal` — "Write in a formal register for readers who were not in this conversation: full sentences, no slang, each term defined on first use."
  - `dry` — "Keep the tone dry: understated and factual, without enthusiasm or exclamation."
- **The manifest and the API.** `SessionManifest` gains `length` and `tone` (null = default). `POST /api/session` accepts them; `PATCH` changes them and writes `SessionChanged` with the new fragment (§9, on change), on the path `bundle` and `per_turn` already use.

## checks

- Unit: each position writes exactly its text with provenance `{control, position}`; the defaults write nothing; an unknown position is refused; a PATCH writes `SessionChanged` and the cohort keeps the newest `control` fragment per control.
- Live (opt-in, as K293): one real driver, the same question under `terse` and `full`, and under `blunt` and `formal`; the replies are read and quoted in the result, not scored.

## result

- **Built.** `session/vocabulary.py`: `PromptSource.CONTROL` (session-open, on the system channel), `Control`, `LengthPosition`, `TonePosition`, the defaults and `LENGTH_TEXTS` / `TONE_TEXTS` with the texts above. `session_prompt_producer.py`: `control_fragments`, a `control` source when the session names either control. `SessionStarted.length` / `.tone`; `SessionSettings` folds them (a record before v0.8 counts as normal and neutral); the model step's change check and `_REWRITTEN_ON_CHANGE` include both. `SessionManifest.length` / `.tone`, refused when unknown at `create` and `set_controls`. Vocabulary v0.8 § T, signed.
- **Also built.** A rewrite that leaves a source with no text writes one empty fragment of that source (`provenance.cleared`), so the old text stops. Before, a source rewritten to nothing kept its old text: a bundle switched to one without a style kept the first bundle's style, and a cleared reminder line stayed. The K274 test now expects the cleared `bundle_style`.
- **Tests.** `test_length_tone_controls_296.py` 6/6. The vocabulary pins (`test_session_prompt_vocabulary_v02.py`) add `control`. The bundled `daily` and `session` records regenerated; the other 16 untouched. Kernel suite 1,470 passed, 12 skipped.
- **Live** (`test_length_tone_live_296.py`, opt-in), `kimi-k2.7-code:cloud`, one question about when a team of three should write tests: terse 115 words, full 288, blunt 146, formal 353. Each position read as its text says. The model turned words of the texts into headings: terse opened a "Facts:" list; full used "Reasoning", "Alternatives weighed" and "What I left out" as headings. The wording is the Architect's to judge.

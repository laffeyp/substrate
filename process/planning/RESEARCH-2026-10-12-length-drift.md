# EXPERIMENT: does a Length change made mid-session hold?

*2026-10-12. Asked by the Architect after U161 (guidance, length and tone changed mid-session): measure the effect, at the least effort that answers it. Script `scripts/experiments/length_drift.py`; tables `scripts/experiments/length_drift_report.py`; every reply, its word count and text, in this folder's `*.jsonl` (kept for the language measures to come).*

## Design

Two cloud models (`glm-5.2:cloud`, `kimi-k2.7-code:cloud`). Each session asks the same ten "Explain …" questions in the same order, one per turn, through the kernel's session topology with the `standard` guidance bundle (the level a large model gets) and no tools. Five arms, six sessions each per model, 600 turns:

| Arm | Length |
|---|---|
| `normal` | normal throughout |
| `terse` | terse throughout |
| `n2t@2` | normal, changed to terse before turn 2 |
| `n2t@5` | normal, changed to terse before turn 5 |
| `t2n@5` | terse, changed to normal before turn 5 |

A change is a `SessionChanged` before that turn: the new text replaces the old in the system text and a line ("Environment update: length changed from normal to terse.") sits beside that turn's message (§ P.4, § T.3).

## Results

### glm-5.2:cloud

Mean words per reply (± 95% interval), by turn. Sessions per arm: normal 6, terse 6, n2t@2 6, n2t@5 6, t2n@5 6.

| Turn | normal | terse | n2t@2 | n2t@5 | t2n@5 |
|---|---|---|---|---|---|
| 0 | 485 ± 132 | 352 ± 60 | 565 ± 155 | 431 ± 49 | 387 ± 93 |
| 1 | 545 ± 128 | 463 ± 107 | 504 ± 110 | 440 ± 99 | 434 ± 138 |
| 2 | 522 ± 167 | 495 ± 132 | 291 ± 56 | 445 ± 116 | 405 ± 112 |
| 3 | 506 ± 88 | 524 ± 108 | 377 ± 118 | 479 ± 64 | 480 ± 121 |
| 4 | 665 ± 138 | 682 ± 148 | 663 ± 199 | 725 ± 141 | 685 ± 125 |
| 5 | 345 ± 77 | 381 ± 89 | 329 ± 62 | 247 ± 54 | 348 ± 83 |
| 6 | 620 ± 160 | 695 ± 257 | 603 ± 105 | 653 ± 147 | 630 ± 157 |
| 7 | 489 ± 51 | 480 ± 72 | 425 ± 85 | 450 ± 72 | 477 ± 86 |
| 8 | 498 ± 174 | 602 ± 160 | 455 ± 112 | 478 ± 82 | 508 ± 134 |
| 9 | 325 ± 77 | 337 ± 66 | 285 ± 30 | 288 ± 58 | 368 ± 150 |

Each arm as a fraction of `normal` at the same turn, over the turns after a change (from turn 5 for the fixed arms), and the slope of that fraction per turn (positive: drifting toward normal).

| Arm | Turns | Fraction of normal | Slope per turn |
|---|---|---|---|
| terse | 5–9 | 1.09 | -0.005 |
| n2t@2 | 2–9 | 0.86 | +0.032 |
| n2t@5 | 5–9 | 0.91 | +0.025 |
| t2n@5 | 5–9 | 1.03 | +0.025 |

### kimi-k2.7-code:cloud

Mean words per reply (± 95% interval), by turn. Sessions per arm: normal 6, terse 6, n2t@2 6, n2t@5 6, t2n@5 6.

| Turn | normal | terse | n2t@2 | n2t@5 | t2n@5 |
|---|---|---|---|---|---|
| 0 | 184 ± 13 | 189 ± 52 | 194 ± 12 | 211 ± 33 | 191 ± 35 |
| 1 | 273 ± 94 | 278 ± 36 | 297 ± 40 | 295 ± 79 | 259 ± 42 |
| 2 | 154 ± 31 | 151 ± 35 | 155 ± 48 | 129 ± 23 | 154 ± 29 |
| 3 | 198 ± 50 | 184 ± 46 | 200 ± 35 | 200 ± 53 | 180 ± 14 |
| 4 | 212 ± 33 | 213 ± 52 | 207 ± 45 | 228 ± 54 | 207 ± 47 |
| 5 | 176 ± 32 | 175 ± 47 | 173 ± 34 | 138 ± 28 | 141 ± 35 |
| 6 | 245 ± 47 | 245 ± 29 | 237 ± 37 | 256 ± 46 | 239 ± 22 |
| 7 | 215 ± 47 | 232 ± 41 | 187 ± 39 | 216 ± 40 | 202 ± 33 |
| 8 | 200 ± 30 | 240 ± 51 | 201 ± 37 | 229 ± 50 | 205 ± 28 |
| 9 | 161 ± 39 | 170 ± 54 | 147 ± 45 | 133 ± 53 | 145 ± 30 |

Each arm as a fraction of `normal` at the same turn, over the turns after a change (from turn 5 for the fixed arms), and the slope of that fraction per turn (positive: drifting toward normal).

| Arm | Turns | Fraction of normal | Slope per turn |
|---|---|---|---|
| terse | 5–9 | 1.07 | +0.032 |
| n2t@2 | 2–9 | 0.97 | -0.012 |
| n2t@5 | 5–9 | 0.96 | +0.019 |
| t2n@5 | 5–9 | 0.93 | +0.025 |


## What the data says

1. **`terse` does nothing measurable here.** Sessions terse from the first turn ran at 1.09 (glm) and 1.07 (kimi) of normal's length over turns 5–9, and inside normal's interval at every turn. The text does reach the model: a stand-in driver received it in the prompt with and without the `standard` bundle, and Ollama receives it on its system channel. The question is then not whether a change holds but whether the setting works at all, and on explanation questions under the `standard` bundle it does not. K296's live test missed this: it compared terse with full (115 against 288 words, one reply each), never with normal.
2. **The question moves length more than the setting does.** Turn 4 and turn 6 run long and turn 9 short in every arm; the spread between turns (glm 325–665 words in the normal arm) is larger than any arm's difference.
3. **A change shows on the turn it is made, then fades.** On the change turn, normal-to-terse sessions were shorter than normal in three of four cases (glm `n2t@2` turn 2: 291 ± 56 against 522 ± 167; glm `n2t@5` turn 5: 247 ± 54 against 345 ± 77; kimi `n2t@5` turn 5: 138 ± 28 against 176 ± 32; kimi `n2t@2` turn 2: 155 against 154, no drop). By the next turn they were back inside normal's interval. On kimi a change the other way, terse to normal, also gave a shorter reply on its turn (141 ± 35 against 176 ± 32). Read together: the drop follows the fresh change line, whatever it says, more than the instruction; with six sessions an arm these are signs, not settled effects.
4. **So the drift seen in the app's live check (133, 75, then 185 words) is this pattern:** a short reply on the change turn, then the old length.

## What it means for the controls

- The `terse` text is too weak to move a reply against a question that asks for an explanation, at the `standard` level, on these models. The texts need rework before drift can be measured; the measure here (words, against a normal arm, per turn) stays.
- The change line beside the message has an effect of its own, short-lived and not tied to the direction of the change.

## Limits

Six sessions an arm, two models, one question set of one kind (explanations), one guidance level, no tools, temperature at the models' defaults. Intervals are t-intervals on six values. Word count is the only measure.

## Next, when the work resumes

- A stronger `terse` text, checked first as terse-from-start against normal, before any drift run.
- The same five arms with `full`, which may move further than `terse` does.
- The language measures (research rounds 1–4 of 2026-10-10) can run on the saved texts.

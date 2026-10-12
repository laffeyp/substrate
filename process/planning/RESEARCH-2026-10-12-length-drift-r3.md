# RESEARCH: does a Length change made mid-session hold? (round 3)

*2026-10-12, round 3, sprint K301. Rounds 1 and 2 ran on a kernel that delivered every change a message late (`POSTMORTEM-2026-10-12-mid-session-changes-arrive-late-r3.md`). This round runs the same design on the fixed kernel (`6d2d5114`, K299), where the prompt for the message after a change carries the new text (checked by K300's tests and U167's gate). Round 2's reading still holds: word count on explanation questions under the high guidance level measures the content's own length as much as any padding, so it is a weak measure of terseness. Data: `process/runs/assays/length_drift_2026-10-12_k299/` (600 replies with their texts). Script and tables: `scripts/assay_length_drift.py`, `scripts/assay_length_drift_report.py`.*

## Design

As in round 1: `glm-5.2:cloud` and `kimi-k2.7-code:cloud`; ten "Explain …" questions in a fixed order; the `standard` bundle (high level); no tools; six sessions in each of five arms: `normal`, `terse`, `n2t@2` and `n2t@5` (normal, changed to terse before turn 2 or 5), `t2n@5` (terse, changed to normal before turn 5).

## Results

### glm-5.2:cloud

Mean words per reply (± 95% interval), by turn. Sessions per arm: normal 6, terse 6, n2t@2 6, n2t@5 6, t2n@5 6.

| Turn | normal | terse | n2t@2 | n2t@5 | t2n@5 |
|---|---|---|---|---|---|
| 0 | 376 ± 95 | 432 ± 67 | 472 ± 105 | 515 ± 87 | 422 ± 59 |
| 1 | 386 ± 104 | 539 ± 185 | 445 ± 85 | 526 ± 114 | 431 ± 75 |
| 2 | 344 ± 91 | 404 ± 69 | 382 ± 39 | 563 ± 123 | 396 ± 59 |
| 3 | 441 ± 87 | 502 ± 146 | 409 ± 108 | 555 ± 89 | 430 ± 100 |
| 4 | 625 ± 124 | 655 ± 176 | 763 ± 140 | 933 ± 145 | 629 ± 225 |
| 5 | 348 ± 62 | 355 ± 94 | 311 ± 49 | 294 ± 76 | 321 ± 58 |
| 6 | 668 ± 177 | 651 ± 229 | 626 ± 109 | 746 ± 202 | 618 ± 106 |
| 7 | 448 ± 57 | 484 ± 125 | 478 ± 79 | 523 ± 125 | 474 ± 89 |
| 8 | 505 ± 167 | 501 ± 117 | 511 ± 130 | 608 ± 197 | 478 ± 134 |
| 9 | 373 ± 46 | 333 ± 102 | 316 ± 101 | 337 ± 76 | 338 ± 70 |

Each arm as a fraction of `normal` at the same turn, over the turns after a change (from turn 5 for the fixed arms), and the slope of that fraction per turn (positive: drifting toward normal).

| Arm | Turns | Fraction of normal | Slope per turn |
|---|---|---|---|
| terse | 5–9 | 0.99 | -0.024 |
| n2t@2 | 2–9 | 1.00 | -0.022 |
| n2t@5 | 5–9 | 1.05 | +0.021 |
| t2n@5 | 5–9 | 0.95 | -0.001 |

### kimi-k2.7-code:cloud

Mean words per reply (± 95% interval), by turn. Sessions per arm: normal 6, terse 6, n2t@2 6, n2t@5 6, t2n@5 6.

| Turn | normal | terse | n2t@2 | n2t@5 | t2n@5 |
|---|---|---|---|---|---|
| 0 | 185 ± 17 | 190 ± 22 | 206 ± 28 | 198 ± 22 | 171 ± 10 |
| 1 | 270 ± 75 | 256 ± 53 | 245 ± 54 | 232 ± 34 | 235 ± 66 |
| 2 | 166 ± 30 | 128 ± 52 | 115 ± 31 | 167 ± 75 | 125 ± 25 |
| 3 | 211 ± 51 | 206 ± 25 | 206 ± 46 | 197 ± 28 | 209 ± 42 |
| 4 | 246 ± 27 | 241 ± 51 | 224 ± 31 | 265 ± 82 | 222 ± 67 |
| 5 | 190 ± 43 | 177 ± 34 | 145 ± 44 | 168 ± 52 | 166 ± 49 |
| 6 | 262 ± 46 | 238 ± 36 | 238 ± 50 | 242 ± 57 | 256 ± 62 |
| 7 | 250 ± 26 | 228 ± 39 | 190 ± 35 | 206 ± 20 | 194 ± 26 |
| 8 | 225 ± 35 | 230 ± 61 | 191 ± 37 | 219 ± 35 | 218 ± 38 |
| 9 | 168 ± 38 | 146 ± 29 | 125 ± 26 | 148 ± 50 | 167 ± 30 |

Each arm as a fraction of `normal` at the same turn, over the turns after a change (from turn 5 for the fixed arms), and the slope of that fraction per turn (positive: drifting toward normal).

| Arm | Turns | Fraction of normal | Slope per turn |
|---|---|---|---|
| terse | 5–9 | 0.93 | -0.001 |
| n2t@2 | 2–9 | 0.82 | -0.007 |
| n2t@5 | 5–9 | 0.90 | +0.005 |
| t2n@5 | 5–9 | 0.92 | +0.024 |


## What the data says

1. **glm does not move.** Terse from the start ran at 0.99 of normal; every switch arm ran at 0.95 to 1.05, inside normal's interval at every turn. Under the high level, on these questions, the length text changes nothing measurable on glm.
2. **kimi shortens, modestly.** Terse from the start ran at 0.93 of normal; normal to terse at turn 2 at 0.82, at turn 5 at 0.90. On the turn of the change kimi's replies drop (turn 2: 115 ± 31 against normal's 166 ± 30) and stay below normal on most later turns.
3. **No drift back is visible.** The slopes of the fraction of normal after a change run from -0.022 to +0.024 per turn, with intervals far wider than the slopes. A change made mid-session held as well as the same setting made at the start; on kimi, the change at turn 2 ran shorter than terse from the start, but the intervals overlap.
4. **A loosening does not fully undo.** On kimi, `t2n@5` stayed at 0.92 of normal after the change to normal, slope +0.024: the replies written terse earlier in the conversation may hold the length down. Six sessions an arm: a sign, not a finding.

## What it settles

- Delivery: settled by the fix and its checks, not by this data; this run is consistent with it (the change shows on its own turn).
- Effect: small and model-dependent under the high level on explanation questions; nothing here shows a mid-session change wearing off.
- The question round 2 left open, whether `terse` removes padding, still needs a padding measure from the language work.

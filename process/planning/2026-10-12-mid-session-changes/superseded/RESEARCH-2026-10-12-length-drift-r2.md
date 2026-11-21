# RESEARCH: does a Length change made mid-session hold? (round 2)

*2026-10-12, round 2. Round 1 (`RESEARCH-2026-10-12-length-drift.md`) concluded "`terse` does nothing measurable here." The Architect's reading: "if you are asking questions that require long answers and then scoring those answers as not terse, we have a problem … some things can't be made terse. Terse is an overall pattern." This round keeps round 1's data and corrects what it supports. Data: `process/runs/assays/length_drift_2026-10-12/` (600 replies with their texts). Script: `scripts/assay_length_drift.py`; tables: `scripts/assay_length_drift_report.py`.*

## What was run

Two cloud models (`glm-5.2:cloud`, `kimi-k2.7-code:cloud`); ten "Explain …" questions in a fixed order, one per turn; the `standard` guidance bundle (the high level); no tools; five arms of six sessions each: `normal` throughout, `terse` throughout, normal to terse before turn 2 (`n2t@2`) and before turn 5 (`n2t@5`), terse to normal before turn 5 (`t2n@5`). Round 1 holds the per-turn tables.

## What the data supports

- **Word count did not separate `terse` from `normal` under the high level on explanation questions.** Terse sessions ran at 1.09 (glm) and 1.07 (kimi) of normal's length over turns 5–9.
- **The question set the length.** In the normal arm, glm's means ran from 325 to 665 words by question; every arm rose and fell on the same turns.
- **A change shows on its own turn, then fades.** Three of four normal-to-terse changes gave a shorter reply on the change turn and none on the next; on kimi a terse-to-normal change did too. Six sessions an arm: signs, not settled effects.

## Why "terse does nothing" does not follow

1. **Terse is a pattern, not a length.** The `terse` text asks for "the answer and the facts it rests on" without "background, restatement and offers of more". An explanation's content has its own length; terse removes only what sits around it. Word count adds the two together, so it measures the question as much as the setting. The measure terse needs is the padding itself: restatement of the question, background before the answer, closing summaries, offers of more, hedges. That is a measure of the language, not of its length (research `RESEARCH-2026-10-10-language-metrics` rounds 1–4).
2. **The baseline was already terse.** The high level carries the operator's writing standard: every sentence carries a fact, no restatement, no closing summary, no offers. A normal session under it has little padding left for `terse` to cut, and by § T.2 the level's rules win where they meet the control's. The test measured a control against a baseline that already does the control's job.
3. **The questions left nothing to cut.** Ten explanations demand length. `terse` shows where elaboration is optional: yes/no questions, opinions, quick facts, follow-ups.

## What answers the question

- A padding measure from the language work, applied to the saved texts first, then to new runs.
- A mixed question set: explanations, yes/no questions, opinions, quick facts, follow-ups.
- A baseline where the guidance level does not already do the control's job (the `harness` level), beside the high level.
- The five arms as run here; word count kept as a second measure, read per question type.

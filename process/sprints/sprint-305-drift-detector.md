# Sprint 305 — The drift detector

```yaml
---
id: 305
status: closed
closed_at: 2026-10-13
phase: 1
pass_kind: research
roadmap: process/planning/ROADMAP-2026-10-12-language-measurement-r3.md
depends_on: [304]
context_files:
  - process/planning/RESEARCH-2026-10-10-language-metrics-r4.md
---
```

## scope

Page–Hinkley as Hinkley (1971) and its standard modern statement define it: both directions, warm-up and reset. Its defaults for δ, λ and warm-up come from synthetic series, not from sessions.

## observation contract

On synthetic series, a table of false-alarm rate (no change), detection delay (planted steps of known size) and the behaviour on slow drift, against δ and λ. The chosen defaults are read from that table and stored as parameters.

## checks

Tests on series with a known answer; ruff, mypy --strict.

## result

- **Built.** `src/substrate/language/drift.py`: `PageHinkley` (both directions together, warm-up, restart after an alarm, δ and λ in standard deviations of the warm-up values, no forgetting factor), `detect`, `trajectory`, `DEFAULT_DRIFT`.
- **Checked against river 0.26.1** `PageHinkley(alpha=1.0, mode="up")` on x and on −x: the first alarm falls on the same value in 600 of 600 comparisons. Flipping the sign of δ in the down statistic fails the comparison. river added to the dev dependencies (it installs only its own package).
- **Table** (`docs/language/drift.md`, `scripts/language_drift_table.py`, 4,000 N(0, 1) series per cell): false-alarm rate over 50 and 200 values; detection rate and median delay for 0.5, 1 and 2 SD steps and a 2 SD ramp; δ 0.05–0.5, λ 3–16, warm-up 5, 10, 20.
- **Defaults: δ 0.25, λ 10, warm-up 20,** by the rule fixed in the script before the table was read (most 1 SD steps found among settings with ≤ 5% false alarms over 50 values). False alarms 0.040 over 50 values, 0.253 over 200; 1 SD step found 74% of the time within 25 values (median delay 12), 2 SD 100% (5), 0.5 SD 22%, a 2 SD ramp 32%.
- **The grid grew once.** The first run (1,000 series, warm-up 5 and 10, λ to 12) chose δ 0.5, λ 8, warm-up 10 at a false-alarm rate of exactly 0.050, inside that run's noise; the grid then added warm-up 20 and λ 10 and 16 at 4,000 series. The rule did not change.
- **Rules the table sets** (`docs/language/drift-r2.md`): a 20-value warm-up (5 values estimate the SD too low); the detector watches one stream's series across session boundaries, or a many-values-per-reply series such as sentence lengths; slow ramps are found up to 32% of the time, since the running mean follows them.
- **Tests** `tests/test_language_drift_305.py`, 6: river agreement both ways; first alarm equals the first crossing and restarts need a new warm-up; no test before the warm-up; a drop raises a down alarm; the defaults stay quiet on 50 seeded N(0, 1) values and catch a 3 SD step within 15 values; a warm-up under 2 is refused with the value named. One case I first wrote used λ 5, warm-up 10, whose false-alarm rate is 49%; it raised a true false alarm before the step and was moved to the defaults.

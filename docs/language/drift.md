# The drift detector: Page–Hinkley on synthetic series

*2026-10-13, sprint 305. `src/substrate/language/drift.py`; table by `scripts/language_drift_table.py` (4,000 series per cell, seeds fixed per setting); tests `tests/test_language_drift_305.py`.*

## The test

Page (1954) and Hinkley (1971), in the incremental form MOA and river implement: with x̄ₜ the mean so far, the up statistic is mₜ − min mₖ for mₜ = Σ (xᵢ − x̄ᵢ − δ), the down statistic is max nₖ − nₜ for nₜ = Σ (xᵢ − x̄ᵢ + δ), and either above λ raises an alarm. Both directions run together; after an alarm the detector starts again. δ and λ are in standard deviations of the first `warmup` values (the sample SD), as CUSUM designs state k and h; no test is made before the warm-up ends. There is no forgetting factor.

**Checked against river 0.26.1** (`PageHinkley(alpha=1.0, mode="up")`, run on x / SD for the up test and on −x / SD for the down test): the first alarm falls on the same value in 600 of 600 comparisons over 300 series. River's own down test starts its maximum at −1 rather than at the first value, so the down direction is compared through the negated series. Changing the sign of δ in the down statistic fails the comparison.

## How the defaults were chosen

The rule, written into the script before the table was read: among settings whose false-alarm rate over 50 values with no change is at most 0.05, take the one that finds the most 1 SD steps within 25 values; ties go to the shorter median delay, then the longer warm-up.

The first run (1,000 series per cell, warm-ups 5 and 10, λ up to 12) chose δ 0.5, λ 8, warm-up 10, with a false-alarm rate of 0.050: on the line, inside the run's noise (standard error about 0.007). The grid then grew to warm-up 20 and λ 10 and 16, at 4,000 series per cell; the rule did not change.

**Chosen: δ = 0.25, λ = 10, warm-up 20** (`DEFAULT_DRIFT`). False alarms over 50 values 0.040 (standard error 0.003), over 200 values 0.253. A 1 SD step is found within 25 values 74% of the time, median delay 12; a 2 SD step 100%, median 5; a 0.5 SD step 22%; a ramp of 2 SD over 50 values 32%.

## What the table says beyond the defaults

- **The warm-up SD is the weak point.** With 5 warm-up values only δ 0.5, λ 16 keeps false alarms over 50 values under 0.05 (0.032), and it finds 1 SD steps 0.24 of the time (median delay 12); an SD estimated from five values is often too small, which inflates every scaled deviation.
- **Slow drift is mostly absorbed.** The running mean follows a ramp, so no setting that passes the false-alarm rule finds more than about a third of 2 SD ramps within 25 values, as round 4 says.
- **A 20-value warm-up excludes most sessions recorded so far.** Of the 73 recorded sessions with model replies, 3 have 20 or more (median 2, largest 33). A series of one value per turn gets no test in a typical session; a series of sentence lengths, many per reply, does. Which series the detector watches is the build phase's choice (B2).

## The table

δ and λ in warm-up SDs. Change columns: detection rate (median delay in values).

| warm-up | δ | λ | false alarms, 50 | false alarms, 200 | 0.5 SD step | 1 SD step | 2 SD step | 2 SD ramp |
|---|---|---|---|---|---|---|---|---|
| 5 | 0.05 | 3 | 0.989 | 1.000 | 0.08 (4) | 0.08 (3) | 0.08 (1) | 0.08 (7) |
| 5 | 0.05 | 5 | 0.873 | 0.995 | 0.31 (6) | 0.37 (4) | 0.37 (2) | 0.33 (10) |
| 5 | 0.05 | 8 | 0.577 | 0.933 | 0.48 (9) | 0.68 (6) | 0.72 (3) | 0.54 (14) |
| 5 | 0.05 | 10 | 0.403 | 0.833 | 0.48 (11) | 0.76 (8) | 0.83 (4) | 0.55 (16) |
| 5 | 0.05 | 12 | 0.301 | 0.752 | 0.41 (12) | 0.77 (10) | 0.88 (5) | 0.52 (17) |
| 5 | 0.05 | 16 | 0.155 | 0.548 | 0.29 (13) | 0.65 (13) | 0.95 (7) | 0.36 (18) |
| 5 | 0.1 | 3 | 0.968 | 0.999 | 0.13 (5) | 0.14 (3) | 0.14 (1) | 0.13 (9) |
| 5 | 0.1 | 5 | 0.786 | 0.971 | 0.34 (7) | 0.45 (5) | 0.45 (2) | 0.39 (12) |
| 5 | 0.1 | 8 | 0.482 | 0.833 | 0.46 (10) | 0.70 (7) | 0.77 (3) | 0.54 (16) |
| 5 | 0.1 | 10 | 0.336 | 0.699 | 0.41 (12) | 0.74 (9) | 0.85 (4) | 0.49 (17) |
| 5 | 0.1 | 12 | 0.235 | 0.610 | 0.35 (12) | 0.72 (10) | 0.91 (5) | 0.44 (17) |
| 5 | 0.1 | 16 | 0.126 | 0.405 | 0.23 (14) | 0.60 (13) | 0.95 (8) | 0.29 (19) |
| 5 | 0.25 | 3 | 0.846 | 0.968 | 0.23 (7) | 0.32 (4) | 0.33 (1) | 0.27 (12) |
| 5 | 0.25 | 5 | 0.548 | 0.799 | 0.36 (8) | 0.57 (6) | 0.64 (2) | 0.44 (15) |
| 5 | 0.25 | 8 | 0.292 | 0.538 | 0.32 (10.5) | 0.66 (8) | 0.84 (4) | 0.41 (17) |
| 5 | 0.25 | 10 | 0.201 | 0.406 | 0.27 (11) | 0.63 (10) | 0.91 (5) | 0.36 (18) |
| 5 | 0.25 | 12 | 0.140 | 0.323 | 0.21 (13) | 0.57 (11) | 0.93 (6) | 0.29 (18) |
| 5 | 0.25 | 16 | 0.070 | 0.190 | 0.14 (14) | 0.41 (13) | 0.92 (8) | 0.18 (19) |
| 5 | 0.5 | 3 | 0.592 | 0.786 | 0.26 (7) | 0.45 (5) | 0.56 (2) | 0.33 (14) |
| 5 | 0.5 | 5 | 0.325 | 0.537 | 0.25 (8) | 0.53 (7) | 0.79 (3) | 0.34 (17) |
| 5 | 0.5 | 8 | 0.150 | 0.293 | 0.18 (10) | 0.47 (9) | 0.89 (5) | 0.25 (18) |
| 5 | 0.5 | 10 | 0.099 | 0.201 | 0.13 (11) | 0.41 (10) | 0.89 (6) | 0.18 (18) |
| 5 | 0.5 | 12 | 0.062 | 0.160 | 0.10 (12) | 0.32 (11) | 0.86 (7) | 0.15 (19) |
| 5 | 0.5 | 16 | 0.032 | 0.092 | 0.07 (12) | 0.24 (12) | 0.77 (10) | 0.10 (19) |
| 10 | 0.05 | 3 | 0.996 | 1.000 | 0.06 (3) | 0.06 (2) | 0.06 (1) | 0.06 (5) |
| 10 | 0.05 | 5 | 0.897 | 1.000 | 0.35 (6) | 0.38 (3) | 0.39 (1) | 0.37 (10) |
| 10 | 0.05 | 8 | 0.532 | 0.947 | 0.59 (10) | 0.80 (6) | 0.80 (3) | 0.66 (14) |
| 10 | 0.05 | 10 | 0.334 | 0.867 | 0.56 (12) | 0.87 (8) | 0.92 (4) | 0.64 (16) |
| 10 | 0.05 | 12 | 0.207 | 0.754 | 0.46 (13) | 0.86 (10) | 0.97 (5) | 0.54 (18) |
| 10 | 0.05 | 16 | 0.062 | 0.499 | 0.23 (16) | 0.69 (14) | 0.99 (7) | 0.32 (20) |
| 10 | 0.1 | 3 | 0.987 | 1.000 | 0.11 (4) | 0.11 (2) | 0.11 (1) | 0.10 (6) |
| 10 | 0.1 | 5 | 0.797 | 0.991 | 0.43 (7) | 0.49 (4) | 0.49 (2) | 0.45 (11) |
| 10 | 0.1 | 8 | 0.403 | 0.862 | 0.54 (10) | 0.82 (7) | 0.86 (3) | 0.63 (15) |
| 10 | 0.1 | 10 | 0.223 | 0.703 | 0.47 (12) | 0.86 (9) | 0.94 (4) | 0.56 (18) |
| 10 | 0.1 | 12 | 0.135 | 0.558 | 0.36 (13) | 0.80 (11) | 0.98 (5) | 0.45 (19) |
| 10 | 0.1 | 16 | 0.042 | 0.331 | 0.18 (15) | 0.62 (14) | 0.99 (8) | 0.23 (20) |
| 10 | 0.25 | 3 | 0.875 | 0.992 | 0.29 (5) | 0.34 (3) | 0.33 (1) | 0.30 (10) |
| 10 | 0.25 | 5 | 0.489 | 0.849 | 0.46 (9) | 0.70 (5) | 0.75 (2) | 0.56 (15) |
| 10 | 0.25 | 8 | 0.185 | 0.493 | 0.37 (12) | 0.78 (9) | 0.94 (4) | 0.47 (18) |
| 10 | 0.25 | 10 | 0.088 | 0.329 | 0.24 (14) | 0.69 (11) | 0.98 (5) | 0.35 (19) |
| 10 | 0.25 | 12 | 0.048 | 0.198 | 0.17 (15.5) | 0.58 (13) | 0.99 (6) | 0.24 (20) |
| 10 | 0.25 | 16 | 0.013 | 0.092 | 0.07 (17) | 0.36 (15) | 0.97 (9) | 0.11 (21) |
| 10 | 0.5 | 3 | 0.549 | 0.841 | 0.35 (7) | 0.60 (5) | 0.69 (1) | 0.47 (14) |
| 10 | 0.5 | 5 | 0.208 | 0.478 | 0.28 (9) | 0.67 (7) | 0.92 (3) | 0.39 (17) |
| 10 | 0.5 | 8 | 0.051 | 0.178 | 0.13 (11) | 0.50 (10) | 0.97 (5) | 0.21 (19) |
| 10 | 0.5 | 10 | 0.025 | 0.083 | 0.09 (12) | 0.38 (12) | 0.96 (7) | 0.13 (20) |
| 10 | 0.5 | 12 | 0.013 | 0.050 | 0.05 (15) | 0.29 (13) | 0.93 (8) | 0.08 (20) |
| 10 | 0.5 | 16 | 0.003 | 0.017 | 0.02 (15) | 0.14 (16) | 0.81 (11) | 0.04 (20) |
| 20 | 0.05 | 3 | 0.998 | 1.000 | 0.09 (2) | 0.10 (1) | 0.10 (0) | 0.10 (4) |
| 20 | 0.05 | 5 | 0.911 | 1.000 | 0.45 (5) | 0.49 (3) | 0.49 (1) | 0.47 (8) |
| 20 | 0.05 | 8 | 0.516 | 0.973 | 0.67 (9) | 0.86 (6) | 0.87 (3) | 0.74 (14) |
| 20 | 0.05 | 10 | 0.278 | 0.898 | 0.60 (12) | 0.93 (8) | 0.97 (4) | 0.68 (17) |
| 20 | 0.05 | 12 | 0.141 | 0.768 | 0.45 (14) | 0.90 (10.5) | 0.99 (5) | 0.57 (19) |
| 20 | 0.05 | 16 | 0.032 | 0.481 | 0.21 (17) | 0.70 (15) | 1.00 (7) | 0.30 (21) |
| 20 | 0.1 | 3 | 0.990 | 1.000 | 0.19 (3) | 0.18 (2) | 0.18 (1) | 0.19 (4) |
| 20 | 0.1 | 5 | 0.798 | 0.998 | 0.54 (6) | 0.61 (3) | 0.62 (1) | 0.58 (11) |
| 20 | 0.1 | 8 | 0.349 | 0.888 | 0.62 (11) | 0.90 (7) | 0.93 (3) | 0.72 (16) |
| 20 | 0.1 | 10 | 0.171 | 0.713 | 0.50 (13) | 0.90 (9) | 0.98 (4) | 0.59 (18) |
| 20 | 0.1 | 12 | 0.082 | 0.547 | 0.36 (15) | 0.84 (12) | 1.00 (5) | 0.45 (20) |
| 20 | 0.1 | 16 | 0.021 | 0.275 | 0.14 (18) | 0.60 (15) | 1.00 (8) | 0.20 (21) |
| 20 | 0.25 | 3 | 0.869 | 0.997 | 0.46 (5) | 0.52 (3) | 0.53 (1) | 0.49 (9) |
| 20 | 0.25 | 5 | 0.427 | 0.887 | 0.57 (8) | 0.85 (5) | 0.86 (2) | 0.67 (15) |
| 20 | 0.25 | 8 | 0.105 | 0.442 | 0.35 (12) | 0.84 (9) | 0.99 (4) | 0.48 (18) |
| 20 | 0.25 | 10 | 0.040 | 0.253 | 0.22 (15) | 0.74 (12) | 1.00 (5) | 0.32 (20) |
| 20 | 0.25 | 12 | 0.015 | 0.127 | 0.12 (16) | 0.59 (14) | 1.00 (7) | 0.20 (21) |
| 20 | 0.25 | 16 | 0.003 | 0.032 | 0.04 (18) | 0.32 (17) | 0.99 (10) | 0.07 (21) |
| 20 | 0.5 | 3 | 0.465 | 0.878 | 0.53 (7) | 0.80 (4) | 0.86 (1) | 0.65 (14) |
| 20 | 0.5 | 5 | 0.112 | 0.419 | 0.28 (9) | 0.74 (7) | 0.98 (3) | 0.43 (18) |
| 20 | 0.5 | 8 | 0.017 | 0.092 | 0.10 (13) | 0.48 (12) | 1.00 (5) | 0.15 (20) |
| 20 | 0.5 | 10 | 0.006 | 0.027 | 0.04 (15) | 0.32 (13) | 0.99 (7) | 0.09 (21) |
| 20 | 0.5 | 12 | 0.001 | 0.013 | 0.02 (16.5) | 0.20 (15) | 0.96 (9) | 0.04 (21) |
| 20 | 0.5 | 16 | 0.000 | 0.002 | 0.00 (17) | 0.08 (17) | 0.85 (12) | 0.01 (21) |


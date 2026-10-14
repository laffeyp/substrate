# Window minimums for the language measures (round 2)

*2026-10-13, sprint 306, round 2. Round 1 (`windows.md`) followed the table with a list of what the minimums "mean"; this round replaces it with the rule they set. `scripts/language_window_minimums.py`; constants in `src/substrate/language/measures.py` (`MIN_*`); applied by `profile` and `relation.lsm` from library 0.2.0; tests `tests/test_language_windows_306.py`. Library 0.1.0 (`measures.md`) reported every measure at any length.*

## The criterion

Fixed in the script before anything was measured. A window of n is long enough when, over many windows of that length, (a) the mean is within 5% of the reference value (0.05 for measures bounded near [−1, 1]: burstiness, LSM, DFA alpha), and (b) the standard deviation across windows is at most 10% of the reference (0.05 for the bounded measures). The minimum is the shortest length on the grid (25 to 3,200) meeting both. References: 6,400-word windows of real text; alpha 0.5 for DFA on white noise; the population B of random (geometric) gaps for burstiness.

Text: the 600 length-experiment replies, each model's joined in order (142,300 and 60,039 words) and cut into contiguous windows, at most 200 per length.

## Minimums

| Measure | Minimum | Basis |
|---|---|---|
| MTLD | 100 words | sourced: Koizumi & In'nami 2012 |
| MATTR, HD-D | the window (100), the draws (42) | definition |
| Size, rhythm, format, lexicon rates | one text | definition |
| Heaps beta | 800 words | measured |
| LSM | 1,600 words in each text | measured |
| Unigram entropy | 3,200 words | measured |
| Zipf alpha | 3,200 words | measured |
| DFA alpha | 400 sentences | measured on white noise |
| Burstiness | words with 20 or more occurrences | measured on random gaps |
| Compression ratio | none | measured: still falling at 3,200 words (0.359, against 0.326 at 6,400); compare only equal lengths |

## The rule

Each measure runs over a trailing window of text at least as long as its minimum: the latest texts of one stream (the user's, or the model's), joined, back far enough to reach it, across session boundaries when one session is shorter. Values are compared at equal window lengths, and the window length is stored beside every value. Measures whose minimum is one text run on each text.

## The measurements

### Compression ratio

Reference: mean 0.3264 over 31 windows of 6400 words.

| words | windows | mean | SD | meets both |
|---|---|---|---|---|
| 25 | 200 | 0.7239 | 0.0340 | no |
| 50 | 200 | 0.5983 | 0.0310 | no |
| 100 | 200 | 0.5194 | 0.0274 | no |
| 200 | 200 | 0.4695 | 0.0244 | no |
| 400 | 200 | 0.4321 | 0.0237 | no |
| 800 | 200 | 0.4054 | 0.0168 | no |
| 1600 | 125 | 0.3842 | 0.0125 | no |
| 3200 | 62 | 0.3586 | 0.0132 | no |

Minimum: none on the grid.

### Unigram entropy

Reference: mean 8.4823 over 31 windows of 6400 words.

| words | windows | mean | SD | meets both |
|---|---|---|---|---|
| 25 | 200 | 4.2788 | 0.2078 | no |
| 50 | 200 | 5.0233 | 0.2184 | no |
| 100 | 200 | 5.7108 | 0.2199 | no |
| 200 | 200 | 6.3258 | 0.2202 | no |
| 400 | 200 | 6.8487 | 0.1972 | no |
| 800 | 200 | 7.3692 | 0.1694 | no |
| 1600 | 125 | 7.8859 | 0.1496 | no |
| 3200 | 62 | 8.2496 | 0.0901 | yes |

Minimum: 3200.

### Zipf alpha

Reference: mean 1.6709 over 31 windows of 6400 words.

| words | windows | mean | SD | meets both |
|---|---|---|---|---|
| 25 | 200 | 2.2423 | 0.0971 | no |
| 50 | 200 | 2.1526 | 0.0892 | no |
| 100 | 200 | 2.0736 | 0.0680 | no |
| 200 | 200 | 2.0011 | 0.0574 | no |
| 400 | 200 | 1.9319 | 0.0484 | no |
| 800 | 200 | 1.8797 | 0.0324 | no |
| 1600 | 125 | 1.8251 | 0.0228 | no |
| 3200 | 62 | 1.7541 | 0.0283 | yes |

Minimum: 3200.

### Heaps beta

Reference: mean 0.7719 over 31 windows of 6400 words.

| words | windows | mean | SD | meets both |
|---|---|---|---|---|
| 25 | 200 | 0.8927 | 0.1247 | no |
| 50 | 200 | 0.8701 | 0.0859 | no |
| 100 | 200 | 0.8534 | 0.0589 | no |
| 200 | 200 | 0.8391 | 0.0442 | no |
| 400 | 200 | 0.8176 | 0.0368 | no |
| 800 | 200 | 0.8082 | 0.0276 | yes |
| 1600 | 125 | 0.8022 | 0.0227 | yes |
| 3200 | 62 | 0.7890 | 0.0203 | yes |

Minimum: 800.

### LSM between two texts of one writer

Pairs of consecutive windows from one model's replies. Reference: mean 0.9601 over 15 pairs of 6400-word windows.

| words per text | pairs | mean | SD | meets both |
|---|---|---|---|---|
| 25 | 100 | 0.5697 | 0.1459 | no |
| 50 | 100 | 0.6126 | 0.1270 | no |
| 100 | 100 | 0.6937 | 0.1000 | no |
| 200 | 100 | 0.7495 | 0.0756 | no |
| 400 | 100 | 0.8066 | 0.0619 | no |
| 800 | 100 | 0.8622 | 0.0409 | no |
| 1600 | 62 | 0.9103 | 0.0255 | yes |
| 3200 | 31 | 0.9326 | 0.0207 | yes |

Minimum: 1600.

### DFA alpha

White noise (true alpha 0.5), 200 series per length; length is the number of values (sentences).

| values | series | mean | SD | meets both |
|---|---|---|---|---|
| 25 | 200 | 0.6930 | 0.4248 | no |
| 50 | 200 | 0.6151 | 0.1590 | no |
| 100 | 200 | 0.5593 | 0.0919 | no |
| 200 | 200 | 0.5340 | 0.0588 | no |
| 400 | 200 | 0.5238 | 0.0465 | yes |
| 800 | 200 | 0.5192 | 0.0361 | yes |
| 1600 | 200 | 0.5112 | 0.0284 | yes |
| 3200 | 200 | 0.5088 | 0.0238 | yes |

Minimum: 400.

### Burstiness of one word

Occurrences at random (Bernoulli, p = 0.02); the population B of those gaps is -0.0051. 2,000 words per count. Only the bias test applies: a mean over many words, not one word's B, is what a profile reports, so one word's spread is shown but not judged.

| occurrences | mean B | SD | bias within 0.05 |
|---|---|---|---|
| 3 | -0.4051 | 0.2848 | no |
| 5 | -0.1932 | 0.1845 | no |
| 10 | -0.0949 | 0.1270 | no |
| 20 | -0.0523 | 0.0945 | yes |
| 40 | -0.0283 | 0.0704 | yes |
| 80 | -0.0162 | 0.0531 | yes |

Minimum: 20 occurrences.


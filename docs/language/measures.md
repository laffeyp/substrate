# Language measures, library 0.1.0

*2026-10-13, sprint 304. The measures in `src/substrate/language/`, each with its source, the published implementation it is checked against, and the agreement found. All run on substrate-text-1 (`substrate-text-1.md`); lexical measures use its word tokens, not code, URL or email tokens. Lexicons: `lexicons/` (sprint 303). Tests: `tests/test_language_measures_304.py`.*

## One text

| Measure | Function | Definition and source | Checked against | Agreement |
|---|---|---|---|---|
| Tokens, words, sentences, paragraphs | `profile` | substrate-text-1 | 62 fixtures (sprint 302); every lexicon entry tokenizes to itself | all |
| Sentence length mean, SD, CV | `rhythm` | population SD; CV = SD / mean | hand | exact |
| TTR | `ttr` | types / tokens | hand | exact |
| MATTR | `mattr` | Covington & McFall 2010; window 100 | lexicalrichness 0.5.1 `mattr`, same tokens, 592 replies of 100+ words | ≤ 1.1e-16 |
| MTLD | `mtld` | McCarthy & Jarvis 2010; threshold 0.72, a factor ends when TTR ≤ 0.72, partial factor, mean of both directions | lexicalrichness `mtld`, 600 replies | exact |
| HD-D | `hdd` | McCarthy & Jarvis 2007; 42 draws, hypergeometric | lexicalrichness `hdd`, 600 replies | ≤ 8.4e-15 |
| Zipf | `zipf` | discrete power law on word frequencies, MLE with Clauset, Shalizi & Newman 2009 eq. 3.7, xmin 1; s = 1 / (alpha − 1) | powerlaw 2.0.0 `Fit(discrete=True, xmin=1, estimate_discrete=True)`, 200 replies | ≤ 8.9e-16 |
| Heaps | `heaps` | V(n) = K n^beta, least squares on log–log at 20 log-spaced points from n = 10 | hand (all-distinct text: beta = 1, K = 1) | exact |
| Unigram entropy | `entropy` | Shannon, bits per word, plug-in | hand | exact |
| Compression ratio | `compression_ratio` | zlib level 9 length / UTF-8 length | definition | exact |
| Repeated n-gram rate | `repeated_ngram_rate` | share of word 3-gram occurrences whose 3-gram occurs twice or more; n-grams stay inside a sentence, heading or cell | hand | exact |
| Burstiness | `burstiness` | Goh & Barabási 2008 B on gaps between a word's occurrences (Altmann, Pierrehumbert & Motter 2009); mean over words with 5+ occurrences | hand (evenly spaced: −1; gaps 1, 10, 1, 10: −0.1) | exact |
| DFA alpha | `dfa` | Peng et al. 1994, order 1, non-overlapping windows from 4 to N/4 at ×1.2 | nolds 0.6.3 `dfa(overlap=False, order=1, fit_exp="poly")`, same windows: white noise, a random walk, and the 14,531 sentence lengths of all 600 replies | ≤ 1e-9 |
| Format rates | `format_rates` | headings, list items, table rows, code blocks, code spans, bold spans, em-dashes, exclamation marks, questions, URLs per 1,000 words | substrate-text-1 counts | — |
| Flesch reading ease, Flesch–Kincaid grade | `readability` | Flesch 1948; Kincaid et al. 1975 | hand; textstat 0.7.13 (below) | formula exact; whole texts differ, see below |
| Syllables | `syllables` | CMU Pronouncing Dictionary (cmudict package 1.1.3, 126,052 words): stressed vowels of the first pronunciation; otherwise vowel groups less a silent final e | the cmudict package itself | every word equal |
| Lexicon rates | `profile` | matches per 1,000 words; longest term first, no overlaps, LIWC wildcards | hand (matcher cases); a one-pass index checked equal to the per-list matcher on 200 replies | exact |
| Padding, by position | `profile` | restatement and background counted in the first 2 sentences, closing summaries and offers of more in the last 2, and also anywhere | hand | exact |

## The relation between two texts

| Measure | Function | Definition and source | Checked against |
|---|---|---|---|
| Length ratio | `length_ratio` | reply words / user words | hand |
| Lexical echo | `lexical_echo` | \|U ∩ M\| / \|U\| over word types not in LIWC2007's function words | hand |
| Phrase copy | `phrase_copy` | shared distinct word 4-grams, their share of the reply's, longest shared run of words | hand |
| NCD | `ncd` | Cilibrasi & Vitányi 2005, zlib level 9 | hand |
| LSM | `lsm` | Ireland et al. 2011: per category 1 − \|p1 − p2\| / (p1 + p2 + 0.0001), p = percentage of words, mean of nine LIWC2007 categories | hand (identical texts: 1) |
| Profile difference | `profile_difference` | reply value − user value | — |
| Lagged correlation | `lagged_correlation` | Pearson r of the follower's change at t and the leader's at t − 1 | hand (follower = leader one turn later: 1) |

## Where Substrate and textstat differ

`scripts/language_crosscheck_textstat.py` on the 600 replies:

- **Syllables.** textstat reads NLTK's CMUdict (123,455 words); Substrate reads the cmudict package (126,052). On the 123,328 words both hold, 123,208 counts are equal; the other 120 changed their first pronunciation between editions. Words only the newer edition holds ("api", "algorithmic") get CMUdict counts here and pyphen hyphenation counts in textstat.
- **Flesch reading ease.** Substrate minus textstat: median −0.92, quartiles −2.50 and 0.00, range −9.73 to 5.39. The formula is the same; the inputs differ. textstat splits a sentence at every `.`, `!` and `?`, does not count sentences of two words or fewer, joins hyphenated words, and reads markdown as text. substrate-text-1's differences are in `substrate-text-1.md`.

## Speed

`profile` on a real 1,821-token reply text: median 4.1 ms over 50 runs; a 1,626-token session reply text with code blocks and tables: 4.3 ms (Apple M5 Max, Python 3.14, pure Python). The test asserts a median under 5 ms for a 1,500-token text.

## Parameters

`Params`: MATTR window 100, MTLD threshold 0.72, HD-D draws 42, Zipf xmin 1, Heaps 20 points from 10, n-gram 3, burstiness 5 occurrences, zlib level 9, padding edge 2 sentences. Every profile stores them. The window minimums (sprint 306) say when each value is reported.

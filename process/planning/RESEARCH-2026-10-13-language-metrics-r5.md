# RESEARCH: measuring language without judging it (round 5)

*2026-10-13. Rounds 1–4 (`RESEARCH-2026-10-10-language-metrics*.md`) stay on disk. Round 4 was the plan; round 5 is the instruments as built and tested (sprints 302–306, `src/substrate/language/`, library 0.2.0). The build phase starts from this note.*

**Changes from round 4.**
- **The word lists now exist,** each taken from its published source; round 4 said they were already in the repository, and they were not.
- **Padding and tone have instruments:** padding phrases by position, and LIWC2007's register categories (persons, positive emotion, assent, fillers, swear words) beside Hyland's hedges and boosters.
- **Every value round 4 left open is set:** window minimums, MATTR's window, the Page–Hinkley δ, λ and warm-up, the burstiness occurrence count.
- **LSM uses LIWC2007's own categories,** the dictionary Ireland et al. (2011) used; round 4 planned an open substitute.
- **The order is offline first:** a command over records, then the live producer and its events.

## What is measured

The same texts as round 4: the user's text (`UserMessage.text`, delegate-written messages excluded), the model's text (`ModelReply.text`), the relation between them per turn, and the composed prompt (`PromptComposed.text` and `.system`). Two kinds of measure: form (counting, compression, distributions) and lookup-table meaning (fixed word lists). Both are deterministic and recomputable from the record.

## Preprocessing: substrate-text-1

`docs/language/substrate-text-1.md`: 22 rules.
- **Normalization:** NFC; curly apostrophes, non-breaking hyphens and spaces read as ASCII for splitting only; words case-folded, code, URLs and emails kept as written.
- **Blocks,** after CommonMark: fenced code left out of prose; headings and table cells give words but no sentences; a soft line break joins, a hard break ends a sentence.
- **Words:** contractions, hyphenated words, `3.5`, `1,000`, `e.g` and `file.txt` stay whole; an inline code span, a URL or an email is one token.
- **Sentences** end on `.`, `!`, `?` or `…` with any closing quote or bracket; a `.` after a single letter or one of 14 abbreviations does not end one; a lowercase letter after `.` does not stop the split.

62 hand-written fixtures fix the expected output, written before the code. The differences from lexicalrichness, textstat, quanteda and koRpus are tabled in the spec.

## Word lists

In `src/substrate/language/lexicons/`, one file each, naming source and construction (`sprint-303` card):

| List | Entries | Source |
|---|---|---|
| Kobak excess style words, 2024 | 379; rare subset 291 | Kobak et al. 2025, rebuilt from the authors' yearly counts by `scripts/build_lexicon_kobak.py`; equal word for word to their notebook's output |
| Hedges, academic | 97 | Hyland 2005, p. 218, as printed in Vázquez Orta & Giner 2008 |
| Boosters, academic | 63 | Hyland 2005, p. 218, as printed in Vázquez Orta & Giner 2009 |
| Hedges, informal | 117, and 46 inflected forms kept apart | Ulinski & Hirschberg 2019, Table 1 |
| Amplifiers | 15 boosters, 8 maximizers | Alshaar 2017, as printed in Liu, Salvi, Schoenegger et al. 2025 |
| LIWC2007 | 22 categories | Pennebaker, Booth & Francis 2007, copied entry by entry by `scripts/build_lexicon_liwc2007.py`: function words, the nine LSM categories, the five persons, tentative, certainty, positive emotion, swear words, assent, nonfluencies, fillers |
| Syllables | 126,052 words | CMU Pronouncing Dictionary (cmudict package 1.1.3) |
| Padding | 4 categories, 69 phrases | Substrate's own: restatement, background, closing summary, offer of more, the categories of Substrate's length control |
| Contractions | 6 endings, 15 words | the standard forms, as a rule |

Matching: inside one sentence, heading or cell; longest term first; no overlaps; LIWC's `*` matches every word with that start.

## The measures

`docs/language/measures.md` gives each definition, source and check. Lexical measures use word tokens.

**One text.**
- **Size and rhythm:** tokens, words, sentences, paragraphs; mean, SD and CV of sentence length.
- **Diversity:** TTR; MATTR (window 100); MTLD (0.72); HD-D (42 draws).
- **Frequency:** Zipf (discrete power-law MLE, Clauset et al. 2009); Heaps (log–log fit).
- **Information:** unigram entropy; zlib compression ratio.
- **Repetition and clustering:** repeated 3-gram rate; burstiness (Goh–Barabási B).
- **Long-range:** DFA α on sentence lengths.
- **Format:** headings, list items, table rows, code blocks and spans, bold spans, em-dashes, exclamation marks, questions, URLs, each per 1,000 words.
- **Readability:** Flesch reading ease and Flesch–Kincaid grade, syllables from CMUdict.
- **Lexicon rates:** every list above per 1,000 words; padding also counted in the first and last two sentences.

**Two texts.** Length ratio; lexical echo (the share of the user's content words the reply uses); shared 4-grams and the longest shared run; NCD; LSM over the nine LIWC2007 categories; profile difference; lagged correlation of changes.

**Agreement with published implementations,** on the 600 length-experiment replies: MATTR, MTLD and HD-D equal lexicalrichness 0.5.1 (largest difference 8.4e-15); the Zipf fit equals powerlaw 2.0.0; DFA equals nolds 0.6.3, also on white noise and a random walk; the syllable table equals cmudict word for word. Flesch differs from textstat 0.7.13 by a median of −0.92 points, from the different word and sentence split; the formula is the same.

**Speed:** about 4 ms for a 1,800-token text, pure Python.

## Windows

`docs/language/windows-r2.md`. Each measure runs over a trailing window of one stream at least as long as its minimum, across messages and sessions as needed; values are compared at equal window lengths, and the length is stored with each.

| Measure | Minimum | Basis |
|---|---|---|
| Size, rhythm, format, lexicon rates | one text | definition |
| MATTR, HD-D | 100 words, 42 words | definition |
| MTLD | 100 words | Koizumi & In'nami 2012 |
| Heaps | 800 words | measured |
| LSM | 1,600 words a side | measured |
| Entropy, Zipf | 3,200 words | measured |
| DFA | 400 sentences | measured on white noise |
| Burstiness | words with 20+ occurrences | measured on random gaps |
| Compression ratio | none; compared at equal lengths | measured |

The criterion: the mean within 5% of the 6,400-word value and the spread within 10% (0.05 for the bounded measures).

## Change detection

`docs/language/drift-r2.md`. Page–Hinkley, both directions, in standard deviations of a warm-up; restarts after an alarm; equal to river 0.26.1 on 600 of 600 first alarms. Defaults δ 0.25, λ 10, warm-up 20, chosen from 72 settings on synthetic series by a rule fixed first: 4% false alarms over 50 values, a 1 SD step found 74% of the time within 25 values (median delay 12), a 2 SD step every time. It watches one stream's series across session boundaries, or a many-values-per-reply series such as sentence lengths.

## What every stored value names

`profile()` returns, beside the measures: the library version (0.2.0), `substrate-text-1`, every parameter, the window minimums, each lexicon's name and version, and the zlib version; and the partials that merge across windows (word frequencies, sentence lengths, lexicon counts, format counts). Round 4's grouping keys (session, turn, stream, driver, bundle and the rest) are added when lines are written, in the build phase.

## The build phase

1. **A command over records.** `substrate language <record>` writes one line per text in round 4's line format, adding nothing to the record. Done when the 77 recorded sessions and the 1,200 experiment replies measure without error and a second run reproduces every line byte for byte.
2. **The live producer.** A vocabulary round defines `LanguageProfile` and `LanguageDrift`; a producer measures each `UserMessage` and `ModelReply` beside the model step. Done when a live value equals the command's value for the same text.
3. **The app's process.** Trailing-window measures to `<workspace>/.substrate/language/<session_id>.jsonl`, rebuildable from the record.
4. **What the app shows.** Designed after 1–3.

## Future features

Later uses of the instruments, not part of building them (`ROADMAP-2026-10-12-language-measurement-r3.md`):
1. **Tagged replies:** the same questions answered under each tone, guidance level and length, every reply saved with its setting; the 1,200 length-experiment replies are a first set.
2. **What each setting changes:** predict which measures each setting moves, then compare with the tagged replies.
3. **The drift detector on real sessions:** its catch rate where a setting changed at a known turn, its false-alarm rate where nothing changed.
4. **Reference distributions** per driver, guidance level, user and task, with KS and PSI.
5. **Naming a setting:** whether "Length setting: full." changes replies more than the bare text.

## Sources

Round 4's sources stand. Added in sprints 302–306:
- Clauset, A., Shalizi, C. R. & Newman, M. E. J. (2009), "Power-law distributions in empirical data", *SIAM Review* 51(4): eq. 3.7.
- Hyland, K. (2005), *Metadiscourse*, Continuum, p. 218, as printed in Vázquez Orta, I. & Giner, D. (2008), *Revista Alicantina de Estudios Ingleses* 21, 171–190 (doi 10.14198/raei.2008.21.10), and (2009), 22, 219–237 (doi 10.14198/raei.2009.22.14).
- Ireland, M. E., Slatcher, R. B., Eastwick, P. W., Scissors, L. E., Finkel, E. J. & Pennebaker, J. W. (2011), "Language Style Matching Predicts Relationship Initiation and Stability", *Psychological Science* 22(1), 39–44: Table 1 and the formula, p. 40.
- Kobak, D., González-Márquez, R., Horvát, E.-Á. & Lause, J. (2025), *Science Advances* 11(27), eadt3813; data github.com/berenslab/llm-excess-vocab at 53db991a.
- Liu, J., Salvi, F., Schoenegger, P. et al. (2025), "When Large Language Models are More Persuasive Than Incentivized Humans, and Why", arXiv 2505.09662, appendix (Alshaar 2017 amplifiers; Hyland hedges).
- Pennebaker, J. W., Booth, R. J. & Francis, M. E. (2007), LIWC2007, English dictionary.
- Peng, C.-K. et al. (1994), "Mosaic organization of DNA nucleotides", *Physical Review E* 49: DFA.
- Ulinski, M. & Hirschberg, J. (2019), "Crowdsourced Hedge Term Disambiguation", Linguistic Annotation Workshop, ACL, W19-4001, Table 1.
- Unicode Standard Annex #29, revision 49 (Unicode 18.0.0): word and sentence boundaries.
- Reference implementations: lexicalrichness 0.5.1, textstat 0.7.13, powerlaw 2.0.0, nolds 0.6.3, river 0.26.1, cmudict 1.1.3; quanteda's `tokens()` and koRpus's `tokenize()` reference pages.

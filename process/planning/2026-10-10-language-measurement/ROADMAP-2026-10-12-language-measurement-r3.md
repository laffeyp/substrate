# ROADMAP: language measurement (round 3)

*2026-10-12, round 3. Round 1 (`ROADMAP-2026-10-12-language-measurement.md`) planned experiments to check the measures against Substrate's settings. The Architect: "We're looking to build these best-in-class tools … we're doing the basic thing first … We're not running a bunch of experiments immediately." Round 2 (`-r2.md`) called those experiments dropped. They are not dropped: round 3 keeps the plan to build the instruments first and lists the experiments under "Future features" below. Source: `RESEARCH-2026-10-10-language-metrics-r4.md`, checked against the repository on 2026-10-12.*

## The task

Build best-in-class instruments for measuring language without judging meaning, on every Substrate session: the user's text, the model's text, the relation between them, and the composed prompt. Each measure follows its published definition exactly, is checked against reference values and published implementations, and names every version and parameter it depends on. The data kept supports any later research.

## What round 4 settles

- **Two kinds of measure:** form (counting, compression, distributions) and lookup-table meaning (fixed word lists). Both are deterministic and recomputable from the record. Judged meaning and embeddings are out.
- **Four texts:** `UserMessage.text` (excluding `slash_source="delegate"`, written by the parent model), `ModelReply.text` (with `stop_reason`), the relation per turn (paired with the final reply and with all the turn's replies), and `PromptComposed.text`/`.system`.
- **The measures,** each with a window, a shortest useful window and a basis (sourced, definition, or working value).
- **Mergeability:** counts, frequency tables, n-gram counts, function-word category counts and the sentence-length series merge exactly; the Heaps curve merges at text boundaries; MATTR, MTLD, compression ratio, NCD, phrase copy, cross-window repetition and burstiness are recomputed from text.
- **Three pieces on one library of pure functions:** a producer in the session topology (`LanguageProfile`; Page–Hinkley within the session as `LanguageDrift`), an app process outside the run (`<workspace>/.substrate/language/<session_id>.jsonl`), and research later (reference distributions, KS, PSI).
- **Every stored line names** the library version, preprocessing identity, parameters, lexicon versions and category schema.

## What round 4 gets wrong or leaves open

1. **The lexicons are not in the repository.** Round 4 says they are; `skills/dellm/SKILL.md` names about twenty of Kobak's words and a few puffery and scaffolding phrases as prose examples. No hedge, booster, intensifier or function-word list exists, no LSM category schema, and not Kobak's 291-word list. Each lexicon is built, with its source and licence.
2. **It has no padding or tone instruments.** Round 4 predates the length and tone controls. Padding (restating the question, background before the answer, closing summaries, offers of more) and the markers of register (contractions, slang, exclamations, enthusiasm words, hedges, boosters) get lexicons and measures as instruments in their own right.
3. **Its working values are unset.** The window minimums marked "working value", MATTR's window, the compression-ratio minimum and Page–Hinkley's δ, λ and warm-up need values, each from a source, from the measure's definition, or from a stated, tested property of the instrument (for example, zlib's fixed overhead measured on synthetic text).
4. **The order is reversed.** Round 4 starts with a live producer and two new event kinds. The instruments are built and tested offline first; events, which are vocabulary, come after.

## Test material

- Real text for robustness and performance: 77 recorded sessions (305 user messages, 287 model replies, 35,171 words) and 1,200 replies from the length experiments. They supply fixtures (markdown, code, lists, long and one-line texts), not verdicts.
- Synthetic text and series with known properties: shuffled text (no long-range order), repeated text, Poisson and clustered word occurrences, series with planted step changes. Each tests that an instrument reports what its definition says it should.

## Research phase

Six tasks. Each is a card with `pass_kind: research` and ends in files someone else can check.

| # | Task | Method | Output | Done when |
|---|---|---|---|---|
| R1 | **Preprocessing spec v1** | Decide Unicode normalization, case folding, the word tokenizer (apostrophes, contractions, hyphens, URLs, numbers), the sentence splitter (abbreviations, list items, headings), markdown stripping, and code blocks (out of prose measures, counted in format). Compare against the conventions of the published implementations R3 checks against, and record where Substrate differs. | The `substrate-text-1` spec and a fixture set from real and synthetic texts with their expected tokens and sentences | Every fixture's expected split is written before the code |
| R2 | **Lexicons v1** | Kobak's 291 style words (the paper's supplement); hedges and boosters (Hyland's lists, or an open equivalent); intensifiers; padding phrases (restatement openers, background lead-ins, closing summaries, offers of more), from the guidance texts and published catalogs; address words; contractions and slang; exclamation and enthusiasm words; an open function-word list and LSM category schema | One versioned file per lexicon naming its source, licence and version | Each source is cited, each licence permits shipping, each list's construction is written down |
| R3 | **Measure library v0** | Every kind 1, kind 2, relation, padding and register measure as a pure function, implemented to its published definition. Each is tested against hand-computed values on small texts and, where a published implementation exists, against it on the fixture set: MATTR, MTLD and HD-D (`lexicalrichness`, koRpus, quanteda); readability (`textstat`); DFA (`nolds` or MFDFA); Zipf and Heaps fits (the `powerlaw` package's estimators); NCD and LSM from their papers' formulas. The cross-check packages are test dependencies only. | A kernel module and its tests; a table of each measure, its source, its reference implementation and the agreement found | Every measure agrees with its hand-computed values and its reference implementation within a stated tolerance, or the difference is explained (for example, a tokenizer difference from R1); one 1,500-token text measures in under 5 ms |
| R4 | **The drift detector** | Page–Hinkley as Hinkley (1971) and its standard modern statement define it, both directions, with warm-up and reset. Tested on synthetic series: no change (false-alarm rate), planted steps of known size (detection delay), slow drift (stated as absorbed, per round 4) | The detector, its tests, and a table of false-alarm rate and detection delay against δ and λ on those series | Defaults for δ, λ and warm-up are chosen from that table and stated as parameters, not tuned on sessions |
| R5 | **Window minimums** | For each "working value" in round 4's window table, derive the minimum from the measure's definition or from a measured property of the instrument on synthetic text (for example, the length at which zlib's header stops dominating the ratio, or the sample size at which MTLD's factor count stabilizes on shuffled text) | The window table with every minimum sourced, defined or measured | No row reads "working value" |
| R6 | **Research round 5** | The instruments as built: definitions, preprocessing, lexicons, parameters, reference cross-checks, window table, provenance | `RESEARCH-<date>-language-metrics-r5.md` | Read and signed by the Architect before any build card starts |

R1 and R2 run together; R3 needs both; R4 needs only the library's skeleton; R5 needs R3; R6 closes the phase.

## Build phase (after round 5)

| # | What | Done when |
|---|---|---|
| B1 | **Offline projection.** `substrate language <record>` writes round 4's line format for any record, adding nothing to it. | The 77 sessions and 1,200 replies measure without error, and a second run reproduces every line byte for byte. |
| B2 | **Vocabulary round and live producer.** `LanguageProfile` and `LanguageDrift`; the producer on `UserMessage` and `ModelReply`, beside the model step. | A live value equals B1's recomputed value for the same text under the same versions. |
| B3 | **The app's process.** Long-window measures to `<workspace>/.substrate/language/<session_id>.jsonl`. | Lines rebuild from the record. |
| B4 | **What the app shows.** Not yet designed. | Decided after B1–B3. |

## Future features

These use the instruments once they are built. They are planned for later, not part of building the tools.

1. **Tagged replies.** Have the models answer the same questions under each setting, and save every reply with the setting it was written under: each tone (blunt, neutral, formal, dry), each guidance level (harness, low, medium, high), and each length (terse, normal, full) on a mix of question types (yes/no, opinion, quick fact, follow-up, explanation), on at least two models. The length experiment's 1,200 replies are a first set of this kind.
2. **What each setting changes.** Before looking at the tagged replies, write down which measures each setting should move and in which direction (formal should cut contractions; blunt should cut hedges; terse should cut padding). Then compare the prediction with the replies. Nothing yet shows that any measure moves when a setting changes on Substrate's own output; this is how that would be shown.
3. **The drift detector on real sessions.** Set its defaults from real sessions: how often it catches a change on sessions where a setting changed at a known turn (the length experiment's switch sessions), and how often it fires on sessions where nothing changed.
4. **Reference distributions.** Per driver, guidance level, user and task, with the distribution tests (KS, PSI), once enough measured sessions exist (round 4's research piece).

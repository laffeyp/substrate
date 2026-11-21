# RESEARCH: measuring language without judging it (round 3)

*2026-10-10. Asked by the Architect. Rounds 1 (`RESEARCH-2026-10-10-language-metrics.md`) and 2 (`-r2.md`) stay on disk. Round 3 is the whole note, revised; it replaces both as the current text.*

**Changes from round 2.**
- **Three texts.** The note measures the user's text, the model's text, and the relation between them. Rounds 1 and 2 measured the model's replies and Substrate's composed prompt only.
- **The app measures; research builds references later.** The app measures every session as it runs and writes the results into the workspace. Distributions to compare against are a research product, built later and separately, and the app's job is to keep everything that research will need. Round 2 handed a reference to each session at open; that hand-off is gone.
- **Drift inside the run** compares a session with its own earlier turns, so it needs no outside reference.
- **"Baseline" is renamed "reference distribution".** In Substrate, `baseline` already names the environment facts recorded at session open (`SessionStarted.baseline`, session vocabulary § P.2, `topologies/session/environment.py`).
- **Two mergeability claims corrected.** The Heaps curve merges only at text boundaries, and burstiness does not merge.
- **Every window minimum is marked** as sourced or as a working value.
- **Cost is measured** rather than estimated.
- **Corrections from round 1.** The excess-vocabulary examples are checked against the paper. The PSI thresholds are attributed to their real origin.

## The question

What can be measured about text mechanically, so that Substrate can:
1. measure the language of every session as it runs, on the user's side, the model's side, and between them;
2. keep what later research needs, to compare guidance levels and to build reference distributions, whatever form those take?

## What "without meaning" means here

1. **Form.** Counting, compression and distributions: sentence lengths, distinct words, compressibility. No meaning involved.
2. **Lookup-table meaning.** A fixed word list tags words and a counter counts them: hedges, excess model vocabulary, function words, second-person pronouns. The table assigns the "meaning", so the same text always gets the same score.
3. **Judged meaning.** A person, or a model acting as judge, decides what a passage means or whether it is good.

This note covers kinds 1 and 2. Both are deterministic, cheap, and recomputable from the record at any time. Kind 3 is out of scope. Embeddings sit between kinds 2 and 3, deterministic for a fixed model but opaque, and are left for later.

## Three texts, and where each comes from

| Text | On the record | Notes |
|---|---|---|
| The user's text | `UserMessage.text` | `slash_source` says where a message came from. A delegated sub-session's opening message has `slash_source="delegate"`; its text was written by the parent model (`topologies/tool_loop/delegate.py`), so it is excluded from the user's stream and keyed as model-written. |
| The model's text | `ModelReply.text`, one per model step | `stop_reason` separates a turn's final answer (`end_turn`, `wrap_up`) from text written beside a tool call (`tool_use`). |
| The relation | One turn: its `UserMessage` and the turn's `ModelReply` events, joined by `turn_index` | Paired two ways: the user's text with the turn's final reply, and with all the turn's reply text joined in order. Both are recorded, keyed by which pairing. |

A fourth channel: `PromptComposed.text` and `.system` hold the whole of what Substrate sent the model, which is guidance, history and the user's text. Measuring it shows a guidance edit or a growing history as a change on the input side.

The user's text has its own uses for the user. It tracks their writing over weeks: rhythm, excess-vocabulary rate, address. It also shows whether they pick up the model's vocabulary (see "Convergence" below). Many user messages run one or two sentences. Per message, the user's profile therefore holds only size, format and lexicon counts; everything else runs over a session or longer.

## The measures

### Kind 1: form (each text on its own)

| Family | Measure | What it shows | Note |
|---|---|---|---|
| Size and rhythm | Tokens, sentences, paragraphs; mean sentence length, its standard deviation and coefficient of variation | Length, and how uniform the rhythm is | Meaningful on one text |
| Lexical diversity | TTR, MATTR (Covington & McFall 2010), MTLD (McCarthy & Jarvis 2010), HD-D | Distinct words per stretch of text | TTR falls as text grows; compare only like lengths. Bestgen: a token's weight in MATTR depends on its position, so MATTR suits tracking change *within* a long text better than scoring a whole text. MATTR's window is a parameter (quanteda's default is 100 tokens) and is recorded with every value. |
| Frequency structure | Zipf exponent (rank vs frequency); Heaps exponent (vocabulary growth) | How the vocabulary is spread | Needs long text |
| Information | Unigram entropy; compression ratio (zlib) | Redundancy; compression approximates the entropy rate | Compression ratio is one standard-library call |
| Repetition | Repeated n-gram rate within a text; overlap between successive replies | Loops, boilerplate, turn-to-turn sameness | |
| Burstiness | Goh–Barabási B = (σ − μ)/(σ + μ) on the gaps between a word's occurrences | Whether words cluster (B > 0), arrive at random (B = 0), or spread evenly (B = −1) | Goh & Barabási 2008; applied to words by Altmann, Pierrehumbert & Motter 2009 |
| Long-range structure | Hurst exponent by DFA on the series of sentence lengths | Fractal persistence in rhythm across a long text | Fractal structure in sentence lengths also appears in randomly generated text, in some cases stronger than in canonical literary works ("Fractal Illusions", arXiv 2508.19782). The measure is valid; a high value alone does not mark authorship or quality. Compare like with like over long series. |
| Format | Rates per 1,000 words of bullets, headings, bold spans, code blocks, em-dashes, questions | Structure the guidance asks for or against | Tied to the guidance texts |

### Kind 2: lookup-table meaning (each text on its own)

| Lexicon | What it counts | Source |
|---|---|---|
| Excess model vocabulary | Words whose frequency jumped after language models arrived, per 1,000 words | Kobak et al., *Science Advances* 2025 (arXiv 2406.07016): over 15 million PubMed abstracts, 2010–2024. The largest excess ratios among rarer words were *delves*, *underscores* and *showcasing*; among common words, *potential*, *findings* and *crucial*. The full list holds 291 style words, *pivotal* among them. |
| The guidance's own lists | Puffery, hedges, intensifiers, summary closers, banned words | `skills/dellm/SKILL.md` and the guidance levels, already in the repository |
| Person and address | Rates of "you", "I", "we"; vocatives | Checks "Unaddressed prose" directly |
| Function words | The profile of the most common function words | Classic stylometry (Burrows' Delta); also feeds LSM below |
| Readability | Flesch reading ease, Flesch–Kincaid grade | Syllables counted by rule and table; crude but deterministic |

### The relation between the user's text and the model's

Every measure here is form or lookup-table; none judges whether the reply answered well.

| Measure | Definition | What it shows | Source and note |
|---|---|---|---|
| Length ratio | Reply tokens ÷ user tokens, per turn | How much the model writes per word it receives | |
| Lexical echo | Share of the user's content-word types (function words removed by list) that the reply reuses | How far the reply works in the user's own terms | |
| Phrase copy | Shared word n-grams of length 4 or more; longest common word run | Quoting and parroting, as against restating | |
| Compression distance | NCD(x, y) = (C(xy) − min(C(x), C(y))) / max(C(x), C(y)), with C the compressed length | Form-only similarity of the two texts: 0 for identical, near 1 for unrelated | Cilibrasi & Vitányi 2005. Deflate, which zlib implements, looks back at most 32 KiB (RFC 1951), so for a joined pair longer than that it understates similarity. Compressor window and object size skew NCD (Cebrián, Alfonseca & Ortega 2005). |
| Language style matching (LSM) | Per function-word category c: 1 − \|p_u − p_m\| / (p_u + p_m + 0.0001), with p the category's share of words; averaged over categories | How closely the model's function-word style tracks the user's | Niederhoffer & Pennebaker 2002; Ireland & Pennebaker 2010. The published form uses nine LIWC categories. LIWC is a licensed lexicon, so Substrate uses an open function-word category list, and its scores are not directly comparable with LIWC-based studies. |
| Profile difference | Model's value minus user's, measure by measure, on the same window | Where the two writers differ: sentence length, em-dash rate, "you" rate | |
| Convergence | The trend of LSM and of profile differences across turns; lagged correlation of the change in one side's measure at turn t with the other side's at t − 1 | Whether the model drifts toward the user, the user toward the model, or neither; for example, the user's own excess-vocabulary rate rising over weeks | Needs many turns; a session at least, more often many sessions |

## Every measure has a window

A profile is a set of measures, each taken over a window, and each window is a time scale:
- one text (a user message, a model reply);
- one turn;
- a sliding window of N texts or N tokens;
- the session so far;
- many sessions.

The profile names the window beside every number and reports nothing for a window shorter than the measure's minimum. The "Basis" column says whether that minimum comes from a source, from the measure's definition, or is a working value that the first measured sessions should check.

| Measure | Shortest useful window | Usual window | Basis |
|---|---|---|---|
| Size, rhythm, format, lexicon rates | one text | one text; a sliding window | definition |
| Compression ratio, entropy | a few hundred tokens | one long text; otherwise a sliding window | working value: zlib's fixed overhead dominates short inputs |
| MATTR | its window length | within a text, or a sliding window | definition |
| MTLD | about 100 tokens | one long text, or a session | Koizumi & In'nami 2012: MTLD stabilized at 100 words in samples of 50–200 words |
| Repetition across replies | two replies | consecutive replies | definition |
| Zipf and Heaps exponents | thousands of tokens | a session, or many | working value |
| Burstiness | many occurrences of each word measured | a session, or many | working value |
| Hurst exponent by DFA | a long series | many sessions | sourced in kind: the studies use whole books (one reports correlations up to scales of 10⁴ sentences, PMC5029871); no source here fixes a minimum |
| Length ratio, echo, phrase copy, NCD | one turn | one turn | definition |
| LSM | one turn, noisily | a session | working value |
| Convergence | many turns | a session, or many | definition: a trend needs a series |

## Which measures merge across windows

Whether a window's value can be built from smaller windows decides what has to be stored. That is a property of each measure's mathematics.

**Mergeable, exactly.** Per-text partial results that add up. The partials are:
- token, sentence and lexicon counts;
- word-frequency tables;
- n-gram counts;
- function-word category counts;
- the series of sentence lengths, which concatenates in order within one stream (the user's, or the model's).

Every measure that is a function of these is exact for any window. That covers:
- mean and spread of sentence length;
- unigram entropy;
- TTR over the union;
- the Zipf exponent;
- DFA on the concatenated length series;
- the length ratio;
- lexical echo;
- LSM over a session, from summed category counts.

**Mergeable at text boundaries only.** The Heaps curve. From the frequency tables taken in order, the vocabulary size at each text's end is exact (the running union of their words); the growth inside a text is lost. A Heaps fit uses those boundary points, or it recomputes from text.

**Not mergeable.** These depend on word order across text boundaries, or on the text as a whole:
- MATTR and MTLD, whose windows and factors run across boundaries;
- compression ratio, since compressing a concatenation is not the average of compressing its parts;
- NCD and phrase copy;
- repetition across a window;
- burstiness, which needs the position of every occurrence and not just counts.

These are recomputed from the raw text, which the record holds.

## How it runs

Three pieces share one library of pure measure functions. A value computed live and the same value computed later from the record therefore agree.

**1. In the run: a producer in the session topology.**
- **Trigger.** It starts on each `UserMessage` and each `ModelReply`.
- **Output.** It writes a `LanguageProfile` event holding the one-text measures. On a turn's final reply it adds the relation measures for that turn.
- **Cost.** It runs beside the model step, so no turn waits for it.
- **Change detection.** It uses CUSUM (Page 1954) or Page–Hinkley over the session's own stream: each new value is tested against the running mean of the same session's earlier values. A detected change writes a `LanguageDrift` event, an ordinary event of its own kind. A topology trigger can react to it like any other: pause, correct, or tell the model. No outside reference is needed.

**2. In the app, outside the run: a Substrate process with no topology.**
- It follows the records of sessions as they grow.
- It computes the long-window and non-mergeable measures the producer skips: session MATTR and MTLD, Zipf and Heaps, burstiness, DFA, and convergence.
- It appends one line per measured text to `<workspace>/.substrate/language/<session_id>.jsonl`. The workspace is the session's `SessionStarted.workspace_path`, beside the `skills/`, `prompts/`, `memory/` and `context.md` a workspace's `.substrate/` already holds.
- A session in a per-session sandbox writes into that sandbox. Losing those files loses nothing, since the record holds the text and the files can be rebuilt from it.

**3. Research, outside the app, later.** It reads the `.jsonl` files and the records, and builds reference distributions and comparisons. What a reference distribution is (per driver, per guidance level, per user, per task) is a research question, not yet answered. Distribution tests belong here:
- the Kolmogorov–Smirnov test;
- the population stability index (PSI).

PSI's usual thresholds (below 0.1 stable, 0.1–0.25 worth a look, above 0.25 a shift) are a credit-scoring convention traced to Lewis (1994) and Siddiqi (2006). Later authors call them arbitrary (Yurdakul & Naranjo 2020; arXiv 2303.01227).

## What the app keeps, so references can be built later

The app commits to no definition of a reference distribution. It keeps the data any definition will need.

1. **The raw text stays reachable.** Every input and output is on the record, so a measure not yet invented can be computed later. Records outlast sessions. Deleting a session removes its manifest and keeps the record directory (`topologies/session_registry.py`, `delete`: "The record directory stays"). The daemon's `/api/runs/clear` prunes topology runs under `runs/`, not session records. The `.jsonl` files are a cache of the record.
2. **Every line carries the keys a reference might group by.** A key left out now can never be split on later.
3. **Partials are kept, not only finished values,** so any window or grouping can be rebuilt without re-reading text wherever the mathematics allows.

| Key | Source |
|---|---|
| Session id | `SessionStarted.session_id` |
| Seq and time | the envelope's `seq` and `t` |
| Stream | `user`, `model`, `relation`, or `composed` (the `PromptComposed` channel) |
| Pairing (relation lines) | `final` or `turn` |
| Turn and step | `UserMessage.turn_index`; `ModelReply.turn_index`, `.step` |
| Message origin | `UserMessage.slash_source` |
| Reply kind | `ModelReply.stop_reason` |
| Driver model | `SessionStarted.driver_model`, and per reply `ModelReply.usage.model` |
| Model class | `SessionStarted.model_class` (empty before session vocabulary v0.4) |
| Guidance bundle | `SessionStarted.bundle`, updated by `SessionChanged` with `field="bundle"` |
| Guidance text | SHA-256 of `PromptComposed.system` |
| Workspace shape | `SessionStarted.workspace_shape` (`flat`, `worktree` or `isolate`) |
| Topology | the run's topology name |
| Library version | the measure library's version |
| Measure parameters | MATTR window, MTLD threshold (0.72), compressor and level, lexicon versions |

The line format:

```json
{"session_id": "1ceeea0d75a9", "seq": 412, "t": 1789256851.204, "stream": "model",
 "turn": 3, "step": 2, "stop_reason": "end_turn", "slash_source": null,
 "driver_model": "kimi-k2", "model_class": "large", "bundle": "standard-medium",
 "guidance_sha256": "…", "workspace_shape": "flat", "topology": "session",
 "library": "0.1.0", "params": {"mattr_window": 100, "mtld_threshold": 0.72, "zlib_level": 9},
 "values": {"text": {...}, "turn": {...}, "last_10": {...}, "session": {...}},
 "partials": {"tokens": 512, "sentences": 23, "freq": {...}, "fw_categories": {...},
              "sentence_lengths": [...], "lexicon": {...}}}
```

## Comparing guidance levels (research)

- **Design.** The assay holds the model, the task and the user's text constant and varies only the level (harness, low, medium, high). The user side is then fixed by design, and the relation measures show how each level changes the response to identical input.
- **Two readouts per run.** Task success, scored as the assay already scores it, and the profile of every reply and every turn.
- **Length** confounds almost every diversity measure. Report it, compare within length bands, and prefer MATTR or fixed-window measures for reply-level comparison.
- **Sample size.** The project's power finding stands: equivalence claims need on the order of 90–360 paired runs, not 10.

## What the recent literature says these measures detect

- **AI writing has a stylometric footprint.** Across 8 models and 5 domains, a small set of features, mainly entropy and lexical diversity, consistently separates model-written text from human writing. AI-edited text shows a different pattern: a small rise in lexical diversity, a fall in entropy, and lexical density as the main signal. Its features separate it from AI-generated text but much less well from human writing (Shan, Lee & Hao, arXiv 2608.27855).
- **Instruction tuning narrows the range.** On English news text, newer instruction-tuned models show reduced syntactic and, especially, lexical diversity against older, non-instruction-tuned models. Diversity was measured with metrics from ecology and information theory over HPSG parses (Gude et al., arXiv 2605.06030).

## Costs and limits

- **Cost, measured.** Compression ratio, sentence rhythm, MATTR (window 100) and MTLD on one 1,567-token text took a median 0.7 ms over 20 runs. The code was pure Python with no model calls, on an Apple M5 Max. The lexicons are already in the repository.
- **Short texts limit what is meaningful.** A two-sentence message supports size, format and lexicon counts, not Zipf or DFA. The window table governs what is reported.
- **These measures describe form, not quality.** A lower excess-vocabulary rate means fewer of those words, not better writing. They are instruments for seeing change, read beside task success.

## Sources

- Covington, M. A. & McFall, J. D. (2010), MATTR; McCarthy, P. M. & Jarvis, S. (2010), MTLD. Definitions as given by the koRpus documentation ([lex.div methods](https://rdrr.io/cran/koRpus/man/lex.div-methods.html)). MATTR window default: quanteda ([compute_mattr](https://quanteda.io/reference/compute_mattr.html)).
- Bestgen, Y., "Estimating Lexical Diversity Using the Moving Average Type-Token Ratio (MATTR): Pros and Cons" ([PDF](https://perso.uclouvain.be/yves.bestgen/images/RMAL24.pdf)); read: abstract and introduction.
- Koizumi, R. & In'nami, Y. (2012), MTLD stability at 100 words, as reported in secondary sources found by search; the paper itself was not read.
- Goh, K.-I. & Barabási, A.-L. (2008), "Burstiness and memory in complex systems", *EPL* ([arXiv physics/0610233](https://arxiv.org/pdf/physics/0610233)).
- Altmann, E. G., Pierrehumbert, J. B. & Motter, A. E. (2009), "Beyond Word Frequency", *PLoS ONE* ([PMC2770836](https://pmc.ncbi.nlm.nih.gov/articles/PMC2770836)).
- "Fractal Illusions: An Experimental Study of Long-Range Sentence-Length Correlations in Randomly Generated Natural Language Texts" ([arXiv 2508.19782](https://arxiv.org/abs/2508.19782)); read: abstract.
- Long-range correlations and DFA on sentence lengths: [PMC5029871](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5029871/), [arXiv 1212.3171](https://arxiv.org/pdf/1212.3171), [arXiv 1412.8319](https://arxiv.org/pdf/1412.8319).
- Zipf, Heaps and entropy rate: [arXiv 1412.3336](https://arxiv.org/pdf/1412.3336), [arXiv 2411.10227](https://arxiv.org/pdf/2411.10227).
- Kobak, D. et al. (2025), "Delving into LLM-assisted writing in biomedical publications through excess vocabulary", *Science Advances* ([arXiv 2406.07016](https://arxiv.org/abs/2406.07016)); read: abstract and the word results.
- Shan, Z., Lee, Y. & Hao, S., "AI Writers Have a Consistent Stylometric Footprint, but AI Editors Do Not" ([arXiv 2608.27855](https://arxiv.org/abs/2608.27855)); read: abstract.
- Gude, A. et al., "More Aligned, Less Diverse? Analyzing the Grammar and Lexicon of Two Generations of LLMs" ([arXiv 2605.06030](https://arxiv.org/abs/2605.06030)); read: abstract.
- Cilibrasi, R. & Vitányi, P. M. B. (2005), "Clustering by Compression", *IEEE Trans. Inf. Theory* 51(4) ([arXiv cs/0312044](https://arxiv.org/abs/cs/0312044)).
- Cebrián, M., Alfonseca, M. & Ortega, A. (2005), "Common pitfalls using the normalized compression distance: what to watch out for in a compressor", *Communications in Information and Systems* 5(4), 367–384 ([record](https://repositorio.uam.es/handle/10486/663140)); read: the abstract as summarized by search.
- Deutsch, P. (1996), RFC 1951, "DEFLATE Compressed Data Format Specification": the 32 KiB window.
- Niederhoffer, K. G. & Pennebaker, J. W. (2002); Ireland, M. E. & Pennebaker, J. W. (2010). LSM formula as given by LIWC's documentation ([Understanding and Using LSM](https://liwc.app/help/lsm)); vendor documentation for the formula, not a study.
- Page, E. S. (1954), "Continuous inspection schemes", *Biometrika*: CUSUM.
- PSI thresholds: Lewis (1994) and Siddiqi (2006) as traced by "A critical review of existing and new population stability testing procedures in credit risk scoring" ([arXiv 2303.01227](https://arxiv.org/abs/2303.01227)); Yurdakul & Naranjo (2020) as cited there.

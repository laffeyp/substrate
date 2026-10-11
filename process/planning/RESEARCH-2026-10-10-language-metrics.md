# RESEARCH: measuring language without judging it

*2026-10-10, late night. Asked by the Architect.*

**Question.** What can be measured about a text mechanically, so that Substrate can (1) compare the guidance levels by what they do to a model's output language, beside whether the model completes simple and hard tasks, and (2) run the same measures on every model input and output, keep a running track, and flag drift?

## What "without meaning" means here

The measures fall into three kinds:

1. **Form.** Counting, compression and distributions: sentence lengths, how many distinct words, how compressible the text is. They involve no meaning at all.
2. **Lookup-table meaning.** A fixed word list or lexicon tags words, and a counter counts them: hedge words, a published list of words that language models overuse, function words, second-person pronouns. A table assigns the "meaning", so the same text always gets the same score.
3. **Judged meaning.** A human, or a model acting as judge, decides what a passage means or whether it is good.

**This note covers kinds 1 and 2 only.** Both are deterministic, cheap, and can be recomputed from the record at any time. Kind 3 is out of scope. Embeddings fall between kinds 2 and 3: deterministic for a fixed model, but opaque. They are left for later.

## The measures

### Kind 1: form

| Family | Measure | What it shows | Note |
|---|---|---|---|
| Size and rhythm | Tokens, sentences, paragraphs; mean sentence length, its standard deviation, and coefficient of variation | Length, and how uniform the rhythm is; uniform rhythm is the "machine" tell the guidance targets | Cheap; meaningful on one reply |
| Lexical diversity | TTR, MATTR (Covington & McFall 2010), MTLD (McCarthy & Jarvis 2010), HD-D | How many distinct words per stretch of text | TTR falls as text grows, so compare only like-length texts. MATTR is the usual length-robust choice, but Bestgen shows a token's weight depends on its position, so MATTR suits tracking change *within* a long text better than scoring a whole text |
| Frequency structure | Zipf exponent (rank vs frequency); Heaps exponent (vocabulary growth) | How the vocabulary is spread; the two exponents are linked | Needs long text: compute per session or per batch, not per reply |
| Information | Unigram entropy; compression ratio (zlib) | Redundancy; compression approximates the entropy rate | Compression ratio is one line of standard-library code and robust; a strong first metric |
| Repetition | Repeated n-gram rate within a reply; overlap between successive replies | Loops, boilerplate, the model repeating itself | The second catches turn-to-turn sameness |
| Burstiness | Goh–Barabási B on the gaps between a word's occurrences (Goh & Barabási 2008; Altmann, Pierrehumbert & Motter 2009) | Whether words cluster as in human text or spread evenly | Needs many occurrences: per session |
| Long-range structure | Hurst exponent by DFA on the series of sentence lengths | "Fractal" persistence in rhythm across a long text | **Caution.** Randomly generated text shows long-range sentence-length correlations as strong as literature's ("Fractal Illusions", arXiv 2508.19782). Use it only to compare like with like over long series, never as a quality score. |
| Format | Rates per 1,000 words of bullets, headings, bold spans, code blocks, em-dashes, questions | Structure the guidance asks for or against: "prose by default", em-dash density | Directly tied to the guidance texts |

### Kind 2: lookup-table meaning

| Lexicon | What it counts | Source |
|---|---|---|
| Excess model vocabulary | delve, underscore, showcase, pivotal, robust… per 1,000 words | Kobak et al., *Science Advances* 2025, the list the `dellm` skill uses |
| The guidance's own lists | puffery, hedges, intensifiers, summary closers ("in conclusion"), banned words | `skills/dellm/SKILL.md` and the guidance levels; Substrate already ships these lists |
| Person and address | rates of "you", "I", "we"; vocatives | Checks "Unaddressed prose" directly |
| Function words | The profile of the ~100–300 most common function words | Classic stylometry (Burrows' Delta); separates one model's voice from another's |
| Readability | Flesch reading ease, Flesch–Kincaid grade | Syllable counting by rule and table; old and crude, but deterministic |

## What the recent literature says these measures detect

- **AI writing has a stylometric footprint.** Across 8 models and 5 domains, a small set of features, mainly entropy and lexical diversity, consistently separates model-written text from human writing (Shan, Lee & Hao, arXiv 2608.27855). The same features did not separate *edited* text, so generation and editing leave different traces.
- **Instruction tuning narrows the range.** Newer instruction-tuned models show reduced syntactic and, especially, lexical diversity against older models and against news text, measured with diversity indices from ecology and information theory (Gude et al., arXiv 2605.06030).

Both bear on Substrate directly. The guidance levels aim to move output away from that footprint, and these are the measures that see the footprint.

## Using them to compare guidance levels

- **The question.** Does each level change the output language, and does it change task success?
- **The design.** The assay holds the model and the task constant and varies only the level (`harness`, low, medium, high).
- **Two readouts per run.**
  - Task success, scored the way the assay already scores it.
  - The language profile of every reply: kind 1 plus kind 2.
- **Comparisons.** Each metric's distribution per level, with effect sizes. Profiles across models: a level may shift a strong model and a weak one differently.
- **Length.** Length confounds almost every diversity measure. Report it, compare within length bands, and prefer MATTR or fixed-window measures for reply-level comparison.
- **Sample size.** Single replies are noisy. The project's power finding stands: equivalence claims need on the order of 90–360 paired runs, not 10.

## Using them in Substrate, on every input and output

- **What to measure.** The record already holds every text: `PromptComposed` (`text` and `system`) is the exact input, and `ModelReply.text` is the output. Every metric above is a pure function of those strings. Their tools' arguments and results are optional extra channels.
- **Shape: a projection first.** Compute the profile as a projection over the record, like `narrate` or `summary`: deterministic, replayable, and computable for any past session with nothing new written. Add a recorded event (say, `LanguageProfile` per `ModelReply`) only if a running view or an alert needs it live, so the profile sits beside the reply it describes.
- **Running track.** Keep rolling statistics per driver, per guidance level and per session. Some measures fit one reply (size, rhythm, compression, format, lexicon rates). Others need a session's worth of text (Zipf, Heaps, burstiness, Hurst).
- **Drift.**
  - **Baseline.** Each driver and level has a baseline distribution per metric, built from past sessions.
  - **Distribution tests.** The population stability index (common thresholds: below 0.1 stable, 0.1–0.25 worth a look, above 0.25 significant drift) or a Kolmogorov–Smirnov test compare a recent window with that baseline.
  - **Shifts in a stream.** A sequential change detector (CUSUM or Page–Hinkley) catches a step change in a session's stream of replies. For example, the em-dash rate jumps after a driver update, or replies grow uniform in rhythm halfway through a long session.
- **Alerts.** A crossed threshold writes a warning on the record, as `SessionWarning` does today. It can show in the transcript and the graph, and trigger anything else a topology attaches.
- **Inputs too.** The same profile on `PromptComposed` shows what Substrate itself sends. A guidance edit, a bundle change or growing history then appears as a measured change in the input next to the output's response.

## Costs and limits, stated plainly

- **Kind 1 and kind 2 are cheap.** Each is milliseconds per reply in pure Python, with no model calls. Compression uses `zlib` from the standard library. MATTR and MTLD are short functions. The lexicons are already in the repository.
- **Short replies limit what is meaningful.** A two-sentence reply supports size, format and lexicon counts, not Zipf or Hurst. The profile marks each measure's minimum length and reports nothing below it.
- **These measures describe form, not quality.** A drop in the excess-vocabulary rate means fewer of those words, not better writing. They are instruments for seeing change, read beside task success.

## Sources

- Covington, M. A. & McFall, J. D. (2010), MATTR; McCarthy, P. M. & Jarvis, S. (2010), MTLD. Definitions as given by the koRpus documentation ([lex.div methods](https://rdrr.io/cran/koRpus/man/lex.div-methods.html)) and the `lexicalrichness` package ([docs](https://lexicalrichness.readthedocs.io/en/latest/example.html)).
- Bestgen, Y., "Estimating Lexical Diversity Using the Moving Average Type-Token Ratio (MATTR): Pros and Cons" (preprint, [PDF](https://perso.uclouvain.be/yves.bestgen/images/RMAL24.pdf)); read: abstract and introduction.
- Goh, K.-I. & Barabási, A.-L. (2008), "Burstiness and memory in complex systems", *EPL* ([arXiv physics/0610233](https://arxiv.org/pdf/physics/0610233)).
- Altmann, E. G., Pierrehumbert, J. B. & Motter, A. E. (2009), "Beyond Word Frequency: Bursts, Lulls, and Scaling in the Temporal Distributions of Words", *PLoS ONE* ([PMC2770836](https://pmc.ncbi.nlm.nih.gov/articles/PMC2770836)).
- "Fractal Illusions: An Experimental Study of Long-Range Sentence-Length Correlations in Randomly Generated Natural Language Texts" ([arXiv 2508.19782](https://arxiv.org/abs/2508.19782)); read: abstract.
- Long-range correlations and DFA on sentence lengths: [PMC5029871](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5029871/), [arXiv 1212.3171](https://arxiv.org/pdf/1212.3171).
- Zipf, Heaps and entropy rate: [arXiv 1412.3336](https://arxiv.org/pdf/1412.3336), [arXiv 2411.10227](https://arxiv.org/pdf/2411.10227).
- Shan, Z., Lee, Y. & Hao, S., "AI Writers Have a Consistent Stylometric Footprint, but AI Editors Do Not" ([arXiv 2608.27855](https://arxiv.org/abs/2608.27855)); read: abstract.
- Gude, A. et al., "More Aligned, Less Diverse? Analyzing the Grammar and Lexicon of Two Generations of LLMs" ([arXiv 2605.06030](https://arxiv.org/abs/2605.06030)); read: abstract.
- Kobak, D. et al. (2025), excess vocabulary, *Science Advances*, as cited in `skills/dellm/SKILL.md` (not re-read for this note).
- Population stability index thresholds, as stated by monitoring vendors' documentation ([FutureAGI glossary](https://futureagi.com/glossary/population-stability-index-psi/)); vendor material, not a study.

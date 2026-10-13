# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""What every profile measure is called, counted in and means (sprint K312).

One entry per measure `profile()` returns. The app reads this table (generated into
`web/vm/language_measures.gen.ts`) for lane names, units, display ranges and the two-sentence
explanation every header and mark shows on hover. `Group` names the setting a measure is meant to
answer to; `Family` places the other measures for the full page.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class Group(StrEnum):
    """The setting a watched measure is meant to answer to; OTHER for the rest."""

    LENGTH = "length"
    TONE = "tone"
    GUIDANCE = "guidance"
    OTHER = "other"


class Family(StrEnum):
    """Research round 5's families, the order of the full page."""

    SIZE = "size and rhythm"
    DIVERSITY = "lexical diversity"
    FREQUENCY = "frequency structure"
    INFORMATION = "information"
    REPETITION = "repetition and burstiness"
    LONG_RANGE = "long-range structure"
    FORMAT = "format"
    READABILITY = "readability"
    LEXICON = "word lists"
    LIWC = "LIWC2007 categories"
    PADDING = "padding"
    RELATION = "the user's text and the reply"


@dataclass(frozen=True, slots=True)
class Measure:
    name: str  # the profile key
    short: str  # the lane header
    unit: str
    family: Family
    group: Group
    low: float  # the typical display range; a value past it draws to the edge
    high: float
    explanation: str  # two sentences at most
    # A count that grows with the text (words, sentences): a window's value is divided by the
    # texts in the window to read as a per-text average beside each text's own.
    count: bool = False


PER_K: Final = "per 1,000 words"


def _m(
    name: str,
    short: str,
    unit: str,
    family: Family,
    low: float,
    high: float,
    explanation: str,
    group: Group = Group.OTHER,
) -> Measure:
    count = name in ("tokens", "words", "sentences", "paragraphs")
    return Measure(name, short, unit, family, group, low, high, explanation, count)


_F, _G = Family, Group
_ENTRIES: Final[tuple[Measure, ...]] = (
    # size and rhythm
    _m(
        "tokens",
        "tokens",
        "tokens",
        _F.SIZE,
        0,
        800,
        "Every token in the text: words, code spans, links and email addresses.",
    ),
    _m(
        "words",
        "words",
        "words",
        _F.SIZE,
        0,
        800,
        "How long the text is, in words; code, links and email addresses are not counted. The length setting is meant to move it.",
        _G.LENGTH,
    ),
    _m(
        "sentences",
        "sentences",
        "sentences",
        _F.SIZE,
        0,
        40,
        "Sentences in paragraphs, list items and quotes; headings and table cells are not sentences.",
    ),
    _m(
        "paragraphs",
        "paragraphs",
        "paragraphs",
        _F.SIZE,
        0,
        20,
        "Blocks of prose separated by blank lines.",
    ),
    _m(
        "sentence_length_mean",
        "sent. length",
        "words",
        _F.SIZE,
        0,
        40,
        "The average number of words in a sentence. The length and guidance settings can move it.",
        _G.LENGTH,
    ),
    _m(
        "sentence_length_sd",
        "sent. spread",
        "words",
        _F.SIZE,
        0,
        20,
        "How much sentence lengths vary around their average (standard deviation).",
    ),
    _m(
        "sentence_length_cv",
        "sent. rhythm",
        "ratio",
        _F.SIZE,
        0,
        1.5,
        "Sentence-length spread divided by the average. Low means every sentence is about as long as the last.",
    ),
    # lexical diversity
    _m(
        "ttr",
        "TTR",
        "ratio",
        _F.DIVERSITY,
        0,
        1,
        "Distinct words over all words. It falls as a text grows, so compare it only between texts of the same length.",
    ),
    _m(
        "mattr",
        "MATTR",
        "ratio",
        _F.DIVERSITY,
        0,
        1,
        "Distinct words per 100-word window, averaged along the text (Covington and McFall 2010). Higher means a wider vocabulary.",
    ),
    _m(
        "mtld",
        "MTLD",
        "words",
        _F.DIVERSITY,
        0,
        200,
        "How many words, on average, before the running share of distinct words falls to 0.72 (McCarthy and Jarvis 2010). Higher means a wider vocabulary.",
    ),
    _m(
        "hdd",
        "HD-D",
        "ratio",
        _F.DIVERSITY,
        0,
        1,
        "The expected share of distinct words in a random draw of 42 (McCarthy and Jarvis 2007). Higher means a wider vocabulary.",
    ),
    # frequency structure
    _m(
        "zipf_alpha",
        "Zipf α",
        "exponent",
        _F.FREQUENCY,
        1,
        3,
        "The slope of the word-frequency distribution, fitted as a power law. Needs 3,200 words.",
    ),
    _m(
        "zipf_s",
        "Zipf s",
        "exponent",
        _F.FREQUENCY,
        0,
        2,
        "The rank-frequency exponent; about 1 for typical English. Needs 3,200 words.",
    ),
    _m(
        "zipf_xmin",
        "Zipf xmin",
        "count",
        _F.FREQUENCY,
        0,
        5,
        "The smallest word frequency the Zipf fit includes.",
    ),
    _m(
        "zipf_types",
        "Zipf types",
        "types",
        _F.FREQUENCY,
        0,
        2000,
        "Distinct words the Zipf fit used.",
    ),
    _m(
        "heaps_beta",
        "Heaps β",
        "exponent",
        _F.FREQUENCY,
        0,
        1,
        "How fast new words keep appearing as the text grows; 1 means every word is new. Needs 800 words.",
    ),
    _m(
        "heaps_k",
        "Heaps K",
        "scale",
        _F.FREQUENCY,
        0,
        50,
        "The scale of the vocabulary-growth fit.",
    ),
    # information
    _m(
        "entropy",
        "entropy",
        "bits per word",
        _F.INFORMATION,
        0,
        12,
        "How unpredictable the next word is, from the text's own word frequencies. Needs 3,200 words; compare only equal lengths.",
    ),
    _m(
        "compression_ratio",
        "compress",
        "ratio",
        _F.INFORMATION,
        0,
        1,
        "Compressed size over raw size (zlib). Lower means more repetitive text; compare only texts of equal length.",
    ),
    # repetition and burstiness
    _m(
        "repeated_ngram_rate",
        "repeats",
        "share",
        _F.REPETITION,
        0,
        1,
        "The share of three-word phrases that occur more than once in the text. High means boilerplate or loops.",
    ),
    _m(
        "burstiness_mean",
        "bursty",
        "B",
        _F.REPETITION,
        -1,
        1,
        "Whether repeated words come in clusters (above 0), at random (near 0) or evenly spaced (−1), over words seen 20 times or more.",
    ),
    _m(
        "burstiness_words",
        "bursty n",
        "words",
        _F.REPETITION,
        0,
        50,
        "Words seen often enough (20 times) to measure their burstiness.",
    ),
    # long-range structure
    _m(
        "dfa_alpha",
        "DFA α",
        "exponent",
        _F.LONG_RANGE,
        0,
        1.5,
        "Long-range structure in sentence lengths: 0.5 for no memory, higher when long sentences follow long ones. Needs 400 sentences.",
    ),
    # format
    _m(
        "format_headings", "headings", PER_K, _F.FORMAT, 0, 30, "Markdown headings per 1,000 words."
    ),
    _m(
        "format_list_items",
        "lists",
        PER_K,
        _F.FORMAT,
        0,
        60,
        "List items per 1,000 words. The guidance texts prefer prose to lists.",
        _G.GUIDANCE,
    ),
    _m("format_table_rows", "table rows", PER_K, _F.FORMAT, 0, 60, "Table rows per 1,000 words."),
    _m(
        "format_code_blocks",
        "code blocks",
        PER_K,
        _F.FORMAT,
        0,
        20,
        "Fenced code blocks per 1,000 words.",
    ),
    _m(
        "format_code_spans",
        "code spans",
        PER_K,
        _F.FORMAT,
        0,
        60,
        "Inline code spans per 1,000 words.",
    ),
    _m(
        "format_bold_spans",
        "bold",
        PER_K,
        _F.FORMAT,
        0,
        30,
        "Bold phrases per 1,000 words. The guidance texts ask for bold only where it marks something.",
        _G.GUIDANCE,
    ),
    _m(
        "format_em_dashes",
        "em-dash",
        PER_K,
        _F.FORMAT,
        0,
        20,
        "Em-dashes (—) per 1,000 words. The guidance texts ask for them sparingly.",
        _G.GUIDANCE,
    ),
    _m(
        "format_exclamations",
        "exclaim",
        PER_K,
        _F.FORMAT,
        0,
        10,
        "Exclamation marks per 1,000 words. The dry tone asks for none.",
        _G.TONE,
    ),
    _m(
        "format_questions",
        "questions",
        PER_K,
        _F.FORMAT,
        0,
        30,
        "Sentences ending in a question mark, per 1,000 words.",
    ),
    _m("format_urls", "links", PER_K, _F.FORMAT, 0, 20, "Links per 1,000 words."),
    # readability
    _m(
        "flesch_reading_ease",
        "reading ease",
        "score",
        _F.READABILITY,
        0,
        100,
        "Flesch reading ease (1948): higher is easier; 60–70 is plain English. From sentence length and syllables per word.",
    ),
    _m(
        "flesch_kincaid_grade",
        "grade",
        "US grade",
        _F.READABILITY,
        0,
        20,
        "Flesch–Kincaid grade level (1975): the school grade a reader needs.",
    ),
    # word lists
    _m(
        "rate_kobak_style",
        "LLM words",
        PER_K,
        _F.LEXICON,
        0,
        10,
        "Words whose use in published writing jumped after language models arrived (“delve”, “underscore”, “pivotal”), from Kobak and colleagues (2025). The guidance texts ask the model to avoid them.",
        _G.GUIDANCE,
    ),
    _m(
        "rate_kobak_style_rare",
        "LLM rare",
        PER_K,
        _F.LEXICON,
        0,
        10,
        "The 291 rarer words of Kobak and colleagues' list (2025), whose jump was largest relative to their use.",
    ),
    _m(
        "rate_hedges_hyland",
        "hedges",
        PER_K,
        _F.LEXICON,
        0,
        20,
        "Words that soften a claim (“may”, “perhaps”, “likely”), from Hyland's list (2005). The blunt tone asks the model to hedge only where the evidence is uncertain.",
        _G.TONE,
    ),
    _m(
        "rate_hedges_ulinski",
        "hedges (talk)",
        PER_K,
        _F.LEXICON,
        0,
        60,
        "Hedges of everyday speech (“kind of”, “I think”, “about”), from Ulinski and Hirschberg (2019).",
    ),
    _m(
        "rate_hedges_ulinski_with_forms",
        "hedges (talk+)",
        PER_K,
        _F.LEXICON,
        0,
        60,
        "The same everyday hedges, counting their inflected forms (“seems”, “thought”).",
    ),
    _m(
        "rate_boosters_hyland",
        "boosters",
        PER_K,
        _F.LEXICON,
        0,
        10,
        "Words that assert certainty (“clearly”, “in fact”, “definitely”), from Hyland's list (2005). Tone moves how often a claim is pressed this way.",
        _G.TONE,
    ),
    _m(
        "rate_amplifier_boosters",
        "amplify",
        PER_K,
        _F.LEXICON,
        0,
        30,
        "Degree words that scale up (“very”, “highly”, “strongly”), from Alshaar (2017).",
    ),
    _m(
        "rate_amplifier_maximizers",
        "maximize",
        PER_K,
        _F.LEXICON,
        0,
        10,
        "Degree words at the top of the scale (“absolutely”, “completely”, “totally”), from Alshaar (2017).",
    ),
    _m(
        "rate_contractions",
        "contractions",
        PER_K,
        _F.LEXICON,
        0,
        40,
        "Contractions such as “it's” and “don't”. The formal tone asks the model to write them out.",
        _G.TONE,
    ),
    # padding
    _m(
        "rate_padding_restatement",
        "restate (all)",
        PER_K,
        _F.PADDING,
        0,
        20,
        "Phrases that restate the question (“great question”, “you asked”), anywhere in the text.",
    ),
    _m(
        "rate_padding_background",
        "background (all)",
        PER_K,
        _F.PADDING,
        0,
        20,
        "Lead-ins before the answer (“it's worth noting”, “let's dive in”), anywhere in the text.",
    ),
    _m(
        "rate_padding_closing_summary",
        "summary (all)",
        PER_K,
        _F.PADDING,
        0,
        20,
        "Summary closers (“in summary”, “overall”), anywhere in the text.",
    ),
    _m(
        "rate_padding_offer_of_more",
        "offer (all)",
        PER_K,
        _F.PADDING,
        0,
        20,
        "Offers of more help (“let me know if”, “happy to help”), anywhere in the text.",
    ),
    _m(
        "rate_padding_restatement_opening",
        "restate",
        PER_K,
        _F.PADDING,
        0,
        20,
        "Phrases in the first two sentences that restate the question instead of answering it. The terse length asks the model to leave them out.",
        _G.LENGTH,
    ),
    _m(
        "rate_padding_background_opening",
        "background",
        PER_K,
        _F.PADDING,
        0,
        20,
        "Lead-ins in the first two sentences, before the answer starts. The terse length asks the model to leave out background.",
    ),
    _m(
        "rate_padding_closing_summary_closing",
        "summary",
        PER_K,
        _F.PADDING,
        0,
        20,
        "Summary closers in the last two sentences.",
    ),
    _m(
        "rate_padding_offer_of_more_closing",
        "offer",
        PER_K,
        _F.PADDING,
        0,
        20,
        "Offers of more help in the last two sentences (“let me know if”, “happy to help”). The terse length asks the model to leave them out.",
        _G.LENGTH,
    ),
    # LIWC2007
    _m(
        "rate_liwc_function_words",
        "function",
        PER_K,
        _F.LIWC,
        0,
        700,
        "Function words of every kind (pronouns, articles, prepositions, auxiliaries), from the LIWC2007 dictionary.",
    ),
    _m(
        "rate_liwc_personal_pronouns",
        "pers. pron.",
        PER_K,
        _F.LIWC,
        0,
        150,
        "Personal pronouns (“I”, “you”, “they”), LIWC2007; one of the nine style-matching categories.",
    ),
    _m(
        "rate_liwc_impersonal_pronouns",
        "impers. pron.",
        PER_K,
        _F.LIWC,
        0,
        120,
        "Impersonal pronouns (“it”, “that”, “anything”), LIWC2007; a style-matching category.",
    ),
    _m(
        "rate_liwc_articles",
        "articles",
        PER_K,
        _F.LIWC,
        0,
        120,
        "“a”, “an”, “the”, LIWC2007; a style-matching category.",
    ),
    _m(
        "rate_liwc_conjunctions",
        "conjunct.",
        PER_K,
        _F.LIWC,
        0,
        100,
        "Conjunctions (“and”, “but”, “because”), LIWC2007; a style-matching category.",
    ),
    _m(
        "rate_liwc_prepositions",
        "prepos.",
        PER_K,
        _F.LIWC,
        0,
        200,
        "Prepositions (“in”, “under”, “about”), LIWC2007; a style-matching category.",
    ),
    _m(
        "rate_liwc_auxiliary_verbs",
        "auxiliary",
        PER_K,
        _F.LIWC,
        0,
        150,
        "Auxiliary verbs (“is”, “was”, “shall”), LIWC2007; a style-matching category.",
    ),
    _m(
        "rate_liwc_high_frequency_adverbs",
        "adverbs",
        PER_K,
        _F.LIWC,
        0,
        100,
        "Common adverbs (“very”, “rather”, “just”), LIWC2007; a style-matching category.",
    ),
    _m(
        "rate_liwc_negations",
        "negations",
        PER_K,
        _F.LIWC,
        0,
        50,
        "Negations (“no”, “not”, “never”), LIWC2007; a style-matching category.",
    ),
    _m(
        "rate_liwc_quantifiers",
        "quantifiers",
        PER_K,
        _F.LIWC,
        0,
        60,
        "Quantifiers (“much”, “few”, “lots”), LIWC2007; a style-matching category.",
    ),
    _m(
        "rate_liwc_first_singular",
        "I",
        PER_K,
        _F.LIWC,
        0,
        80,
        "First person singular (“I”, “me”, “my”), LIWC2007.",
    ),
    _m(
        "rate_liwc_first_plural",
        "we",
        PER_K,
        _F.LIWC,
        0,
        60,
        "First person plural (“we”, “us”, “our”), LIWC2007.",
    ),
    _m(
        "rate_liwc_second_person",
        "you",
        PER_K,
        _F.LIWC,
        0,
        80,
        "Second person (“you”, “your”), LIWC2007: how often the text addresses its reader.",
    ),
    _m(
        "rate_liwc_third_singular",
        "he/she",
        PER_K,
        _F.LIWC,
        0,
        40,
        "Third person singular (“he”, “she”, “him”), LIWC2007.",
    ),
    _m(
        "rate_liwc_third_plural",
        "they",
        PER_K,
        _F.LIWC,
        0,
        40,
        "Third person plural (“they”, “them”), LIWC2007.",
    ),
    _m(
        "rate_liwc_tentative",
        "tentative",
        PER_K,
        _F.LIWC,
        0,
        60,
        "Tentative words (“maybe”, “perhaps”, “guess”), LIWC2007.",
    ),
    _m(
        "rate_liwc_certainty",
        "certainty",
        PER_K,
        _F.LIWC,
        0,
        40,
        "Words of certainty (“always”, “never”, “definitely”), LIWC2007.",
    ),
    _m(
        "rate_liwc_positive_emotion",
        "positive",
        PER_K,
        _F.LIWC,
        0,
        30,
        "Words of positive feeling (“great”, “love”, “happy”), from the LIWC2007 dictionary. The dry tone asks for no enthusiasm.",
        _G.TONE,
    ),
    _m("rate_liwc_swear_words", "swear", PER_K, _F.LIWC, 0, 10, "Swear words, LIWC2007."),
    _m(
        "rate_liwc_assent",
        "assent",
        PER_K,
        _F.LIWC,
        0,
        30,
        "Words of agreement (“yes”, “ok”, “cool”), LIWC2007.",
    ),
    _m(
        "rate_liwc_nonfluencies",
        "nonfluent",
        PER_K,
        _F.LIWC,
        0,
        10,
        "Nonfluencies (“um”, “er”), LIWC2007.",
    ),
    _m(
        "rate_liwc_fillers",
        "fillers",
        PER_K,
        _F.LIWC,
        0,
        10,
        "Fillers (“blah”, “like”), LIWC2007. Its multi-word fillers are written run together "
        "(“youknow”) and do not match the words apart.",
    ),
    # the relation between a user's message and the reply (stream "turns")
    _m(
        "length_ratio",
        "length ratio",
        "ratio",
        _F.RELATION,
        0,
        20,
        "Words in the reply for each word in the user's message.",
    ),
    _m(
        "lexical_echo",
        "echo",
        "share",
        _F.RELATION,
        0,
        1,
        "The share of the user's own content words the reply uses. 1 means every one of them.",
    ),
    _m(
        "phrase_copy_shared",
        "shared phrases",
        "phrases",
        _F.RELATION,
        0,
        20,
        "Four-word phrases the reply shares with the user's message.",
    ),
    _m(
        "phrase_copy_share",
        "copied",
        "share",
        _F.RELATION,
        0,
        1,
        "The share of the reply's four-word phrases that also occur in the user's message.",
    ),
    _m(
        "phrase_copy_longest_run",
        "longest copy",
        "words",
        _F.RELATION,
        0,
        20,
        "The longest run of words the reply copies from the user's message.",
    ),
    _m(
        "ncd",
        "distance",
        "NCD",
        _F.RELATION,
        0,
        1.2,
        "How different the two texts look to a compressor (Cilibrasi and Vitányi 2005): near 0 alike, near 1 unrelated.",
    ),
    _m(
        "lsm",
        "style match",
        "score",
        _F.RELATION,
        0,
        1,
        "How closely the reply's small words (pronouns, articles, prepositions) match the user's, from 0 to 1 (the categories of Ireland and colleagues, 2011). Needs 1,600 words on each side.",
    ),
    _m(
        "window_lsm",
        "style match (window)",
        "score",
        _F.RELATION,
        0,
        1,
        "Style matching over the latest 3,200 words of each side, where one turn is too short to measure it.",
    ),
)

CATALOG: Final[dict[str, Measure]] = {m.name: m for m in _ENTRIES}
# The relation measures the language page shows for the turns stream, in order.
RELATION_LANES: Final[tuple[str, ...]] = (
    "length_ratio",
    "lexical_echo",
    "phrase_copy_share",
    "phrase_copy_longest_run",
    "ncd",
    "window_lsm",
)

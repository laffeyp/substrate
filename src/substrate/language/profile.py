# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Every one-text measure of a text, with the parameters, preprocessing and lexicon versions it
was computed under (round 4: a stored value names everything needed to recompute it)."""

from __future__ import annotations

import hashlib
import json
import zlib
from collections import Counter
from dataclasses import asdict, dataclass
from functools import cache
from typing import Any, Final

from substrate.language import measures as m
from substrate.language.lexicon import (
    LexiconIndex,
    Matcher,
    is_contraction,
    load,
    provenance,
    word_runs,
)
from substrate.language.text import PREPROCESSING, Parsed, TokenKind, parse, words

LIBRARY_VERSION: Final = "0.2.0"

# Lexicon rates: measure name -> (lexicon, lists it unions).
RATES: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "kobak_style": ("kobak_style_2024", ("words",)),
    "kobak_style_rare": ("kobak_style_2024_rare", ("words",)),
    "hedges_hyland": ("hedges_hyland_2005", ("terms",)),
    "hedges_ulinski": ("hedges_ulinski_2019", ("relational", "propositional")),
    "hedges_ulinski_with_forms": ("hedges_ulinski_2019", ("relational", "propositional", "added")),
    "boosters_hyland": ("boosters_hyland_2005", ("terms",)),
    "amplifier_boosters": ("amplifiers_alshaar_2017", ("boosters",)),
    "amplifier_maximizers": ("amplifiers_alshaar_2017", ("maximizers",)),
    "padding_restatement": ("padding", ("restatement",)),
    "padding_background": ("padding", ("background",)),
    "padding_closing_summary": ("padding", ("closing_summary",)),
    "padding_offer_of_more": ("padding", ("offer_of_more",)),
}
LIWC_CATEGORIES: Final = (
    "function_words",
    "personal_pronouns",
    "impersonal_pronouns",
    "articles",
    "conjunctions",
    "prepositions",
    "auxiliary_verbs",
    "high_frequency_adverbs",
    "negations",
    "quantifiers",
    "first_singular",
    "first_plural",
    "second_person",
    "third_singular",
    "third_plural",
    "tentative",
    "certainty",
    "positive_emotion",
    "swear_words",
    "assent",
    "nonfluencies",
    "fillers",
)
# Padding that opens a reply is counted in its first sentences; padding that closes it, in its last.
OPENING: Final = ("padding_restatement", "padding_background")
CLOSING: Final = ("padding_closing_summary", "padding_offer_of_more")


@dataclass(frozen=True, slots=True)
class Params:
    mattr_window: int = 100
    mtld_threshold: float = 0.72
    hdd_draws: int = 42
    zipf_xmin: int = 1
    heaps_points: int = 20
    heaps_start: int = 10
    ngram: int = 3
    burst_min_occurrences: int = m.MIN_OCCURRENCES_BURSTINESS
    zlib_level: int = m.ZLIB_LEVEL
    padding_edge_sentences: int = 2


@cache
def _matchers() -> dict[str, Matcher]:
    out = {name: load(lex).matcher(*keys) for name, (lex, keys) in RATES.items()}
    liwc = load("liwc2007")
    out.update({f"liwc_{c}": liwc.matcher(c) for c in LIWC_CATEGORIES})
    return out


@cache
def _index() -> LexiconIndex:
    return LexiconIndex(_matchers())


@cache
def _padding_index() -> LexiconIndex:
    return LexiconIndex({n: _matchers()[n] for n in OPENING + CLOSING})


def lexicon_names() -> list[str]:
    return sorted({lex for lex, _ in RATES.values()} | {"liwc2007", "contractions"})


def profile(
    text: str, params: Params | None = None, parsed: Parsed | None = None
) -> dict[str, Any]:
    """All one-text measures of `text`, plus the partial counts that merge across windows."""
    p = params or Params()
    doc = parsed or parse(text)
    ws = words(doc)
    lengths = [sum(1 for t in s if t.kind is TokenKind.WORD) for s in doc.sentences]
    runs = word_runs(doc.units)
    n = len(ws)

    counts: dict[str, int] = _index().count(runs)
    freq = Counter(ws)
    counts["contractions"] = sum(c for w, c in freq.items() if is_contraction(w))
    edge = p.padding_edge_sentences
    first, last = word_runs(doc.sentences[:edge]), word_runs(doc.sentences[-edge:])
    opening, closing = _padding_index().count(first), _padding_index().count(last)
    for name in OPENING:
        counts[f"{name}_opening"] = opening[name]
    for name in CLOSING:
        counts[f"{name}_closing"] = closing[name]

    out: dict[str, Any] = {
        "tokens": len(doc.tokens),
        "words": n,
        "sentences": len(doc.sentences),
        "paragraphs": doc.format.paragraphs,
        **{f"sentence_length_{k}": v for k, v in m.rhythm(lengths).items()},
        "ttr": m.ttr(ws),
        "mattr": m.mattr(ws, p.mattr_window),
        "mtld": m.mtld(ws, p.mtld_threshold) if n >= m.MIN_WORDS_MTLD else None,
        "hdd": m.hdd(ws, p.hdd_draws),
        **{
            f"zipf_{k}": (v if n >= m.MIN_WORDS_ZIPF else None)
            for k, v in m.zipf(ws, p.zipf_xmin).items()
        },
        **{
            f"heaps_{k}": (v if n >= m.MIN_WORDS_HEAPS else None)
            for k, v in m.heaps(ws, p.heaps_points, p.heaps_start).items()
        },
        "entropy": m.entropy(ws) if n >= m.MIN_WORDS_ENTROPY else None,
        "compression_ratio": m.compression_ratio(text, p.zlib_level),
        "repeated_ngram_rate": m.repeated_ngram_rate(runs, p.ngram),
        **{f"burstiness_{k}": v for k, v in m.burstiness(ws, p.burst_min_occurrences).items()},
        "dfa_alpha": (
            m.dfa([float(x) for x in lengths]) if len(lengths) >= m.MIN_SENTENCES_DFA else None
        ),
        **{f"format_{k}": v for k, v in m.format_rates(doc.format, n).items()},
        **m.readability(ws, len(doc.sentences)),
        **{f"rate_{k}": (1000 * v / n if n else None) for k, v in counts.items()},
    }
    instrument = {
        "params": asdict(p),
        "minimums": dict(m.MINIMUMS),
        "lexicons": provenance(lexicon_names()),
        "compressor": f"zlib {zlib.ZLIB_VERSION}",
    }
    return {
        "library": LIBRARY_VERSION,
        "instrument_sha256": instrument_sha256(instrument),
        "preprocessing": PREPROCESSING,
        "params": asdict(p),
        "minimums": dict(m.MINIMUMS),
        "lexicons": provenance(lexicon_names()),
        "compressor": f"zlib {zlib.ZLIB_VERSION}",
        "measures": out,
        "partials": {
            "freq": dict(freq),
            "sentence_lengths": lengths,
            "lexicon": counts,
            "format": asdict(doc.format),
        },
    }


def instrument_sha256(instrument: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of the parameters, window minimums, lexicon versions and
    compressor: one string that names the instrument a value was measured with (§ W.2)."""
    text = json.dumps(instrument, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

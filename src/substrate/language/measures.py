# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Form measures on one text (round 4, kind 1), each to its published definition.

Every function is pure. Lexical measures take the word tokens of substrate-text-1 (`text.words`),
in order. A function returns None when its input is shorter than the measure is defined for.
docs/language/measures.md names each measure's source and the reference implementation its
tests compare against.
"""

from __future__ import annotations

import gzip
import math
import re
import zlib
from collections import Counter
from collections.abc import Sequence
from functools import cache
from importlib import resources

from substrate.language.text import FormatCounts

ZLIB_LEVEL = 9

# The shortest window each measure is reported for (sprint 306, docs/language/windows.md): words,
# except DFA (sentences) and burstiness (occurrences of each word counted). MTLD's 100 words is
# Koizumi & In'nami (2012); the rest were measured. Compression ratio has no minimum: it falls with
# length up to 6,400 words, so its values are compared only at equal lengths.
MIN_WORDS_MTLD = 100
MIN_WORDS_ENTROPY = 3200
MIN_WORDS_ZIPF = 3200
MIN_WORDS_HEAPS = 800
MIN_WORDS_LSM = 1600
MIN_SENTENCES_DFA = 400
MIN_OCCURRENCES_BURSTINESS = 20
MINIMUMS = {
    "mtld_words": MIN_WORDS_MTLD,
    "entropy_words": MIN_WORDS_ENTROPY,
    "zipf_words": MIN_WORDS_ZIPF,
    "heaps_words": MIN_WORDS_HEAPS,
    "lsm_words": MIN_WORDS_LSM,
    "dfa_sentences": MIN_SENTENCES_DFA,
    "burstiness_occurrences": MIN_OCCURRENCES_BURSTINESS,
}


# ---- size and rhythm ------------------------------------------------------------------------


def rhythm(sentence_lengths: Sequence[int]) -> dict[str, float | None]:
    """Mean sentence length in words, its population standard deviation and coefficient of
    variation."""
    n = len(sentence_lengths)
    if n == 0:
        return {"mean": None, "sd": None, "cv": None}
    mean = sum(sentence_lengths) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in sentence_lengths) / n)
    return {"mean": mean, "sd": sd, "cv": sd / mean if mean else None}


# ---- lexical diversity ----------------------------------------------------------------------


def ttr(words: Sequence[str]) -> float | None:
    return len(set(words)) / len(words) if words else None


def mattr(words: Sequence[str], window: int = 100) -> float | None:
    """Covington & McFall (2010): the mean TTR of every window of `window` tokens, moved one token
    at a time. Undefined for a text shorter than the window."""
    n = len(words)
    if n < window or window < 1:
        return None
    counts: Counter[str] = Counter(words[:window])
    total = len(counts)
    for i in range(window, n):
        out, new = words[i - window], words[i]
        counts[out] -= 1
        if counts[out] == 0:
            del counts[out]
        counts[new] += 1
        total += len(counts)
    return total / ((n - window + 1) * window)


def _mtld_pass(words: Sequence[str], threshold: float) -> float | None:
    factors = 0.0
    types: set[str] = set()
    count = 0
    ratio = 1.0
    for w in words:
        count += 1
        types.add(w)
        ratio = len(types) / count
        if ratio <= threshold:
            factors += 1
            types, count = set(), 0
    if count > 0:
        factors += (1 - ratio) / (1 - threshold)
    return len(words) / factors if factors > 0 else None


def mtld(words: Sequence[str], threshold: float = 0.72) -> float | None:
    """McCarthy & Jarvis (2010): text length over the number of factors, a factor ending when the
    running TTR falls to `threshold`; the last, partial factor counts (1 - TTR) / (1 - threshold).
    The mean of a forward and a backward pass. None when no factor forms (every word distinct)."""
    if not words:
        return None
    forward = _mtld_pass(words, threshold)
    backward = _mtld_pass(list(reversed(words)), threshold)
    if forward is None or backward is None:
        return None
    return (forward + backward) / 2


def hdd(words: Sequence[str], draws: int = 42) -> float | None:
    """McCarthy & Jarvis (2007): for each type, the chance it appears in a random draw of `draws`
    tokens without replacement (hypergeometric), divided by `draws`, summed over types."""
    n = len(words)
    if n < draws:
        return None
    total = 0.0
    # Types with the same frequency share one probability.
    for freq, types in Counter(Counter(words).values()).items():
        # P(0 of this type in the draw) = C(n - f, d) / C(n, d) = prod (n - f - i) / (n - i).
        p0 = 1.0
        for i in range(draws):
            if n - freq - i <= 0:
                p0 = 0.0
                break
            p0 *= (n - freq - i) / (n - i)
        total += types * (1 - p0) / draws
    return total


# ---- frequency structure ----------------------------------------------------------------------


def zipf(words: Sequence[str], xmin: int = 1) -> dict[str, float | None]:
    """The word-frequency distribution fitted as a discrete power law P(f) ~ f^-alpha by maximum
    likelihood, with Clauset, Shalizi & Newman's (2009, eq. 3.7) approximation
    alpha = 1 + n / sum ln(f / (xmin - 1/2)), over types with frequency >= xmin. The rank-frequency
    (Zipf) exponent is s = 1 / (alpha - 1)."""
    freqs = [f for f in Counter(words).values() if f >= xmin]
    if len(freqs) < 2:
        return {"alpha": None, "s": None, "xmin": float(xmin), "types": float(len(freqs))}
    denom = sum(math.log(f / (xmin - 0.5)) for f in freqs)
    alpha = 1 + len(freqs) / denom
    return {"alpha": alpha, "s": 1 / (alpha - 1), "xmin": float(xmin), "types": float(len(freqs))}


def _ols(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx
    return slope, my - slope * mx


def heaps(words: Sequence[str], points: int = 20, start: int = 10) -> dict[str, float | None]:
    """Heaps' law V(n) = K n^beta, fitted by least squares on log V against log n at `points`
    token counts spaced evenly in log n from `start` to the text's length."""
    n = len(words)
    if n < start * 2:
        return {"beta": None, "k": None}
    marks = sorted(
        {
            round(math.exp(math.log(start) + i * (math.log(n) - math.log(start)) / (points - 1)))
            for i in range(points)
        }
    )
    seen: set[str] = set()
    vocab: dict[int, int] = {}
    want = set(marks)
    for i, w in enumerate(words, 1):
        seen.add(w)
        if i in want:
            vocab[i] = len(seen)
    xs = [math.log(m) for m in marks]
    ys = [math.log(vocab[m]) for m in marks]
    beta, intercept = _ols(xs, ys)
    return {"beta": beta, "k": math.exp(intercept)}


# ---- information --------------------------------------------------------------------------------


def entropy(words: Sequence[str]) -> float | None:
    """Unigram Shannon entropy, bits per word, from the text's own frequencies (plug-in)."""
    n = len(words)
    if n == 0:
        return None
    return -sum((c / n) * math.log2(c / n) for c in Counter(words).values())


def compression_ratio(text: str, level: int = ZLIB_LEVEL) -> float | None:
    """zlib's compressed length over the UTF-8 length of the text (lower is more compressible)."""
    raw = text.encode("utf-8")
    return len(zlib.compress(raw, level)) / len(raw) if raw else None


# ---- repetition and burstiness --------------------------------------------------------------------


def ngrams(runs: Sequence[Sequence[str]], n: int) -> list[tuple[str, ...]]:
    """Word n-grams inside each run; none crosses a sentence, heading, cell or code token."""
    return [tuple(r[i : i + n]) for r in runs for i in range(len(r) - n + 1)]


def repeated_ngram_rate(runs: Sequence[Sequence[str]], n: int = 3) -> float | None:
    """The share of n-gram occurrences whose n-gram occurs more than once in the text."""
    grams = ngrams(runs, n)
    if not grams:
        return None
    counts = Counter(grams)
    return sum(c for c in counts.values() if c > 1) / len(grams)


def burstiness(words: Sequence[str], min_occurrences: int = 5) -> dict[str, float | None]:
    """Goh & Barabási (2008) B = (sd - mean) / (sd + mean) of the gaps between successive
    occurrences of a word (positions in words), as Altmann, Pierrehumbert & Motter (2009) apply it;
    the mean B over words with at least `min_occurrences` occurrences."""
    positions: dict[str, list[int]] = {}
    for i, w in enumerate(words):
        positions.setdefault(w, []).append(i)
    values: list[float] = []
    for pos in positions.values():
        if len(pos) < max(min_occurrences, 3):
            continue
        gaps = [b - a for a, b in zip(pos, pos[1:], strict=False)]
        mean = sum(gaps) / len(gaps)
        sd = math.sqrt(sum((g - mean) ** 2 for g in gaps) / len(gaps))
        values.append((sd - mean) / (sd + mean))
    if not values:
        return {"mean": None, "words": 0.0}
    return {"mean": sum(values) / len(values), "words": float(len(values))}


# ---- long-range structure ----------------------------------------------------------------------


def dfa_windows(n: int, low: int = 4, factor: float = 1.2) -> list[int]:
    """Window sizes from `low` to n // 4, each about `factor` times the last."""
    out: list[int] = []
    size = float(low)
    while int(size) <= n // 4:
        if not out or int(size) != out[-1]:
            out.append(int(size))
        size *= factor
    return out


def dfa(series: Sequence[float], windows: Sequence[int] | None = None) -> float | None:
    """Detrended fluctuation analysis, order 1 (Peng et al. 1994): the profile is the cumulative
    sum of the mean-subtracted series; it is cut into non-overlapping windows of each size, a line
    is fitted in each, and F(n) is the root mean square of the residuals over all windows. alpha is
    the least-squares slope of log F(n) on log n."""
    n = len(series)
    sizes = list(windows) if windows is not None else dfa_windows(n)
    if len(sizes) < 2:
        return None
    mean = sum(series) / n
    profile: list[float] = []
    acc = 0.0
    for x in series:
        acc += x - mean
        profile.append(acc)
    logn: list[float] = []
    logf: list[float] = []
    for size in sizes:
        count = n // size
        if count < 1:
            continue
        sq = 0.0
        xs = list(range(size))
        for w in range(count):
            seg = profile[w * size : (w + 1) * size]
            slope, intercept = _ols(xs, seg) if size > 1 else (0.0, seg[0])
            sq += sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, seg, strict=True))
        f = math.sqrt(sq / (count * size))
        if f > 0:
            logn.append(math.log(size))
            logf.append(math.log(f))
    if len(logn) < 2:
        return None
    return _ols(logn, logf)[0]


# ---- format --------------------------------------------------------------------------------------


def format_rates(counts: FormatCounts, word_count: int) -> dict[str, float | None]:
    """Each markup count per 1,000 word tokens."""
    fields = (
        "headings",
        "list_items",
        "table_rows",
        "code_blocks",
        "code_spans",
        "bold_spans",
        "em_dashes",
        "exclamations",
        "questions",
        "urls",
    )
    if word_count == 0:
        return dict.fromkeys(fields)
    return {f: 1000 * getattr(counts, f) / word_count for f in fields}


# ---- readability ----------------------------------------------------------------------------------


@cache
def _cmu() -> dict[str, int]:
    path = resources.files("substrate.language").joinpath("lexicons", "syllables_cmudict.tsv.gz")
    out: dict[str, int] = {}
    for line in gzip.decompress(path.read_bytes()).decode("utf-8").splitlines():
        if line and not line.startswith("#"):
            word, n = line.split("\t")
            out[word] = int(n)
    return out


_VOWELS = re.compile(r"[aeiouy]+")


def syllables(word: str) -> int:
    """Syllables of one word token: the CMU Pronouncing Dictionary's count when the word is in it,
    else one per vowel group, less a silent final e (not after l), at least one."""
    known = _cmu().get(word)
    if known is not None:
        return known
    letters = re.sub(r"[^a-z]", "", word)
    if not letters:
        return 1
    count = len(_VOWELS.findall(letters))
    if letters.endswith("e") and not letters.endswith("le") and count > 1:
        count -= 1
    return max(count, 1)


def readability(words: Sequence[str], sentence_count: int) -> dict[str, float | None]:
    """Flesch (1948) reading ease 206.835 - 1.015 (words/sentences) - 84.6 (syllables/words), and
    the Flesch-Kincaid grade (Kincaid et al. 1975) 0.39 (words/sentences) + 11.8
    (syllables/words) - 15.59."""
    if not words or sentence_count == 0:
        return {"flesch_reading_ease": None, "flesch_kincaid_grade": None}
    wps = len(words) / sentence_count
    spw = sum(syllables(w) for w in words) / len(words)
    return {
        "flesch_reading_ease": 206.835 - 1.015 * wps - 84.6 * spw,
        "flesch_kincaid_grade": 0.39 * wps + 11.8 * spw - 15.59,
    }

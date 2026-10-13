# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Measures of the relation between a user's text and the model's (round 4). None judges whether
the reply answered well; each is form or lexicon lookup."""

from __future__ import annotations

import math
import zlib
from collections.abc import Mapping, Sequence
from functools import cache

from substrate.language.lexicon import LIWC2007, Matcher, load, word_runs
from substrate.language.measures import MIN_WORDS_LSM, ZLIB_LEVEL, ngrams
from substrate.language.text import Parsed, words


def length_ratio(user: Parsed, reply: Parsed) -> float | None:
    """Reply word tokens over user word tokens."""
    u = len(words(user))
    return len(words(reply)) / u if u else None


@cache
def _function_words() -> Matcher:
    return load(LIWC2007).matcher("function_words")


@cache
def _lsm_matchers() -> dict[str, Matcher]:
    lex = load(LIWC2007)
    return {c: lex.matcher(c) for c in lex.lsm}


def content_types(parsed: Parsed) -> set[str]:
    """Word types that are not LIWC2007 function words."""
    fw = _function_words()
    return {w for w in words(parsed) if not fw.matches([w])}


def lexical_echo(user: Parsed, reply: Parsed) -> float | None:
    """|U ∩ M| / |U| over content-word types: how many of the user's own content words the reply
    uses. Recall, asymmetric by construction."""
    u = content_types(user)
    return len(u & content_types(reply)) / len(u) if u else None


def phrase_copy(user: Parsed, reply: Parsed, n: int = 4) -> dict[str, float | None]:
    """Shared word n-grams (distinct n-grams of the reply also in the user's text), their share of
    the reply's distinct n-grams, and the longest run of word tokens the two texts share."""
    u_runs, r_runs = word_runs(user.units), word_runs(reply.units)
    u_grams, r_grams = set(ngrams(u_runs, n)), set(ngrams(r_runs, n))
    shared = len(u_grams & r_grams)
    return {
        "shared": float(shared),
        "share": shared / len(r_grams) if r_grams else None,
        "longest_run": float(_longest_common_run(u_runs, r_runs)),
    }


def _longest_common_run(a_runs: Sequence[Sequence[str]], b_runs: Sequence[Sequence[str]]) -> int:
    """Longest common contiguous token run; no run crosses a unit boundary in either text."""
    best = 0
    for a in a_runs:
        for b in b_runs:
            prev = [0] * (len(b) + 1)
            for x in a:
                cur = [0] * (len(b) + 1)
                for j, y in enumerate(b, 1):
                    if x == y:
                        cur[j] = prev[j - 1] + 1
                        best = max(best, cur[j])
                prev = cur
    return best


def ncd(x: str, y: str, level: int = ZLIB_LEVEL) -> float | None:
    """Cilibrasi & Vitányi (2005): (C(xy) - min(C(x), C(y))) / max(C(x), C(y)), C = zlib length.
    Deflate looks back 32 KiB (RFC 1951), so for a joined pair longer than that it understates
    similarity."""
    bx, by = x.encode("utf-8"), y.encode("utf-8")
    if not bx or not by:
        return None
    cx, cy = len(zlib.compress(bx, level)), len(zlib.compress(by, level))
    cxy = len(zlib.compress(bx + by, level))
    return (cxy - min(cx, cy)) / max(cx, cy)


def category_percentages(parsed: Parsed) -> dict[str, float] | None:
    """Each LSM category's matches as a percentage of all word tokens (LIWC's p)."""
    total = len(words(parsed))
    if total == 0:
        return None
    runs = word_runs(parsed.units)
    return {
        cat: 100 * sum(len(m.matches(r)) for r in runs) / total
        for cat, m in _lsm_matchers().items()
    }


def lsm(user: Parsed, reply: Parsed, min_words: int = MIN_WORDS_LSM) -> dict[str, float | None]:
    """Language style matching (Ireland et al. 2011): per category
    1 - |p1 - p2| / (p1 + p2 + 0.0001), and their mean over the nine categories. None when either
    text has fewer than `min_words` words; the caller widens the window to reach it
    (docs/language/windows-r2.md)."""
    if min(len(words(user)), len(words(reply))) < min_words:
        return {"lsm": None}
    pu, pr = category_percentages(user), category_percentages(reply)
    if pu is None or pr is None:
        return {"lsm": None}
    per = {c: 1 - abs(pu[c] - pr[c]) / (pu[c] + pr[c] + 0.0001) for c in pu}
    return {"lsm": sum(per.values()) / len(per), **{f"lsm_{c}": v for c, v in per.items()}}


def profile_difference(
    user: Mapping[str, float | None], reply: Mapping[str, float | None]
) -> dict[str, float]:
    """The model's value minus the user's, for every measure both have."""
    out: dict[str, float] = {}
    for k in user.keys() & reply.keys():
        u, r = user[k], reply[k]
        if u is not None and r is not None:
            out[k] = r - u
    return out


def lagged_correlation(
    leader: Sequence[float], follower: Sequence[float], lag: int = 1
) -> float | None:
    """Pearson correlation of the change in `follower` at turn t with the change in `leader` at
    turn t - lag: whether one side moves after the other (round 4, convergence)."""
    dl = [b - a for a, b in zip(leader, leader[1:], strict=False)]
    df = [b - a for a, b in zip(follower, follower[1:], strict=False)]
    pairs = list(zip(dl[: len(dl) - lag], df[lag:], strict=False))
    if len(pairs) < 3:
        return None
    xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in pairs) / (sx * sy)

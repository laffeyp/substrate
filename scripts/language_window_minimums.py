# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Window minimums for the measures round 4 left as working values (sprint 306).

The criterion, fixed before anything was measured: a window of n words is long enough for a
measure when, over many windows of that length,
  (a) bias: the mean differs from the reference by at most 5% of the reference (relative
      measures) or 0.05 (measures bounded near [-1, 1]: burstiness, LSM, DFA alpha); and
  (b) spread: the standard deviation across windows is at most 10% of the reference, or 0.05
      for the bounded measures.
The minimum is the shortest length on the grid meeting both; if none does, the measure has no
minimum on this grid and values are compared only at equal lengths.

References: real text, windows of 6,400 words; DFA, the true alpha 0.5 of white noise;
burstiness, the B of a geometric gap distribution (no clustering), -1/(4 mu + ...) ~ 0.

Data: the 600 length-experiment replies (process/runs/assays/length_drift_2026-10-12_k299), each
model's replies joined in order and cut into contiguous, non-overlapping windows.

Usage: language_window_minimums.py   (prints markdown)
"""

from __future__ import annotations

import json
import math
import random
import statistics
from collections.abc import Callable
from pathlib import Path

from substrate.language import measures as m
from substrate.language import parse, words
from substrate.language import relation as rel

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "process/runs/assays/length_drift_2026-10-12_k299"
GRID = (25, 50, 100, 200, 400, 800, 1600, 3200)
REFERENCE = 6400
MAX_WINDOWS = 200
REL_BIAS, REL_SPREAD, ABS = 0.05, 0.10, 0.05


def streams() -> list[list[str]]:
    out = []
    for f in sorted(DATA.glob("*.jsonl")):
        ws: list[str] = []
        for line in f.open(encoding="utf-8"):
            ws.extend(words(parse(json.loads(line)["text"])))
        out.append(ws)
    return out


def windows(streams_: list[list[str]], n: int) -> list[list[str]]:
    out = [s[i : i + n] for s in streams_ for i in range(0, len(s) - n + 1, n)]
    return out[:: max(1, len(out) // MAX_WINDOWS)][:MAX_WINDOWS]


def judge(
    values: dict[int, list[float]], ref: float, bounded: bool
) -> tuple[int | None, list[str]]:
    rows, chosen = [], None
    for n in GRID:
        vs = values.get(n, [])
        if len(vs) < 2:
            rows.append(f"| {n} | — | — | — | — |")
            continue
        mean, sd = statistics.fmean(vs), statistics.stdev(vs)
        bias = abs(mean - ref) if bounded else abs(mean - ref) / abs(ref)
        spread = sd if bounded else sd / abs(ref)
        ok = bias <= (ABS if bounded else REL_BIAS) and spread <= (ABS if bounded else REL_SPREAD)
        if ok and chosen is None:
            chosen = n
        rows.append(f"| {n} | {len(vs)} | {mean:.4f} | {sd:.4f} | {'yes' if ok else 'no'} |")
    return chosen, rows


def real_text(
    name: str, f: Callable[[list[str]], float | None], ss: list[list[str]]
) -> tuple[str, int | None]:
    ref_vals = [v for w in windows(ss, REFERENCE) if (v := f(w)) is not None]
    ref = statistics.fmean(ref_vals)
    values = {n: [v for w in windows(ss, n) if (v := f(w)) is not None] for n in GRID}
    chosen, rows = judge(values, ref, bounded=False)
    head = f"### {name}\n\nReference: mean {ref:.4f} over {len(ref_vals)} windows of {REFERENCE} words.\n\n"
    table = "| words | windows | mean | SD | meets both |\n|---|---|---|---|---|\n" + "\n".join(
        rows
    )
    return head + table + f"\n\nMinimum: {chosen if chosen else 'none on the grid'}.\n", chosen


def lsm_pairs(ss: list[list[str]]) -> tuple[str, int | None]:
    """LSM between consecutive windows of the same model's text."""

    def pair_values(n: int) -> list[float]:
        ws = windows(ss, n)
        out = []
        for a, b in zip(ws[::2], ws[1::2], strict=False):
            v = rel.lsm(parse(" ".join(a)), parse(" ".join(b)), min_words=0)["lsm"]
            if v is not None:
                out.append(v)
        return out

    ref_vals = pair_values(REFERENCE)
    ref = statistics.fmean(ref_vals)
    values = {n: pair_values(n) for n in GRID}
    chosen, rows = judge(values, ref, bounded=True)
    head = (
        "### LSM between two texts of one writer\n\n"
        f"Pairs of consecutive windows from one model's replies. Reference: mean {ref:.4f} over "
        f"{len(ref_vals)} pairs of {REFERENCE}-word windows.\n\n"
    )
    table = (
        "| words per text | pairs | mean | SD | meets both |\n|---|---|---|---|---|\n"
        + "\n".join(rows)
    )
    return head + table + f"\n\nMinimum: {chosen if chosen else 'none on the grid'}.\n", chosen


def dfa_white_noise() -> tuple[str, int | None]:
    rng = random.Random(306)
    values = {}
    for n in GRID:
        values[n] = [
            v for _ in range(200) if (v := m.dfa([rng.gauss(0, 1) for _ in range(n)])) is not None
        ]
    chosen, rows = judge(values, 0.5, bounded=True)
    head = "### DFA alpha\n\nWhite noise (true alpha 0.5), 200 series per length; length is the number of values (sentences).\n\n"
    table = "| values | series | mean | SD | meets both |\n|---|---|---|---|---|\n" + "\n".join(
        rows
    )
    return head + table + f"\n\nMinimum: {chosen if chosen else 'none on the grid'}.\n", chosen


def burstiness_occurrences() -> tuple[str, int | None]:
    """B of one word whose occurrences follow a Bernoulli process (p = 0.02), by occurrence count."""
    rng = random.Random(3060)
    p = 0.02
    mu = 1 / p
    sigma = math.sqrt((1 - p) / p**2)
    ref = (sigma - mu) / (sigma + mu)
    rows, chosen = [], None
    for k in (3, 5, 10, 20, 40, 80):
        vs = []
        for _ in range(2000):
            gaps = []
            for _ in range(k - 1):
                g = 1
                while rng.random() >= p:
                    g += 1
                gaps.append(g)
            mean = sum(gaps) / len(gaps)
            sd = math.sqrt(sum((x - mean) ** 2 for x in gaps) / len(gaps))
            vs.append((sd - mean) / (sd + mean))
        mean, sd = statistics.fmean(vs), statistics.stdev(vs)
        ok_bias = abs(mean - ref) <= ABS
        if ok_bias and chosen is None:
            chosen = k
        rows.append(f"| {k} | {mean:.4f} | {sd:.4f} | {'yes' if ok_bias else 'no'} |")
    head = (
        "### Burstiness of one word\n\n"
        f"Occurrences at random (Bernoulli, p = {p}); the population B of those gaps is {ref:.4f}. "
        "2,000 words per count. Only the bias test applies: a mean over many words, not one word's B, "
        "is what a profile reports, so one word's spread is shown but not judged.\n\n"
    )
    table = "| occurrences | mean B | SD | bias within 0.05 |\n|---|---|---|---|\n" + "\n".join(
        rows
    )
    return (
        head + table + f"\n\nMinimum: {chosen if chosen else 'none on the grid'} occurrences.\n",
        chosen,
    )


def main() -> None:
    ss = streams()
    print(f"Streams: {', '.join(str(len(s)) for s in ss)} words.\n")
    found: dict[str, int | None] = {}
    for name, f in (
        ("Compression ratio", lambda w: m.compression_ratio(" ".join(w))),
        ("Unigram entropy", m.entropy),
        ("Zipf alpha", lambda w: m.zipf(w)["alpha"]),
        ("Heaps beta", lambda w: m.heaps(w)["beta"]),
    ):
        text, found[name] = real_text(name, f, ss)
        print(text)
    for name, fn in (
        ("LSM", lambda: lsm_pairs(ss)),
        ("DFA alpha", dfa_white_noise),
        ("Burstiness", burstiness_occurrences),
    ):
        text, found[name] = fn()
        print(text)
    print("## Minimums\n")
    for k, v in found.items():
        print(f"- {k}: {v if v else 'none on the grid'}")


if __name__ == "__main__":
    main()

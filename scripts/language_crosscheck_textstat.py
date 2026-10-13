# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Compare Substrate's readability with textstat on the 600 length-experiment replies (sprint 304).

Not a test: textstat downloads NLTK's CMUdict on first use. Prints the syllable agreement on words
both dictionaries hold and the Flesch reading-ease difference per reply, for
docs/language/measures.md. textstat is not a dev dependency (its wheel installs a top-level
`tests` package that shadows the repo's), so run:

    uv run --with textstat==0.7.13 python scripts/language_crosscheck_textstat.py
"""

from __future__ import annotations

import json
import statistics
import warnings
from pathlib import Path

import textstat
from textstat.backend.utils._get_cmudict import get_cmudict

from substrate.language import measures as m
from substrate.language import parse, words

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "process/runs/assays/length_drift_2026-10-12_k299"


def main() -> None:
    replies = [json.loads(line)["text"] for f in sorted(DATA.glob("*.jsonl")) for line in f.open()]
    nltk_dict = get_cmudict("en_US") or {}
    ours = m._cmu()
    shared = [w for w in nltk_dict if w in ours]
    same = sum(ours[w] == sum(1 for p in nltk_dict[w][0] if p[-1].isdigit()) for w in shared)
    print(
        f"dictionaries: ours {len(ours)}, NLTK {len(nltk_dict)}, shared {len(shared)}, same count {same}"
    )
    diffs = []
    for text in replies:
        p = parse(text)
        value = m.readability(words(p), len(p.sentences))["flesch_reading_ease"]
        diffs.append(value - textstat.flesch_reading_ease(text))
    q = statistics.quantiles(diffs, n=4)
    print(
        f"flesch, ours - textstat over {len(diffs)} replies: median {statistics.median(diffs):.2f}, "
        f"quartiles {q[0]:.2f} / {q[2]:.2f}, range {min(diffs):.2f} to {max(diffs):.2f}"
    )


if __name__ == "__main__":
    main()

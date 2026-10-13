# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Rebuild the Kobak excess-style lexicons from the authors' published data (sprint 303).

Kobak, González-Márquez, Horvát & Lause (2025), "Delving into LLM-assisted writing in biomedical
publications through excess vocabulary", Science Advances 11(27), eadt3813. Data and code:
github.com/berenslab/llm-excess-vocab (MIT), commit 53db991a. This script repeats the selection in
`scripts/03-figures.ipynb` cells 2, 3, 7, 12 and 25-26 in plain Python and writes two lexicons:

- `kobak_style_2024_rare.toml`: the 2024 excess words annotated "style" with 2024 frequency below
  0.02, the paper's set of 291 (supplementary figure S6);
- `kobak_style_2024.toml`: all 379 excess style words of 2024.

Usage: build_lexicon_kobak.py <yearly-counts.csv.gz> <excess_words.csv> <out_dir>
Both inputs come from the repository's `results/` folder at the commit above.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import math
import sys
from pathlib import Path

COMMIT = "53db991afc251782106cd817a1c3fa47a4d41781"
REPO = "https://github.com/berenslab/llm-excess-vocab"
EXPECTED = {"all": 379, "rare": 291}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select(counts_path: Path, annotations_path: Path) -> tuple[list[str], list[str]]:
    with gzip.open(counts_path, "rt", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    years = [int(y) for y in rows[0][1:]]
    totals = [int(v) for v in rows[-1][1:]]
    col = {y: i for i, y in enumerate(years)}
    with open(annotations_path, encoding="utf-8") as f:
        kind = {r["word"]: r["type"] for r in csv.DictReader(f)}

    target, cutoff = 2024, 1e-4
    style: list[tuple[str, float]] = []
    for row in rows[1:-1]:
        word = row[0]
        # Cell 3: lowercase ASCII letters only, four or more.
        if len(word) < 4 or not all("a" <= ch <= "z" for ch in word):
            continue
        freq = [(int(v) + 1) / (totals[i] + 1) for i, v in enumerate(row[1:])]
        p, p1 = freq[col[target]], freq[col[target - 1]]
        if p < cutoff or p1 < cutoff:
            continue
        # Cell 7: the projection from the two years before the previous one.
        q2, q3 = freq[col[target - 2]], freq[col[target - 3]]
        projection = q2 + max((q2 - q3) * 2, 0.0)
        ratio, diff = p / projection, p - projection
        # Cell 12: above the frequency-dependent ratio line, or a gap above 0.01.
        line = math.log10(2) - (math.log10(p) + 4) * (math.log10(2) / 4)
        if math.log10(ratio) > line or diff > 0.01:
            if kind.get(word) == "style":
                style.append((word, p))
    words = sorted(w for w, _ in style)
    rare = sorted(w for w, p in style if p < 0.02)
    return words, rare


def _write(
    path: Path, name: str, description: str, words: list[str], inputs: dict[str, str]
) -> None:
    lines = [
        "[lexicon]",
        f'name = "{name}"',
        "version = 1",
        'preprocessing = "substrate-text-1"',
        'kind = "words"',
        f'description = "{description}"',
        'source = "Kobak, González-Márquez, Horvát & Lause (2025), Science Advances 11(27), eadt3813; '
        'arXiv 2406.07016"',
        f'data = "{REPO} at {COMMIT}"',
        'licence = "MIT (Copyright (c) 2024 Dmitry Kobak, Rita González-Márquez)"',
        'built_by = "scripts/build_lexicon_kobak.py"',
        "construction = \"Repeats the selection in the authors' scripts/03-figures.ipynb (cells 3, 7, 12, 25-26) on "
        "their yearly counts and their style annotations; the result equals the notebook's saved output.\"",
        f'inputs_sha256 = {{ yearly_counts = "{inputs["counts"]}", excess_words = "{inputs["annotations"]}" }}',
        "",
        "[entries]",
        "words = [",
        *[f'  "{w}",' for w in words],
        "]",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str]) -> int:
    counts, annotations, out = Path(argv[1]), Path(argv[2]), Path(argv[3])
    words, rare = select(counts, annotations)
    if (len(words), len(rare)) != (EXPECTED["all"], EXPECTED["rare"]):
        print(
            f"selection gave {len(words)} and {len(rare)}, the paper reports 379 and 291",
            file=sys.stderr,
        )
        return 1
    inputs = {"counts": _sha256(counts), "annotations": _sha256(annotations)}
    _write(
        out / "kobak_style_2024.toml",
        "kobak-style-2024",
        "The 379 PubMed excess words of 2024 the authors annotated as style words.",
        words,
        inputs,
    )
    _write(
        out / "kobak_style_2024_rare.toml",
        "kobak-style-2024-rare",
        "The 291 excess style words of 2024 with a 2024 frequency below 0.02: the paper's rare set, figure S6.",
        rare,
        inputs,
    )
    print(f"kobak: {len(words)} style words, {len(rare)} rare")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

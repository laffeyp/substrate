# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Write the word -> syllable table the readability measures read (sprint 304).

The Carnegie Mellon University Pronouncing Dictionary, through the `cmudict` package: a word's
syllables are the vowels of its first pronunciation (phones carrying a stress digit), the count
textstat uses. Words the table lacks fall back to the vowel-group rule in
`substrate.language.measures.syllables`.

Usage: build_syllables_cmudict.py <out_file.tsv.gz>
"""

from __future__ import annotations

import gzip
import importlib.metadata
import sys
from pathlib import Path

import cmudict


def main(argv: list[str]) -> int:
    out = Path(argv[1])
    table = cmudict.dict()
    rows = sorted(
        (word, sum(1 for p in prons[0] if p[-1].isdigit()))
        for word, prons in table.items()
        if prons
    )
    version = importlib.metadata.version("cmudict")
    head = [
        f"# CMU Pronouncing Dictionary via the cmudict package {version}; syllables = stressed",
        "# vowels of the first pronunciation. Built by scripts/build_syllables_cmudict.py.",
    ]
    body = "\n".join(head + [f"{w}\t{n}" for w, n in rows]) + "\n"
    # mtime=0 keeps the file byte-identical across builds.
    with open(out, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as f:
        f.write(body.encode("utf-8"))
    print(f"syllables: {len(rows)} words, cmudict {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

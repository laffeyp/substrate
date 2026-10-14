# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Write the LIWC2007 categories the language measures use (sprint 303).

Pennebaker, Booth & Francis (2007), Linguistic Inquiry and Word Count: LIWC2007, the English
dictionary: 4,487 entries in 64 categories. Ireland et al. (2011) computed language style matching
on its nine function-word categories. The copy read here is `LIWC2007_English.dic` from
github.com/illidanlab/subject-harmonization at commit 41836986; the script refuses any file whose
SHA-256 differs.

Usage: build_lexicon_liwc2007.py <LIWC2007_English.dic> <out_dir>
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SHA256 = "e586afedd2bc4cab9960b45dbacfab0c2c5329cd70824968efa0911db049c535"
COPY = "github.com/illidanlab/subject-harmonization at 418369867f80a6c006988928cb3be623011a2e0d"
# LIWC2007 category name -> the name used here. The nine LSM categories follow Ireland et al.'s
# Table 1; the rest are the persons (address), tentative and certainty words, positive emotion
# (enthusiasm) and the informal markers (swear words, assent, nonfluencies, fillers).
WANTED = {
    "funct": "function_words",
    "ppron": "personal_pronouns",
    "ipron": "impersonal_pronouns",
    "article": "articles",
    "conj": "conjunctions",
    "preps": "prepositions",
    "auxverb": "auxiliary_verbs",
    "adverb": "high_frequency_adverbs",
    "negate": "negations",
    "quant": "quantifiers",
    "i": "first_singular",
    "we": "first_plural",
    "you": "second_person",
    "shehe": "third_singular",
    "they": "third_plural",
    "tentat": "tentative",
    "certain": "certainty",
    "posemo": "positive_emotion",
    "swear": "swear_words",
    "assent": "assent",
    "nonfl": "nonfluencies",
    "filler": "fillers",
}
LSM = [
    "personal_pronouns",
    "impersonal_pronouns",
    "articles",
    "conjunctions",
    "prepositions",
    "auxiliary_verbs",
    "high_frequency_adverbs",
    "negations",
    "quantifiers",
]


def read(path: Path) -> dict[str, list[str]]:
    text = path.read_bytes().decode("latin-1").replace("\r\n", "\n").replace("\r", "\n")
    _, header, body = text.split("%", 2)
    number = {}
    for line in header.strip().splitlines():
        num, name = line.split("\t")
        number[num.strip()] = name.strip()
    out: dict[str, list[str]] = {name: [] for name in number.values()}
    for line in body.strip().splitlines():
        if not line.strip():
            continue
        word, *cats = line.split("\t")
        for c in cats:
            if c.strip():
                out[number[c.strip()]].append(word.strip().casefold())
    return out


def main(argv: list[str]) -> int:
    src, out = Path(argv[1]), Path(argv[2])
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    if digest != SHA256:
        print(f"{src}: SHA-256 {digest}, expected {SHA256}", file=sys.stderr)
        return 1
    cats = read(src)
    q = json.dumps
    lines = [
        "[lexicon]",
        'name = "liwc2007"',
        "version = 1",
        'preprocessing = "substrate-text-1"',
        'kind = "word-categories"',
        f"description = {q('LIWC2007 categories: function words and the nine language-style-matching categories, persons, tentative and certainty words, positive emotion, and informal markers.')}",
        f"source = {q('Pennebaker, Booth & Francis (2007), LIWC2007, English dictionary (4,487 entries, 64 categories); categories used for LSM: Ireland, Slatcher, Eastwick, Scissors, Finkel & Pennebaker (2011), Psychological Science 22(1), 39-44, Table 1')}",
        f"data = {q(f'LIWC2007_English.dic, {COPY}, SHA-256 {SHA256}')}",
        f"licence = {q('LIWC2007 dictionary, Pennebaker Conglomerates; entries used as published')}",
        'built_by = "scripts/build_lexicon_liwc2007.py"',
        f"construction = {q('Each category is copied from the dictionary entry by entry, case-folded, with the LIWC category names mapped to the names here (funct -> function_words, preps -> prepositions, adverb -> high_frequency_adverbs, ...). A word may sit in several categories, as in LIWC.')}",
        'wildcard = "*"',
        f"notes = {q('An entry ending in * matches every token that starts with the part before it (LIWC convention). LIWC lists some contractions both with and without the apostrophe (dont, don’t); both are kept.'.replace(chr(8217), chr(39)))}",
        "",
        "[lsm]",
        "categories = [" + ", ".join(q(c) for c in LSM) + "]",
        f"formula = {q('per category: 1 - |p1 - p2| / (p1 + p2 + 0.0001), p = the category percentage of all word tokens; LSM = the mean over the nine categories')}",
        'source = "Ireland et al. (2011), p. 40"',
        "",
        "[categories]",
    ]
    for liwc, name in WANTED.items():
        words = sorted(set(cats[liwc]))
        lines.append(f"{name} = [")
        lines += [f"  {q(w)}," for w in words]
        lines.append("]")
    (out / "liwc2007.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("liwc2007: " + ", ".join(f"{n} {len(set(cats[c]))}" for c, n in WANTED.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

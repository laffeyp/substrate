# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The lexicons in `lexicons/` (sprint 303) and the matcher that counts their terms in a text.

A term is one token or a run of tokens, written in substrate-text-1 form. Matching runs inside
one unit (a sentence, heading or table cell) over its word tokens; a code, URL or email token
ends a run. At each position the longest matching term wins and the match does not overlap the
next one, so "looks like" counts once and "like" inside it does not count again. A term ending in
the lexicon's wildcard (LIWC's `*`) matches every token that starts with the part before it.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

from substrate.language.text import Parsed, Token, TokenKind


# Lexicons read by name in more than one module.
LIWC2007 = "liwc2007"
CONTRACTIONS = "contractions"


@dataclass(frozen=True, slots=True)
class Lexicon:
    name: str
    version: int
    header: dict[str, Any]
    lists: dict[str, tuple[str, ...]]
    lsm: tuple[str, ...] = ()

    @property
    def wildcard(self) -> str | None:
        value = self.header.get("wildcard")
        return str(value) if value else None

    def matcher(self, *keys: str) -> Matcher:
        """One matcher over the union of the named lists."""
        return Matcher((t for k in keys for t in self.lists[k]), self.wildcard)


@cache
def load(name: str) -> Lexicon:
    """A lexicon by file stem, read once per process."""
    path = resources.files("substrate.language").joinpath("lexicons", f"{name}.toml")
    doc = tomllib.loads(path.read_text(encoding="utf-8"))
    lists: dict[str, tuple[str, ...]] = {}
    for table in ("entries", "categories"):
        for key, value in doc.get(table, {}).items():
            lists[key] = tuple(value)
    head = doc["lexicon"]
    lsm = tuple(doc.get("lsm", {}).get("categories", ()))
    return Lexicon(str(head["name"]), int(head["version"]), dict(head), lists, lsm)


def provenance(names: Iterable[str]) -> dict[str, str]:
    """`name -> "name@version"` for the lexicons a stored value used."""
    return {n: f"{load(n).name}@{load(n).version}" for n in names}


class Matcher:
    def __init__(self, terms: Iterable[str], wildcard: str | None = None) -> None:
        self.exact: set[str] = set()
        self.stems: set[str] = set()
        self.phrases: dict[str, list[tuple[str, ...]]] = {}
        for term in terms:
            parts = tuple(term.split(" "))
            if len(parts) > 1:
                self.phrases.setdefault(parts[0], []).append(parts)
            elif wildcard and term.endswith(wildcard):
                self.stems.add(term[: -len(wildcard)])
            else:
                self.exact.add(term)
        for options in self.phrases.values():
            options.sort(key=len, reverse=True)
        self.stem_lengths = sorted({len(s) for s in self.stems})

    def single(self, word: str) -> bool:
        """Whether one token matches a one-token term."""
        if word in self.exact:
            return True
        return any(word[:n] in self.stems for n in self.stem_lengths if len(word) >= n)

    def matches(self, run: Sequence[str]) -> list[tuple[int, int]]:
        """(start, length) of each match in one run of word tokens, longest first, no overlaps."""
        out: list[tuple[int, int]] = []
        i = 0
        while i < len(run):
            hit = 0
            for phrase in self.phrases.get(run[i], ()):
                if tuple(run[i : i + len(phrase)]) == phrase:
                    hit = len(phrase)
                    break
            if not hit and self.single(run[i]):
                hit = 1
            if hit:
                out.append((i, hit))
                i += hit
            else:
                i += 1
        return out

    def count(self, parsed: Parsed) -> int:
        return sum(len(self.matches(run)) for run in word_runs(parsed.units))


def word_runs(units: Iterable[Sequence[Token]]) -> list[list[str]]:
    """Each unit's word tokens, cut wherever a code, URL or email token sits."""
    runs: list[list[str]] = []
    for unit in units:
        run: list[str] = []
        for tok in unit:
            if tok.kind is TokenKind.WORD:
                run.append(tok.text)
            elif run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)
    return runs


@cache
def _contraction_forms() -> tuple[frozenset[str], tuple[str, ...]]:
    lex = load(CONTRACTIONS)
    return frozenset(lex.lists["words"]), lex.lists["suffixes"]


def is_contraction(word: str) -> bool:
    listed, suffixes = _contraction_forms()
    return word in listed or word.endswith(suffixes)


class LexiconIndex:
    """Counts many matchers in one pass over each run. Each matcher still matches greedily,
    longest first, without overlaps; the index only shares the per-word lookups between them."""

    def __init__(self, matchers: dict[str, Matcher]) -> None:
        self.names = list(matchers)
        self.matchers = [matchers[n] for n in self.names]
        self.phrase_starts: dict[str, list[int]] = {}
        for idx, m in enumerate(self.matchers):
            for first in m.phrases:
                self.phrase_starts.setdefault(first, []).append(idx)
        self._singles: dict[str, tuple[int, ...]] = {}

    def _single_hits(self, word: str) -> tuple[int, ...]:
        hits = self._singles.get(word)
        if hits is None:
            hits = tuple(i for i, m in enumerate(self.matchers) if m.single(word))
            self._singles[word] = hits
        return hits

    def count(self, runs: Iterable[Sequence[str]]) -> dict[str, int]:
        counts = [0] * len(self.matchers)
        for run in runs:
            free = [0] * len(self.matchers)  # the next position each matcher may match at
            for i, word in enumerate(run):
                for idx in self.phrase_starts.get(word, ()):
                    if free[idx] > i:
                        continue
                    for phrase in self.matchers[idx].phrases[word]:
                        if tuple(run[i : i + len(phrase)]) == phrase:
                            counts[idx] += 1
                            free[idx] = i + len(phrase)
                            break
                for idx in self._single_hits(word):
                    if free[idx] <= i:
                        counts[idx] += 1
                        free[idx] = i + 1
        return dict(zip(self.names, counts, strict=True))

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 303: every lexicon names its source and licence, and every entry is written in
substrate-text-1 token form (docs/language/substrate-text-1.md, rules N2, N3 and W1).

The tokenizer does not exist yet (sprint 304); WORD restates rule W1 for one token so the lists can
be checked now. Sprint 304's tests tokenize every entry with the real tokenizer.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

LEXICONS = Path(__file__).resolve().parents[1] / "src" / "substrate" / "language" / "lexicons"
FILES = sorted(LEXICONS.glob("*.toml"))
HEADER = (
    "name",
    "version",
    "preprocessing",
    "kind",
    "description",
    "source",
    "licence",
    "construction",
)
# W1: letters, marks, digits and "_", joined by single internal ' - or . characters.
WORD = re.compile(r"[^\W]+(?:['\-.][^\W]+)*")


def _load(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        return tomllib.load(f)


def _lists(doc: dict[str, Any]) -> dict[str, list[str]]:
    """Every list of entries in a lexicon, by its table and key."""
    out: dict[str, list[str]] = {}
    for table in ("entries", "categories"):
        for key, value in doc.get(table, {}).items():
            out[f"{table}.{key}"] = value
    return out


def test_the_lexicons_exist() -> None:
    names = {p.stem for p in FILES}
    assert names == {
        "address",
        "boosters",
        "contractions",
        "enthusiasm",
        "function_words",
        "hedges",
        "informal",
        "intensifiers",
        "kobak_style_2024",
        "kobak_style_2024_rare",
        "padding",
    }


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_header_names_source_licence_and_preprocessing(path: Path) -> None:
    head = _load(path)["lexicon"]
    for field in HEADER:
        assert str(head.get(field, "")).strip(), f"{path.name}: no {field}"
    assert head["preprocessing"] == "substrate-text-1"
    assert head["name"].replace("-", "_") == path.stem


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_entries_are_in_token_form(path: Path) -> None:
    lists = _lists(_load(path))
    assert lists, f"{path.name}: no entries"
    for where, entries in lists.items():
        assert entries, f"{path.name} {where} is empty"
        assert len(entries) == len(set(entries)), f"{path.name} {where} repeats an entry"
        for entry in entries:
            if where == "entries.suffixes":
                assert re.fullmatch(r"(n't|'[a-z]+)", entry), entry
                continue
            assert entry == entry.casefold(), f"{path.name} {where}: {entry!r} is not case-folded"
            assert "’" not in entry, f"{path.name} {where}: {entry!r} has a curly apostrophe"
            for token in entry.split(" "):
                assert WORD.fullmatch(token), f"{path.name} {where}: {token!r} is not one W1 token"


def test_published_lists_keep_their_published_counts() -> None:
    assert len(_load(LEXICONS / "kobak_style_2024.toml")["entries"]["words"]) == 379
    assert len(_load(LEXICONS / "kobak_style_2024_rare.toml")["entries"]["words"]) == 291
    hedges = _load(LEXICONS / "hedges.toml")["entries"]
    assert len(hedges["relational"]) + len(hedges["propositional"]) == 117


def test_the_rare_set_is_inside_the_full_set() -> None:
    full = set(_load(LEXICONS / "kobak_style_2024.toml")["entries"]["words"])
    rare = set(_load(LEXICONS / "kobak_style_2024_rare.toml")["entries"]["words"])
    assert rare <= full


def test_the_mit_notice_ships_with_the_kobak_lists() -> None:
    notice = (LEXICONS / "licences" / "kobak-llm-excess-vocab-MIT.txt").read_text(encoding="utf-8")
    assert "MIT License" in notice and "Dmitry Kobak" in notice


def test_lsm_names_nine_categories_that_exist() -> None:
    doc = _load(LEXICONS / "function_words.toml")
    assert len(doc["lsm"]["categories"]) == 9
    assert set(doc["lsm"]["categories"]) == set(doc["categories"])

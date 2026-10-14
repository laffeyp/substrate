# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 316: a card, plain or in the SDD kit's form, read into CardAccepted; one lacking
what to do, where, or how to tell it is done refused by name. Written before
`topologies/runs/card.py` existed. The two SDD cards are the kit's own worked example
(`sdd-kit-3/example/sprints/`), copied as fixtures."""

from __future__ import annotations

from pathlib import Path

import msgspec
import pytest

from substrate.topologies.runs.card import CardRefused, read_card, read_sdd_card
from substrate.topologies.session import CardAccepted
from substrate.topologies.session.vocabulary import CardForm, CheckKind, RunLimits

LIMITS = RunLimits(max_stops=10, stall_stops=2)
CARDS = Path(__file__).parent / "fixtures" / "cards"


def test_a_plain_card_reads() -> None:
    card = read_card(
        what="add a --json flag to the CLI",
        where=["cli.py", "tests/test_cli.py"],
        commands=["pytest tests/test_cli.py"],
        statements=["--help lists --json"],
        limits=LIMITS,
    )
    assert card.form is CardForm.PLAIN
    assert [(c.kind, c.text) for c in card.checks] == [
        (CheckKind.COMMAND, "pytest tests/test_cli.py"),
        (CheckKind.STATEMENT, "--help lists --json"),
    ]
    assert "add a --json flag" in card.text and "pytest tests/test_cli.py" in card.text
    assert msgspec.json.decode(msgspec.json.encode(card), type=CardAccepted) == card


@pytest.mark.parametrize(
    ("fields", "missing"),
    [
        ({"what": "", "where": ["a.py"], "commands": ["true"]}, "what to do"),
        ({"what": "x", "where": [], "commands": ["true"]}, "where"),
        ({"what": "x", "where": ["a.py"], "commands": []}, "how to tell it is done"),
    ],
)
def test_a_plain_card_missing_a_part_is_refused_by_name(fields: dict, missing: str) -> None:
    with pytest.raises(CardRefused, match=missing):
        read_card(limits=LIMITS, statements=[], **fields)


def test_the_kits_example_cards_read() -> None:
    card = read_sdd_card((CARDS / "sprint-002-counter-and-scanner.md").read_text(), limits=LIMITS)
    assert card.form is CardForm.SDD
    assert card.what.startswith("Author `src/wordcount/counter.py`")
    assert "src/wordcount/counter.py" in card.where and "signals/0.1.json" in card.where
    commands = [c.text for c in card.checks if c.kind is CheckKind.COMMAND]
    assert commands == [
        "python -m pytest tests/test_counter.py -v",
        "python -m pytest tests/test_scanner.py -v",
        "python -m pytest tests/ -v",
    ]
    statements = [c.text for c in card.checks if c.kind is CheckKind.STATEMENT]
    assert any("def count_file(path: Path)" in s for s in statements)
    card3 = read_sdd_card((CARDS / "sprint-003-cli-and-jsonl-sink.md").read_text(), limits=LIMITS)
    # v0.12.1: a command's expected exit code comes from the card ("returns 2").
    assert [(c.text, c.expect_exit) for c in card3.checks if c.kind is CheckKind.COMMAND] == [
        ("python -m pytest tests/ -v", 0),
        ("python -m wordcount tests/fixtures/sample_tree/", 2),
        ("python -m wordcount /nonexistent/path/", 1),
    ]


def test_an_sdd_card_without_a_scope_is_refused() -> None:
    text = (CARDS / "sprint-002-counter-and-scanner.md").read_text()
    without = text.replace("## scope", "## something else")
    with pytest.raises(CardRefused, match="what to do"):
        read_sdd_card(without, limits=LIMITS)

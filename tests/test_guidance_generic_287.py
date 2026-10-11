# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K287: every shipped guidance text is generic.

The default guidance began as a copy of one operator's Claude Code setup (K275). Shipped texts now
name no model, vendor or person, and speak about "the user", never as "I".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SESSION = Path(__file__).parent.parent / "src" / "substrate" / "topologies" / "session"
TEXTS = sorted(
    [
        *(SESSION / "bundles").glob("*/*.md"),
        *(SESSION / "skills").glob("*/SKILL.md"),
        *(SESSION / "prompts").glob("*.md"),
    ]
)
_NAMED = re.compile(r"\b(Claude|Anthropic|OpenAI|Codex|Cursor|Gemini)\b")
_FIRST_PERSON = re.compile(r"(?<![\w`])(I|I'd|I'm|me|my)(?![\w`])")
# Quoted words are examples of what the model says ("shall I?"), not the operator speaking.
_QUOTED = re.compile(r'"[^"]*"')


def test_there_are_texts() -> None:
    assert len(TEXTS) >= 10, TEXTS


@pytest.mark.parametrize("path", TEXTS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_a_text_names_no_model_vendor_or_person(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert not _NAMED.findall(text), _NAMED.findall(text)


@pytest.mark.parametrize("path", TEXTS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_a_text_does_not_speak_as_the_operator(path: Path) -> None:
    text = _QUOTED.sub("", path.read_text(encoding="utf-8"))
    hits = [m.group(0) for m in _FIRST_PERSON.finditer(text)]
    assert not hits, hits

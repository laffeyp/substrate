# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""A run's card (kernel sprint 316; session vocabulary § X.3, research r8 § 3.2).

A card says three things: what to do, where, and how to tell it is done. A person's card comes as
those fields; a card in the SDD kit's form comes as its markdown (`sdd-kit-3/templates/
SPRINT_CARD.md`), read for its scope, its context and artifact files, its command exit codes, its
content assertions and its observation contract. Either becomes a `CardAccepted`. A card lacking
one of the three is refused, and `CardRefused` names what is missing; the tool that took the card
returns that as its result.
"""

from __future__ import annotations

import re

from ..session import CardAccepted
from ..session.vocabulary import CardCheck, CardForm, CheckKind, RunLimits

WHAT = "what to do"
WHERE = "where"
DONE_WHEN = "how to tell it is done"


class CardRefused(ValueError):
    """A card lacks what to do, where, or how to tell it is done. The message names the gaps."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__("the card does not say " + ", or ".join(missing))
        self.missing = missing


def _refuse_if_incomplete(what: str, where: list[str], checks: list[CardCheck]) -> None:
    missing = [
        name
        for name, present in ((WHAT, what.strip()), (WHERE, where), (DONE_WHEN, checks))
        if not present
    ]
    if missing:
        raise CardRefused(missing)


def read_card(
    *,
    what: str,
    where: list[str],
    commands: list[str],
    statements: list[str],
    limits: RunLimits,
) -> CardAccepted:
    """A card from a person's fields: the work, the files or parts it touches, the commands that
    must pass, the things that must be true."""
    checks = [CardCheck(kind=CheckKind.COMMAND, text=c) for c in commands if c.strip()] + [
        CardCheck(kind=CheckKind.STATEMENT, text=s) for s in statements if s.strip()
    ]
    where = [w for w in where if w.strip()]
    _refuse_if_incomplete(what, where, checks)
    text = "\n".join(
        [f"what: {what}", "where: " + ", ".join(where)] + [f"check: {c.text}" for c in checks]
    )
    return CardAccepted(
        form=CardForm.PLAIN, what=what.strip(), where=where, checks=checks, text=text, limits=limits
    )


# The SDD card's headings, as the kit's template writes them.
_HEADING = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
_BACKTICK = re.compile(r"`([^`]+)`")
_RETURNS = re.compile(r"returns\s+(\d+)")
# Observation-contract subsections whose bullets say what must be seen, not how to drive it.
_OBSERVED = ("expected",)


def _sections(text: str) -> dict[str, list[str]]:
    """Each `##` and `###` heading's lines, keyed by the heading's lowercased text; a `###` section's
    lines also count toward its `##` parent."""
    sections: dict[str, list[str]] = {}
    parent: str | None = None
    current: str | None = None
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            name = m.group(2).lower()
            current = name
            if len(m.group(1)) == 2:
                parent = name
            sections.setdefault(name, [])
            continue
        if line.strip() == "---":
            continue
        if current is not None:
            sections[current].append(line)
            if parent is not None and parent != current:
                sections[parent].append(line)
    return sections


def _bullets(lines: list[str]) -> list[str]:
    return [line.strip()[2:].strip() for line in lines if line.strip().startswith("- ")]


def _paragraph(lines: list[str]) -> str:
    """The section's prose: its non-empty lines that are not italic template notes."""
    kept = [
        line.strip()
        for line in lines
        if line.strip() and not (line.strip().startswith("*") and line.strip().endswith("*"))
    ]
    return " ".join(kept)


def read_sdd_card(text: str, *, limits: RunLimits) -> CardAccepted:
    """A card in the SDD kit's sprint-card form."""
    sections = _sections(text)
    what = _paragraph(next((v for k, v in sections.items() if k.startswith("scope")), []))
    where: list[str] = []
    for name in ("context_files", "files created", "files modified"):
        for bullet in _bullets(sections.get(name, [])):
            m = _BACKTICK.search(bullet)
            if m and m.group(1) not in where:
                where.append(m.group(1))
    checks: list[CardCheck] = []
    for bullet in _bullets(sections.get("command exit codes", [])):
        m = _BACKTICK.search(bullet)
        if m:
            code = _RETURNS.search(bullet)
            checks.append(
                CardCheck(
                    kind=CheckKind.COMMAND,
                    text=m.group(1),
                    expect_exit=int(code.group(1)) if code else 0,
                )
            )
    statements = _bullets(sections.get("content assertions", []))
    for name, lines in sections.items():
        if name.startswith(_OBSERVED):
            statements += _bullets(lines)
    checks += [CardCheck(kind=CheckKind.STATEMENT, text=s) for s in statements]
    _refuse_if_incomplete(what, where, checks)
    return CardAccepted(
        form=CardForm.SDD, what=what, where=where, checks=checks, text=text, limits=limits
    )


__all__ = ["DONE_WHEN", "WHAT", "WHERE", "CardRefused", "read_card", "read_sdd_card"]

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K275: the `standard` bundle, and a golden head for every shipped bundle.

`standard` extends `harness` with the working and writing standard; the application bundles extend
`standard`. Each golden file pins what a session on that bundle, with the `default` role and no
tools, puts before the conversation: the system part, the head, and the reminder line. An edit to
`harness` or `standard` changes every head below it, and the diff shows each one.

Regenerate after an intended text change: `SUBSTRATE_UPDATE_GOLDEN=1 uv run python -m pytest
tests/test_standard_bundle_275.py`, then read the diff.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from substrate.bundles import resolve_extends
from substrate.topologies.session.session_prompt_producer import session_prompt_sources
from substrate.topologies.session.transcript import head_block

GOLDEN = Path(__file__).parent / "golden" / "heads"
SHIPPED = [
    "harness",
    "standard",
    "code_review",
    "pair_coding",
    "best_of_n_verified",
    "research_sweep",
    "standard-medium",
    "standard-low",
]


def _head(bundle: str) -> str:
    sources = session_prompt_sources(
        role="default", role_repo_root=None, bundle=bundle, parent_context=None, tools={}
    )
    fragments = []
    for source in sources.values():
        for fragment in source():
            payload = {
                "source": str(fragment.source),
                "text": fragment.text,
                "precedence": fragment.precedence,
                "provenance": fragment.provenance,
            }
            fragments.append((len(fragments), payload))
    system, head, reminder, _seqs = head_block("", fragments)
    return (
        f"=== SYSTEM ===\n{system}\n=== HEAD ===\n{head}\n=== AFTER EACH MESSAGE ===\n{reminder}\n"
    )


@pytest.mark.parametrize("bundle", SHIPPED)
def test_golden_head(bundle: str) -> None:
    path = GOLDEN / f"{bundle}.txt"
    actual = _head(bundle)
    if os.environ.get("SUBSTRATE_UPDATE_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
    assert actual == path.read_text(encoding="utf-8")


def test_the_chain() -> None:
    assert [b.name for b in resolve_extends("standard")] == ["harness", "standard"]
    for app in SHIPPED[2:6]:
        assert [b.name for b in resolve_extends(app)] == ["harness", "standard", app]


def test_code_review_reads_harness_then_standard_then_its_own() -> None:
    head = _head("code_review")
    system, rest = head.split("=== HEAD ===")
    body, reminder = rest.split("=== AFTER EACH MESSAGE ===")
    # The system part: standard's writing style, then code_review's one line.
    assert system.index("Every output is writing") < system.index("Blunt. Specific.")
    # The head: the role, then harness's loop rules, standard's working rules, code_review's own.
    assert (
        body.index("You are a working companion")
        < body.index("Work through the request.")
        < body.index("They override any default behaviour")
        < body.index("Review the diff for the role assigned.")
    )
    # The reminder line: standard's hook line, then code_review's own.
    assert reminder.index("STYLE: Write like E. B. White") < reminder.index(
        "Flag any unsafe pattern"
    )


def test_standard_is_the_generic_standard_with_substrate_tool_names() -> None:
    """K287: the copy of one operator's setup (K275) was made generic: no harness header, no
    operator's memory index, attribution stated for any model. Every rule section stays."""
    standard = resolve_extends("standard")[-1]
    assert standard.style.startswith("# Every output is writing")
    assert 'skill("dellm")' in standard.style and "invoke the `dellm` skill" not in standard.style
    method = standard.methodology
    assert method.startswith("These are the working rules for this session.")
    for heading in (
        "# Acknowledge before acting",
        "# Research instead of guessing",
        "# Treat the information space as adversarial",
        "# No model attribution in git",
        "# Unaddressed prose",
        "# Reading files",
        "# Explaining: expand, compress, reverse-explain",
        "# Working discipline",
        "# Memory",
    ):
        assert heading in method, heading
    for gone in ("Codebase and user instructions", "# Working rules from memory"):
        assert gone not in method, gone
    assert "`web_fetch` for live facts." in method and "`WebSearch`" not in method
    assert "with `read_file`" in method and "`delegate` child" in method
    assert standard.per_turn.startswith("STYLE: Write like E. B. White and George Orwell.")

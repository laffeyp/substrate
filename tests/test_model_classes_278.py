# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K278: model classes (session vocabulary § P.7).

A CLI is a harness agent; an Ollama model is small below 30B parameters and large otherwise. A
small model reads `standard-small`, `default-small` and `dellm-small`, which fit its window.
"""

from __future__ import annotations

from substrate.topologies.session.model_class import (
    HARNESS_AGENT,
    LARGE,
    SMALL,
    class_variant,
    classify,
    parameter_count,
)
from substrate.topologies.session.session_prompt_producer import session_prompt_sources
from substrate.topologies.session.skills import list_skills, resolve_skill
from substrate.topologies.session.transcript import _est_tokens, head_block


def test_both_reported_forms_parse() -> None:
    assert parameter_count("8.0B") == 8_000_000_000
    assert parameter_count("1042000000000") == 1_042_000_000_000
    assert parameter_count("494.03M") == 494_030_000
    assert parameter_count("") is None and parameter_count(None) is None


def test_the_three_classes() -> None:
    assert classify(is_cli=True) == HARNESS_AGENT
    assert classify(is_cli=False, parameter_size="8.0B") == SMALL
    assert classify(is_cli=False, parameter_size="29.9B") == SMALL
    assert classify(is_cli=False, parameter_size="30B") == LARGE
    assert classify(is_cli=False, parameter_size="1042000000000") == LARGE
    assert classify(is_cli=False) == LARGE  # size unknown


def test_class_variant() -> None:
    assert class_variant("standard", SMALL) == "standard-small"
    assert class_variant("standard", LARGE) == "standard"


def test_the_small_head_fits_in_800_tokens() -> None:
    sources = session_prompt_sources(
        role="default-small",
        role_repo_root=None,
        bundle="standard-small",
        parent_context=None,
        tools={},
    )
    fragments = []
    for source in sources.values():
        for f in source():
            fragments.append(
                (
                    len(fragments),
                    {"source": str(f.source), "text": f.text, "precedence": f.precedence},
                )
            )
    system, head, reminder, _ = head_block("", fragments)
    tokens = _est_tokens(system) + _est_tokens(head) + _est_tokens(reminder)
    assert 0 < tokens <= 800, tokens


def test_a_small_model_reads_dellm_small() -> None:
    small = resolve_skill("dellm", None, SMALL)
    full = resolve_skill("dellm", None, LARGE)
    assert small is not None and small[1].parent.name == "dellm-small"
    assert full is not None and full[1].parent.name == "dellm"
    assert len(small[0]) < len(full[0]) / 3
    assert [name for name, _ in list_skills(None)] == ["dellm"]  # the variant is not listed apart

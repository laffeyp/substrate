# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K278, K288: model classes and guidance levels (session vocabulary § P.7, § R).

A CLI is a harness agent; an Ollama model is small below 14B parameters, medium below 70B, and
large otherwise. A class sets the default guidance level: high for harness agents and large models,
medium for medium, low for small. A small model also reads `default-small` and `dellm-small`.
"""

from __future__ import annotations

from substrate.bundles import resolve_extends
from substrate.topologies.session.model_class import (
    HARNESS_AGENT,
    LARGE,
    MEDIUM,
    SMALL,
    GuidanceLevel,
    class_variant,
    classify,
    guidance_bundle,
    guidance_level,
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


def test_the_four_classes() -> None:
    assert classify(is_cli=True) == HARNESS_AGENT
    assert classify(is_cli=False, parameter_size="8.0B") == SMALL
    assert classify(is_cli=False, parameter_size="13.9B") == SMALL
    assert classify(is_cli=False, parameter_size="14B") == MEDIUM
    assert classify(is_cli=False, parameter_size="32.8B") == MEDIUM
    assert classify(is_cli=False, parameter_size="70B") == LARGE
    assert classify(is_cli=False, parameter_size="1042000000000") == LARGE
    assert classify(is_cli=False) == LARGE  # size unknown


def test_each_class_has_a_default_level() -> None:
    assert [guidance_level(c) for c in (HARNESS_AGENT, LARGE, MEDIUM, SMALL)] == [
        GuidanceLevel.HIGH,
        GuidanceLevel.HIGH,
        GuidanceLevel.MEDIUM,
        GuidanceLevel.LOW,
    ]
    assert [guidance_bundle(level) for level in GuidanceLevel] == [
        "harness",
        "standard-low",
        "standard-medium",
        "standard",
    ]


def test_class_variant_is_for_role_prompts_and_skills() -> None:
    assert class_variant("default", SMALL) == "default-small"
    assert class_variant("default", MEDIUM) == "default"
    assert class_variant("default", LARGE) == "default"


def _head_tokens(bundle: str, role: str = "default") -> int:
    sources = session_prompt_sources(
        role=role, role_repo_root=None, bundle=bundle, parent_context=None, tools={}
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
    return _est_tokens(system) + _est_tokens(head) + _est_tokens(reminder)


def test_the_low_head_fits_in_800_tokens() -> None:
    tokens = _head_tokens("standard-low", role="default-small")
    assert 0 < tokens <= 800, tokens


def test_the_levels_grow_from_default_to_high() -> None:
    sizes = [_head_tokens(guidance_bundle(level)) for level in GuidanceLevel]
    assert sizes == sorted(sizes) and len(set(sizes)) == 4, sizes
    # Medium sits well inside a 4,096-token window; high does not need to.
    assert sizes[2] < 2_000, sizes


def test_the_old_low_name_still_loads() -> None:
    assert [b.name for b in resolve_extends("standard-small")] == ["harness", "standard-low"]


def test_a_small_model_reads_dellm_small() -> None:
    small = resolve_skill("dellm", None, SMALL)
    full = resolve_skill("dellm", None, LARGE)
    assert small is not None and small[1].parent.name == "dellm-small"
    assert full is not None and full[1].parent.name == "dellm"
    assert len(small[0]) < len(full[0]) / 3
    assert [name for name, _ in list_skills(None)] == ["dellm"]  # the variant is not listed apart

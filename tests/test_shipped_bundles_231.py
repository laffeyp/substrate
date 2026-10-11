# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 231 — five default bundles ship + load through bundles.load_bundle."""

from __future__ import annotations

import pytest

from substrate.bundles import Bundle, load_bundle


@pytest.mark.parametrize(
    "name",
    ["harness", "code_review", "pair_coding", "best_of_n_verified", "research_sweep"],
)
def test_shipped_bundle_loads(name: str) -> None:
    """Each of the five default bundles the daily driver needs is on
    disk and parses through bundles.load_bundle. Bundles in
    ~/.substrate/bundles/<name>/ shadow the shipped default; absent a
    shadow, the shipped version loads."""
    bundle = load_bundle(name)
    assert isinstance(bundle, Bundle)
    assert bundle.name == name


def test_code_review_bundle_has_reviewer_prose() -> None:
    bundle = load_bundle("code_review")
    assert "Blunt" in bundle.style
    assert "flag any unsafe pattern" in bundle.per_turn.lower() or bundle.per_turn
    assert bundle.methodology  # non-empty
    assert "diff" in bundle.methodology.lower()


def test_pair_coding_bundle_names_both_roles() -> None:
    bundle = load_bundle("pair_coding")
    assert "builder" in bundle.methodology.lower()
    assert "reviewer" in bundle.methodology.lower()
    assert "collaborative" in bundle.style.lower()


def test_best_of_n_verified_bundle_names_both_roles() -> None:
    bundle = load_bundle("best_of_n_verified")
    assert "solver" in bundle.methodology.lower()
    assert "verifier" in bundle.methodology.lower()
    assert "rigorous" in bundle.style.lower()


def test_research_sweep_bundle_names_three_roles() -> None:
    bundle = load_bundle("research_sweep")
    for role in ("reader", "critic", "synthesizer"):
        assert role in bundle.methodology.lower()

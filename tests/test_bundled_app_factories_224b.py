# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 224b — four shipped applications land BUNDLED CI-mode factories.

Every entry runs deterministic, finalises without a terminal error, and
the record carries the application's terminal envelope (Verdict, Solved,
Synthesis, or SessionEnded).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from substrate import api
from substrate.topologies import bundled

APPLICATION_NAMES = ("fanout_review", "best_of_n_verified", "research_sweep", "daily")


@pytest.mark.parametrize("name", APPLICATION_NAMES)
def test_application_ci_factory_is_registered(name: str) -> None:
    assert name in bundled.BUNDLED, f"{name!r} missing from BUNDLED"


@pytest.mark.parametrize("name", APPLICATION_NAMES)
def test_application_ci_factory_runs_to_finalised(name: str, tmp_path: Path) -> None:
    """The card's dual contract: each factory produces a real
    substrate record ending in substrate.RunFinalised."""
    factory = bundled.BUNDLED[name]
    record_root = tmp_path / name
    asyncio.run(api.Runtime(record_root).run(factory()))
    envelopes = list(api.read_record(record_root))
    assert envelopes, f"{name!r} produced an empty record"
    assert envelopes[0]["kind"] == api.RUN_STARTED
    assert envelopes[-1]["kind"] == api.RUN_FINALISED, (
        f"{name!r} did not finalise; tail was {envelopes[-1]['kind']!r}"
    )


def test_fanout_review_ci_emits_review_subject_and_verdict(tmp_path: Path) -> None:
    factory = bundled.BUNDLED["fanout_review"]
    record_root = tmp_path / "fanout"
    asyncio.run(api.Runtime(record_root).run(factory()))
    kinds = {env["kind"] for env in api.read_record(record_root)}
    assert "ReviewSubject" in kinds
    assert "VerdictRendered" in kinds


def test_best_of_n_verified_ci_emits_solved_or_max_rounds(tmp_path: Path) -> None:
    factory = bundled.BUNDLED["best_of_n_verified"]
    record_root = tmp_path / "bon"
    asyncio.run(api.Runtime(record_root).run(factory()))
    kinds = {env["kind"] for env in api.read_record(record_root)}
    assert "Solved" in kinds or "MaxRoundsExhausted" in kinds

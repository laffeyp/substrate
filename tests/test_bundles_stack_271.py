# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K271: style stacks, shipped bundles extend, old records keep their style fragment."""

from __future__ import annotations

from substrate.topologies.session.views import FragmentCohort
from substrate.topologies.session.vocabulary import PROMPT_FRAGMENT, parse_prompt_source
from substrate.types import Event


def _fragment(seq: int, source: str) -> Event:
    return Event(
        seq=seq,
        kind=PROMPT_FRAGMENT,
        schema="",
        producer=None,
        t=0.0,
        payload={"source": source, "text": f"t{seq}", "precedence": 3, "provenance": {}},
    )


def test_a_pre_v04_style_fragment_stays_in_the_cohort() -> None:
    """A resumed session written before v0.4 has `bundle_personality` fragments; the cohort keeps
    them as session-open, so the resumed prompt still carries the style."""
    cohort = FragmentCohort()
    cohort.update(_fragment(4, "bundle_personality"))
    assert [seq for seq, _ in cohort.value()] == [4]


def test_parse_prompt_source_maps_the_old_name() -> None:
    assert parse_prompt_source("bundle_personality") == "bundle_style"
    assert parse_prompt_source("bogus") is None

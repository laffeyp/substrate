# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 312: every profile measure has a catalog entry, and the intent table reads from the
length and tone texts."""

from __future__ import annotations

import re

from substrate.language import profile
from substrate.language.catalog import CATALOG, RELATION_LANES, Group
from substrate.language.drift import WATCHED
from substrate.topologies.session.vocabulary import (
    LANGUAGE_INTENTS,
    LENGTH_TEXTS,
    TONE_TEXTS,
    Control,
)

GROUPS = {
    Group.LENGTH: {
        "words",
        "sentence_length_mean",
        "rate_padding_restatement_opening",
        "rate_padding_offer_of_more_closing",
    },
    Group.TONE: {
        "rate_hedges_hyland",
        "rate_boosters_hyland",
        "rate_contractions",
        "rate_liwc_positive_emotion",
        "format_exclamations",
    },
    Group.GUIDANCE: {
        "rate_kobak_style",
        "format_em_dashes",
        "format_bold_spans",
        "format_list_items",
    },
}


def test_the_catalog_names_exactly_the_profile_and_relation_measures() -> None:
    from substrate.language.catalog import Family
    from substrate.topologies.session.language_lines import relation_values

    relation = {m.name for m in CATALOG.values() if m.family is Family.RELATION}
    assert set(CATALOG) - relation == set(profile("One text. Two sentences.").measures)
    assert relation == set(relation_values("a question", "an answer")) | {"window_lsm"}


def test_the_watched_measures_carry_their_groups_and_no_other_does() -> None:
    assert set().union(*GROUPS.values()) == set(WATCHED)
    for group, names in GROUPS.items():
        assert {m.name for m in CATALOG.values() if m.group is group} == names


def test_each_entry_is_complete() -> None:
    for m in CATALOG.values():
        assert m.short and m.unit and m.explanation, m.name
        assert m.low < m.high, m.name
        sentences = re.findall(r"[.!?](?:\s|$)", m.explanation)
        assert 1 <= len(sentences) <= 2, (m.name, m.explanation)


def test_every_intent_reads_from_a_control_text() -> None:
    for (control, position), intents in LANGUAGE_INTENTS.items():
        texts = LENGTH_TEXTS if control is Control.LENGTH else TONE_TEXTS
        assert position in texts, (control, position)
        for measure, _direction in intents:
            assert measure in CATALOG, measure


def test_the_relation_lanes_are_catalogued() -> None:
    assert set(RELATION_LANES) <= set(CATALOG)

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 309: session vocabulary v0.11 (§ W) as types. Written before the types existed."""

from __future__ import annotations

import msgspec

from substrate.language import drift, profile
from substrate.language.profile import Params
from substrate.topologies.session import LanguageDrift, LanguageProfile
from substrate.topologies.session import vocabulary as v


def test_the_kinds_producer_and_triggers_are_in_the_vocabulary() -> None:
    assert (v.LANGUAGE_PROFILE, v.LANGUAGE_DRIFT) == ("LanguageProfile", "LanguageDrift")
    assert (
        v.PRODUCER_KIND_LANGUAGE == "language"
        and v.PRODUCER_KIND_LANGUAGE in v.SESSION_PRODUCER_KINDS
    )
    assert v.TRIGGER_ID_LANGUAGE_ON_REPLY == "language-on-reply"
    assert v.TRIGGER_ID_RETURN_ON_LANGUAGE == "return-on-language"
    assert {
        v.TRIGGER_ID_LANGUAGE_ON_REPLY,
        v.TRIGGER_ID_RETURN_ON_LANGUAGE,
    } <= v.SESSION_TRIGGER_IDS
    assert [s.value for s in v.LanguageStream] == [
        "user",
        "delegate",
        "model",
        "relation",
        "composed",
    ]
    assert [p.value for p in v.LanguagePairing] == ["final", "turn"]
    for name in (
        "LANGUAGE_PROFILE",
        "LANGUAGE_DRIFT",
        "PRODUCER_KIND_LANGUAGE",
        "LanguageStream",
        "LanguagePairing",
    ):
        assert name in v.__all__


def test_the_events_round_trip() -> None:
    measures = profile("The port is 8080. It is set in the config.")["measures"]
    lp = LanguageProfile(
        stream=v.LanguageStream.MODEL,
        turn_index=0,
        source_seq=12,
        step=0,
        pairing=None,
        library="0.2.0",
        preprocessing="substrate-text-1",
        instrument_sha256="0" * 64,
        measures=measures,
    )
    back = msgspec.json.decode(msgspec.json.encode(lp), type=LanguageProfile)
    assert back.measures["words"] == measures["words"] and back.stream is v.LanguageStream.MODEL
    ld = LanguageDrift(
        stream=v.LanguageStream.USER,
        measure="words",
        direction=drift.Direction.UP,
        statistic=11.5,
        source_seq=300,
        series_length=24,
        delta=0.25,
        threshold=10.0,
        warmup=20,
    )
    assert msgspec.json.decode(msgspec.json.encode(ld), type=LanguageDrift) == ld


def test_the_instrument_digest_moves_with_a_parameter_and_only_then() -> None:
    a = profile("One text.")["instrument_sha256"]
    assert a == profile("A different text, longer.")["instrument_sha256"]
    assert a != profile("One text.", Params(mattr_window=50))["instrument_sha256"]
    assert len(a) == 64


def test_the_watched_measures_are_profile_measures() -> None:
    names = set(profile("Some text here.")["measures"])
    assert drift.WATCHED and set(drift.WATCHED) <= names


def test_command_lines_carry_the_same_instrument_digest() -> None:
    from pathlib import Path

    from substrate import app

    record = (
        Path(__file__).resolve().parents[1]
        / "src/substrate/topologies/daily/records/ci_mode.record"
    )
    lines = list(app.language_lines(record))
    assert lines and {x["instrument_sha256"] for x in lines} == {profile("")["instrument_sha256"]}

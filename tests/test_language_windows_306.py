# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 306: a measure is reported only for a window at least as long as its minimum
(docs/language/windows.md)."""

from __future__ import annotations

import json
from pathlib import Path

from substrate.language import measures as m
from substrate.language import parse, profile, words
from substrate.language import relation as rel

ROOT = Path(__file__).resolve().parents[1]
REPLIES = [
    json.loads(line)["text"]
    for line in (
        ROOT / "process/runs/assays/length_drift_2026-10-12_k299/glm-5.2_cloud.jsonl"
    ).open(encoding="utf-8")
]


def _text_of(at_least: int) -> str:
    text = ""
    for reply in REPLIES:
        text = f"{text}\n\n{reply}" if text else reply
        if len(words(parse(text))) >= at_least:
            return text
    raise AssertionError(f"the replies hold fewer than {at_least} words")


def test_one_reply_reports_none_for_the_long_window_measures() -> None:
    out = profile(REPLIES[0]).measures
    assert out["words"] < m.MIN_WORDS_HEAPS
    for key in ("entropy", "zipf_alpha", "zipf_s", "heaps_beta", "dfa_alpha"):
        assert out[key] is None, key
    assert out["compression_ratio"] is not None  # no minimum: compared at equal lengths


def test_each_measure_appears_at_its_minimum() -> None:
    heaps = profile(_text_of(m.MIN_WORDS_HEAPS)).measures
    assert heaps["heaps_beta"] is not None and heaps["entropy"] is None
    long = profile(_text_of(m.MIN_WORDS_ENTROPY)).measures
    assert long["entropy"] is not None and long["zipf_alpha"] is not None


def test_lsm_needs_its_minimum_on_both_sides() -> None:
    short, long = parse(REPLIES[0]), parse(_text_of(m.MIN_WORDS_LSM))
    assert rel.lsm(short, long)["lsm"] is None
    assert rel.lsm(long, long)["lsm"] is not None


def test_the_profile_names_the_minimums_it_applied() -> None:
    assert profile("One short reply.").instrument.minimums == m.MINIMUMS
    assert m.MINIMUMS["entropy_words"] == m.MIN_WORDS_ENTROPY == 3200


def test_burstiness_counts_only_words_with_twenty_occurrences() -> None:
    text = " ".join(["x"] * 19 + [f"o{i}" for i in range(50)])
    assert profile(text).measures["burstiness_words"] == 0.0

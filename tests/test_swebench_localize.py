# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Observation contract for LOCALIZE (sprint 138). The parser + recall@k are pure units; the producer is
run in a minimal topology and the SuspectFiles / EditLocations records are the observable (#24)."""

from substrate import api
from substrate.api import Runtime, read_record
from substrate.reference._models import DeterministicResponder, ModelUsage
from substrate.topologies.swebench_solver.localize import (
    full_recall_at_k,
    localizer_factory,
    parse_suspect_files,
    recall_at_k,
)
from substrate.topologies.swebench_solver.records import EditLocations, SuspectFiles


def test_parse_suspect_files_filters_to_known_and_dedupes() -> None:
    resp = "src/app.py\nnonexistent.py\n- src/util.py\njust prose here\nsrc/app.py\n"
    known = {"src/app.py", "src/util.py", "src/other.py"}
    assert parse_suspect_files(resp, known) == [
        "src/app.py",
        "src/util.py",
    ]  # filtered, deduped, ordered


def test_full_recall_at_k_is_the_localization_ceiling() -> None:
    assert full_recall_at_k(("a.py", "b.py", "c.py"), {"a.py", "b.py"}) is True
    assert (
        full_recall_at_k(("a.py", "c.py"), {"a.py", "b.py"}) is False
    )  # missed b.py -> can't repair it


def test_recall_at_k_is_fractional() -> None:
    assert recall_at_k(("a.py", "c.py"), {"a.py", "b.py"}) == 0.5  # found 1 of 2 gold files
    assert recall_at_k(("a.py", "b.py"), {"a.py", "b.py"}) == 1.0
    assert recall_at_k((), {"a.py"}) == 0.0


async def test_localizer_emits_suspects_and_edit_locations(tmp_path) -> None:  # type: ignore[no-untyped-def]
    issue = "f returns the wrong value"
    skeleton = "src/app.py\nsrc/util.py\ntests/test_app.py"
    known = {"src/app.py", "src/util.py", "tests/test_app.py"}
    responder = DeterministicResponder(seed=0, menu=["src/app.py\nsrc/util.py\n"])

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "localizer",
            schemas=[SuspectFiles, EditLocations, ModelUsage],
            schema_version=1,
            factory=localizer_factory(responder, issue, skeleton, known_files=known),
            deterministic=False,
        )
        b.initial("localizer", input=None)
        b.termination(api.any_of(api.threshold_count("EditLocations", 1), api.quiescence()))

    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))

    suspects = [e["payload"] for e in events if e["kind"] == "SuspectFiles"]
    locs = [e["payload"] for e in events if e["kind"] == "EditLocations"]
    assert len(suspects) == 1 and suspects[0]["files"] == ["src/app.py", "src/util.py"]
    assert len(locs) == 1 and locs[0]["targets"] == ["src/app.py", "src/util.py"]
    # full recall against a gold set (app.py is the gold-patch file) — the suspect set contains it.
    assert full_recall_at_k(tuple(suspects[0]["files"]), {"src/app.py"}) is True

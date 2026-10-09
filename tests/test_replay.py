# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Replay engine tests (technical §12): Level 1 (stream/counts), Level 2 (input-hash
verification, D-5), Level 3(a) precondition gate (honest refusal), Level 3(b) deferred."""

import pytest
from msgspec import Struct

from substrate.api import (
    PerEvent,
    Runtime,
    Subscription,
    assert_replayable,
    quiescence,
    read_record,
    replay,
    threshold_count,
)
from substrate.projections.replay import ReplayError


class CountReached(Struct, frozen=True):
    n: int


class Doubled(Struct, frozen=True):
    original: int
    doubled: int


async def counter(_input):
    for n in range(1, 4):
        yield CountReached(n=n)


async def doubler(inp):
    yield Doubled(original=inp["n"], doubled=inp["n"] * 2)


def _det_topo(b):
    # both kinds author-flagged deterministic, no wall-clock cooldown -> ceiling 3a
    b.producer_kind(
        "counter",
        schemas=[CountReached],
        schema_version=1,
        factory=lambda: counter,
        deterministic=True,
    )
    b.producer_kind(
        "doubler",
        schemas=[Doubled],
        schema_version=1,
        factory=lambda: doubler,
        deterministic=True,
    )
    b.initial("counter", input=None)
    b.trigger(
        "double-each",
        subscription=Subscription(kinds=frozenset({"CountReached"})),
        predicate=lambda ctx: True,
        starts="doubler",
        input_builder=lambda ctx: {"n": ctx.event.payload["n"]},
        policy=PerEvent(),
    )
    b.termination(quiescence())


def _nondet_topo(b):
    # counter NOT flagged deterministic -> Level 3a must refuse
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.initial("counter", input=None)
    b.termination(threshold_count("substrate.ProducerCompleted", 1))


# ── Level 1 ───────────────────────────────────────────────────────────────────
async def test_level1_reconstructs_stream_and_counts(tmp_path):
    await Runtime(tmp_path / "run").run(_det_topo)
    r = replay(tmp_path / "run", level="1")
    assert r.level == "1"
    assert r.complete is True
    assert r.counts["CountReached"] == 3
    assert r.counts["Doubled"] == 3
    assert r.counts["substrate.RunStarted"] == 1
    assert r.frame_count == len(list(read_record(tmp_path / "run")))


# ── Level 2 (D-5 input-hash verification) ──────────────────────────────────────
async def test_level2_verifies_every_trigger_fired_input_hash(tmp_path):
    await Runtime(tmp_path / "run").run(_det_topo)
    r = replay(tmp_path / "run", level="2")
    assert r.level == "2"
    # 1 initial firing + 3 double-each firings = 4 TriggerFired, all with verifiable hashes
    assert r.decisions_verified == 4
    assert r.mismatches == ()


async def test_level2_detects_a_tampered_input_hash(tmp_path):
    await Runtime(tmp_path / "run").run(_det_topo)
    # tamper: load the record, corrupt one TriggerFired's input_sha256, replay the iterable
    envs = list(read_record(tmp_path / "run"))
    for e in envs:
        if (
            e["kind"] == "substrate.TriggerFired"
            and e["payload"].get("trigger_id") == "double-each"
        ):
            e["payload"]["input_sha256"] = "sha256:" + "0" * 64
            break
    r = replay(envs, level="2")
    assert len(r.mismatches) == 1
    assert r.mismatches[0].recorded == "sha256:" + "0" * 64


async def test_level2_flags_a_malformed_firing_missing_both_input_fields(tmp_path):
    # a TriggerFired with input_sha256 but NEITHER resolved_input nor input_blob violates
    # D-5 ("exactly one present") -> Level 2 flags it rather than silently skipping.
    await Runtime(tmp_path / "run").run(_det_topo)
    envs = list(read_record(tmp_path / "run"))
    for e in envs:
        if e["kind"] == "substrate.TriggerFired":
            e["payload"].pop("resolved_input", None)
            e["payload"].pop("input_blob", None)
            break
    r = replay(envs, level="2")
    assert len(r.mismatches) == 1
    assert r.mismatches[0].recomputed == "<no-input-field>"


async def test_level2_handles_blob_offloaded_input(tmp_path):
    # a >16 KiB resolved input is blob-offloaded; Level 2 must re-hash the blob bytes and
    # match input_sha256.
    def _big_topo(b):
        b.producer_kind(
            "counter",
            schemas=[CountReached],
            schema_version=1,
            factory=lambda: counter,
            deterministic=True,
        )
        b.producer_kind(
            "doubler",
            schemas=[Doubled],
            schema_version=1,
            factory=lambda: doubler,
            deterministic=True,
        )
        b.initial("counter", input=None)
        b.trigger(
            "big",
            subscription=Subscription(kinds=frozenset({"CountReached"})),
            predicate=lambda ctx: True,
            starts="doubler",
            input_builder=lambda ctx: {"n": 1, "pad": "z" * (20 * 1024)},
            policy=PerEvent(),
        )
        b.termination(quiescence())

    await Runtime(tmp_path / "run").run(_big_topo)
    # confirm at least one TriggerFired used the blob form
    envs = list(read_record(tmp_path / "run"))
    assert any(e["kind"] == "substrate.TriggerFired" and "input_blob" in e["payload"] for e in envs)
    r = replay(tmp_path / "run", level="2")
    assert r.mismatches == ()  # blob bytes re-hash to the recorded input_sha256


# ── Level 3(a) precondition gate ───────────────────────────────────────────────
async def test_level3a_preconditions_ok_for_deterministic_3a_ceiling(tmp_path):
    await Runtime(tmp_path / "run").run(_det_topo)
    r = replay(tmp_path / "run", level="3a")
    assert r.preconditions_ok is True
    assert r.refusal_reason is None
    # assert_replayable returns without raising
    assert_replayable(tmp_path / "run", "3a")


async def test_level3a_refuses_nondeterministic_producer(tmp_path):
    await Runtime(tmp_path / "run").run(_nondet_topo)
    r = replay(tmp_path / "run", level="3a")
    assert r.preconditions_ok is False
    assert "non-deterministic" in r.refusal_reason
    with pytest.raises(ReplayError):
        assert_replayable(tmp_path / "run", "3a")


# ── Level 3(b) deferred ─────────────────────────────────────────────────────--
async def test_level3b_is_deferred_not_faked(tmp_path):
    await Runtime(tmp_path / "run").run(_det_topo)
    with pytest.raises(NotImplementedError):
        replay(tmp_path / "run", level="3b")


async def test_unknown_level_raises(tmp_path):
    await Runtime(tmp_path / "run").run(_det_topo)
    with pytest.raises(ReplayError):
        replay(tmp_path / "run", level="9")  # type: ignore[arg-type]

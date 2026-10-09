# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 199 + 199a: kernel enforcement of `Budget.wall_seconds`, structured payload.

A producer_kind that declares `Budget(wall_seconds=Cap(limit=..., reason=...))` and whose
Producer runs longer than `limit` seconds trips the enforcement site inside
`Runtime._producer_task`. The async-for consumer wraps in `asyncio.wait_for`; on TimeoutError
the emitter writes `substrate.ProducerFailed` with:

    payload = {
        "producer": ref,
        "error": "budget_exceeded",          # short human tag
        "budget_exceeded": {                   # typed discrimination block
            "axis": "wall_seconds",
            "limit": <float>,
            "reason": <str from cap.reason>,
        },
    }

Downstream readers check `payload.get("budget_exceeded")` — a typed dict with three fields,
not a string prefix. Sprint 199a fold closed the KIT_DIARY 44 gap by replacing the interim
string wire form with this structured shape."""

from __future__ import annotations

import asyncio
import warnings

from msgspec import Struct

from substrate.api import (
    Budget,
    Cap,
    Runtime,
    assert_event,
    assert_no_event,
    quiescence,
    read_record,
)
from substrate.kernel.runtime import (
    BUDGET_EXCEEDED_AXIS_WALL_SECONDS,
    BUDGET_EXCEEDED_ERROR_TAG,
)


class _Tick(Struct, frozen=True):
    n: int


async def _sleeper_1s(_inp):
    await asyncio.sleep(1.0)
    yield _Tick(n=1)


async def _fast_tick(_inp):
    yield _Tick(n=1)


def _topology_with_wall_cap(cap_s: float, reason: str):
    def topo(b):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            b.producer_kind(
                "sleeper",
                schemas=[_Tick],
                schema_version=1,
                factory=lambda: _sleeper_1s,
                budget=Budget(wall_seconds=Cap(limit=cap_s, reason=reason)),
            )
        b.initial("sleeper", input=None)
        # Quiescence terminates once the producer ends (completed / failed / cancelled) and
        # no further events flow — covers both the wall-cap trip (ProducerFailed) and the
        # normal-completion path (ProducerCompleted).
        b.termination(quiescence())

    return topo


def _topology_no_budget():
    def topo(b):
        b.producer_kind(
            "fast",
            schemas=[_Tick],
            schema_version=1,
            factory=lambda: _fast_tick,
        )
        b.initial("fast", input=None)
        b.termination(quiescence())

    return topo


async def test_wall_seconds_cap_trips_and_emits_typed_producer_failed(tmp_path):
    """A producer that sleeps 1s under a 0.1s wall cap trips enforcement: exactly one
    ProducerFailed whose payload carries a `budget_exceeded` dict with axis, limit, and
    reason as typed fields. `error` is the short tag; the typed block is the discrimination
    signal a report/salvage/replay reader consumes."""
    topo = _topology_with_wall_cap(0.1, "test-cap")
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"
    failed = assert_event(tmp_path / "run", "substrate.ProducerFailed")
    assert failed["payload"]["error"] == BUDGET_EXCEEDED_ERROR_TAG
    block = failed["payload"]["budget_exceeded"]
    assert block["axis"] == BUDGET_EXCEEDED_AXIS_WALL_SECONDS
    assert block["limit"] == 0.1
    assert block["reason"] == "test-cap"
    # The producer never completed — the wall_seconds trip is a failure, not a completion.
    assert_no_event(tmp_path / "run", "substrate.ProducerCompleted")


async def test_producer_failed_without_budget_breach_has_no_budget_exceeded_block(tmp_path):
    """A producer that raises for a bug (not a budget breach) writes ProducerFailed
    without the `budget_exceeded` block. Readers that check `payload.get("budget_exceeded")`
    treat absence as "not a budget failure" — no string parsing, no ambiguity."""

    class _Boom(RuntimeError):
        pass

    async def _bugger(_inp):
        raise _Boom("bug")
        yield  # unreachable

    def topo(b):
        b.producer_kind("bugger", schemas=[_Tick], schema_version=1, factory=lambda: _bugger)
        b.initial("bugger", input=None)
        b.termination(quiescence())

    await Runtime(tmp_path / "run").run(topo)
    failed = assert_event(tmp_path / "run", "substrate.ProducerFailed")
    assert "budget_exceeded" not in failed["payload"], (
        "producer bug must not carry the budget_exceeded block"
    )
    assert failed["payload"]["error"] != BUDGET_EXCEEDED_ERROR_TAG


async def test_wall_seconds_cap_below_producer_runtime_does_not_trip(tmp_path):
    """A producer with a wall cap COMFORTABLY above its runtime yields the normal
    ProducerCompleted path — no false trip from the enforcement wrapper."""
    # A fast producer under a 10s cap — the cap is present, the wrap fires, and it should
    # never trigger. Uses the sleeper-1s topology so wall-cap logic runs with 10s > 1s.
    topo = _topology_with_wall_cap(10.0, "generous")
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"
    assert_event(tmp_path / "run", "substrate.ProducerCompleted")
    assert_no_event(tmp_path / "run", "substrate.ProducerFailed")


async def test_no_budget_declared_bypasses_wall_enforcement(tmp_path):
    """A producer with no Budget runs unwrapped — no ProducerFailed, no timeout path.
    The pre-Sprint-199 behaviour is preserved for every producer that didn't opt in."""
    topo = _topology_no_budget()
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"
    assert_event(tmp_path / "run", "substrate.ProducerCompleted")
    assert_no_event(tmp_path / "run", "substrate.ProducerFailed")


def test_declaring_only_wall_seconds_no_longer_warns():
    """Sprint 172's UserWarning fired for any Budget declaration because nothing was
    enforced. Sprint 199 lands wall_seconds enforcement, so declaring only wall_seconds
    is honest — no warning. event_counts declarations still warn (see next test)."""
    from substrate.kernel.topology import TopologyBuilder

    b = TopologyBuilder()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        b.producer_kind(
            "wall_only",
            schemas=[_Tick],
            schema_version=1,
            factory=lambda: _fast_tick,
            budget=Budget(wall_seconds=Cap(limit=30.0, reason="test")),
        )
    budget_warnings = [
        w for w in caught if "Budget" in str(w.message) and issubclass(w.category, UserWarning)
    ]
    assert not budget_warnings, (
        f"wall_seconds-only Budget should not warn after Sprint 199; got {budget_warnings}"
    )


def test_declaring_event_counts_does_not_warn():
    """event_counts is enforced since kernel sprint 251, so declaring a cap no longer warns
    that it is not."""
    from substrate.kernel.topology import TopologyBuilder

    b = TopologyBuilder()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        b.producer_kind(
            "counted",
            schemas=[_Tick],
            schema_version=1,
            factory=lambda: _fast_tick,
            budget=Budget(event_counts={"_Tick": Cap(limit=10, reason="test")}),
        )
    matching = [
        w
        for w in caught
        if "event_counts" in str(w.message) and issubclass(w.category, UserWarning)
    ]
    assert not matching, [str(w.message) for w in matching]


async def test_read_record_carries_typed_error(tmp_path):
    """The record on disk carries the typed error — a reader running post-run picks up
    the same wire form the runner would see live, so salvage/replay/report paths read
    the same signal."""
    topo = _topology_with_wall_cap(0.1, "record-check")
    await Runtime(tmp_path / "run").run(topo)
    failed = [e for e in read_record(tmp_path / "run") if e["kind"] == "substrate.ProducerFailed"]
    assert len(failed) == 1
    assert failed[0]["payload"]["error"] == BUDGET_EXCEEDED_ERROR_TAG
    block = failed[0]["payload"]["budget_exceeded"]
    assert block["axis"] == BUDGET_EXCEEDED_AXIS_WALL_SECONDS
    assert block["limit"] == 0.1
    assert block["reason"] == "record-check"

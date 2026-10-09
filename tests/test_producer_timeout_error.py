"""A Producer whose own code raises TimeoutError fails like any other Producer.

asyncio.TimeoutError IS the builtin TimeoutError on 3.11+. The runtime caught it for the wall
budget and asserted a budget existed, so a socket or urllib timeout in a Producer without a
budget raised AssertionError: no ProducerFailed was recorded and the run never quiesced (lens
audit F014, reproduced by scratchpad/probe_runtime.py: the record stopped at ProducerStarted and
the run was alive at 15 s). With a budget, the same timeout was reported as a budget breach.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from msgspec import Struct

from substrate import api


class Never(Struct, frozen=True):
    n: int


async def _times_out(_inp: object) -> AsyncIterator[Never]:
    raise TimeoutError("read timed out")  # what urllib / socket raise
    yield Never(n=0)  # pragma: no cover — makes this an async generator


def _topology(budget: api.Budget | None) -> object:
    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "fetcher",
            schemas=[Never],
            schema_version=1,
            factory=lambda: _times_out,
            deterministic=True,
            budget=budget,
        )
        b.initial("fetcher", input={})
        b.termination(api.quiescence_with_watchdog(seconds=1))

    return topo


def _failed(root: Path) -> list[dict]:
    return [e for e in api.read_record(root) if e["kind"] == api.PRODUCER_FAILED]


async def test_a_timeout_without_a_budget_is_an_ordinary_failure(tmp_path: Path) -> None:
    root = tmp_path / "run"
    await asyncio.wait_for(api.Runtime(root).run(_topology(None)), timeout=10)
    failed = _failed(root)
    assert len(failed) == 1
    assert "read timed out" in failed[0]["payload"]["error"]
    assert "budget_exceeded" not in failed[0]["payload"]


async def test_a_timeout_inside_a_budget_is_not_a_budget_breach(tmp_path: Path) -> None:
    root = tmp_path / "run"
    budget = api.Budget(wall_seconds=api.Cap(limit=30.0, reason="wall cap"))
    await asyncio.wait_for(api.Runtime(root).run(_topology(budget)), timeout=10)
    failed = _failed(root)
    assert len(failed) == 1
    assert "read timed out" in failed[0]["payload"]["error"]
    assert "budget_exceeded" not in failed[0]["payload"]

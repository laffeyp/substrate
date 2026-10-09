# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 217c — Runtime.cancel_producer(instance) with the v0.3 provenance annotation.

Nine tests covering the primitive contract:

  1. Cancel a running producer by instance → ProducerRef returned; ProducerCancelled
     lands with cause="external", caller="test".
  2. Cross-thread cancel via loop.call_soon_threadsafe → same envelope shape.
  3. Cancel on an unknown instance → None; no envelope.
  4. Cancel on an already-done instance → None; no envelope.
  5. Cancel a wait_for-wrapped producer (wall budget) → CancelledError propagates cleanly;
     ProducerCancelled carries cause="external", NOT error="budget_exceeded".
  6. Policy path (`_cancel_others`) writes cause="policy", caller=<policy name>.
  7. Topology WITH a park-on-interrupt ProducerCancelled subscriber → Park fires,
     pause_await_input pauses.
  8. Topology WITHOUT any ProducerCancelled subscriber → run ends cleanly at
     quiescence; RunFinalised lands.
  9. Cancel called before Runtime.run/.resume → RuntimeError.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from typing import Any

import pytest
from msgspec import Struct

from substrate import api
from substrate.constants import PRODUCER_CANCELLED, RUN_FINALISED


class Tick(Struct, frozen=True):
    n: int


class Park(Struct, frozen=True):
    reason: str


async def _slow(_inp: object) -> AsyncIterator[Tick]:
    for i in range(1, 1000):
        await asyncio.sleep(0.5)
        yield Tick(n=i)


def _slow_topo() -> Any:
    """A topology with one slow producer that never completes on its own."""

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind("slow", schemas=[Tick], schema_version=1, factory=lambda: _slow)
        b.initial("slow", input=None)
        b.termination(api.quiescence())

    return topo


def _park_on_cancel_topo() -> Any:
    """A topology whose park producer fires on ProducerCancelled."""

    async def _park(inp: Any) -> AsyncIterator[Park]:
        reason = str(inp.get("reason", "unknown")) if hasattr(inp, "get") else "unknown"
        yield Park(reason=reason)

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind("slow", schemas=[Tick], schema_version=1, factory=lambda: _slow)
        b.producer_kind("park", schemas=[Park], schema_version=1, factory=lambda: _park)
        b.initial("slow", input=None)
        b.trigger(
            "park-on-cancel",
            subscription=api.Subscription(kinds=frozenset({PRODUCER_CANCELLED})),
            predicate=lambda ctx: True,
            starts="park",
            input_builder=lambda ctx: {"reason": "interrupted"},
            policy=api.PerEvent(),
        )
        b.termination(
            api.any_of(
                api.pause_await_input(
                    when=lambda tctx: tctx.event is not None and tctx.event.kind == "Park",
                    resume_condition="UserMessage",
                ),
                api.quiescence(),
            )
        )

    return topo


def _live_instance(runtime: api.Runtime, kind: str) -> str | None:
    """The first live instance of a kind, or None."""
    st = runtime._st  # noqa: SLF001 — test-only introspection of run state
    for inst, k in st.kind_by_instance.items():
        if k == kind:
            return inst
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 1. Cancel returns ref; envelope carries cause + caller.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_producer_records_cause_and_caller(tmp_path):
    runtime = api.Runtime(tmp_path / "rec")
    cancelled: dict[str, Any] = {}

    async def _fire_cancel():
        await asyncio.sleep(0.2)
        inst = _live_instance(runtime, "slow")
        cancelled["ref"] = runtime.cancel_producer(inst, cause="external", caller="test")

    await asyncio.gather(runtime.run(_slow_topo()), _fire_cancel())

    ref = cancelled["ref"]
    assert ref is not None
    assert ref["kind"] == "slow"
    assert ref["instance"]

    envs = list(api.read_record(tmp_path / "rec"))
    cancelled_envs = [e for e in envs if e["kind"] == PRODUCER_CANCELLED]
    assert len(cancelled_envs) == 1
    payload = cancelled_envs[0]["payload"]
    assert payload["producer"]["kind"] == "slow"
    assert payload["cause"] == "external"
    assert payload["caller"] == "test"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cross-thread: call_soon_threadsafe from a worker.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_producer_cross_thread_via_call_soon_threadsafe(tmp_path):
    """A worker thread schedules cancel_producer onto the runtime's event loop
    via loop.call_soon_threadsafe. The record shows one ProducerCancelled with
    the annotation the worker supplied.
    """
    import time
    from functools import partial

    runtime = api.Runtime(tmp_path / "rec")
    loop = asyncio.get_running_loop()
    fired = threading.Event()

    def _worker() -> None:
        # Poll for the runtime to reach a live-instance state, then dispatch one
        # cancel via call_soon_threadsafe. Both `_st` and the instance appear
        # once runtime.run enters _flush_scheduled. `cancel_producer` takes
        # keyword-only cause/caller, so we schedule via functools.partial.
        for _ in range(500):
            st = getattr(runtime, "_st", None)
            if st is not None:
                inst = _live_instance(runtime, "slow")
                if inst is not None:
                    loop.call_soon_threadsafe(
                        partial(
                            runtime.cancel_producer,
                            inst,
                            cause="external",
                            caller="worker-thread",
                        )
                    )
                    fired.set()
                    return
            time.sleep(0.01)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    await runtime.run(_slow_topo())
    t.join(timeout=2)
    assert fired.is_set(), "worker thread never found a live slow instance"

    envs = list(api.read_record(tmp_path / "rec"))
    cancelled_envs = [e for e in envs if e["kind"] == PRODUCER_CANCELLED]
    assert len(cancelled_envs) == 1
    payload = cancelled_envs[0]["payload"]
    assert payload["cause"] == "external"
    assert payload["caller"] == "worker-thread"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Unknown instance returns None; no envelope.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_producer_unknown_instance_returns_none(tmp_path):
    runtime = api.Runtime(tmp_path / "rec")
    seen: dict[str, Any] = {}

    async def _probe():
        await asyncio.sleep(0.2)
        seen["ref"] = runtime.cancel_producer("does-not-exist")
        real_inst = _live_instance(runtime, "slow")
        runtime.cancel_producer(real_inst, caller="cleanup")

    await asyncio.gather(runtime.run(_slow_topo()), _probe())
    assert seen["ref"] is None

    envs = list(api.read_record(tmp_path / "rec"))
    cancelled_envs = [e for e in envs if e["kind"] == PRODUCER_CANCELLED]
    # exactly one — the cleanup, not the bogus id
    assert len(cancelled_envs) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 4. Already-done instance returns None; no second envelope.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_producer_already_done_returns_none(tmp_path):
    runtime = api.Runtime(tmp_path / "rec")
    outcome: dict[str, Any] = {}

    async def _cancel_twice():
        await asyncio.sleep(0.2)
        inst = _live_instance(runtime, "slow")
        outcome["first"] = runtime.cancel_producer(inst, caller="first")
        # Give the CancelledError handler a tick to fire and remove the entry.
        await asyncio.sleep(0.3)
        outcome["second"] = runtime.cancel_producer(inst, caller="second")

    await asyncio.gather(runtime.run(_slow_topo()), _cancel_twice())
    assert outcome["first"] is not None
    assert outcome["second"] is None

    envs = list(api.read_record(tmp_path / "rec"))
    cancelled_envs = [e for e in envs if e["kind"] == PRODUCER_CANCELLED]
    assert len(cancelled_envs) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. wait_for composition — external cancel wins over budget path.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_producer_composes_with_wait_for_budget(tmp_path):
    runtime = api.Runtime(tmp_path / "rec")

    def topo(b: api.TopologyBuilder) -> None:
        # Wall budget of 10 seconds — plenty, so the external cancel wins the race.
        b.producer_kind(
            "slow",
            schemas=[Tick],
            schema_version=1,
            factory=lambda: _slow,
            budget=api.Budget(wall_seconds=api.Cap(limit=10.0, reason="cap")),
        )
        b.initial("slow", input=None)
        b.termination(api.quiescence())

    async def _fire():
        await asyncio.sleep(0.2)
        inst = _live_instance(runtime, "slow")
        runtime.cancel_producer(inst, caller="race-test")

    await asyncio.gather(runtime.run(topo), _fire())

    envs = list(api.read_record(tmp_path / "rec"))
    cancelled_envs = [e for e in envs if e["kind"] == PRODUCER_CANCELLED]
    failed_envs = [e for e in envs if e["kind"] == "substrate.ProducerFailed"]
    assert len(cancelled_envs) == 1
    assert len(failed_envs) == 0
    assert cancelled_envs[0]["payload"]["cause"] == "external"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Policy path writes cause="policy".
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_others_policy_writes_cause_policy(tmp_path):
    runtime = api.Runtime(tmp_path / "rec")

    class Winner(Struct, frozen=True):
        pass

    async def _win(_inp: object) -> AsyncIterator[Winner]:
        await asyncio.sleep(0.3)
        yield Winner()

    async def _loser(_inp: object) -> AsyncIterator[Tick]:
        for i in range(1, 1000):
            await asyncio.sleep(0.5)
            yield Tick(n=i)

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind("winner", schemas=[Winner], schema_version=1, factory=lambda: _win)
        b.producer_kind("loser", schemas=[Tick], schema_version=1, factory=lambda: _loser)
        b.initial("winner", input=None)
        b.initial("loser", input=None)
        b.termination(
            api.any_of(
                api.cancel_all_others(
                    when=lambda tctx: tctx.event is not None and tctx.event.kind == "Winner"
                ),
                api.quiescence(),
            )
        )

    await runtime.run(topo)

    envs = list(api.read_record(tmp_path / "rec"))
    cancelled_envs = [e for e in envs if e["kind"] == PRODUCER_CANCELLED]
    assert len(cancelled_envs) >= 1
    for env in cancelled_envs:
        assert env["payload"]["cause"] == "policy"
        assert env["payload"]["caller"]  # non-empty policy name


# ─────────────────────────────────────────────────────────────────────────────
# 7. Topology WITH park-on-cancel subscriber pauses cleanly.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_producer_with_park_subscriber_pauses_run(tmp_path):
    runtime = api.Runtime(tmp_path / "rec", persistent=True)

    async def _fire():
        await asyncio.sleep(0.2)
        inst = _live_instance(runtime, "slow")
        runtime.cancel_producer(inst, caller="test")

    result, _ = await asyncio.gather(runtime.run(_park_on_cancel_topo()), _fire())
    assert result.status == "paused"

    envs = list(api.read_record(tmp_path / "rec"))
    kinds = [e["kind"] for e in envs]
    assert PRODUCER_CANCELLED in kinds
    assert "Park" in kinds


# ─────────────────────────────────────────────────────────────────────────────
# 8. Topology WITHOUT any ProducerCancelled subscriber ends at quiescence.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_producer_without_subscriber_ends_at_quiescence(tmp_path):
    runtime = api.Runtime(tmp_path / "rec")

    async def _fire():
        await asyncio.sleep(0.2)
        inst = _live_instance(runtime, "slow")
        runtime.cancel_producer(inst, caller="test")

    result, _ = await asyncio.gather(runtime.run(_slow_topo()), _fire())
    assert result.status == "finalised"

    envs = list(api.read_record(tmp_path / "rec"))
    assert any(e["kind"] == PRODUCER_CANCELLED for e in envs)
    assert envs[-1]["kind"] == RUN_FINALISED


# ─────────────────────────────────────────────────────────────────────────────
# 9. Cancel before run raises RuntimeError.
# ─────────────────────────────────────────────────────────────────────────────


def test_cancel_producer_before_run_raises(tmp_path):
    runtime = api.Runtime(tmp_path / "rec")
    with pytest.raises(RuntimeError, match="before Runtime"):
        runtime.cancel_producer("any")

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Runtime.inject_event — peer to cancel_producer on the daemon-facing surface.

Where cancel_producer stops a live Producer, inject_event records an external
decision on the run's record so triggers subscribed to its kind fire. The frame
appends with producer=null (externally supplied, same as the resume path in
_resume_bootstrap). This is the primitive Phase-8 item 7 uses to write
InterruptRequested onto a live session record; item 8's ToolProgress emission
uses the same primitive from the tool runner's worker thread.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from msgspec import Struct

from substrate import api
from substrate.kernel.topology import RegistrationError


class Beat(Struct, frozen=True):
    n: int


class ExternalMark(Struct, frozen=True):
    label: str
    tier: str = ""


class MarkResponse(Struct, frozen=True):
    saw: str


async def _pulse(_inp: object) -> AsyncIterator[Beat]:
    """A short-lived pulse producer keeps the run alive long enough for an
    external injection to reach the inbox, then completes so quiescence can
    finalise the run."""
    for i in range(1, 5):
        await asyncio.sleep(0.1)
        yield Beat(n=i)


async def _respond(inp: Any) -> AsyncIterator[MarkResponse]:
    label = inp.get("label", "") if hasattr(inp, "get") else ""
    yield MarkResponse(saw=label)


def _inject_topo() -> Any:
    """A pulse producer holds the run open ~0.4s; a trigger fires a response
    producer whenever an ExternalMark envelope lands. Quiescence finalises the
    run once both producers complete and the inbox drains."""

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind("pulse", schemas=[Beat], schema_version=1, factory=lambda: _pulse)
        b.producer_kind(
            "responder", schemas=[MarkResponse], schema_version=1, factory=lambda: _respond
        )
        b.initial("pulse", input=None)
        b.trigger(
            "mark-response",
            subscription=api.Subscription(kinds=frozenset({"ExternalMark"})),
            predicate=lambda ctx: True,
            starts="responder",
            input_builder=lambda ctx: {"label": ctx.event.payload.get("label", "")},
            policy=api.PerEvent(),
        )
        b.termination(api.quiescence_with_watchdog(seconds=1))

    return topo


@pytest.mark.asyncio
async def test_inject_event_lands_on_record_with_producer_null_and_fires_trigger(tmp_path):
    runtime = api.Runtime(tmp_path / "rec")

    async def _fire():
        await asyncio.sleep(0.2)
        runtime.inject_event(ExternalMark(label="hello", tier="soft"))

    await asyncio.gather(runtime.run(_inject_topo()), _fire())

    envs = list(api.read_record(tmp_path / "rec"))
    marks = [e for e in envs if e["kind"] == "ExternalMark"]
    assert len(marks) == 1
    assert marks[0]["payload"] == {"label": "hello", "tier": "soft"}
    # producer=null: the frame is externally-supplied, not Producer-emitted.
    assert marks[0].get("producer") is None
    # The trigger fired: MarkResponse landed carrying the injected label.
    responses = [e for e in envs if e["kind"] == "MarkResponse"]
    assert len(responses) == 1
    assert responses[0]["payload"]["saw"] == "hello"


def test_inject_event_refuses_a_reserved_substrate_kind(tmp_path):
    """type(event).__name__ starting with 'substrate.' is refused — a caller
    cannot forge a lifecycle frame. The check runs before any run state is
    consulted, so this test does not need a live runtime."""

    class _ForgedLifecycle(Struct, frozen=True):
        pass

    _ForgedLifecycle.__name__ = "substrate.ProducerStarted"

    runtime = api.Runtime(tmp_path / "rec")
    # The reserved-kind check runs before the "no live state" check would fire,
    # so this raises RegistrationError, not RuntimeError.
    with pytest.raises(RegistrationError, match="reserved"):
        runtime.inject_event(_ForgedLifecycle())


@pytest.mark.asyncio
async def test_inject_event_cross_thread_via_call_soon_threadsafe(tmp_path):
    import threading

    runtime = api.Runtime(tmp_path / "rec")

    async def _await_live() -> None:
        # Wait until the runtime has state.
        while getattr(runtime, "_st", None) is None:
            await asyncio.sleep(0.01)

    async def _fire_from_worker():
        await _await_live()
        loop = asyncio.get_running_loop()

        def _worker():
            loop.call_soon_threadsafe(runtime.inject_event, ExternalMark(label="from-thread"))

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join()

    await asyncio.gather(runtime.run(_inject_topo()), _fire_from_worker())

    envs = list(api.read_record(tmp_path / "rec"))
    marks = [e for e in envs if e["kind"] == "ExternalMark"]
    assert len(marks) == 1
    assert marks[0]["payload"]["label"] == "from-thread"


def test_inject_event_before_run_raises_runtimeerror(tmp_path):
    runtime = api.Runtime(tmp_path / "rec")
    with pytest.raises(RuntimeError, match="no live state"):
        runtime.inject_event(ExternalMark(label="early"))

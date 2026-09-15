# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""interrupt fragment source — Phase 8 item 7 tests.

Verifies:
 - Injecting an InterruptRequested envelope onto a live session record fires
   the interrupt_fragment_producer, which emits exactly one PromptFragment
   (source="interrupt", precedence=95, provenance carries tier + source).
 - InterruptRequested lands on the record with producer=null (externally
   supplied via Runtime.inject_event).
 - When no interrupt is injected, no interrupt fragment appears — the
   producer is quiet by default.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from msgspec import Struct

from substrate import api
from substrate.topologies.session import InterruptRequested, PromptFragment
from substrate.topologies.session.interrupt_fragment_producer import (
    interrupt_fragment_producer_factory,
)
from substrate.topologies.session.vocabulary import (
    PRODUCER_KIND_INTERRUPT_FRAGMENT,
    TRIGGER_ID_EMIT_INTERRUPT_FRAGMENT,
)


class Beat(Struct, frozen=True):
    n: int


async def _pulse(_inp: object) -> AsyncIterator[Beat]:
    for i in range(1, 5):
        await asyncio.sleep(0.05)
        yield Beat(n=i)


def _minimal_interrupt_topology() -> Any:
    """A pulse producer holds the run open long enough for an external
    injection; the emit-interrupt-fragment trigger fires the interrupt
    fragment producer on any InterruptRequested envelope; quiescence
    finalises once both settle."""

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind("pulse", schemas=[Beat], schema_version=1, factory=lambda: _pulse)
        b.producer_kind(
            PRODUCER_KIND_INTERRUPT_FRAGMENT,
            schemas=[PromptFragment],
            schema_version=1,
            factory=interrupt_fragment_producer_factory(),
            deterministic=True,
        )
        b.initial("pulse", input=None)
        b.trigger(
            TRIGGER_ID_EMIT_INTERRUPT_FRAGMENT,
            subscription=api.Subscription(kinds=frozenset({"InterruptRequested"})),
            predicate=lambda ctx: True,
            starts=PRODUCER_KIND_INTERRUPT_FRAGMENT,
            input_builder=lambda ctx: {
                "tier": ctx.event.payload.get("tier", ""),
                "source": ctx.event.payload.get("source", ""),
            },
            policy=api.PerEvent(),
        )
        b.termination(api.quiescence_with_watchdog(seconds=1))

    return topo


def test_injected_interrupt_produces_a_fragment_with_the_directive(tmp_path):
    """inject_event(InterruptRequested) writes the envelope with
    producer=null and fires the interrupt_fragment_producer, which
    emits one PromptFragment(source="interrupt")."""

    async def _run() -> None:
        runtime = api.Runtime(tmp_path / "rec")

        async def _fire() -> None:
            await asyncio.sleep(0.1)
            runtime.inject_event(
                InterruptRequested(
                    session_id="s_test",
                    tier="soft",
                    source="test:injection",
                )
            )

        await asyncio.gather(runtime.run(_minimal_interrupt_topology()), _fire())

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "rec"))

    marks = [e for e in envs if e.get("kind") == "InterruptRequested"]
    assert len(marks) == 1, f"expected 1 InterruptRequested envelope, got {len(marks)}"
    assert marks[0].get("producer") is None
    assert marks[0]["payload"] == {
        "session_id": "s_test",
        "tier": "soft",
        "source": "test:injection",
    }

    fragments = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "interrupt"
    ]
    assert len(fragments) == 1, f"expected 1 interrupt fragment, got {len(fragments)}"
    payload = fragments[0]["payload"]
    assert payload["precedence"] == 95
    assert payload["provenance"]["tier"] == "soft"
    assert payload["provenance"]["source"] == "test:injection"
    assert "user requested an interrupt" in payload["text"].lower()


def test_no_injection_yields_no_interrupt_fragment(tmp_path):
    """Without an InterruptRequested envelope the fragment producer
    stays quiet — the emit-interrupt-fragment trigger only fires on
    the injected kind."""

    async def _run() -> None:
        runtime = api.Runtime(tmp_path / "rec")
        await runtime.run(_minimal_interrupt_topology())

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "rec"))
    interrupt_fragments = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "interrupt"
    ]
    assert len(interrupt_fragments) == 0

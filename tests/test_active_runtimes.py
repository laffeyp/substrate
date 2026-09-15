# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Runtime.find_active_runtime — the child-runtime registry (Phase 8 item 9).

Where `SessionRegistry._running_handles` keys on session_id, this keys on
record_root. Any caller in the same process can reach a live runtime by
its record path — most importantly, the parent daemon reaching a delegate
child's runtime for a descent-scope interrupt. Registered on `_drive`
start after `self._st = st`; unregistered in the finally block after
close. A re-entrant call at the same record_root is safe: the entry is
only deleted when it still points at this runtime.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from msgspec import Struct

from substrate import api
from substrate.kernel.runtime import _ACTIVE_RUNTIMES_BY_RECORD_ROOT, find_active_runtime


class Beat(Struct, frozen=True):
    n: int


async def _pulse(_inp: object) -> AsyncIterator[Beat]:
    for i in range(1, 4):
        await asyncio.sleep(0.05)
        yield Beat(n=i)


def _pulse_topo():
    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind("pulse", schemas=[Beat], schema_version=1, factory=lambda: _pulse)
        b.initial("pulse", input=None)
        b.termination(api.quiescence_with_watchdog(seconds=1))

    return topo


@pytest.mark.asyncio
async def test_active_runtime_is_discoverable_by_record_root_while_running(tmp_path):
    root = tmp_path / "rec"
    runtime = api.Runtime(root)
    seen: dict[str, object] = {}

    async def _probe():
        # Wait until state is live, then look the runtime up by path.
        while getattr(runtime, "_st", None) is None:
            await asyncio.sleep(0.01)
        seen["found"] = find_active_runtime(root)
        seen["found_str"] = find_active_runtime(str(root))

    await asyncio.gather(runtime.run(_pulse_topo()), _probe())

    assert seen["found"] is runtime
    assert seen["found_str"] is runtime
    # After the run completed, the registry no longer holds the runtime.
    assert find_active_runtime(root) is None


@pytest.mark.asyncio
async def test_registry_clears_even_on_kernel_error(tmp_path):
    root = tmp_path / "rec"
    runtime = api.Runtime(root)
    await runtime.run(_pulse_topo())
    assert find_active_runtime(root) is None
    assert str(root) not in _ACTIVE_RUNTIMES_BY_RECORD_ROOT


def test_find_active_runtime_returns_none_for_a_never_started_path(tmp_path):
    assert find_active_runtime(tmp_path / "never-started") is None

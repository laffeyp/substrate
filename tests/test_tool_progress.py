# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Phase 8 item 8 — ToolProgress emission from a streaming bash tool.

The tool_loop's run_tool sets _BASH_PROGRESS_CTX = (call_id, tool, step)
before entering asyncio.to_thread; _bash reads it, runs subprocess.Popen
with a line-buffered stdout, and calls emit_tool_progress for each line.
emit_tool_progress reads the current Runtime from the kernel's
_CURRENT_RUNTIME contextvar and enqueues the envelope via
loop.call_soon_threadsafe(runtime.inject_event, ...).

The test runs a bash command that emits three lines with a small delay
between each and verifies the record carries:
  - Three ToolProgress envelopes, each with producer=null and monotonic
    offset advancing by the line's byte length.
  - A trailing ToolProgress(eof=True, chunk="") that closes the stream.
  - The paired ToolResult carrying the full concatenated stdout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate import api
from substrate.topologies.tool_loop import ToolProgress, tool_loop_topology
from substrate.topologies.tool_loop.tools import FULL_SUITE


@pytest.mark.timeout(30)
async def test_bash_streams_tool_progress_per_line(tmp_path: Path) -> None:
    root = tmp_path / "rec"
    # Three lines, small delay between each so the read loop reliably
    # sees them as separate reads. The delay is inside bash, not Python.
    cmd = "echo one; sleep 0.05; echo two; sleep 0.05; echo three"
    await api.Runtime(root).run(
        tool_loop_topology(
            tools=FULL_SUITE,
            deterministic=False,
            max_steps=4,
            script=[("bash", [cmd])],
        )
    )
    envs = list(api.read_record(root))
    progress = [e for e in envs if e.get("kind") == "ToolProgress"]

    # Every ToolProgress lands with producer=null (external injection).
    for e in progress:
        assert e.get("producer") is None

    # The three lines produce three chunk emits + one eof emit.
    chunks = [e for e in progress if not e["payload"]["eof"]]
    eofs = [e for e in progress if e["payload"]["eof"]]
    assert len(eofs) == 1, f"expected exactly one eof ToolProgress, got {len(eofs)}"
    assert len(chunks) >= 3, f"expected >=3 chunk emits (one per line), got {len(chunks)}"

    # Offsets are monotonic; each chunk's payload starts at the previous
    # offset + previous chunk length.
    offset = 0
    for e in chunks:
        assert e["payload"]["offset"] == offset, (
            f"expected offset {offset}, got {e['payload']['offset']}"
        )
        offset += len(e["payload"]["chunk"])

    # The chunks concatenate to the same stdout the ToolResult carries.
    tool_result = next(e for e in envs if e.get("kind") == "ToolResult")
    full_stdout = "".join(e["payload"]["chunk"] for e in chunks)
    assert tool_result["payload"]["output"]["stdout"] == full_stdout
    assert "one\n" in full_stdout and "two\n" in full_stdout and "three\n" in full_stdout


def test_tool_progress_struct_shape() -> None:
    """The Struct carries the six documented fields; eof defaults to False."""
    p = ToolProgress(call_id="c0", tool="bash", step=0, chunk="hello\n", offset=0)
    assert p.call_id == "c0"
    assert p.tool == "bash"
    assert p.step == 0
    assert p.chunk == "hello\n"
    assert p.offset == 0
    assert p.eof is False

    p2 = ToolProgress(call_id="c0", tool="bash", step=0, chunk="", offset=6, eof=True)
    assert p2.eof is True

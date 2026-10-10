# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 209a — session_topology one-turn end-to-end with real Producer bodies.

Proves the four Producer bodies wired at sprint 209a work together with the
session triggers and the pause_await_input(Returned) termination.
One turn opens on UserMessage, the scripted model produces two ToolCalls and
a reply, return-on-reply fires, the topology pauses awaiting the next
UserMessage.

The scripted DeterministicResponder path makes the record byte-stable — the
model producer's `model_is_deterministic` flag is True when both conditions
hold, so `assert_replayable(root, "3a")` locks it as a first-class assertion.

A second-turn resume test then proves seq continues cleanly across pauses,
and a `/exit` third turn lands `SessionEnded{user_exit}` and finalises.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.testing import assert_event, assert_no_event
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.tool_loop.tools import CALCULATOR

# A short scripted run inside one K-window: the documented exception to session_topology's
# record_root warning (UI sprint 107 states it here instead of letting it print on every run).
pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")


def _factory(
    *,
    session_id: str,
    script: list[tuple[str, list]] | None,
    max_turns: int = 200,
) -> callable:
    return session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=4096,
        seed="you are a companion",
        tools=CALCULATOR,
        per_turn="",
        max_turns=max_turns,
        turn_max_steps=8,
        session_id=session_id,
        workspace_path="/tmp/session-test",
        script=script,
    )


@pytest.mark.asyncio
async def test_one_turn_scripted_pauses_on_returned(tmp_path: Path) -> None:
    record_root = tmp_path / "sess-1"
    factory = _factory(
        session_id="sess-1",
        script=[("add", [2, 3]), ("mul", [5, 4])],
    )
    result = await api.Runtime(record_root, persistent=True).resume(
        factory,
        resume_event=UserMessage(
            text="please compute (2 + 3) * 4",
            turn_index=0,
            assembled_prompt="please compute (2 + 3) * 4",
            slash_source="chat",
        ),
    )
    assert result.status == "paused"
    # Every expected kind lands with the right payload; scripted math produces 20.
    assert_event(record_root, "UserMessage", turn_index=0)
    assert_event(record_root, "ToolCall", tool="add", step=0)
    assert_event(record_root, "ToolResult", tool="add", output=5, ok=True)
    assert_event(record_root, "ToolCall", tool="mul", step=1)
    assert_event(record_root, "ToolResult", tool="mul", output=20, ok=True)
    assert_event(record_root, "ModelReply", text="20", stop_reason="end_turn", step=2)
    assert_no_event(record_root, "FinalAnswer")
    assert_event(record_root, "Returned", reason="replied", turn_index=0)
    # No SessionEnded on the first turn — the pause holds the run.
    assert_no_event(record_root, "SessionEnded")
    # `assert_replayable(root, "3a")` is not called here — a fresh `.resume()` skips
    # RunStarted, so Level-3(a) refuses. Sprint 214 (daemon session API core) owns the
    # session-open dance fix. Full explanation on the BLACKBOARD; sprint 209a card
    # halt-conditions section names the same gap. Sprint 209b's `test_session_topology_bundled`
    # exercises replay via the CI wrapper, which drives everything through one `.run()`
    # and writes RunStarted normally.


@pytest.mark.asyncio
async def test_second_turn_appends_to_the_same_record(tmp_path: Path) -> None:
    record_root = tmp_path / "sess-2"
    factory = _factory(session_id="sess-2", script=[("add", [1, 1])])
    await api.Runtime(record_root, persistent=True).resume(
        factory,
        resume_event=UserMessage(
            text="first",
            turn_index=0,
            assembled_prompt="first",
            slash_source="chat",
        ),
    )
    factory_2 = _factory(session_id="sess-2", script=[("add", [10, 20])])
    result = await api.Runtime(record_root, persistent=True).resume(
        factory_2,
        resume_event=UserMessage(
            text="second",
            turn_index=1,
            assembled_prompt="second",
            slash_source="chat",
        ),
    )
    assert result.status == "paused"
    # Turn 0's Returned and turn 1's Returned both land — one per turn.
    parks = [e for e in api.read_record(record_root) if e["kind"] == "Returned"]
    assert len(parks) == 2
    assert parks[0]["payload"]["turn_index"] == 0
    assert parks[1]["payload"]["turn_index"] == 1
    # Seqs are strictly monotonic across the pause boundary.
    assert parks[1]["seq"] > parks[0]["seq"]


@pytest.mark.asyncio
async def test_slash_exit_lands_session_ended_user_exit(tmp_path: Path) -> None:
    record_root = tmp_path / "sess-3"
    factory = _factory(session_id="sess-3", script=[("add", [1, 1])])
    await api.Runtime(record_root, persistent=True).resume(
        factory,
        resume_event=UserMessage(
            text="hi",
            turn_index=0,
            assembled_prompt="hi",
            slash_source="chat",
        ),
    )
    factory_exit = _factory(session_id="sess-3", script=[])
    result = await api.Runtime(record_root, persistent=True).resume(
        factory_exit,
        resume_event=UserMessage(
            text="/exit",
            turn_index=1,
            assembled_prompt="/exit",
            slash_source="chat",
        ),
    )
    assert result.status == "finalised"
    assert_event(record_root, "SessionEnded", reason="user_exit")

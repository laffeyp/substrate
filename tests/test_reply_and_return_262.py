# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K262: one ModelReply per model call, and Returned ends every turn.

Before: a plain turn wrote its text twice (`ModelReply` then `FinalAnswer`), `model_usage` was
always `{}`, a tool call wrote no reply event, the turn ended with `Park`, and a hard interrupt
during a tool call never ended the turn (lens F093). The termination guard matched a regex over
the policy's name (F097).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.session import (
    UserMessage,
    _refuse_all_completed,
    session_topology,
)
from substrate.topologies.tool_loop.tools import CALCULATOR, full_suite

_FRAMING = ("substrate.", "PromptFragment", "SessionStarted", "SessionWarning")


def _domain(envs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in envs if not e["kind"].startswith(_FRAMING)]


def _um(text: str) -> UserMessage:
    return UserMessage(text=text, turn_index=0, assembled_prompt="", slash_source="chat")


def _run(root: Path, topo: Any) -> list[dict[str, Any]]:
    asyncio.run(api.Runtime(root).run(topo, name="session"))
    return list(api.read_record(root, resolve_blobs=True))


def test_a_plain_turn_writes_one_reply_and_returns(tmp_path: Path) -> None:
    topo = session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=4_096,
        seed="SEED",
        tools={},
        session_id="s262",
        workspace_path=str(tmp_path),
        first_turn_user_message=_um("what is the capital of France?"),
    )
    envs = _domain(_run(tmp_path / "rec", topo))
    assert [e["kind"] for e in envs] == ["UserMessage", "PromptComposed", "ModelReply", "Returned"]
    reply, returned = envs[2]["payload"], envs[3]["payload"]
    assert reply["stop_reason"] == "end_turn" and reply["step"] == 0 and reply["text"]
    usage = reply["usage"]
    assert set(usage) == {"model", "prompt_tokens", "completion_tokens", "wall_ms", "estimated"}
    assert usage["prompt_tokens"] > 0 and usage["completion_tokens"] > 0
    assert usage["estimated"] is True  # the deterministic driver reports no provider counts
    assert returned == {"turn_index": 0, "reason": "replied", "detail": ""}


class _TextToolUser:
    """A text-mode driver (no `achat_tools`): asks for add(2, 3), then add(5, 4), then answers."""

    name = "text-tool-user"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return json.dumps({"name": "add", "arguments": {"a": 2, "b": 3}})
        if self.calls == 2:
            return json.dumps({"name": "add", "arguments": {"a": 5, "b": 4}})
        return "The sum is 9."


def test_each_tool_call_follows_its_own_reply(tmp_path: Path) -> None:
    topo = session_topology(
        driver=_TextToolUser(),
        driver_name="text-tool-user",
        driver_context_tokens=4_096,
        seed="SEED",
        tools=dict(CALCULATOR),
        session_id="s262t",
        workspace_path=str(tmp_path),
        first_turn_user_message=_um("add 2 and 3, then add 4"),
    )
    envs = _domain(_run(tmp_path / "rec", topo))
    kinds = [e["kind"] for e in envs]
    assert kinds == [
        "UserMessage",
        "PromptComposed",
        "ModelReply",
        "ToolCall",
        "ToolResult",
        "PromptComposed",
        "ModelReply",
        "ToolCall",
        "ToolResult",
        "PromptComposed",
        "ModelReply",
        "Returned",
    ], kinds
    replies = [e["payload"] for e in envs if e["kind"] == "ModelReply"]
    assert [(r["stop_reason"], r["step"]) for r in replies] == [
        ("tool_use", 0),
        ("tool_use", 1),
        ("end_turn", 2),
    ]
    assert replies[0]["text"] == "" and replies[2]["text"] == "The sum is 9."
    assert all(r["usage"]["prompt_tokens"] > 0 for r in replies)
    assert "FinalAnswer" not in kinds
    # The history the last call saw renders each tool call once and no empty MODEL line.
    last_prompt = [e for e in envs if e["kind"] == "PromptComposed"][-1]["payload"]["text"]
    assert "MODEL:" not in last_prompt and last_prompt.count("TOOL add") == 2


class _Fails:
    name = "fails"

    def respond(self, prompt: str) -> str:
        raise ConnectionError("provider returned 502")


def test_a_model_failure_returns_with_the_error(tmp_path: Path) -> None:
    topo = session_topology(
        driver=_Fails(),
        driver_name="fails",
        driver_context_tokens=4_096,
        seed="SEED",
        tools={},
        session_id="s262f",
        workspace_path=str(tmp_path),
        first_turn_user_message=_um("hello"),
    )
    envs = _run(tmp_path / "rec", topo)
    returned = [e["payload"] for e in envs if e["kind"] == "Returned"]
    assert len(returned) == 1
    assert returned[0]["reason"] == "model_error"
    assert "provider returned 502" in returned[0]["detail"]


def test_a_hard_interrupt_during_a_tool_call_ends_the_turn(tmp_path: Path) -> None:
    """The registry's hard tier cancels the live tool when no model is running (session_registry
    `interrupt`). Before K262 only a cancelled model ended the turn; this run then hung."""
    root = tmp_path / "rec"
    runtime = api.Runtime(root)
    topo = session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=4_096,
        seed="SEED",
        tools=full_suite(tmp_path),
        session_id="s262i",
        workspace_path=str(tmp_path),
        script=[("bash", ["sleep 30"])],
        first_turn_user_message=_um("wait a while"),
    )

    async def _cancel_the_tool() -> None:
        for _ in range(500):
            st = runtime._st  # noqa: SLF001 — the registry reads the same table
            live = [i for i, k in (st.kind_by_instance.items() if st else []) if k == "tool"]
            if live:
                await asyncio.sleep(0.2)  # the shell is in its sleep
                runtime.cancel_producer(live[0], cause="external", caller="test:interrupt-hard")
                return
            await asyncio.sleep(0.01)
        raise AssertionError("the bash tool never started")

    async def _both() -> None:
        await asyncio.wait_for(
            asyncio.gather(runtime.run(topo, name="session"), _cancel_the_tool()), 20
        )

    asyncio.run(_both())
    envs = list(api.read_record(root, resolve_blobs=True))
    returned = [e["payload"] for e in envs if e["kind"] == "Returned"]
    assert returned == [{"turn_index": 0, "reason": "interrupted", "detail": ""}]
    assert not any(e["kind"] == "ToolResult" for e in envs)


def test_the_guard_reads_structure_not_names() -> None:
    """A threshold on a kind whose name contains `all_completed` is allowed; the regex refused it."""
    _refuse_all_completed(api.any_of(api.threshold_count("all_completed_marker", 1)))
    with pytest.raises(api.RegistrationError):
        _refuse_all_completed(
            api.all_of(api.any_of(api.quiescence(), api.all_completed()), api.quiescence())
        )

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K262 on a real model: every model call's ModelReply carries Ollama's own token counts.

Before K262 a session wrote `model_usage={}` on every reply, and a native tool call wrote no
reply at all (`achat_tools` discarded Ollama's counts). One turn that calls `add` and then
answers must write a `tool_use` reply and an `end_turn` reply, both with provider counts
(`estimated: false`), then `Returned(replied)`.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from substrate import api
from substrate.adapters import OllamaResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.tool_loop.tools import CALCULATOR

pytestmark = [pytest.mark.realmodel]

_DRIVER = "qwen2.5:7b-instruct"
_OLLAMA_V1 = "http://localhost:11434/v1"


def _require_model() -> None:
    try:
        ids = {m["id"] for m in httpx.get(_OLLAMA_V1 + "/models", timeout=4).json().get("data", [])}
    except Exception as exc:  # noqa: BLE001 — any unreachability is a SKIP
        pytest.skip(f"Ollama not reachable ({type(exc).__name__})")
    if _DRIVER not in ids:
        pytest.skip(f"model absent: {_DRIVER}")


@pytest.mark.asyncio
async def test_each_call_records_the_providers_counts(tmp_path: Path) -> None:
    _require_model()
    task = "Use the add tool to add 17 and 25, then tell me the sum."
    topo = session_topology(
        driver=OllamaResponder(_DRIVER, max_tokens=200, temperature=0),
        driver_name=_DRIVER,
        driver_context_tokens=8192,
        seed="You are a careful assistant. Use a tool when asked to.",
        tools=dict(CALCULATOR),
        session_id="s_usage_262",
        workspace_path=str(tmp_path),
        first_turn_user_message=UserMessage(
            text=task, turn_index=0, assembled_prompt="", slash_source="test"
        ),
    )
    root = tmp_path / "record"
    result = await api.Runtime(root, persistent=True).run(topo, name="session")
    assert result.status == "paused"
    envs = list(api.read_record(root, resolve_blobs=True))
    replies = [e["payload"] for e in envs if e["kind"] == "ModelReply"]
    calls = [e["payload"] for e in envs if e["kind"] == "ToolCall"]

    assert calls and calls[0]["tool"] == "add", [e["kind"] for e in envs]
    assert [r["stop_reason"] for r in replies] == ["tool_use"] * len(calls) + ["end_turn"]
    assert "42" in replies[-1]["text"], replies[-1]["text"]
    for r in replies:
        usage = r["usage"]
        assert usage["model"] == _DRIVER and usage["estimated"] is False, usage
        assert usage["prompt_tokens"] > 0 and usage["completion_tokens"] > 0, usage
        assert usage["wall_ms"] > 0, usage
    assert not any(e["kind"] == "FinalAnswer" for e in envs)
    returned = [e["payload"] for e in envs if e["kind"] == "Returned"]
    assert returned == [{"turn_index": 0, "reason": "replied", "detail": ""}]

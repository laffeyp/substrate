# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 052 — web_fetch tool comprehension via stubbed urlopen
(Layer 1). No real network reaches the wire while the test runs.

The stub replaces `urllib.request.urlopen` for the duration of the
test with a caller-supplied handler; `web_fetch` returns whatever the
handler decides. Real HTTP GET is unreachable. Layer 3
`no_escape_guard` still asserts nothing outside tmp_path changed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from substrate.topologies.session.vocabulary import turn_replies
from substrate import api
from substrate.adapters import OllamaResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.tool_loop.tools import full_suite
from tests._sandbox import stub_urlopen

pytestmark = [pytest.mark.realmodel, pytest.mark.usefixtures("no_escape_guard")]

_DRIVER = "qwen2.5:7b-instruct"
_OLLAMA_V1 = "http://localhost:11434/v1"


def _require_model() -> None:
    try:
        ids = {m["id"] for m in httpx.get(_OLLAMA_V1 + "/models", timeout=4).json().get("data", [])}
    except Exception as exc:  # noqa: BLE001 — any unreachability is a SKIP
        pytest.skip(f"network-tool skipped — Ollama not reachable ({type(exc).__name__})")
    if _DRIVER not in ids:
        pytest.skip(f"network-tool skipped — model absent: {_DRIVER}")


def _open(*, tmp_path: Path, tools: dict, first_text: str) -> Any:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace, session_topology(
        driver=OllamaResponder(
            _DRIVER,
            max_tokens=180,
            temperature=0,
            system="You have access to tools. Call the RIGHT one. Do EXACTLY what the user asks.",
        ),
        driver_name=_DRIVER,
        driver_context_tokens=8192,
        seed="",
        tools=tools,
        per_turn="",
        max_turns=6,
        turn_max_steps=4,
        session_id="s_net_test",
        workspace_path=str(workspace),
        script=None,
        first_turn_user_message=UserMessage(
            text=first_text, turn_index=0, assembled_prompt=first_text, slash_source="test"
        ),
    )


def _events(root: Path) -> list[dict]:
    return list(api.read_record(root))


def _by_kind(envs: list[dict], kind: str) -> list[dict]:
    return [e for e in envs if e["kind"] == kind]


def _last_answer(envs: list[dict]) -> str:
    finals = turn_replies(envs)
    return finals[-1][1] if finals else ""


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_web_fetch_reads_stub_and_model_quotes_body(tmp_path: Path) -> None:
    """Model calls web_fetch on a URL; the stub returns a controlled
    body; the model's final answer quotes something from that body."""
    _require_model()
    calls_seen: list[str] = []

    def handler(url: str) -> bytes:
        calls_seen.append(url)
        return b"MAGIC_TOKEN_42 is the answer for the test."

    tools = {"web_fetch": full_suite(tmp_path / "workspace")["web_fetch"]}
    _ws, factory = _open(
        tmp_path=tmp_path,
        tools=tools,
        first_text=(
            "Call web_fetch with url='https://example.invalid/x'. "
            "Report the magic token from the body."
        ),
    )
    with stub_urlopen(handler):
        result = await api.Runtime(tmp_path / "record", persistent=True).run(factory)
    assert result.status == "paused"
    envs = _events(tmp_path / "record")
    assert any(c["payload"].get("tool") == "web_fetch" for c in _by_kind(envs, "ToolCall"))
    tr = _by_kind(envs, "ToolResult")
    ok = [r for r in tr if r["payload"].get("ok") is True]
    assert ok, f"no successful web_fetch: {[r['payload'] for r in tr]}"
    assert calls_seen, "the stub was never invoked — real network may have leaked through"
    assert calls_seen[0].startswith("https://example.invalid/"), calls_seen
    # (c) Comprehension: the model's answer quotes the magic token.
    assert "MAGIC_TOKEN_42" in _last_answer(envs), _last_answer(envs)

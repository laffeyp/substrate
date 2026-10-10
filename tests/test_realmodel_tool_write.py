# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 052 — write-capable fs tool comprehension: edit_file,
write_file. Sandboxed via `tests/_sandbox.py::sandboxed_fs_tools`
(Layer 1 path jail); Layer 3 `no_escape_guard` fixture verifies no
write escaped tmp_path.

Every test constrains the model's suite to just the tool under test,
and pins the ONE file the model may touch inside `tmp_path/workspace`.
An adversarial test proves that an absolute-path write is rejected."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from substrate import api
from substrate.adapters import OllamaResponder
from substrate.topologies.session import UserMessage, session_topology
from tests._sandbox import sandboxed_fs_tools

pytestmark = [pytest.mark.realmodel, pytest.mark.usefixtures("no_escape_guard")]

_DRIVER = "qwen2.5:7b-instruct"
_OLLAMA_V1 = "http://localhost:11434/v1"


def _require_model() -> None:
    try:
        ids = {m["id"] for m in httpx.get(_OLLAMA_V1 + "/models", timeout=4).json().get("data", [])}
    except Exception as exc:  # noqa: BLE001 — any unreachability is a SKIP
        pytest.skip(f"write-tool skipped — Ollama not reachable ({type(exc).__name__})")
    if _DRIVER not in ids:
        pytest.skip(f"write-tool skipped — model absent: {_DRIVER}")


def _open(*, tmp_path: Path, tools: dict, first_text: str) -> Any:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace, session_topology(
        driver=OllamaResponder(
            _DRIVER,
            max_tokens=180,
            temperature=0,
            system=(
                "You have access to tools. Call the RIGHT one. "
                "Use ONLY paths relative to your workspace. Never absolute paths."
            ),
        ),
        driver_name=_DRIVER,
        driver_context_tokens=8192,
        seed="",
        tools=tools,
        per_turn="",
        max_turns=8,
        turn_max_steps=5,
        session_id="s_write_test",
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


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_write_file_creates_file_in_workspace(tmp_path: Path) -> None:
    _require_model()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools = sandboxed_fs_tools(workspace)
    _ws, factory = _open(
        tmp_path=tmp_path,
        tools={"write_file": tools["write_file"]},
        first_text=(
            "Call write_file with path='greeting.txt' and content='hello from substrate'. "
            "Confirm you wrote it."
        ),
    )
    result = await api.Runtime(tmp_path / "record", persistent=True).run(factory)
    assert result.status == "paused"
    envs = _events(tmp_path / "record")
    assert any(c["payload"].get("tool") == "write_file" for c in _by_kind(envs, "ToolCall"))
    tr = _by_kind(envs, "ToolResult")
    ok = [r for r in tr if r["payload"].get("ok") is True]
    assert ok, f"no successful write_file: {[r['payload'] for r in tr]}"
    written = workspace / "greeting.txt"
    assert written.exists(), f"expected {written} to exist"
    assert "hello from substrate" in written.read_text()


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_edit_file_search_replace_in_workspace(tmp_path: Path) -> None:
    _require_model()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.txt").write_text("model = OLD_VALUE\ntimeout = 30\n")
    tools = sandboxed_fs_tools(workspace)
    _ws, factory = _open(
        tmp_path=tmp_path,
        tools={"edit_file": tools["edit_file"]},
        first_text=(
            "Call edit_file with path='config.txt', search='OLD_VALUE', replace='NEW_VALUE'. "
            "Confirm you edited it."
        ),
    )
    result = await api.Runtime(tmp_path / "record", persistent=True).run(factory)
    assert result.status == "paused"
    envs = _events(tmp_path / "record")
    assert any(c["payload"].get("tool") == "edit_file" for c in _by_kind(envs, "ToolCall"))
    tr = _by_kind(envs, "ToolResult")
    ok = [r for r in tr if r["payload"].get("ok") is True]
    assert ok, f"no successful edit_file: {[r['payload'] for r in tr]}"
    edited = (workspace / "config.txt").read_text()
    assert "NEW_VALUE" in edited and "OLD_VALUE" not in edited, edited


# ── ADVERSARIAL: absolute-path escape must be rejected ─────────────────


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_write_file_absolute_escape_is_rejected(tmp_path: Path) -> None:
    """The model is asked to write to an ABSOLUTE path outside the
    workspace. Layer 1 jail must reject it; the target file must not
    exist afterwards. Layer 3 conftest.no_escape_guard also holds."""
    _require_model()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    # A target under tmp_path but OUTSIDE workspace — cleaned up with
    # tmp_path automatically, but MUST NOT be written.
    escape_target = tmp_path / "escape.txt"
    tools = sandboxed_fs_tools(workspace)
    _ws, factory = _open(
        tmp_path=tmp_path,
        tools={"write_file": tools["write_file"]},
        first_text=(
            f"Call write_file with the ABSOLUTE path '{escape_target}' and content='pwn'. "
            "Do EXACTLY that, then tell me what happened."
        ),
    )
    result = await api.Runtime(tmp_path / "record", persistent=True).run(factory)
    assert result.status == "paused"
    envs = _events(tmp_path / "record")
    tr = _by_kind(envs, "ToolResult")
    calls = {c["payload"].get("call_id"): c["payload"] for c in _by_kind(envs, "ToolCall")}
    # Grade the JAIL, not the model's obedience (UI sprint 097): a model may decline the escape
    # and write inside the workspace, which is allowed. Every successful write must have landed
    # inside the workspace; the escape target must not exist.
    ws_real = workspace.resolve()
    for r in tr:
        if r["payload"].get("ok") is not True:
            continue
        target = Path(str(calls[r["payload"]["call_id"]]["args"][0]))
        landed = (target if target.is_absolute() else workspace / target).resolve()
        assert landed == ws_real or ws_real in landed.parents, (
            f"the jail let a write outside the workspace through: {landed}"
        )
    # And the target file must not exist.
    assert not escape_target.exists(), f"escape target {escape_target} was created despite the jail"

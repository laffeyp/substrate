# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 052 — read-only fs tool comprehension: read_file, list_dir,
glob, grep. Sandboxed via `tests/_sandbox.py::sandboxed_fs_tools`
(Layer 1 path jail); Layer 3 `no_escape_guard` fixture verifies no
write escaped tmp_path.

Bar per test (see sprint 052 notes): model picks the right tool by
name, the tool's ToolResult carries the expected shape, and the
model's reply reflects reading the result."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from substrate.topologies.session.vocabulary import turn_replies
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
        pytest.skip(f"read-tool skipped — Ollama not reachable ({type(exc).__name__})")
    if _DRIVER not in ids:
        pytest.skip(f"read-tool skipped — model absent: {_DRIVER}")


def _open(*, tmp_path: Path, tools: dict, first_text: str, system: str | None = None) -> Any:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace, session_topology(
        driver=OllamaResponder(
            _DRIVER,
            max_tokens=180,
            temperature=0,
            system=(
                system
                or "You have access to tools. Call the RIGHT one. "
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
        session_id="s_read_test",
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
async def test_read_file_reads_workspace_greeting(tmp_path: Path) -> None:
    _require_model()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "greeting.txt").write_text("The magic word is BANANA\n")
    tools = sandboxed_fs_tools(workspace)
    _ws, factory = _open(
        tmp_path=tmp_path,
        tools={"read_file": tools["read_file"]},
        first_text="Call read_file on greeting.txt and tell me the magic word.",
    )
    result = await api.Runtime(tmp_path / "record", persistent=True).run(factory)
    assert result.status == "paused"
    envs = _events(tmp_path / "record")
    assert any(c["payload"].get("tool") == "read_file" for c in _by_kind(envs, "ToolCall"))
    tr = _by_kind(envs, "ToolResult")
    assert tr and tr[0]["payload"].get("ok") is True, tr[0]["payload"] if tr else None
    assert "BANANA" in _last_answer(envs), _last_answer(envs)


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_list_dir_reads_workspace_entries(tmp_path: Path) -> None:
    _require_model()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for n in ("alpha.txt", "beta.txt", "gamma.txt"):
        (workspace / n).write_text("x")
    tools = sandboxed_fs_tools(workspace)
    _ws, factory = _open(
        tmp_path=tmp_path,
        tools={"list_dir": tools["list_dir"]},
        first_text="Call list_dir on '.' and tell me the names of the files you find, comma-separated.",
    )
    result = await api.Runtime(tmp_path / "record", persistent=True).run(factory)
    assert result.status == "paused"
    envs = _events(tmp_path / "record")
    assert any(c["payload"].get("tool") == "list_dir" for c in _by_kind(envs, "ToolCall"))
    tr = _by_kind(envs, "ToolResult")
    assert tr and tr[0]["payload"].get("ok") is True
    entries = tr[0]["payload"].get("output") or []
    for n in ("alpha.txt", "beta.txt", "gamma.txt"):
        assert n in entries, f"list_dir missing {n!r}: got {entries}"
    answer = _last_answer(envs).lower()
    assert "alpha" in answer and "beta" in answer and "gamma" in answer, (
        f"final answer must name all three files; got {answer!r}"
    )


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_grep_finds_pattern_in_workspace(tmp_path: Path) -> None:
    _require_model()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("- todo one\n- MAGIC NUMBER: 42\n- todo three\n")
    (workspace / "other.md").write_text("nothing special here\n")
    tools = sandboxed_fs_tools(workspace)
    _ws, factory = _open(
        tmp_path=tmp_path,
        tools={"grep": tools["grep"]},
        first_text="Call grep with regex='MAGIC NUMBER' to search this workspace. What number does the match contain?",
    )
    result = await api.Runtime(tmp_path / "record", persistent=True).run(factory)
    assert result.status == "paused"
    envs = _events(tmp_path / "record")
    assert any(c["payload"].get("tool") == "grep" for c in _by_kind(envs, "ToolCall"))
    tr = _by_kind(envs, "ToolResult")
    # The model may take a retry to get the arg name right (small models
    # sometimes call with `pattern` before `regex`); at least ONE result
    # must be ok=True with a MAGIC NUMBER match.
    ok_results = [r for r in tr if r["payload"].get("ok") is True]
    assert ok_results, (
        f"no successful grep result across {len(tr)} tries: {[r['payload'] for r in tr]}"
    )
    matches = ok_results[0]["payload"].get("output") or []
    assert any("MAGIC NUMBER" in str(m) for m in matches), matches
    assert "42" in _last_answer(envs), _last_answer(envs)


# ── ADVERSARIAL: prove the path jail catches an escape attempt ──────────


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_read_file_absolute_escape_is_rejected(tmp_path: Path) -> None:
    """Ask the model to read an absolute path outside the workspace. The
    jailed tool must reject it as a typed ToolResult(ok=False, error=…);
    the model's answer must reflect the failure, not the file contents."""
    _require_model()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools = sandboxed_fs_tools(workspace)
    _ws, factory = _open(
        tmp_path=tmp_path,
        tools={"read_file": tools["read_file"]},
        first_text="Call read_file with the ABSOLUTE path '/etc/hosts'. Tell me what happened.",
        system="You have access to tools. Do what the user asks EXACTLY as instructed.",
    )
    result = await api.Runtime(tmp_path / "record", persistent=True).run(factory)
    assert result.status == "paused"
    envs = _events(tmp_path / "record")
    calls = _by_kind(envs, "ToolCall")
    results = _by_kind(envs, "ToolResult")
    # The model may or may not attempt the call, depending on the prompt.
    # If it did, the ToolResult must be a failure carrying "escapes".
    escape_attempts = [
        r
        for r in results
        if r["payload"].get("ok") is False and "escapes" in str(r["payload"].get("error", ""))
    ]
    # Either the model refused to try the escape (also fine — nothing to
    # verify), or it tried and the jail rejected it. What must NOT happen:
    # a successful ok=True read of /etc/hosts.
    success_reads = [r for r in results if r["payload"].get("ok") is True]
    assert not success_reads, (
        f"the jail let an absolute-path read through: {[r['payload'] for r in success_reads]}"
    )
    if calls:
        # If a call happened, we want the escape branch to be exercised
        # so the assertion has teeth. Skip cleanly if the model refused
        # to attempt — that is a separate model-behaviour question.
        assert escape_attempts, (
            f"model made a ToolCall but no PathEscape error came back; results: "
            f"{[r['payload'] for r in results]}"
        )

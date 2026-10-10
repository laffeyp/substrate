# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""UI sprint 103 observation contract: a real model runs a server in the background.

The model starts `python3 -m http.server` with `run_in_background`, reads its log with
`bash_output`, fetches a page through it, and stops it with `bash_stop`. Afterwards the port is
free and no task of this session is running.
"""

from __future__ import annotations

import socket
from pathlib import Path

import httpx
import pytest

from substrate import api
from substrate.adapters import OllamaResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.tool_loop.background import TABLE
from substrate.topologies.tool_loop.tools import full_suite

pytestmark = [pytest.mark.realmodel]

_DRIVER = "kimi-k2.7-code:cloud"  # the app's default driver; qwen2.5:7b skipped step 4 (bash_stop)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


@pytest.mark.timeout(300)
async def test_model_runs_supervises_and_stops_a_background_server(tmp_path: Path) -> None:
    try:
        names = {
            m["name"]
            for m in httpx.get("http://localhost:11434/api/tags", timeout=4).json()["models"]
        }
    except Exception as exc:  # noqa: BLE001 — unreachable Ollama is a SKIP
        pytest.skip(f"Ollama not reachable ({type(exc).__name__})")
    if _DRIVER not in names:
        pytest.skip(f"model absent: {_DRIVER}")

    port = _free_port()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("HELLO-103\n")
    owner = "s_realmodel_bg_103"
    suite = full_suite(workspace, owner=owner)
    tools = {k: suite[k] for k in ("bash", "bash_output", "bash_stop", "bash_tasks")}
    task = (
        f"Step 1: start a web server in the background with the bash tool: cmd "
        f"'python3 -m http.server {port} --bind 127.0.0.1', run_in_background true. "
        f"Step 2: call bash_output with the task_id it returns. "
        f"Step 3: run bash with cmd 'curl -s http://127.0.0.1:{port}/hello.txt'. "
        f"Step 4: call bash_stop with the same task_id. Then say what the file contained."
    )
    topo = session_topology(
        driver=OllamaResponder(
            _DRIVER, temperature=0, system="Use the tools exactly as instructed, one call per step."
        ),
        driver_name=_DRIVER,
        driver_context_tokens=8192,
        seed="",
        tools=tools,
        per_turn="",
        max_turns=4,
        turn_max_steps=10,
        session_id=owner,
        workspace_path=str(workspace),
        script=None,
        first_turn_user_message=UserMessage(
            text=task, turn_index=0, assembled_prompt=task, slash_source="test"
        ),
    )
    try:
        await api.Runtime(tmp_path / "record", persistent=True).run(topo)
        envs = list(api.read_record(tmp_path / "record", resolve_blobs=True))
        calls = [e["payload"] for e in envs if e["kind"] == "ToolCall"]
        results = [e["payload"] for e in envs if e["kind"] == "ToolResult"]
        used = [c["tool"] for c in calls]
        assert "bash_output" in used and "bash_stop" in used, f"tools used: {used}"
        curl = [
            r for r, c in zip(results, calls) if c["tool"] == "bash" and "curl" in str(c["args"])
        ]
        assert curl and "HELLO-103" in str(curl[-1]["output"]), f"curl results: {curl}"
        assert not _port_open(port), "the server is still listening after bash_stop"
        assert all(t.poll() != "running" for t in TABLE.tasks_of(owner))
    finally:
        TABLE.stop_owner(owner, "test teardown")

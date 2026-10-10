# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""UI sprint 104 observation contract: a real model learns that its background task ended.

The model starts `sleep 2; echo READY-104` in the background, then runs a foreground `sleep 4`,
and is told not to call bash_output. Its answer can name READY-104 only if the
BackgroundTaskEnded notice reached it.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from substrate.topologies.session.vocabulary import turn_replies
from substrate import api
from substrate.adapters import OllamaResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.tool_loop.background import TABLE
from substrate.topologies.tool_loop.tools import full_suite

pytestmark = [pytest.mark.realmodel]

_DRIVER = "kimi-k2.7-code:cloud"  # the app's default driver


@pytest.mark.timeout(300)
async def test_model_hears_its_background_task_end(tmp_path: Path) -> None:
    try:
        names = {
            m["name"]
            for m in httpx.get("http://localhost:11434/api/tags", timeout=4).json()["models"]
        }
    except Exception as exc:  # noqa: BLE001 — unreachable Ollama is a SKIP
        pytest.skip(f"Ollama not reachable ({type(exc).__name__})")
    if _DRIVER not in names:
        pytest.skip(f"model absent: {_DRIVER}")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sid = "s_realmodel_notice_104"
    suite = full_suite(workspace, owner=sid)
    task = (
        "Step 1: call bash with cmd 'sleep 2; echo READY-104' and run_in_background true. "
        "Step 2: call bash with cmd 'sleep 4'. "
        "Do not call bash_output. Then tell me exactly what the background task printed."
    )
    topo = session_topology(
        driver=OllamaResponder(
            _DRIVER, temperature=0, system="Use the tools exactly as instructed."
        ),
        driver_name=_DRIVER,
        driver_context_tokens=8192,
        seed="",
        tools={k: suite[k] for k in ("bash", "bash_output", "bash_stop")},
        per_turn="",
        max_turns=4,
        turn_max_steps=8,
        session_id=sid,
        workspace_path=str(workspace),
        script=None,
        first_turn_user_message=UserMessage(
            text=task, turn_index=0, assembled_prompt=task, slash_source="test"
        ),
    )
    try:
        await api.Runtime(tmp_path / "record", persistent=True).run(topo)
        envs = list(api.read_record(tmp_path / "record", resolve_blobs=True))
        kinds = [e["kind"] for e in envs]
        assert "BackgroundTaskEnded" in kinds, f"no notice on the record: {kinds}"
        assert "bash_output" not in [e["payload"]["tool"] for e in envs if e["kind"] == "ToolCall"]
        reply_seq, final = turn_replies(envs)[-1]
        notice_seq = next(e["seq"] for e in envs if e["kind"] == "BackgroundTaskEnded")
        assert notice_seq < reply_seq
        assert "READY-104" in final, final
    finally:
        TABLE.stop_owner(sid, "test teardown")

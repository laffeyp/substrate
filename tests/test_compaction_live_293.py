# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K293: the codex case, live (opt-in: SUBSTRATE_LIVE_DRIVER_TESTS=1).

Session s_b8dab6b0… lost its first two turns to one heavy turn of file reads, and codex answered the
next question without them. Here: a fact in turn 0, a heavy `cat` in turn 1 that forces a cut at a
30,000-token window, then a question in turn 2 that needs turn 0. The cut clears the tool output and
keeps both earlier requests and replies, and codex answers from them.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

import pytest

from substrate import api
from substrate.adapters import CliResponder
from substrate.adapters.harness_streams import CODEX_JSON
from substrate.topologies.session import UserMessage, session_topology

pytestmark = pytest.mark.skipif(
    os.environ.get("SUBSTRATE_LIVE_DRIVER_TESTS") != "1",
    reason="real harness runs; run on demand with SUBSTRATE_LIVE_DRIVER_TESTS=1",
)

_ASKS = [
    "Remember this code word for later: PELICAN-42. Reply only: noted.",
    "Run the shell command `cat big.txt`, then reply with only the number of lines it printed.",
    "What was the code word I gave you in my first message? Reply with only the code word.",
]


def test_a_heavy_turn_does_not_erase_earlier_requests(tmp_path: Path) -> None:
    if shutil.which("codex") is None:
        pytest.skip("codex not installed")
    work = tmp_path / "work"
    work.mkdir()
    (work / "big.txt").write_text(
        "".join(f"line {i:05d} " + "lorem ipsum " * 2 + "\n" for i in range(4_000))
    )
    root = tmp_path / "record"
    command = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
    ]
    for i, ask in enumerate(_ASKS):
        um = UserMessage(text=ask, turn_index=i, assembled_prompt="", slash_source="chat")
        cli = CliResponder(command, cwd=work, stream_format=CODEX_JSON, stream_flags=["--json"])
        topo = session_topology(
            driver=cli,
            driver_name="codex",
            driver_context_tokens=30_000,
            seed="SEED",
            tools={},
            session_id="s293",
            workspace_path=str(work),
            first_turn_user_message=um if i == 0 else None,
        )
        rt = api.Runtime(root, persistent=True)
        asyncio.run(rt.run(topo, name="session") if i == 0 else rt.resume(topo, resume_event=um))

    envs = list(api.read_record(root, resolve_blobs=True))
    cuts = [e["payload"] for e in envs if e["kind"] == "TranscriptCompacted"]
    assert cuts and cuts[-1]["strategy"] == "tool_output_cleared", cuts
    last_prompt = [e["payload"]["text"] for e in envs if e["kind"] == "PromptComposed"][-1]
    assert "PELICAN-42" in last_prompt and "[cleared:" in last_prompt
    replies = [e["payload"]["text"] for e in envs if e["kind"] == "ModelReply"]
    assert "PELICAN-42" in replies[-1], replies

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K293: compaction keeps earlier requests, live, on every driver family (opt-in:
SUBSTRATE_LIVE_DRIVER_TESTS=1).

Session s_b8dab6b0… lost its first two turns to one heavy turn of file reads, and the model answered
the next question without them. Here, for claude, codex, cursor-agent and an Ollama model: a fact in
turn 0, a read in turn 1 that forces a cut at a 3,000-token window, then a question in turn 2 that
needs turn 0. Each harness caps very large outputs at its own end (Claude Code saves them to a file,
cursor-agent's stream reports them empty), so the read is a mid-size `head -n 300`. The
cut clears the tool output and keeps both earlier requests and replies, and the model answers from
them.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import CliResponder, OllamaResponder
from substrate.adapters.harness_streams import CLAUDE_STREAM_JSON, CODEX_JSON, CURSOR_STREAM_JSON
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.tool_loop.tools import full_suite

pytestmark = pytest.mark.skipif(
    os.environ.get("SUBSTRATE_LIVE_DRIVER_TESTS") != "1",
    reason="real harness runs; run on demand with SUBSTRATE_LIVE_DRIVER_TESTS=1",
)

_CLI = {
    "claude": (
        [
            "claude",
            "-p",
            "--strict-mcp-config",
            "--setting-sources",
            "",
            "--dangerously-skip-permissions",
        ],
        CLAUDE_STREAM_JSON,
        ["--output-format", "stream-json", "--verbose"],
    ),
    "codex": (
        ["codex", "exec", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox"],
        CODEX_JSON,
        ["--json"],
    ),
    "cursor-agent": (
        ["cursor-agent", "-p", "--trust", "--force", "--sandbox", "disabled"],
        CURSOR_STREAM_JSON,
        ["--output-format", "stream-json"],
    ),
}
_OLLAMA = "kimi-k2.7-code:cloud"


def _asks(read: str) -> list[str]:
    return [
        "Remember this code word for later: PELICAN-42. Reply only: noted.",
        f"{read} Then reply with only the last line it printed.",
        "What was the code word I gave you in my first message? Reply with only the code word.",
    ]


def _driver(name: str, work: Path) -> tuple[Any, dict[str, Any], int, str]:
    """The driver, its tools, its window for this test, and how turn 1 asks for the heavy read."""
    if name in _CLI:
        command, fmt, flags = _CLI[name]
        if shutil.which(command[0]) is None:
            pytest.skip(f"{command[0]} not installed")
        cli = CliResponder(command, cwd=work, stream_format=fmt, stream_flags=flags)
        return (
            cli,
            {},
            3_000,
            "Run exactly this shell command and nothing else: `head -n 300 big.txt`.",
        )
    return (
        OllamaResponder(_OLLAMA, num_ctx=65_536),
        full_suite(work),
        12_000,  # one read fits; two do not (Ollama also counts the tool schemas: scale ~1.7-2.6)
        "Use the bash tool to run `head -n 300 big.txt`, then use it again to run"
        " `tail -n 300 big.txt`.",
    )


@pytest.mark.timeout(900)
@pytest.mark.parametrize("name", ["claude", "codex", "cursor-agent", _OLLAMA])
def test_a_heavy_turn_does_not_erase_earlier_requests(tmp_path: Path, name: str) -> None:
    work = tmp_path / "work"
    work.mkdir()
    (work / "big.txt").write_text(
        "".join(f"line {i:05d} " + "lorem ipsum " * 2 + "\n" for i in range(4_000))
    )
    root = tmp_path / "record"
    _, _, _, read = _driver(name, work)
    for i, ask in enumerate(_asks(read)):
        driver, tools, window, _ = _driver(name, work)
        um = UserMessage(text=ask, turn_index=i, assembled_prompt="", slash_source="chat")
        topo = session_topology(
            driver=driver,
            driver_name=name,
            driver_context_tokens=window,
            seed="SEED",
            tools=tools,
            session_id="s293",
            workspace_path=str(work),
            first_turn_user_message=um if i == 0 else None,
        )
        rt = api.Runtime(root, persistent=True)
        asyncio.run(rt.run(topo, name="session") if i == 0 else rt.resume(topo, resume_event=um))

    envs = list(api.read_record(root, resolve_blobs=True))
    cuts = [e["payload"] for e in envs if e["kind"] == "TranscriptCompacted"]
    assert cuts and all(c.get("dropped_seq_range") is None for c in cuts), cuts
    last_prompt = [e["payload"]["text"] for e in envs if e["kind"] == "PromptComposed"][-1]
    assert "PELICAN-42" in last_prompt and "[cleared:" in last_prompt
    replies = [e["payload"]["text"] for e in envs if e["kind"] == "ModelReply"]
    assert "PELICAN-42" in replies[-1], replies

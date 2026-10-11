# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K283: reading a harness driver's stream (session vocabulary § Q).

The fixtures are real streams from 2026-10-10: each CLI, with the flags Substrate uses, was asked
to "Create a file named a.txt containing ok, then run the shell command: ls. Then reply done."
`codex-tools-off.jsonl` is Codex with its shell features disabled, which still wrote the file.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import CliResponder
from substrate.adapters.harness_streams import (
    CLAUDE_STREAM_JSON,
    CODEX_JSON,
    CURSOR_STREAM_JSON,
    HarnessStreamError,
    StreamToolCall,
    StreamToolResult,
    StreamUsage,
    parser_for,
)
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.tool_loop.tools import CALCULATOR

FIXTURES = Path(__file__).parent / "fixtures" / "harness_streams"


def _parse(fmt: str, name: str) -> tuple[list[Any], str | None]:
    parser = parser_for(fmt)
    items: list[Any] = []
    for line in (FIXTURES / name).read_text().splitlines():
        items += parser.feed(line)
    return items, parser.final_text


def _calls(items: list[Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(i.tool, i.args) for i in items if isinstance(i, StreamToolCall)]


def _results(items: list[Any]) -> list[tuple[bool, str]]:
    return [(i.ok, i.output) for i in items if isinstance(i, StreamToolResult)]


def test_claude_stream() -> None:
    items, final = _parse(CLAUDE_STREAM_JSON, "claude.jsonl")
    assert _calls(items) == [
        (
            "Bash",
            {
                "command": "printf 'ok\\n' > a.txt && ls",
                "description": "Create a.txt and list files",
            },
        )
    ]
    assert _results(items) == [(True, "a.txt")]
    assert final is not None and final.endswith("done")
    (usage,) = [i for i in items if isinstance(i, StreamUsage)]
    assert usage.completion_tokens == 136 and usage.prompt_tokens == 4 + 6310 + 27573


def test_codex_stream() -> None:
    items, final = _parse(CODEX_JSON, "codex.jsonl")
    assert _calls(items) == [
        ("command_execution", {"command": "/bin/zsh -lc 'printf ok > a.txt'"}),
        ("command_execution", {"command": "/bin/zsh -lc ls"}),
    ]
    assert _results(items) == [(True, ""), (True, "a.txt\n")]
    assert final == "done"
    (usage,) = [i for i in items if isinstance(i, StreamUsage)]
    assert (usage.prompt_tokens, usage.completion_tokens) == (28583, 64)


def test_codex_file_change_with_no_start_writes_its_call_first() -> None:
    items, _final = _parse(CODEX_JSON, "codex-tools-off.jsonl")
    calls = [i for i in items if isinstance(i, StreamToolCall)]
    results = [i for i in items if isinstance(i, StreamToolResult)]
    assert [c.tool for c in calls] == ["file_change"]
    assert results[0].call_id == calls[0].call_id and results[0].ok
    assert results[0].output.startswith("add ") and results[0].output.endswith("/a.txt")
    assert items.index(calls[0]) < items.index(results[0])


def test_cursor_stream() -> None:
    items, final = _parse(CURSOR_STREAM_JSON, "cursor.jsonl")
    calls = _calls(items)
    assert [tool for tool, _args in calls] == ["edit", "shell"]
    assert calls[0][1]["path"].endswith("/a.txt") and calls[0][1]["streamContent"] == "ok\n"
    assert calls[1][1]["command"] == "ls"
    results = _results(items)
    assert results[1] == (True, "a.txt\n")
    assert results[0][0] and "+ok" in results[0][1]
    assert final is not None and final.endswith("done")


def test_a_failed_run_raises() -> None:
    parser = parser_for(CLAUDE_STREAM_JSON)
    with pytest.raises(HarnessStreamError, match="boom"):
        parser.feed('{"type": "result", "is_error": true, "result": "boom"}')
    with pytest.raises(HarnessStreamError):
        parser_for(CODEX_JSON).feed('{"type": "turn.failed", "error": {"message": "nope"}}')


def test_lines_that_are_not_json_objects_are_skipped() -> None:
    parser = parser_for(CODEX_JSON)
    assert parser.feed("Reading additional input from stdin...") == []
    assert parser.feed("") == []


# A stand-in CLI: prints a saved stream whatever its arguments, as a harness would.
_REPLAY = "import sys; sys.stdout.write(open(sys.argv[1]).read())"


def _replaying(name: str, fmt: str) -> CliResponder:
    return CliResponder(
        [sys.executable, "-c", _REPLAY, str(FIXTURES / name)], name="replay", stream_format=fmt
    )


def test_arespond_returns_the_streams_reply() -> None:
    reply = asyncio.run(_replaying("codex.jsonl", CODEX_JSON).arespond("anything"))
    assert reply == "done"
    assert _replaying("codex.jsonl", CODEX_JSON).respond("anything") == "done"


def test_a_session_turn_records_the_harness_calls(tmp_path: Path) -> None:
    root = tmp_path / "record"
    um = UserMessage(text="make a.txt", turn_index=0, assembled_prompt="", slash_source="chat")
    topo = session_topology(
        driver=_replaying("cursor.jsonl", CURSOR_STREAM_JSON),
        driver_name="cursor-agent",
        driver_context_tokens=100_000,
        seed="SEED",
        tools=dict(CALCULATOR),
        session_id="s_283",
        workspace_path=str(tmp_path),
        first_turn_user_message=um,
    )
    asyncio.run(api.Runtime(root, persistent=True).run(topo, name="session"))
    events = list(api.read_record(root, resolve_blobs=True))
    kinds = [e["kind"] for e in events]
    calls = [e["payload"] for e in events if e["kind"] == "HarnessToolCall"]
    results = [e["payload"] for e in events if e["kind"] == "HarnessToolResult"]
    assert [(c["tool"], c["turn_index"]) for c in calls] == [("edit", 0), ("shell", 0)]
    assert {r["call_id"] for r in results} == {c["call_id"] for c in calls}
    reply = next(e["payload"] for e in events if e["kind"] == "ModelReply")
    assert reply["text"].endswith("done") and reply["stop_reason"] == "end_turn"
    assert reply["usage"]["estimated"] is False
    # The calls come before the reply, and nothing ran Substrate's own tool producer.
    assert kinds.index("HarnessToolCall") < kinds.index("ModelReply")
    assert "ToolCall" not in kinds and "ToolResult" not in kinds


_live = pytest.mark.skipif(
    os.environ.get("SUBSTRATE_LIVE_DRIVER_TESTS") != "1",
    reason="real harness runs; run on demand with SUBSTRATE_LIVE_DRIVER_TESTS=1",
)


@_live
@pytest.mark.parametrize(
    ("command", "fmt"),
    [
        (
            [
                "claude",
                "-p",
                "--strict-mcp-config",
                "--setting-sources",
                "",
                "--dangerously-skip-permissions",
            ],
            CLAUDE_STREAM_JSON,
        ),
        (
            [
                "codex",
                "exec",
                "--skip-git-repo-check",
                "--dangerously-bypass-approvals-and-sandbox",
            ],
            CODEX_JSON,
        ),
        (["cursor-agent", "-p", "--trust", "--force", "--sandbox", "disabled"], CURSOR_STREAM_JSON),
    ],
)
def test_a_real_harness_write_is_read_from_its_stream(
    tmp_path: Path, command: list[str], fmt: str
) -> None:
    if shutil.which(command[0]) is None:
        pytest.skip(f"{command[0]} not installed")
    flags = {
        CLAUDE_STREAM_JSON: ["--output-format", "stream-json", "--verbose"],
        CODEX_JSON: ["--json"],
        CURSOR_STREAM_JSON: ["--output-format", "stream-json"],
    }[fmt]
    cli = CliResponder(command, cwd=tmp_path, stream_format=fmt, stream_flags=flags)

    async def run() -> list[Any]:
        return [i async for i in cli.astream("Create a file named a.txt containing ok.")]

    items = asyncio.run(run())
    assert (tmp_path / "a.txt").read_text().strip() == "ok"
    assert any(isinstance(i, StreamToolCall) for i in items), items

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K348: a CLI driver's prompt goes on standard input.

Before, the prompt was the command's last argument, and macOS refuses an argument list past
ARG_MAX (1,048,576 bytes, shared with the environment; a 1.1 MB argument fails with errno 7,
measured 2026-11-12). A stand-in CLI reports what reached it: its arguments and its stdin.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from substrate.adapters.harness_streams import StreamReply
from substrate.adapters.models import CliResponder

FAKE = """
import json, sys
data = sys.stdin.read()
print(json.dumps({"args": sys.argv[1:], "stdin_bytes": len(data.encode()), "head": data[:40], "tail": data[-20:]}))
"""
FAKE_STREAM = """
import json, sys
data = sys.stdin.read()
reply = json.dumps({"args": sys.argv[1:], "stdin_bytes": len(data.encode()), "tail": data[-20:]})
print(json.dumps({"type": "result", "result": reply}))
"""
BIG = "x" * 2_000_000 + " the end"


def _cli(tmp_path: Path, body: str, **kw: object) -> CliResponder:
    script = tmp_path / "fake_cli.py"
    script.write_text(body, encoding="utf-8")
    return CliResponder([sys.executable, str(script)], **kw)  # type: ignore[arg-type]


def test_respond_sends_a_2mb_prompt_on_stdin(tmp_path: Path) -> None:
    seen = json.loads(
        _cli(tmp_path, FAKE, system_flag=["--system-prompt"]).respond(BIG, system="S")
    )
    assert seen["args"] == ["--system-prompt", "S"]
    assert seen["stdin_bytes"] == len(BIG.encode()) and seen["tail"].endswith("the end")


def test_arespond_sends_the_prompt_on_stdin(tmp_path: Path) -> None:
    seen = json.loads(asyncio.run(_cli(tmp_path, FAKE).arespond(BIG, system="S")))
    assert seen["args"] == []
    assert seen["head"].startswith("S\n\nxxx") and seen["tail"].endswith("the end")


def test_astream_sends_the_prompt_on_stdin(tmp_path: Path) -> None:
    cli = _cli(
        tmp_path, FAKE_STREAM, system_flag=["--system-prompt"], stream_format="claude-stream-json"
    )

    async def run() -> list[object]:
        return [item async for item in cli.astream(BIG, system="S")]

    (reply,) = [i for i in asyncio.run(run()) if isinstance(i, StreamReply)]
    seen = json.loads(reply.text)
    assert seen["args"] == ["--system-prompt", "S"]
    assert seen["stdin_bytes"] == len(BIG.encode()) and seen["tail"].endswith("the end")


def test_a_short_prompt_takes_the_same_path(tmp_path: Path) -> None:
    seen = json.loads(
        _cli(tmp_path, FAKE, system_flag=["--system-prompt"]).respond("hi", system="")
    )
    assert seen["args"] == ["--system-prompt", ""] and seen["stdin_bytes"] == 2

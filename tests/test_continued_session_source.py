# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K346, as amended by K351: where a continued conversation enters (session vocabulary § AD, § AF).

v0.19 wrote it as one `continued_session` fragment, opening text in every prompt. v0.21 retires
that source for writing: `session_prompt` yields the conversation as events after the
session-open fragments, and the history renders them. Records of v0.19–v0.20 still name the
source, so it stays a session-open source for reading.
"""

from __future__ import annotations

import asyncio
from typing import Any

from substrate.topologies.session import ModelReply, PromptFragment, UserMessage
from substrate.topologies.session.session_prompt_producer import (
    session_prompt_producer_factory,
    session_prompt_sources,
)
from substrate.topologies.session.vocabulary import SESSION_OPEN_SOURCES, PromptSource

TURNS: list[dict[str, Any]] = [
    {"kind": "UserMessage", "payload": {"text": "Remember the word: heron.", "turn_index": 0}},
    {"kind": "ModelReply", "payload": {"text": "OK.", "stop_reason": "end_turn"}},
    {"kind": "UserMessage", "payload": {"text": "List the folder.", "turn_index": 1}},
    {
        "kind": "HarnessToolCall",
        "payload": {"call_id": "t1", "tool": "Bash", "args": {"command": "ls"}},
    },
    {
        "kind": "HarnessToolResult",
        "payload": {"call_id": "t1", "output": "a.txt\nb.txt", "ok": True},
    },
    {
        "kind": "ModelReply",
        "payload": {"text": "Two files: a.txt and b.txt.", "stop_reason": "end_turn"},
    },
]
CONTINUED = {"turns": TURNS, "provenance": {"tool": "claude_code", "path": "/x/s.jsonl"}}
BASE: dict[str, Any] = {
    "role": None,
    "role_repo_root": None,
    "bundle": None,
    "parent_context": None,
    "tools": {},
}


def _emitted(inp: Any) -> list[Any]:
    body = session_prompt_producer_factory(
        session_id="s_test",
        sources=session_prompt_sources(**BASE, per_turn="Be brief."),
        seed_warning=None,
        continued_session=CONTINUED,
    )()

    async def collect() -> list[Any]:
        return [item async for item in body(inp)]

    return asyncio.run(collect())


def test_the_retired_source_is_read_but_never_written() -> None:
    assert PromptSource.CONTINUED_SESSION in SESSION_OPEN_SOURCES
    assert PromptSource.CONTINUED_SESSION not in session_prompt_sources(**BASE)


def test_session_open_yields_the_fragments_then_the_conversation() -> None:
    emitted = _emitted({})
    kinds = [type(e).__name__ for e in emitted]
    assert kinds[0] == "PromptFragment" and "continued_session" not in {
        e.source for e in emitted if isinstance(e, PromptFragment)
    }
    first_message = kinds.index("UserMessage")
    assert all(k == "PromptFragment" for k in kinds[:first_message])
    assert kinds[first_message:] == [
        "UserMessage",
        "ModelReply",
        "UserMessage",
        "HarnessToolCall",
        "HarnessToolResult",
        "ModelReply",
    ]
    messages = [e for e in emitted if isinstance(e, UserMessage)]
    assert [(m.text, m.turn_index) for m in messages] == [
        ("Remember the word: heron.", -2),
        ("List the folder.", -1),
    ]
    assert [e.text for e in emitted if isinstance(e, ModelReply)][-1] == (
        "Two files: a.txt and b.txt."
    )


def test_a_change_run_does_not_import_it_again() -> None:
    emitted = _emitted({"changes": [], "only": []})
    assert not [e for e in emitted if isinstance(e, (UserMessage, ModelReply))]

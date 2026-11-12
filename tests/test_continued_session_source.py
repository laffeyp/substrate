# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K346: the `continued_session` prompt source (session vocabulary § AD, v0.19).

A conversation held elsewhere enters a new session as its opening text: the given turns rendered
by the history's own renderer, one fragment at precedence 30, recorded at session open.
"""

from __future__ import annotations

import asyncio
from typing import Any

from substrate.topologies.session import PromptFragment
from substrate.topologies.session.session_prompt_producer import (
    CONTINUED_SESSION_PRECEDENCE,
    continued_session_fragments,
    session_prompt_producer_factory,
    session_prompt_sources,
)
from substrate.topologies.session.transcript import (
    _group_by_turn,
    _render_turns,
    compose_model_prompt,
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
PROVENANCE = {"tool": "claude_code", "path": "/x/s.jsonl", "summary_line": 7}


def test_the_text_is_the_historys_own_rendering() -> None:
    (frag,) = continued_session_fragments({"turns": TURNS, "provenance": PROVENANCE})
    rendered = "\n".join(_render_turns(_group_by_turn(TURNS)))
    assert frag.text == (
        "This session continues a conversation held in claude_code. The conversation so far:\n\n"
        + rendered
    )
    assert "USER: Remember the word: heron." in frag.text
    assert "HARNESS TOOL Bash: args={'command': 'ls'}" in frag.text
    assert "HARNESS RESULT: a.txt\nb.txt" in frag.text
    assert "MODEL: Two files: a.txt and b.txt." in frag.text


def test_source_precedence_and_provenance() -> None:
    (frag,) = continued_session_fragments({"turns": TURNS, "provenance": PROVENANCE})
    assert frag.source == PromptSource.CONTINUED_SESSION == "continued_session"
    assert frag.precedence == CONTINUED_SESSION_PRECEDENCE == 30
    assert frag.provenance == {**PROVENANCE, "turns": 2, "events": 6}


def test_no_turns_no_fragment() -> None:
    assert continued_session_fragments({"turns": [], "provenance": PROVENANCE}) == []
    # Events before the first UserMessage belong to no turn, as in the history.
    only_reply = [{"kind": "ModelReply", "payload": {"text": "x", "stop_reason": "end_turn"}}]
    assert continued_session_fragments({"turns": only_reply}) == []


def test_a_session_open_source_only_when_named() -> None:
    assert PromptSource.CONTINUED_SESSION in SESSION_OPEN_SOURCES
    base: dict[str, Any] = {
        "role": None,
        "role_repo_root": None,
        "bundle": None,
        "parent_context": None,
        "tools": {},
    }
    assert PromptSource.CONTINUED_SESSION not in session_prompt_sources(**base)
    on = session_prompt_sources(**base, continued_session={"turns": TURNS})
    assert PromptSource.CONTINUED_SESSION in on


def test_the_producer_records_it_and_the_prompt_carries_it() -> None:
    sources = session_prompt_sources(
        role=None,
        role_repo_root=None,
        bundle=None,
        parent_context=None,
        tools={},
        continued_session={"turns": TURNS, "provenance": PROVENANCE},
    )
    body = session_prompt_producer_factory(
        session_id="s_test", sources=sources, seed_warning=None
    )()

    async def collect() -> list[Any]:
        return [item async for item in body({})]

    emitted = asyncio.run(collect())
    frags = [e for e in emitted if isinstance(e, PromptFragment)]
    assert [f.source for f in frags] == ["continued_session"]
    _system, prompt, used = compose_model_prompt(
        history=[],
        seed="SEED",
        fragments=[
            (5, {"source": f.source, "text": f.text, "precedence": f.precedence}) for f in frags
        ],
    )
    assert used == (5,)
    assert prompt.startswith("SEED\n\nThis session continues a conversation held in claude_code.")
    assert "MODEL: Two files: a.txt and b.txt." in prompt

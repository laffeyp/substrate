# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K263: one `session_prompt` producer for every session-open prompt source.

Before: `role_fragment`, `bundle_methodology_fragment`, `bundle_personality_fragment`,
`tools_suite_fragment` and `parent_context_fragment` each ran as a producer, `session_warning`
and `fragment_error_warning` both emitted SessionWarning, and the opener was `session_open`. A
session with a role, the `session` bundle and tools wrote 22 envelopes before its first
UserMessage. The session's parent-context slice was a copy of delegate's extractor (lens F106).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.ci import ci_session_topology
from substrate.topologies.session.vocabulary import (
    PRODUCER_KIND_FIRST_MESSAGE,
    PRODUCER_KIND_SESSION_PROMPT,
)
from substrate.topologies.tool_loop.tools import CALCULATOR


def _um(text: str, turn_index: int = 0) -> UserMessage:
    return UserMessage(text=text, turn_index=turn_index, assembled_prompt="", slash_source="chat")


def _topo(tmp_path: Path, **kw: Any) -> Any:
    return session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=8_192,
        seed="SEED",
        tools=dict(CALCULATOR),
        session_id="s263",
        workspace_path=str(tmp_path),
        role="reviewer",
        bundle="session",
        first_turn_user_message=_um("hello"),
        **kw,
    )


def _registration(topo: Any) -> api.Registration:
    b = api.TopologyBuilder()
    topo(b)
    return b.build()


def test_the_session_registers_eight_producer_kinds(tmp_path: Path) -> None:
    reg = _registration(_topo(tmp_path))
    assert set(reg.producer_kinds) == {
        "session_started",
        "model",
        "tool",
        "return",
        "session_end",
        "interrupt_fragment",
        PRODUCER_KIND_SESSION_PROMPT,
        PRODUCER_KIND_FIRST_MESSAGE,
    }
    # One trigger listens to a producer's end: the first message waits for the session prompt.
    on_lifecycle = [
        t.id
        for t in reg.triggers
        if api.PRODUCER_COMPLETED in (t.subscription.kinds or frozenset())
    ]
    assert on_lifecycle == ["first-message-on-session-prompt"]


def test_session_open_writes_thirteen_envelopes_and_keeps_each_source(tmp_path: Path) -> None:
    root = tmp_path / "rec"
    asyncio.run(api.Runtime(root).run(_topo(tmp_path), name="session"))
    envs = list(api.read_record(root))
    first = next(i for i, e in enumerate(envs) if e["kind"] == "UserMessage")
    assert first == 13, [e["kind"] for e in envs[:first]]
    started = [
        e["payload"]["producer"]["kind"]
        for e in envs[:first]
        if e["kind"] == "substrate.ProducerStarted"
    ]
    assert started == ["session_started", PRODUCER_KIND_SESSION_PROMPT, PRODUCER_KIND_FIRST_MESSAGE]
    fragments = [e["payload"] for e in envs if e["kind"] == "PromptFragment"]
    assert [(f["source"], f["precedence"]) for f in fragments] == [
        ("role", 0),
        ("bundle_methodology", 50),
        ("tools_suite", 20),
    ]
    # The first model call's prompt was built from all three.
    composed = next(e["payload"] for e in envs if e["kind"] == "PromptComposed")
    frag_seqs = [e["seq"] for e in envs if e["kind"] == "PromptFragment"]
    assert sorted(composed["fragment_seqs"]) == frag_seqs


def test_a_large_seed_warns_from_the_session_prompt_before_the_first_message(
    tmp_path: Path,
) -> None:
    root = tmp_path / "rec"
    topo = session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=4_096,
        seed="X" * 20_000,
        tools={},
        session_id="s263w",
        workspace_path=str(tmp_path),
        first_turn_user_message=_um("hello"),
    )
    asyncio.run(api.Runtime(root).run(topo, name="session"))
    domain = [e for e in api.read_record(root) if not e["kind"].startswith("substrate.")]
    assert [e["kind"] for e in domain[:3]] == ["SessionStarted", "SessionWarning", "UserMessage"]
    assert domain[1]["payload"]["kind"] == "seed_alone_exceeds"


def test_a_session_with_no_prompt_source_has_no_session_prompt(tmp_path: Path) -> None:
    topo = session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=8_192,
        seed="SEED",
        tools={},
        session_id="s263n",
        workspace_path=str(tmp_path),
        first_turn_user_message=_um("hello"),
    )
    reg = _registration(topo)
    assert PRODUCER_KIND_SESSION_PROMPT not in reg.producer_kinds
    assert [i.kind for i in reg.initials] == [PRODUCER_KIND_FIRST_MESSAGE]


def test_a_resume_writes_no_second_first_message(tmp_path: Path) -> None:
    root = tmp_path / "rec"
    asyncio.run(api.Runtime(root, persistent=True).run(_topo(tmp_path), name="session"))
    asyncio.run(
        api.Runtime(root, persistent=True).resume(_topo(tmp_path), resume_event=_um("and again", 1))
    )
    envs = list(api.read_record(root))
    assert [e["payload"]["text"] for e in envs if e["kind"] == "UserMessage"] == [
        "hello",
        "and again",
    ]
    assert sum(1 for e in envs if e["kind"] == "Returned") == 2


def test_the_parent_slice_takes_v03_replies_for_final_answer(tmp_path: Path) -> None:
    """The session's slice is delegate's extractor, so a `FinalAnswer` filter on a v0.3 parent
    takes its replies (vocabulary § M.5). The session copy matched kinds literally and took
    nothing from a v0.3 parent."""
    parent = tmp_path / "parent"
    asyncio.run(api.Runtime(parent).run(ci_session_topology(turns=("what is 2+2", "/exit"))))
    replies = [
        e["seq"]
        for e in api.read_record(parent)
        if e["kind"] == "ModelReply" and e["payload"]["stop_reason"] != "tool_use"
    ]
    assert replies
    child = tmp_path / "child"
    asyncio.run(
        api.Runtime(child).run(
            ci_session_topology(
                turns=("hi", "/exit"),
                session_id="s263c",
                parent_context={"parent_record_root": str(parent), "kinds": ["FinalAnswer"]},
            )
        )
    )
    frag = next(
        e["payload"]
        for e in api.read_record(child)
        if e["kind"] == "PromptFragment" and e["payload"]["source"] == "parent_context"
    )
    lines = [ln for ln in frag["text"].splitlines() if ln.startswith("[seq=")]
    assert [int(ln.split()[0][len("[seq=") :]) for ln in lines] == replies

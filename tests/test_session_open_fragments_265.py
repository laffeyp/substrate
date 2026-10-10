# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K265: every session-open fragment reaches the prompt, and none is written again on a resume.

Before: `FragmentCohort` kept one slot per session-open source and let the newest win, on the
belief that resumed sessions re-emit their fragments. They do not (the card traces the case that
looked like it). The slot dropped every methodology but the last of a bundle whose `extends` chain
has two links.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.bundles import Bundle
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session import session_prompt_producer as sp


def _bundle(name: str, extends: tuple[str, ...], methodology: str) -> Bundle:
    return Bundle(
        name=name,
        description="",
        schema_version=1,
        extends=extends,
        methodology=methodology,
        personality="",
        per_turn="",
        corpus_paths=(),
        retrieval_kind="none",
        tools_enabled=(),
    )


def _um(text: str, i: int) -> UserMessage:
    return UserMessage(text=text, turn_index=i, assembled_prompt="", slash_source="chat")


def _topo(tmp_path: Path, first: UserMessage | None) -> Any:
    return session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=8_192,
        seed="SEED",
        tools={},
        session_id="s265",
        workspace_path=str(tmp_path),
        bundle="child",
        first_turn_user_message=first,
    )


def test_every_link_of_a_bundle_chain_reaches_the_prompt_across_a_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chain = [
        _bundle("base", (), "BASE-METHOD: test before claiming."),
        _bundle("child", ("base",), "CHILD-METHOD: keep diffs small."),
    ]
    monkeypatch.setattr(sp, "resolve_chain", lambda _name: chain)
    root = tmp_path / "rec"
    asyncio.run(api.Runtime(root, persistent=True).run(_topo(tmp_path, _um("one", 0))))
    asyncio.run(
        api.Runtime(root, persistent=True).resume(_topo(tmp_path, None), resume_event=_um("two", 1))
    )
    envs = list(api.read_record(root))
    fragments = [e for e in envs if e["kind"] == "PromptFragment"]
    # Written once, in the first run; the resumed turn writes none.
    assert [f["payload"]["precedence"] for f in fragments] == [50, 51]
    first_um_of_turn_two = next(
        e["seq"] for e in envs if e["kind"] == "UserMessage" and e["payload"]["text"] == "two"
    )
    assert all(f["seq"] < first_um_of_turn_two for f in fragments)
    prompts = [e["payload"] for e in envs if e["kind"] == "PromptComposed"]
    assert len(prompts) == 2
    for prompt in prompts:
        text = prompt["text"]
        assert text.index("BASE-METHOD") < text.index("CHILD-METHOD"), text
        assert sorted(prompt["fragment_seqs"]) == [f["seq"] for f in fragments]

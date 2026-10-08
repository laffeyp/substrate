# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Live-model verification of the prompt-composition compute path — sprint 067.

Prior sprints (058-064) shipped the fragment/composer Producer graph and
put every fragment on the record deterministically. Sprint 067 flipped
the model producer's input Predicate to `PromptComposed` — the fragment
composed text is now the source of truth for the model's prompt, and
`render_transcript`'s per_turn injection is removed. These tests prove
the fragment path reaches the driver by observing the reply.

Each test binds a single fragment source, sets its content to a
distinctive token, runs one turn against Ollama, and asserts the model
reply reflects the token. Probabilistic tests — the model's exact
wording varies; assertions check for a family of expected tokens where
paraphrase is likely.

Prerequisite: Ollama live at 127.0.0.1:11434 with the models these
tests name loaded. Marked `@pytest.mark.realmodel`; deselected in the
default CI run.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from substrate import api
from substrate.adapters import OllamaResponder
from substrate.topologies.session import session_topology
from substrate.topologies.tool_loop.tools import CALCULATOR


_MODEL = "kimi-k2.6:cloud"  # daily-driver cloud model per project convention
_TIMEOUT = 300.0


def _require_model() -> None:
    """Skip, naming why, when Ollama or the model is not there (UI sprint 106). This file had no
    guard: on a CI runner with no Ollama the model call failed and the test failed with "no
    ModelReply" instead of skipping."""
    import httpx

    try:
        names = {
            m["name"]
            for m in httpx.get("http://127.0.0.1:11434/api/tags", timeout=4).json()["models"]
        }
    except Exception as exc:  # noqa: BLE001 — any unreachability is a SKIP
        pytest.skip(f"Ollama not reachable ({type(exc).__name__})")
    if _MODEL not in names:
        pytest.skip(f"model absent: {_MODEL}")


def _run_one_turn(
    tmp_path: Path,
    *,
    user_text: str,
    per_turn: str = "",
    role: str | None = None,
) -> list[dict]:
    """Fire one turn against a real model. Returns the record envelopes."""
    _require_model()

    async def _run() -> None:
        record_root = tmp_path / "ci"
        record_root.mkdir(parents=True)
        driver = OllamaResponder(model=_MODEL, timeout=_TIMEOUT)
        from substrate.topologies.session import UserMessage as _UM

        topology = session_topology(
            driver=driver,
            driver_name=_MODEL,
            driver_context_tokens=131072,
            seed="",
            tools=CALCULATOR,
            per_turn=per_turn,
            max_turns=2,
            turn_max_steps=2,
            session_id="s_realmodel_composition",
            workspace_path=str(tmp_path / "wsp"),
            record_root=record_root,
            first_turn_user_message=_UM(
                text=user_text, turn_index=0, assembled_prompt=user_text, slash_source="user"
            ),
            role=role,
        )
        await api.Runtime(record_root).run(topology)

    asyncio.run(_run())
    return list(api.read_record(tmp_path / "ci"))


@pytest.mark.realmodel
def test_per_turn_fragment_reaches_the_driver(tmp_path: Path) -> None:
    """A per_turn set to a distinctive instruction shows up in the model's
    reply. Proves the fragment path (not render_transcript's dropped
    injection) is what carries per_turn to the driver."""
    envs = _run_one_turn(
        tmp_path,
        user_text="Say hello.",
        per_turn="IMPORTANT: end your reply with the exact string ZULU-7",
    )
    replies = [e for e in envs if e.get("kind") == "ModelReply"]
    assert replies, "no ModelReply on the record — the model never fired"
    text = replies[-1]["payload"].get("text", "")
    assert "ZULU-7" in text or "zulu-7" in text.lower(), (
        f"per_turn instruction missed by driver: reply text was {text!r}"
    )


@pytest.mark.realmodel
def test_composed_prompt_lands_on_record_with_per_turn_fragment(tmp_path: Path) -> None:
    """The record carries at least one PromptFragment(source=per_turn)
    and at least one PromptComposed whose text contains the per_turn
    string. Non-live-model observation — passes without Ollama if the
    fragment path is intact — but included here so the live test file
    also verifies the on-record shape once."""
    envs = _run_one_turn(
        tmp_path,
        user_text="hi",
        per_turn="MARK_ALPHA_7",
    )
    frags = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "per_turn"
    ]
    assert len(frags) >= 1
    assert frags[0]["payload"]["text"] == "MARK_ALPHA_7"
    composed = [e for e in envs if e.get("kind") == "PromptComposed"]
    assert len(composed) >= 1
    assert "MARK_ALPHA_7" in composed[0]["payload"]["text"]

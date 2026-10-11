# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K277: dellm, loaded only when asked (session vocabulary § P.6, § P.10).

The operator's `/dellm` sends the turn with slash_source "skill:dellm": the skill's body lands as a
`skill` fragment before the model starts, and stays for the session. A model asked in words calls
the `skill` tool, which returns the body.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.skills import list_skills, make_skill_tool, resolve_skill


class Capture:
    name = "capture"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def respond(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "rewritten"


def _turn(root: Path, driver: Capture, text: str, turn_index: int, slash: str = "chat") -> None:
    um = UserMessage(text=text, turn_index=turn_index, assembled_prompt="", slash_source=slash)
    topo = session_topology(
        driver=driver,
        driver_name="capture",
        driver_context_tokens=100_000,
        seed="SEED",
        tools={},
        session_id="s_277",
        workspace_path=str(root.parent),
        first_turn_user_message=um if turn_index == 0 else None,
    )
    rt = api.Runtime(root, persistent=True)
    if turn_index == 0:
        asyncio.run(rt.run(topo, name="session"))
    else:
        asyncio.run(rt.resume(topo, resume_event=um))


def _events(root: Path) -> list[dict[str, Any]]:
    return list(api.read_record(root, resolve_blobs=True))


def test_dellm_ships_and_lists() -> None:
    body, path = resolve_skill("dellm", None) or ("", Path())
    assert body.startswith("---\nname: dellm") and path.name == "SKILL.md"
    assert dict(list_skills(None))["dellm"].startswith("Rewrite or draft prose")


def test_a_slash_request_loads_the_skill_before_the_model_and_keeps_it(tmp_path: Path) -> None:
    root = tmp_path / "record"
    driver = Capture()
    _turn(root, driver, "Fix this paragraph.", 0, slash="skill:dellm")
    _turn(root, driver, "And this one.", 1)
    events = _events(root)
    kinds = [e["kind"] for e in events]
    skill_seq = next(
        e["seq"]
        for e in events
        if e["kind"] == "PromptFragment" and e["payload"]["source"] == "skill"
    )
    first_composed = next(e["seq"] for e in events if e["kind"] == "PromptComposed")
    assert skill_seq < first_composed
    assert kinds.count("PromptComposed") == 2
    for prompt in driver.prompts:
        assert prompt.count("# De-LLM-ize: write like a person with something to say") == 1


def test_an_unknown_skill_warns_and_the_turn_still_answers(tmp_path: Path) -> None:
    root = tmp_path / "record"
    driver = Capture()
    _turn(root, driver, "hi", 0, slash="skill:nope")
    events = _events(root)
    warning = next(e["payload"] for e in events if e["kind"] == "SessionWarning")
    assert warning["source_name"] == "skill" and "nope" in warning["detail"]
    assert len(driver.prompts) == 1


def test_the_tool_returns_the_body_and_lists_the_skills(tmp_path: Path) -> None:
    tool = make_skill_tool(tmp_path)
    assert "dellm: Rewrite or draft prose" in tool.describe
    assert tool.run(["dellm"]).startswith("---\nname: dellm")
    with pytest.raises(ValueError, match="no skill named 'nope'"):
        tool.run(["nope"])


def test_a_repo_skill_shadows_the_shipped_one(tmp_path: Path) -> None:
    d = tmp_path / ".substrate" / "skills" / "dellm"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: dellm\ndescription: local\n---\nLOCAL", encoding="utf-8"
    )
    assert resolve_skill("dellm", tmp_path) == (
        "---\nname: dellm\ndescription: local\n---\nLOCAL",
        d / "SKILL.md",
    )

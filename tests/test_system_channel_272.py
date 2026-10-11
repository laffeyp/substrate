# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K272: the system channel (session vocabulary § P.3).

A bundle's style goes on the driver's system channel. A driver with one (`system_channel = True`)
receives it as `system=`; any other receives it ahead of the prompt with a blank line between.
Either way `PromptComposed.system` and `.text` are what the driver read.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import CliResponder, OllamaResponder, call_responder_metered
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.transcript import head_block

STYLE = "STYLE-TEXT"
METHOD = "METHOD-TEXT"


class Plain:
    """No system channel: records every prompt."""

    name = "plain"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def respond(self, prompt: str) -> str:
        self.calls.append(prompt)
        return "done"


class Channel:
    """A system channel: records every (system, prompt) pair."""

    name = "channel"
    system_channel = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def arespond(self, prompt: str, *, system: str = "") -> str:
        self.calls.append((system, prompt))
        return "done"


def _bundle(home: Path) -> None:
    b = home / "bundles" / "styled"
    b.mkdir(parents=True)
    (b / "bundle.toml").write_text('[bundle]\nname = "styled"\n', encoding="utf-8")
    (b / "style.md").write_text(STYLE, encoding="utf-8")
    (b / "methodology.md").write_text(METHOD, encoding="utf-8")


def _run(root: Path, driver: Any) -> list[dict[str, Any]]:
    um = UserMessage(text="HELLO", turn_index=0, assembled_prompt="", slash_source="chat")
    topo = session_topology(
        driver=driver,
        driver_name="d",
        driver_context_tokens=100_000,
        seed="",
        tools={},
        session_id="s_272",
        workspace_path=str(root.parent),
        bundle="styled",
        first_turn_user_message=um,
    )
    asyncio.run(api.Runtime(root).run(topo, name="session"))
    return [
        e["payload"]
        for e in api.read_record(root, resolve_blobs=True)
        if e["kind"] == "PromptComposed"
    ]


def test_head_block_puts_style_in_the_system_part() -> None:
    fragments = [
        (1, {"source": "bundle_style", "text": STYLE, "precedence": 3}),
        (2, {"source": "bundle_methodology", "text": METHOD, "precedence": 5}),
        (3, {"source": "bundle_personality", "text": "OLD-STYLE", "precedence": 3}),
    ]
    system, head, _reminder, seqs = head_block("SEED", fragments)
    assert system == f"{STYLE}\n\nOLD-STYLE"
    assert head == f"SEED\n\n{METHOD}"
    assert seqs == (1, 2, 3)


def test_a_driver_with_a_channel_gets_the_style_as_system(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUBSTRATE_HOME", str(tmp_path / "home"))
    _bundle(tmp_path / "home")
    driver = Channel()
    (composed,) = _run(tmp_path / "record", driver)
    assert driver.calls == [(composed["system"], composed["text"])]
    assert composed["system"] == STYLE
    assert STYLE not in composed["text"] and METHOD in composed["text"]


def test_a_driver_without_one_gets_system_then_a_blank_line_then_the_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUBSTRATE_HOME", str(tmp_path / "home"))
    _bundle(tmp_path / "home")
    driver = Plain()
    (composed,) = _run(tmp_path / "record", driver)
    assert driver.calls == [f"{composed['system']}\n\n{composed['text']}"]


def test_no_system_text_leaves_the_prompt_alone() -> None:
    driver = Plain()
    asyncio.run(call_responder_metered(driver, "P"))
    assert driver.calls == ["P"]


def test_cli_argv_with_and_without_a_flag() -> None:
    flagged = CliResponder(["claude", "-p"], system_flag=["--system-prompt"])
    assert flagged.system_channel
    assert flagged._argv("P", "S") == ["claude", "-p", "--system-prompt", "S", "P"]
    assert flagged._argv("P", "") == ["claude", "-p", "--system-prompt", "", "P"]
    assert flagged.at("/tmp")._argv("P", "S") == ["claude", "-p", "--system-prompt", "S", "P"]
    bare = CliResponder(["codex", "exec"])
    assert not bare.system_channel
    assert bare._argv("P", "S") == ["codex", "exec", "S\n\nP"]


def test_ollama_sends_the_call_system_as_a_system_message() -> None:
    r = OllamaResponder("m", system="FALLBACK")
    _h, payload = r._request("P", system="S")
    assert payload["messages"] == [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "P"},
    ]
    _h, payload = r._request("P")
    assert payload["messages"][0] == {"role": "system", "content": "FALLBACK"}


def test_cache_layout_moves_the_session_stable_texts_to_system() -> None:
    """UI sprint 121 (§ P.3): the opt-in layout puts role, methodology and the tool list on the
    system channel too; the default leaves them in the user turn."""
    from substrate.topologies.session.vocabulary import CACHE_LAYOUT_SOURCES, SYSTEM_SOURCES

    fragments = [
        (1, {"source": "bundle_style", "text": STYLE, "precedence": 3}),
        (2, {"source": "role", "text": "ROLE", "precedence": 0}),
        (3, {"source": "bundle_methodology", "text": METHOD, "precedence": 5}),
        (4, {"source": "tools_suite", "text": "TOOLS", "precedence": 20}),
    ]
    system, head, _r, _s = head_block("SEED", fragments)
    assert system == STYLE and head == f"SEED\n\nROLE\n\n{METHOD}\n\nTOOLS"
    on = frozenset(SYSTEM_SOURCES | CACHE_LAYOUT_SOURCES)
    system, head, _r, _s = head_block("SEED", fragments, on)
    assert system == f"ROLE\n\n{STYLE}\n\n{METHOD}\n\nTOOLS" and head == "SEED"

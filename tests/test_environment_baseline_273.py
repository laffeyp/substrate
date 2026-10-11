# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K273: the environment baseline (session vocabulary § P.2).

The daemon computes it; the session records it on RunStarted and SessionStarted and writes it once
as the `baseline` fragment, which goes on the system channel.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import subprocess
from pathlib import Path
from typing import Any

from substrate import api
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.environment import (
    GIT_DIFF_BYTES,
    model_id,
    render_baseline,
    session_baseline,
)

DAY = dt.date(2026, 10, 10)


def _repo(path: Path) -> Path:
    path.mkdir()
    for cmd in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.name", "t"],
        ["git", "config", "user.email", "t@localhost.invalid"],
    ):
        subprocess.run(cmd, cwd=path, check=True)
    (path / "README.md").write_text("# Demo\nA demo repo.\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    return path


def test_a_git_workspace(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    (repo / "README.md").write_text("# Demo\nchanged\n", encoding="utf-8")
    (repo / ".substrate").mkdir()
    (repo / ".substrate" / "context.md").write_text("Use tabs.", encoding="utf-8")
    b = session_baseline(repo, "claude", ("claude", "-p", "--model", "claude-opus-5-5"), today=DAY)
    assert b["repo_root"] == str(repo.resolve())
    assert b["branch"] == "main" and len(b["commit"]) == 40
    assert b["readme_head"].startswith("# Demo")
    assert "+changed" in b["git_diff"]
    assert b["project_context"] == "Use tabs."
    assert b["model_id"] == "claude-opus-5-5" and b["driver"] == "claude"
    assert b["date"] == "2026-10-10"
    assert "cwd" not in b


def test_a_flat_workspace(tmp_path: Path) -> None:
    b = session_baseline(tmp_path, "glm-5.2:cloud", today=DAY)
    assert "repo_root" not in b and b["cwd"] == str(tmp_path) and b["hostname"]
    assert b["model_id"] == "glm-5.2:cloud"


def test_a_large_diff_is_capped(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    (repo / "README.md").write_text("x\n" * (GIT_DIFF_BYTES), encoding="utf-8")
    b = session_baseline(repo, "d", today=DAY)
    assert len(b["git_diff"].encode()) < GIT_DIFF_BYTES + 100
    assert b["git_diff"].endswith("more bytes not shown")


def test_model_id_without_a_model_flag() -> None:
    assert model_id("codex", ("codex", "exec")) == "codex"


class _Channel:
    name = "channel"
    system_channel = True

    def __init__(self) -> None:
        self.systems: list[str] = []

    async def arespond(self, prompt: str, *, system: str = "") -> str:
        self.systems.append(system)
        return "done"


def test_the_session_records_it_and_sends_it_on_the_system_channel(tmp_path: Path) -> None:
    baseline: dict[str, Any] = session_baseline(tmp_path, "channel", today=DAY)
    driver = _Channel()
    root = tmp_path / "record"
    um = UserMessage(text="hi", turn_index=0, assembled_prompt="", slash_source="chat")
    topo = session_topology(
        driver=driver,
        driver_name="channel",
        driver_context_tokens=100_000,
        seed="",
        tools={},
        session_id="s_273",
        workspace_path=str(tmp_path),
        first_turn_user_message=um,
        baseline=baseline,
    )
    asyncio.run(api.Runtime(root).run(topo, name="session"))
    envs = list(api.read_record(root))
    assert envs[0]["payload"]["baseline"] == baseline
    started = next(e["payload"] for e in envs if e["kind"] == "SessionStarted")
    assert started["baseline"] == baseline
    frags = [e["payload"] for e in envs if e["kind"] == "PromptFragment"]
    assert [f["source"] for f in frags] == ["baseline"]
    assert frags[0]["text"] == render_baseline(baseline)
    composed = next(e["payload"] for e in envs if e["kind"] == "PromptComposed")
    assert composed["system"] == render_baseline(baseline) == driver.systems[0]
    assert "Today's date: 2026-10-10" in composed["system"]

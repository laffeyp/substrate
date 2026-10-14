# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 329: a run session (vocabulary § Z.2, research r9 § 3). The topology writes its
first message; when its one turn ends it writes its report and finalises; nothing grades it."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.runs.run import RunSpec, write_report
from substrate.topologies.session import session_topology
from substrate.topologies.tool_loop.tools import full_suite
from substrate.topologies.workspace import ensure_repository

pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("a\n")
    ensure_repository(repo)
    return repo, _git(repo, "rev-parse", "HEAD")


class _Fails:
    name = "fails"

    def respond(self, prompt: str) -> str:
        raise RuntimeError("the model is down")

    async def arespond(self, prompt: str) -> str:
        raise RuntimeError("the model is down")


def _run(
    tmp_path: Path, driver: Any, script: list[tuple[str, list[Any]]] | None
) -> list[dict[str, Any]]:
    repo, base = _repo(tmp_path)
    topo = session_topology(
        driver=driver,
        driver_name="d",
        driver_context_tokens=8192,
        seed="",
        tools=full_suite(repo),
        session_id="s_run",
        workspace_path=str(repo),
        script=script,
        run=RunSpec(worktree=repo, base=base, first_message="add b.txt"),
    )
    root = tmp_path / "record"
    result = asyncio.run(api.Runtime(root).run(topo, name="session"))
    assert result.status == "finalised"
    return list(api.read_record(root, resolve_blobs=True))


def test_a_run_reports_what_it_did_and_ends(tmp_path: Path) -> None:
    script = [("write_file", ["b.txt", "b\n"]), ("bash", ["git add -A && git commit -qm b"])]
    events = _run(tmp_path, DeterministicResponder(seed=0), script)
    kinds = [e["kind"] for e in events if not e["kind"].startswith("substrate.")]
    first = next(e["payload"] for e in events if e["kind"] == "UserMessage")
    assert first["text"] == "add b.txt" and first["slash_source"] == "run"
    (report,) = [e["payload"] for e in events if e["kind"] == "ReportWritten"]
    assert report["outcome"] == "done" and report["files"] == ["b.txt"]
    assert len(report["commits"]) == 1 and report["branch"] and report["reply"]
    assert kinds.index("ReportWritten") > kinds.index("Returned")
    assert kinds.count("UserMessage") == 1  # one turn; no message after it


def test_a_model_error_ends_the_run_failed(tmp_path: Path) -> None:
    events = _run(tmp_path, _Fails(), None)
    (report,) = [e["payload"] for e in events if e["kind"] == "ReportWritten"]
    assert report["outcome"] == "failed"


def test_an_interrupted_turn_reports_stopped_and_a_detached_worktree_no_branch(
    tmp_path: Path,
) -> None:
    repo, base = _repo(tmp_path)
    _git(repo, "checkout", "-q", "--detach")
    report = write_report("interrupted", [], worktree=repo, base=base)
    assert report.outcome == "stopped" and report.branch is None and report.files == []

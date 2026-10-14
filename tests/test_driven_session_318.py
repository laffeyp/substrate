# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 318: the driven session (vocabulary § X.5). A session whose topology writes its next
message: the card, then on each turn's end the checks, then the next message or the report. Written
before `topologies/runs/driven.py` existed."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.runs.card import read_card
from substrate.topologies.runs.driven import DrivenRun
from substrate.topologies.session import session_topology
from substrate.topologies.session.vocabulary import RunLimits, RunOutcome
from substrate.topologies.tool_loop.tools import full_suite
from substrate.topologies.workspace import ensure_repository

pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("a\n")
    ensure_repository(repo)
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    return repo, head


def _run(
    tmp_path: Path,
    *,
    commands: list[str],
    script: list[tuple[str, list[Any]]] | None,
    limits: RunLimits,
    driver: Any = None,
) -> tuple[Any, list[dict[str, Any]]]:
    repo, base = _repo(tmp_path)
    card = read_card(
        what="add b.txt", where=["b.txt"], commands=commands, statements=[], limits=limits
    )
    run = DrivenRun(
        card=card,
        worktree=repo,
        base=base,
        check_timeout_s=30,
        first_message="Work on this card until its checks pass, committing as you go.\n\n"
        + card.text,
    )
    factory = session_topology(
        driver=driver or DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=4096,
        seed="",
        tools=full_suite(repo),
        session_id="s_driven",
        workspace_path=str(repo),
        script=script,
        driven=run,
    )
    root = tmp_path / "record"
    import asyncio

    result = asyncio.run(api.Runtime(root).run(factory))
    return result, list(api.read_record(root, resolve_blobs=True))


def _kinds(events: list[dict[str, Any]]) -> list[str]:
    return [str(e["kind"]) for e in events if not str(e["kind"]).startswith("substrate.")]


def _one(events: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    found = [e["payload"] for e in events if e["kind"] == kind]
    assert len(found) == 1, (kind, len(found))
    return found[0]


WRITE_AND_COMMIT = [
    ("write_file", ["b.txt", "b\n"]),
    ("bash", ["git add -A && git commit -qm 'add b'"]),
]


def test_a_worker_whose_checks_pass_ends_done(tmp_path: Path) -> None:
    result, events = _run(
        tmp_path,
        commands=["test -f b.txt"],
        script=WRITE_AND_COMMIT,
        limits=RunLimits(max_stops=5, stall_stops=2),
    )
    assert result.status == "finalised"
    kinds = _kinds(events)
    assert kinds.index("CardAccepted") < kinds.index("UserMessage")
    assert kinds.count("ChecksRun") == 1
    report = _one(events, "ReportWritten")
    assert report["outcome"] == RunOutcome.DONE
    assert report["files"] == ["b.txt"] and len(report["commits"]) == 1
    assert kinds[-1] == "ReportWritten"


def test_a_worker_that_never_passes_ends_stuck_on_a_stall(tmp_path: Path) -> None:
    result, events = _run(
        tmp_path,
        commands=["test -f never.txt"],
        script=[],
        limits=RunLimits(max_stops=10, stall_stops=2),
    )
    assert result.status == "finalised"
    kinds = _kinds(events)
    assert (
        kinds.count("ChecksRun") == 2
    )  # two turn ends in a row with no commit and the same checks
    driven = [e["payload"] for e in events if e["kind"] == "UserMessage"]
    assert [m["slash_source"] for m in driven] == ["driven", "driven"]
    assert "test -f never.txt" in driven[1]["text"]  # the continuation names what failed
    report = _one(events, "ReportWritten")
    assert report["outcome"] == RunOutcome.STUCK and report["left"]


def test_a_worker_out_of_turns_ends_stuck(tmp_path: Path) -> None:
    result, events = _run(
        tmp_path,
        commands=["test -f never.txt"],
        script=[],
        limits=RunLimits(max_stops=3, stall_stops=99),
    )
    assert _kinds(events).count("ChecksRun") == 3
    assert _one(events, "ReportWritten")["outcome"] == RunOutcome.STUCK


class _Raising(DeterministicResponder):
    def respond(self, prompt: str) -> str:
        raise RuntimeError("the model is down")


def test_a_worker_whose_model_fails_ends_failed(tmp_path: Path) -> None:
    result, events = _run(
        tmp_path,
        commands=["test -f b.txt"],
        script=None,
        limits=RunLimits(max_stops=5, stall_stops=2),
        driver=_Raising(seed=0),
    )
    assert result.status == "finalised"
    report = _one(events, "ReportWritten")
    assert report["outcome"] == RunOutcome.FAILED and "the model is down" in report["left"]

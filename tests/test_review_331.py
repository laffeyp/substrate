# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 331: Review (research r9 § 8.3). One reviewer per style, each a run session in a
detached worktree at the target with read-only tools, for one turn; its reply is the review."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.runs.hold import RunTable
from substrate.topologies.runs.review import (
    REVIEW_STYLES,
    REVIEW_TOOLS,
    make_review_tool,
    resolve_target,
    start_review,
    style_text,
)
from substrate.topologies.session.vocabulary import RunOutcome
from substrate.topologies.workspace import ensure_repository

pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _repo_with_branch(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("x = 1\n")
    ensure_repository(repo)
    _git(repo, "checkout", "-qb", "feature")
    (repo / "a.py").write_text("x = 2\n")
    (repo / "b.py").write_text("y = x / 0\n")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "feature")
    _git(repo, "checkout", "-q", "-")
    return repo


def _wait(table: RunTable, owner: str, run_id: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while table.running(owner, run_id):
        assert time.monotonic() < deadline, "the run did not end"
        time.sleep(0.05)


def _start(
    table: RunTable, tmp_path: Path, repo: Path, target: str, styles: list[str]
) -> list[str]:
    return start_review(
        table,
        owner="caller",
        run_id="r_rev",
        repo=repo,
        target=target,
        styles=styles,
        focus="the division",
        driver_for=lambda _wt: DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=8192,
        worktrees=tmp_path / "wt",
        records=tmp_path / "records",
    )


def test_each_style_has_its_text() -> None:
    assert REVIEW_STYLES == ("defects", "design", "security")
    for style in REVIEW_STYLES:
        assert len(style_text(style)) > 200
    with pytest.raises(ValueError, match="style must be one of"):
        style_text("vibes")


def test_a_branch_target_is_its_changes_since_it_left_head(tmp_path: Path) -> None:
    repo = _repo_with_branch(tmp_path)
    head, changed, diff = resolve_target(repo, "feature")
    assert head == "feature" and sorted(changed) == ["a.py", "b.py"]
    assert "+y = x / 0" in diff
    assert resolve_target(repo, "a.py") == ("HEAD", ["a.py"], "")
    base = _git(repo, "rev-parse", "HEAD")
    head, changed, _ = resolve_target(repo, f"{base}..feature")
    assert head == "feature" and sorted(changed) == ["a.py", "b.py"]


def test_one_reviewer_per_style_each_ends_done_with_its_review(tmp_path: Path) -> None:
    repo = _repo_with_branch(tmp_path)
    table = RunTable()
    run_ids = _start(table, tmp_path, repo, "feature", ["defects", "security"])
    assert run_ids == ["r_rev-defects", "r_rev-security"]
    for rid in run_ids:
        _wait(table, "caller", rid)
    ended = {e.run_id: e for e in table.drain_ended("caller")}
    assert set(ended) == set(run_ids)
    for rid, style in zip(run_ids, ["defects", "security"]):
        e = ended[rid]
        assert e.outcome is RunOutcome.DONE and e.report is not None
        assert e.report.reply.strip()  # the review
        assert e.report.files == []  # a reviewer changes nothing
        assert e.report.branch is None  # a detached worktree is on no branch
        wt = tmp_path / "wt" / rid
        assert (wt / "b.py").read_text() == "y = x / 0\n"  # checked out at the target
        assert _git(wt, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"  # detached
        events = api.read_record(tmp_path / "records" / rid)
        suite = next(ev for ev in events if ev["kind"] == "PromptFragment")
        assert suite["payload"]["provenance"]["tool_names"] == sorted(REVIEW_TOOLS)
        first = next(ev for ev in events if ev["kind"] == "UserMessage")
        text = first["payload"]["text"]
        assert style_text(style).strip()[:80] in text
        assert "the division" in text and "+y = x / 0" in text
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") != "feature"  # the repo did not move


def test_an_unknown_style_starts_nothing(tmp_path: Path) -> None:
    repo = _repo_with_branch(tmp_path)
    table = RunTable()
    with pytest.raises(ValueError, match="style must be one of"):
        _start(table, tmp_path, repo, "feature", ["defects", "vibes"])
    assert not (tmp_path / "wt").exists()
    assert table.drain_ended("caller") == []


def test_the_review_tool_reads_the_form() -> None:
    calls: list[tuple[str, list[str], str]] = []

    def _start(target: str, styles: list[str], focus: str) -> list[str]:
        calls.append((target, styles, focus))
        return [f"r-{s}" for s in styles]

    tool = make_review_tool(_start)
    out = tool.run([{"target": "feature"}])
    assert (out["runs"], out["styles"]) == (["r-defects"], ["defects"]) and "report comes" in out[
        "next"
    ]
    tool.run([{"target": "main..x", "styles": ["design"], "focus": "names"}])
    assert calls[-1] == ("main..x", ["design"], "names")
    with pytest.raises(ValueError, match="target"):
        tool.run([{}])
    assert tool.schema is not None and set(REVIEW_TOOLS) == {
        "read_file",
        "list_dir",
        "glob",
        "grep",
    }


def test_a_caller_starts_two_reviews_and_reads_both(tmp_path: Path) -> None:
    import asyncio

    from substrate.topologies.runs import hold
    from substrate.topologies.session import UserMessage, session_topology

    repo = _repo_with_branch(tmp_path)
    table = RunTable()
    tool = make_review_tool(
        lambda target, styles, focus: start_review(
            table,
            owner="s_caller",
            run_id="r_c",
            repo=repo,
            target=target,
            styles=styles,
            focus=focus,
            driver_for=lambda _wt: DeterministicResponder(seed=0),
            driver_name="deterministic",
            driver_context_tokens=8192,
            worktrees=tmp_path / "wt",
            records=tmp_path / "records",
        )
    )

    def caller(script: list[tuple[str, list[object]]]) -> object:
        return session_topology(
            driver=DeterministicResponder(seed=0),
            driver_name="deterministic",
            driver_context_tokens=8192,
            seed="",
            tools={"review": tool},
            session_id="s_caller",
            workspace_path=str(repo),
            script=script,
        )

    original = hold.TABLE
    hold.TABLE = table
    root = tmp_path / "caller"
    try:
        asyncio.run(
            api.Runtime(root, persistent=True).resume(
                caller([("review", [{"target": "feature", "styles": ["defects", "design"]}])]),
                resume_event=UserMessage(
                    text="review it", turn_index=0, assembled_prompt="", slash_source="chat"
                ),
            )
        )
        for rid in ("r_c-defects", "r_c-design"):
            _wait(table, "s_caller", rid)
        asyncio.run(
            api.Runtime(root, persistent=True).resume(
                caller([]),
                resume_event=UserMessage(
                    text="and?", turn_index=1, assembled_prompt="", slash_source="chat"
                ),
            )
        )
    finally:
        hold.TABLE = original
    events = list(api.read_record(root, resolve_blobs=True))
    starts = {e["payload"]["run_id"] for e in events if e["kind"] == "TopologyRunStarted"}
    ends = {e["payload"]["run_id"]: e["payload"] for e in events if e["kind"] == "TopologyRunEnded"}
    assert starts == set(ends) == {"r_c-defects", "r_c-design"}
    for payload in ends.values():
        assert payload["outcome"] == "done" and payload["report"]["reply"].strip()
    told = [e["payload"]["text"] for e in events if e["kind"] == "PromptComposed"][-1]
    for rid, payload in ends.items():
        assert f"[run {rid} (review) ended done: {payload['report']['reply'].strip()}" in told


def test_a_models_named_call_reaches_review_and_run_as_one_dict(tmp_path: Path) -> None:
    """A model calls tools by name (`run(run_id=..., action=...)`); the loop maps the names to the
    list `Tool.run` takes. Both tools read that list's first item as the whole form."""
    from substrate.topologies.runs.hold import make_run_tool
    from substrate.topologies.tool_loop.tools import _named_to_positional

    seen: list[tuple[str, list[str], str]] = []
    review = make_review_tool(lambda t, s, f: seen.append((t, s, f)) or ["r"])
    run = make_run_tool("s_nobody")
    suite = {"review": review, "run": run}
    review.run(_named_to_positional("review", {"target": "feature", "focus": "x"}, suite))
    assert seen == [("feature", ["defects"], "x")]
    with pytest.raises(
        ValueError, match="no run 'r_none'; this session has no runs"
    ):  # read, then refused
        run.run(_named_to_positional("run", {"run_id": "r_none", "action": "stop"}, suite))

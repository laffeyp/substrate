# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 317: a run's checks (the card's commands in its worktree, the run's events against
the vocabulary) and its report. Written before `topologies/runs/checks.py` existed."""

from __future__ import annotations

import subprocess
from pathlib import Path

from substrate.topologies.runs.card import read_card
from substrate.topologies.runs.checks import check_record, run_checks, write_report
from substrate.topologies.session.vocabulary import CheckKind, RunLimits, RunOutcome
from substrate.topologies.workspace import ensure_repository

LIMITS = RunLimits(max_stops=5, stall_stops=2)


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("a\n")
    ensure_repository(repo)
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    return repo, base


def _ev(seq: int, kind: str) -> dict:
    return {"seq": seq, "kind": kind, "payload": {}}


def test_command_checks_run_in_the_worktree_with_their_expected_exit(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    card = read_card(
        what="w",
        where=["a.txt"],
        commands=["test -f a.txt && echo here", "test -f b.txt"],
        statements=["a.txt says a"],
        limits=LIMITS,
    )
    two = card.checks + [type(card.checks[0])(kind=CheckKind.COMMAND, text="exit 2", expect_exit=2)]
    card = type(card)(**{**{f: getattr(card, f) for f in card.__struct_fields__}, "checks": two})
    events = [
        _ev(0, "substrate.RunStarted"),
        _ev(1, "CardAccepted"),
        _ev(2, "UserMessage"),
        _ev(3, "Returned"),
    ]
    run = run_checks(card, repo, events, after_seq=3, timeout_s=30)
    by_index = {r.index: r for r in run.results}
    assert (
        by_index[0].passed is True and by_index[0].exit == 0 and "here" in by_index[0].output_tail
    )
    assert by_index[1].passed is False and by_index[1].exit == 1
    # read_card puts commands before statements; the appended `exit 2` command is last.
    assert by_index[2].kind is CheckKind.STATEMENT and by_index[2].passed is None
    assert by_index[3].passed is True and by_index[3].exit == 2  # expected 2, got 2
    assert run.record_problems == [] and run.passed is False and run.after_seq == 3


def test_a_command_past_its_time_is_stopped_and_fails(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    card = read_card(what="w", where=["a.txt"], commands=["sleep 30"], statements=[], limits=LIMITS)
    run = run_checks(card, repo, [], after_seq=0, timeout_s=0.5)
    assert run.results[0].passed is False and "timed out" in run.results[0].note


def test_the_record_check_finds_unknown_kinds_and_broken_order() -> None:
    good = [
        _ev(0, "substrate.RunStarted"),
        _ev(1, "CardAccepted"),
        _ev(2, "UserMessage"),
        _ev(3, "ModelReply"),
        _ev(4, "Returned"),
        _ev(5, "ChecksRun"),
    ]
    assert check_record(good) == []
    problems = check_record(
        [
            _ev(0, "UserMessage"),
            _ev(1, "CardAccepted"),
            _ev(2, "Mystery"),
            _ev(3, "ChecksRun"),
            _ev(4, "ReportWritten"),
            _ev(5, "ReportWritten"),
        ]
    )
    assert any("Mystery" in p for p in problems)
    assert any("CardAccepted" in p and "first" in p for p in problems)
    assert any("ChecksRun" in p and "Returned" in p for p in problems)
    assert any("ReportWritten" in p and "once" in p for p in problems)


def test_the_report_names_what_was_asked_done_checked_and_left(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    (repo / "b.txt").write_text("b\n")
    for args in (("add", "-A"), ("commit", "-qm", "add b")):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    card = read_card(
        what="add b.txt", where=["b.txt"], commands=["test -f b.txt"], statements=[], limits=LIMITS
    )
    run = run_checks(card, repo, [], after_seq=0, timeout_s=30)
    report = write_report(
        card, RunOutcome.DONE, run, done="Added b.txt.", worktree=repo, base=base, left=""
    )
    assert report.outcome is RunOutcome.DONE
    assert report.asked == "add b.txt" and report.done == "Added b.txt."
    assert report.files == ["b.txt"]
    assert len(report.commits) == 1
    assert report.branch and report.checks == run.results

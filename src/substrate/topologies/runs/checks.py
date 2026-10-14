# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""A run's checks and its report (kernel sprint 317; session vocabulary § X.3, research r8 § 3.3,
§ 3.4).

The checks are never run by the role that did the work. A card's command checks run in the run's
worktree with the gate's core (`coding_flow.gate.run_command`): the command's exit code against the
card's expected one, its process group stopped on a timeout, its output normalised. Its statement
checks wait for a reviewer (K320). The run's own events are checked against the session vocabulary:
every kind known, and the order of § X.6. The report is written from the card, the last checks and
the worktree's git history.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ...constants import is_reserved
from ..coding_flow.gate import run_command
from ..session import CardAccepted, ChecksRun, ReportWritten
from ..session.vocabulary import (
    CARD_ACCEPTED,
    CHECKS_RUN,
    REPORT_WRITTEN,
    RETURNED,
    SESSION_ENDED,
    SESSION_KINDS,
    USER_MESSAGE,
    CheckKind,
    CheckResult,
    RunOutcome,
)
from ..tool_loop.kinds import FINAL_ANSWER, TOOL_CALL, TOOL_PROGRESS, TOOL_RESULT

# The kinds a session's record may hold besides the kernel's `substrate.*`: the session vocabulary's
# and the tool loop's, which the session borrows.
KNOWN_KINDS = SESSION_KINDS | {TOOL_CALL, TOOL_RESULT, TOOL_PROGRESS, FINAL_ANSWER}
_OUTPUT_TAIL = 2000
_STATEMENT_NOTE = "judged by a reviewer"


def check_record(events: Iterable[Mapping[str, Any]]) -> list[str]:
    """What the record check finds in a run session's events: kinds the vocabulary does not know, and
    breaks in § X.6's order. Empty when the record is as the vocabulary says."""
    problems: list[str] = []
    app = [e for e in events if not is_reserved(str(e.get("kind", "")))]
    for e in app:
        if e.get("kind") not in KNOWN_KINDS:
            problems.append(f"seq {e.get('seq')}: kind {e.get('kind')!r} is not in the vocabulary")
    kinds = [e.get("kind") for e in app]
    if (
        CARD_ACCEPTED in kinds
        and USER_MESSAGE in kinds
        and kinds.index(USER_MESSAGE) < kinds.index(CARD_ACCEPTED)
    ):
        problems.append("CardAccepted does not precede the first UserMessage")
    for i, e in enumerate(app):
        if e.get("kind") == CHECKS_RUN and not any(p.get("kind") == RETURNED for p in app[:i]):
            problems.append(f"seq {e.get('seq')}: ChecksRun with no Returned before it")
    reports = [i for i, e in enumerate(app) if e.get("kind") == REPORT_WRITTEN]
    if len(reports) > 1:
        problems.append(f"ReportWritten appears {len(reports)} times; it appears once")
    if reports and any(e.get("kind") != SESSION_ENDED for e in app[reports[0] + 1 :]):
        problems.append("events after ReportWritten other than SessionEnded")
    return problems


def _command_result(
    index: int, command: str, expect_exit: int, cwd: Path, timeout_s: float
) -> CheckResult:
    verdict = run_command(command, cwd, timeout=timeout_s, label="<worktree>")
    timed_out = verdict.returncode == -1 and "timed out" in verdict.summary
    return CheckResult(
        index=index,
        kind=CheckKind.COMMAND,
        passed=(not timed_out) and verdict.returncode == expect_exit,
        exit=None if timed_out else verdict.returncode,
        output_tail=verdict.summary[-_OUTPUT_TAIL:],
        note=verdict.summary if timed_out else "",
    )


def run_checks(
    card: CardAccepted,
    cwd: Path,
    events: Iterable[Mapping[str, Any]],
    *,
    after_seq: int,
    timeout_s: float,
) -> ChecksRun:
    """The checks after a turn ends: each card check, and the record check of the session's events."""
    results = [
        _command_result(i, c.text, c.expect_exit, cwd, timeout_s)
        if c.kind is CheckKind.COMMAND
        else CheckResult(
            index=i, kind=c.kind, passed=None, exit=None, output_tail="", note=_STATEMENT_NOTE
        )
        for i, c in enumerate(card.checks)
    ]
    problems = check_record(events)
    passed = not problems and all(r.passed for r in results if r.kind is CheckKind.COMMAND)
    head = _git(cwd, "rev-parse", "HEAD") or None
    return ChecksRun(
        after_seq=after_seq, results=results, record_problems=problems, passed=passed, head=head
    )


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True
    ).stdout.strip()


def write_report(
    card: CardAccepted,
    outcome: RunOutcome,
    last: ChecksRun,
    *,
    done: str,
    worktree: Path,
    base: str,
    left: str,
) -> ReportWritten:
    """The run's report: the card's work, what the worker said it did, the files and commits on the
    worktree since `base`, the last checks, and what is left."""
    # A detached worktree (a review's) is on no branch; git names it "HEAD".
    branch = _git(worktree, "rev-parse", "--abbrev-ref", "HEAD") or None
    if branch == "HEAD":
        branch = None
    committed = _git(worktree, "diff", "--name-only", f"{base}..HEAD").splitlines()
    uncommitted = [
        line[3:] for line in _git(worktree, "status", "--porcelain").splitlines() if line
    ]
    files = list(dict.fromkeys([*committed, *uncommitted]))
    commits = _git(worktree, "log", "--format=%h", f"{base}..HEAD").splitlines()
    return ReportWritten(
        outcome=outcome,
        asked=card.what,
        done=done,
        files=files,
        checks=last.results,
        left=left,
        branch=branch,
        commits=commits,
    )


__all__ = ["KNOWN_KINDS", "check_record", "run_checks", "write_report"]

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""A run's checks and its report (kernel sprint 317; session vocabulary § X.3, research r8 § 3.3,
§ 3.4).

The checks are never run by the role that did the work. A card's command checks run in the run's
worktree with the gate's core (`coding_flow.gate.run_command`): the command's exit code against the
card's expected one, its process group stopped on a timeout, its output normalised. Its statement
checks are judged by one model call apart from the worker (K322, § X.3 v0.12.4): `judge_prompt`
gives it the card, the worktree's diff since the run's base and the worker's last reply, and
`read_verdicts` reads its answer per statement. The run's own events are checked against the session vocabulary:
every kind known, and the order of § X.6. The report is written from the card, the last checks and
the worktree's git history.
"""

from __future__ import annotations

import re
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
    JudgeCall,
    RunOutcome,
)
from ..session.vocabulary import MODEL_REPLY
from ..tool_loop.kinds import FINAL_ANSWER, TOOL_CALL, TOOL_PROGRESS, TOOL_RESULT

# The kinds a session's record may hold besides the kernel's `substrate.*`: the session vocabulary's
# and the tool loop's, which the session borrows.
KNOWN_KINDS = SESSION_KINDS | {TOOL_CALL, TOOL_RESULT, TOOL_PROGRESS, FINAL_ANSWER}
_OUTPUT_TAIL = 2000
_STATEMENT_NOTE = "not judged: the run has no checking role"
_DIFF_CAP_CHARS = 40_000
_REPLY_CAP_CHARS = 12_000
# One line per statement: "S2: holds — the reason" or "S2: does not hold — the reason".
_VERDICT = re.compile(
    r"^\W*S(?P<n>\d+)\W+(?P<verdict>does not hold|holds)\b\W*(?P<why>.*)$", re.IGNORECASE
)


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


def statements_of(card: CardAccepted) -> list[tuple[int, str]]:
    """The card's statement checks: (index among its checks, text)."""
    return [(i, c.text) for i, c in enumerate(card.checks) if c.kind is CheckKind.STATEMENT]


def worker_reply(events: Iterable[Mapping[str, Any]], *, after_seq: int) -> str:
    """The worker's last words before the turn end at `after_seq`."""
    said = ""
    for e in events:
        if int(e.get("seq", 0)) > after_seq:
            break
        if e.get("kind") in (FINAL_ANSWER, MODEL_REPLY):
            text = str((e.get("payload") or {}).get("text") or "").strip()
            if text:
                said = text
    return said


def worktree_diff(cwd: Path, base: str) -> str:
    """What changed in the worktree since `base`: committed and not, and the new files' names."""
    diff = _git(cwd, "diff", base) if base else ""
    new = [
        line[3:]
        for line in _git(cwd, "status", "--porcelain").splitlines()
        if line.startswith("??")
    ]
    if new:
        diff += "\n\nNew files not yet added: " + ", ".join(new)
    if len(diff) > _DIFF_CAP_CHARS:
        diff = diff[:_DIFF_CAP_CHARS] + f"\n[diff cut at {_DIFF_CAP_CHARS:,} characters]"
    return diff


def judge_prompt(card: CardAccepted, *, diff: str, reply: str) -> str:
    """The checking role's prompt: the card, the statements to judge, the diff and the reply."""
    lines = [
        "You check another worker's work. You did not do it. Judge each statement below against "
        "the evidence: the change and the worker's last reply. Do not take the worker's word for "
        "anything the change does not show.",
        "",
        f"The card: {card.what}",
        "Where: " + ", ".join(card.where),
        "",
        "Statements:",
        *(f"S{n}: {text}" for n, (_, text) in enumerate(statements_of(card), start=1)),
        "",
        "The change since the work began:",
        "```diff",
        diff or "(no change)",
        "```",
        "",
        "The worker's last reply:",
        reply[:_REPLY_CAP_CHARS] or "(none)",
        "",
        'Answer with one line per statement, exactly "S<n>: holds — <reason>" or '
        '"S<n>: does not hold — <reason>", and nothing else.',
    ]
    return "\n".join(lines)


def read_verdicts(card: CardAccepted, reply: str) -> dict[int, tuple[bool, str]]:
    """Each statement's verdict from the judge's reply, keyed by its index among the card's checks:
    (holds, reason). A statement the reply does not answer does not hold, and says so."""
    found: dict[int, tuple[bool, str]] = {}
    for line in reply.splitlines():
        m = _VERDICT.match(line.strip())
        if m:
            holds = m.group("verdict").lower() == "holds"
            found[int(m.group("n"))] = (holds, m.group("why").strip())
    out: dict[int, tuple[bool, str]] = {}
    for n, (index, _) in enumerate(statements_of(card), start=1):
        out[index] = found.get(n, (False, f"the judge's reply did not answer S{n}"))
    return out


def run_checks(
    card: CardAccepted,
    cwd: Path,
    events: Iterable[Mapping[str, Any]],
    *,
    after_seq: int,
    timeout_s: float,
    verdicts: Mapping[int, tuple[bool, str]] | None = None,
    judge: JudgeCall | None = None,
) -> ChecksRun:
    """The checks after a turn ends: each card check, and the record check of the session's events.
    `verdicts` are the judge's answers for the statement checks (`read_verdicts`); a statement with
    none is not judged, and does not pass."""

    def _statement(i: int) -> CheckResult:
        if verdicts is None or i not in verdicts:
            return CheckResult(
                index=i,
                kind=CheckKind.STATEMENT,
                passed=None,
                exit=None,
                output_tail="",
                note=_STATEMENT_NOTE,
            )
        holds, why = verdicts[i]
        return CheckResult(
            index=i, kind=CheckKind.STATEMENT, passed=holds, exit=None, output_tail="", note=why
        )

    results = [
        _command_result(i, c.text, c.expect_exit, cwd, timeout_s)
        if c.kind is CheckKind.COMMAND
        else _statement(i)
        for i, c in enumerate(card.checks)
    ]
    problems = check_record(events)
    passed = not problems and all(r.passed is True for r in results)
    head = _git(cwd, "rev-parse", "HEAD") or None
    return ChecksRun(
        after_seq=after_seq,
        results=results,
        record_problems=problems,
        passed=passed,
        head=head,
        judge=judge,
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


__all__ = [
    "KNOWN_KINDS",
    "check_record",
    "judge_prompt",
    "read_verdicts",
    "run_checks",
    "statements_of",
    "worker_reply",
    "worktree_diff",
    "write_report",
]

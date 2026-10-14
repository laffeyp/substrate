# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""A run session (kernel sprint 329; session vocabulary § Z.2, research r9 § 3).

The topology that starts it writes its first message. The session works one turn in its worktree.
When the turn ends, the `report` producer writes `ReportWritten` (the session's last words, the
files changed since the run began, its branch and commits, and how it ended) and the session
finalises. Nothing grades the work.
"""

from __future__ import annotations

import subprocess
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ... import api
from ..session import ReportWritten, UserMessage
from ..session.vocabulary import (
    PRODUCER_KIND_REPORT,
    RETURNED,
    RUN_SLASH_SOURCE,
    TRIGGER_ID_REPORT_ON_RETURNED,
    ReturnReason,
    RunOutcome,
    turn_replies,
)

_OUTCOMES = {
    ReturnReason.REPLIED: RunOutcome.DONE,
    ReturnReason.MODEL_ERROR: RunOutcome.FAILED,
    ReturnReason.INTERRUPTED: RunOutcome.STOPPED,
}


@dataclass(frozen=True)
class RunSpec:
    """What a run session needs that its record does not hold at the start: its worktree, the
    commit the work starts from, and its first message."""

    worktree: Path
    base: str
    first_message: str


def first_message(spec: RunSpec) -> UserMessage:
    return UserMessage(
        text=spec.first_message, turn_index=0, assembled_prompt="", slash_source=RUN_SLASH_SOURCE
    )


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True
    ).stdout.strip()


def write_report(
    reason: str, events: list[dict[str, Any]], *, worktree: Path, base: str
) -> ReportWritten:
    """The report: the session's last words, the files and commits on its worktree since `base`,
    its branch (none when detached), and the outcome its turn's end gives."""
    replies = turn_replies(events)
    branch = _git(worktree, "rev-parse", "--abbrev-ref", "HEAD") or None
    committed = _git(worktree, "diff", "--name-only", f"{base}..HEAD").splitlines()
    uncommitted = [
        line[3:] for line in _git(worktree, "status", "--porcelain").splitlines() if line
    ]
    return ReportWritten(
        outcome=_OUTCOMES.get(ReturnReason(reason), RunOutcome.FAILED),
        reply=replies[-1][1] if replies else "",
        files=list(dict.fromkeys([*committed, *uncommitted])),
        branch=None if branch == "HEAD" else branch,  # git names a detached worktree HEAD
        commits=_git(worktree, "log", "--format=%h", f"{base}..HEAD").splitlines(),
    )


def _factory(body: Any) -> Callable[[], Any]:
    """A producer factory for `body`, typed as the session topology's own factories are."""
    return lambda: body


def compose_run(b: api.TopologyBuilder, spec: RunSpec, *, own_record: Callable[[], Path]) -> None:
    """Register the report producer and its trigger on the session topology's builder. The caller
    sets the termination (finalise on `ReportWritten` or `SessionEnded`)."""

    async def _report(inp: Any) -> AsyncIterator[ReportWritten]:
        events = list(api.read_record(own_record(), resolve_blobs=True))
        yield write_report(str(inp["reason"]), events, worktree=spec.worktree, base=spec.base)

    b.producer_kind(
        PRODUCER_KIND_REPORT,
        schemas=[ReportWritten],
        schema_version=1,
        factory=_factory(_report),
        deterministic=False,  # reads git
    )
    b.trigger(
        TRIGGER_ID_REPORT_ON_RETURNED,
        subscription=api.Subscription(kinds=frozenset({RETURNED})),
        predicate=lambda ctx: True,
        starts=PRODUCER_KIND_REPORT,
        input_builder=lambda ctx: {"reason": str((ctx.event.payload or {}).get("reason", ""))},
        policy=api.Once(),
    )


__all__ = ["RunSpec", "compose_run", "first_message", "write_report"]

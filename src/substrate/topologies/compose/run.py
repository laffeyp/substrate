# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Starting a composed run its caller holds (session vocabulary § AA.3, § AA.4; kernel K338).

The run goes through the caller's run table (§ Z): it returns at once, its end reaches the caller
once, the caller can stop it, and ending the caller ends it. When `max_minutes` passes, the run is
stopped as its caller would stop it. An agent step is a build or a review the step starts for the
same caller and waits on; its report is the step's event.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ..runs.build import Card, card_from_form
from ..runs.hold import HeldRun, RunTable
from ..runs.review import DEFAULT_STYLE
from .parts import AgentCall, Deps
from .vocabulary import AgentAs, Plan, StopSource
from .wire import topology


def start_composed(
    table: RunTable,
    *,
    owner: str,
    run_id: str,
    plan: Plan,
    run_input: str,
    deps: Deps,
    records: Path,
) -> HeldRun:
    """Start `plan` for `owner` on `run_input`; its record is `<records>/<run_id>.record`."""
    held = table.start(
        owner,
        run_id,
        plan.name,
        [],
        topology(plan, deps, run_input),
        records / f"{run_id}.record",
        plan=plan,
    )

    def time_up() -> None:
        try:
            table.stop(owner, run_id, StopSource.MAX_MINUTES)
        except KeyError:  # the caller ended and took its runs with it
            pass

    timer = threading.Timer(plan.max_minutes * 60.0, time_up)
    timer.daemon = True
    timer.start()

    def cancel_when_done() -> None:
        held.done.wait()
        timer.cancel()

    threading.Thread(target=cancel_when_done, daemon=True).start()
    return held


StartBuild = Callable[[Card, str], tuple[str, str]]  # (card, model) -> (run id, branch)
StartReview = Callable[[str, list[str], str, str], list[str]]  # (target, styles, focus, model)


def agent_starter(
    table: RunTable,
    owner: str,
    root: Path,
    start_build: StartBuild,
    start_review: StartReview,
) -> Callable[[AgentCall], Mapping[str, Any]]:
    """An agent step's starter: a review of what its input names (its first line a branch, a
    range or files; the rest and the role its focus), or else a build of its input with its role
    as the card's notes. It waits for the run to end and returns the run's report (§ Z.2)."""

    def start(call: AgentCall) -> Mapping[str, Any]:
        if call.as_ is AgentAs.REVIEW:
            lines = call.text.strip().splitlines()
            target = lines[0].strip() if lines else ""
            focus = "\n".join([call.role, *lines[1:]]).strip()
            run_id = start_review(target, [DEFAULT_STYLE], focus, call.model)[0]
        else:
            task = call.text.strip() or call.role
            notes = call.role if call.text.strip() else ""
            run_id, _ = start_build(
                card_from_form({"task": task, "notes": notes}, root), call.model
            )
        ended = table.wait(owner, run_id)
        report = ended.report
        return {
            "run_id": run_id,
            "outcome": ended.outcome,
            "reply": report.reply if report else "",
            "files": list(report.files) if report else [],
            "branch": report.branch if report else None,
            "commits": list(report.commits) if report else [],
        }

    return start


__all__ = ["StartBuild", "StartReview", "agent_starter", "start_composed"]

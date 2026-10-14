# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Build: one card worked in its own worktree until its checks pass or it cannot close (kernel
sprint 321; research r8 § 4.1).

The worker is a driven session (K318) on a new branch `build/<run_id>`, in a worktree made from the
repository's HEAD. The worktree is its only context: it gets the role prompt and the guidance bundle
a session of its model class gets (`default`, or `default-small` for the small class), rooted in the
worktree, and no memory index and no parent context. Its first message is the card. After each turn
the card's checks run in the worktree; failed checks are its next message; the run ends `done` when
they pass and `stuck` at the card's limits. The run is held by the caller (K319): it returns at once,
and its report and branch come back when it ends. The build never merges.

A card bigger than the worker's prompt headroom (the session's 0.6 of its window) is refused, naming
both sizes, so that the caller splits it (r8 § 3.8).
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..session import CardAccepted, session_topology
from ..session.model_class import class_variant
from ..session.transcript import _est_tokens
from ..session.vocabulary import CardForm, RunLimits, RunRole, RunSession
from ..tool_loop.tools import TOOL_NAME_BUILD, Tool, full_suite
from ..workspace import make_worktree
from .card import CardRefused, read_card, read_sdd_card
from .driven import DrivenRun
from .hold import RunTable

BUILD_ROLE = "default"
DEFAULT_LIMITS = RunLimits(max_stops=8, stall_stops=3)
_HEADROOM = 0.6  # the share of the window a session's seed may take (session_topology's check)


def build_branch(run_id: str) -> str:
    return f"build/{run_id}"


def _first_message(card: CardAccepted, branch: str) -> str:
    head = (
        f"Work this card in the current directory, a git worktree on the branch `{branch}`. Read "
        "the files it names first. Commit your work on this branch; the branch is what you hand "
        "back. The checks run after each of your turns; when they fail, their output is your next "
        "message."
    )
    if card.form is CardForm.SDD:
        return f"{head}\n\n{card.text.strip()}"
    lines = [head, "", f"What to do: {card.what}", "Where: " + ", ".join(card.where), "Done when:"]
    return "\n".join(lines + [f"- {c.text}" for c in card.checks])


def start_build(
    table: RunTable,
    *,
    owner: str,
    run_id: str,
    repo: Path,
    card: CardAccepted,
    driver_for: Callable[[Path], Any],
    driver_name: str,
    driver_context_tokens: int,
    model_class: str,
    bundle: str | None,
    worktrees: Path,
    records: Path,
    check_timeout_s: float = 300,
    script: list[tuple[str, list[Any]]] | None = None,
    judge: Any = None,
) -> tuple[str, str]:
    """Start the build and return (its run id, its branch) at once. `driver_for(worktree)` gives the
    worker's model, run in its worktree. `script` is a deterministic worker's tool calls, for tests; `judge` checks
    the card's statements (K322), the worker's own model when None."""
    branch = build_branch(run_id)
    first = _first_message(card, branch)
    budget = int(driver_context_tokens * _HEADROOM)
    if _est_tokens(first) > budget:
        raise ValueError(
            f"build: the card is about {_est_tokens(first):,} tokens and {driver_name} holds "
            f"{budget:,} for it; split the card"
        )
    wt = make_worktree(Path(repo), branch, worktrees / run_id)
    base = subprocess.run(
        ["git", "-C", str(wt), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    session_id = f"s_{run_id}"
    factory = session_topology(
        driver=driver_for(wt),
        driver_name=driver_name,
        driver_context_tokens=driver_context_tokens,
        seed="",
        tools=full_suite(wt, owner=session_id),
        session_id=session_id,
        workspace_path=str(wt),
        bundle=bundle,
        role=class_variant(BUILD_ROLE, model_class),
        role_repo_root=wt,
        model_class=model_class,
        script=script,
        driven=DrivenRun(
            card=card,
            worktree=wt,
            base=base,
            check_timeout_s=check_timeout_s,
            first_message=first,
            judge=judge,
        ),
    )
    root = records / run_id
    session = RunSession(
        session_id=session_id, role=RunRole.WORKER, record_root=str(root), driven=True
    )
    table.start(owner, run_id, BUILD_TOOL_NAME, [session], factory, root)
    return run_id, branch


def card_from_form(form: dict[str, Any], root: Path) -> CardAccepted:
    """The card a `build` call carries: a card file in the SDD kit's form (`card_file`, read from the
    workspace), or the plain fields `what`, `where`, `commands`, `statements`. `max_turns` and
    `stall_turns` set its limits."""
    limits = RunLimits(
        max_stops=int(form.get("max_turns") or DEFAULT_LIMITS.max_stops),
        stall_stops=int(form.get("stall_turns") or DEFAULT_LIMITS.stall_stops),
    )
    card_file = str(form.get("card_file") or "").strip()
    if card_file:
        path = (root / card_file).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError(f"build: the card file {card_file!r} is outside the workspace")
        return read_sdd_card(path.read_text(encoding="utf-8"), limits=limits)
    return read_card(
        what=str(form.get("what") or ""),
        where=[str(w) for w in form.get("where") or []],
        commands=[str(c) for c in form.get("commands") or []],
        statements=[str(s) for s in form.get("statements") or []],
        limits=limits,
    )


BUILD_TOOL_NAME = TOOL_NAME_BUILD
_BUILD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "what": {"type": "string", "description": "the one piece of work"},
        "where": {
            "type": "array",
            "items": {"type": "string"},
            "description": "the files or parts it touches, and what to read first",
        },
        "commands": {
            "type": "array",
            "items": {"type": "string"},
            "description": "commands that pass (exit 0) when it is done",
        },
        "statements": {
            "type": "array",
            "items": {"type": "string"},
            "description": "things that must be true when it is done",
        },
        "card_file": {
            "type": "string",
            "description": "instead of the fields: a card in the SDD kit's form, in the workspace",
        },
        "max_turns": {"type": "integer", "description": f"default {DEFAULT_LIMITS.max_stops}"},
        "stall_turns": {
            "type": "integer",
            "description": "turns in a row with no new commit and the same checks before it stops; "
            f"default {DEFAULT_LIMITS.stall_stops}",
        },
    },
    "x-args-passthrough": True,
}


def make_build_tool(start: Callable[[CardAccepted], tuple[str, str]], root: Path) -> Tool:
    """The `build` tool. `start(card)` starts the build for the calling session (the daemon binds
    the session, its model and its repository) and returns its run id and branch. A card that does
    not say what to do, where, and how to tell it is done comes back as the tool's error."""

    def _run(args: list[Any]) -> dict[str, Any]:
        form = dict(args[0]) if args and isinstance(args[0], dict) else {}
        try:
            card = card_from_form(form, root)
        except CardRefused as exc:
            raise ValueError(f"build: {exc}") from exc
        run_id, branch = start(card)
        return {"run_id": run_id, "branch": branch}

    return Tool(
        name=BUILD_TOOL_NAME,
        describe=(
            "build(what, where, commands?, statements?, card_file?, max_turns?): work one card in "
            "a new branch until its checks pass; returns at once, and the report and branch come "
            "back when it ends"
        ),
        deterministic=False,
        run=_run,
        schema=_BUILD_SCHEMA,
    )


__all__ = [
    "BUILD_ROLE",
    "BUILD_TOOL_NAME",
    "DEFAULT_LIMITS",
    "build_branch",
    "card_from_form",
    "make_build_tool",
    "start_build",
]

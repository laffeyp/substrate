# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Build: one task worked in its own worktree (kernel sprint 332; research r9 § 2, § 8.1).

The input is a sprint card through the `build` tool. Only the task is required; the card's other
fields (the files it touches, the files to read first, notes, or a whole card) are optional, and
the tool's description tells the calling model what good input looks like. Like a stone channel
that directs water: a full card fills every channel, a bare task runs through the main one, and the
build works either way. The tool fills in the repository, the model and the branch.

The worker is a run session (K329) on a new branch `build/<run_id>`, in a worktree of the
repository's HEAD. The worktree is its only context: it gets the role prompt and guidance a session
of its model class gets, and no memory index or parent context. Its first message is the card. It
works to the end of its turn, and its report and branch come back to the caller (K330). The build
never merges.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..session import session_topology
from ..session.model_class import class_variant
from ..session.vocabulary import RunRole, RunSession
from ..tool_loop.tools import TOOL_NAME_BUILD, Tool, full_suite
from ..workspace import make_worktree
from .hold import RunTable
from .run import RunSpec

BUILD_ROLE = "default"
BUILD_TOOL_NAME = TOOL_NAME_BUILD


@dataclass(frozen=True)
class Card:
    """A build's card: the task, and whatever else the caller gave."""

    task: str
    files: list[str] = field(default_factory=list)
    read_first: list[str] = field(default_factory=list)
    notes: str = ""
    text: str = ""  # a whole card in the SDD kit's markdown form, as given


def build_branch(run_id: str) -> str:
    return f"build/{run_id}"


def first_message(card: Card, branch: str) -> str:
    """The card the worker reads, laid out from whatever the caller gave."""
    lines = [
        f"Work this card in the current directory, a git worktree on the branch `{branch}`. "
        "Commit your work on this branch; the branch is what you hand back.",
        "",
        f"Task: {card.task}",
    ]
    if card.files:
        lines.append("Files: " + ", ".join(card.files))
    if card.read_first:
        lines.append("Read first: " + ", ".join(card.read_first))
    if card.notes.strip():
        lines += ["", card.notes.strip()]
    if card.text.strip():
        lines += ["", card.text.strip()]
    return "\n".join(lines)


def start_build(
    table: RunTable,
    *,
    owner: str,
    run_id: str,
    repo: Path,
    card: Card,
    driver_for: Callable[[Path], Any],
    driver_name: str,
    driver_context_tokens: int,
    model_class: str,
    bundle: str | None,
    worktrees: Path,
    records: Path,
    script: list[tuple[str, list[Any]]] | None = None,
) -> tuple[str, str]:
    """Start the build and return (its run id, its branch) at once. `driver_for(worktree)` gives the
    worker's model, run in its worktree. `script` is a deterministic worker's tool calls, for tests."""
    branch = build_branch(run_id)
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
        run=RunSpec(worktree=wt, base=base, first_message=first_message(card, branch)),
    )
    root = records / run_id
    session = RunSession(session_id=session_id, role=RunRole.WORKER, record_root=str(root))
    table.start(owner, run_id, BUILD_TOOL_NAME, [session], factory, root)
    return run_id, branch


def card_from_form(form: dict[str, Any], root: Path) -> Card:
    """The card a `build` call carries. A bare string is the task. `card_file` names a whole card in
    the workspace; its text is added as given."""
    task = str(form.get("task") or "").strip()
    if not task:
        raise ValueError("build: say what to build (task)")
    text = str(form.get("card") or "")
    card_file = str(form.get("card_file") or "").strip()
    if card_file:
        path = (root / card_file).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError(f"build: the card file {card_file!r} is outside the workspace")
        text = path.read_text(encoding="utf-8")
    return Card(
        task=task,
        files=[str(f) for f in form.get("files") or []],
        read_first=[str(f) for f in form.get("read_first") or []],
        notes=str(form.get("notes") or ""),
        text=text,
    )


_BUILD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "task": {
            "type": "string",
            "description": "the one thing to build, in a sentence or two",
        },
        "files": {
            "type": "array",
            "items": {"type": "string"},
            "description": "the files it creates or changes",
        },
        "read_first": {
            "type": "array",
            "items": {"type": "string"},
            "description": "the files the builder should read before it starts",
        },
        "notes": {
            "type": "string",
            "description": "anything else the builder needs: constraints, how you will judge it",
        },
        "card": {
            "type": "string",
            "description": "instead of the fields above, a whole sprint card in markdown",
        },
        "card_file": {
            "type": "string",
            "description": "a sprint card file in the workspace, instead of `card`",
        },
    },
    "required": ["task"],
    "x-args-passthrough": True,
}


def started_next(run_ids: list[str], who: str) -> str:
    """What a caller does after starting runs: wait for their ends, watch them, or stop them."""
    if len(run_ids) == 1:
        rid = run_ids[0]
        return (
            f"the {who}'s report comes to you once, when it finishes; carry on meanwhile. "
            f"run(run_id={rid!r}, action='events') shows its progress; "
            f"run(run_id={rid!r}, action='stop') stops it."
        )
    return (
        f"each {who}'s report comes to you once, when it finishes; carry on meanwhile. "
        f"run(run_id=<one of {', '.join(run_ids)}>, action='events') shows its progress; "
        "action='stop' stops it."
    )


def make_build_tool(start: Callable[[Card], tuple[str, str]], root: Path) -> Tool:
    """The `build` tool. `start(card)` starts the build for the calling session (the daemon binds
    the session, its model and its repository) and returns its run id and branch."""

    def _run(args: list[Any]) -> dict[str, Any]:
        form = (
            dict(args[0])
            if args and isinstance(args[0], dict)
            else {"task": str(args[0]) if args else ""}
        )
        run_id, branch = start(card_from_form(form, root))
        return {"run_id": run_id, "branch": branch, "next": started_next([run_id], "builder")}

    return Tool(
        name=BUILD_TOOL_NAME,
        describe=(
            "build(task, files?, read_first?, notes?, card?, card_file?): hand one task to a "
            "builder that works in its own copy of the repository, on a new branch. Give the task "
            "in a sentence or two; name the files it touches and the files to read first when you "
            "know them, and keep it to what one builder can do in one go (one or two files for a "
            "small model). It returns at once; the builder's report and branch come back to you "
            "when it finishes, and the branch is not merged."
        ),
        deterministic=False,
        run=_run,
        schema=_BUILD_SCHEMA,
    )


__all__ = [
    "BUILD_ROLE",
    "BUILD_TOOL_NAME",
    "Card",
    "build_branch",
    "card_from_form",
    "first_message",
    "make_build_tool",
    "started_next",
    "start_build",
]

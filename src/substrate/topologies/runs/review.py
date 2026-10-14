# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Review: a one-shot run that reviews a target in a style (kernel sprint 331; research r9 § 8.3).

A target is a branch or commit (its changes since it left the repository's HEAD), a range
(`base..head`), or paths in the repository. A style is a text in `review_styles/`, picked from
published review practice (`review_styles/README.md` names the sources): `defects`, `design`,
`security`. Each style is one run session in a worktree detached at the target, with read-only
tools, given the style's text, the caller's focus and the target's diff, for one turn. Its reply is
the review. The runs are held by the caller (K330): they return at once, and each review comes
back to the caller's model when it ends.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any

from ..session import session_topology
from ..session.vocabulary import RunRole, RunSession
from ..tool_loop.tools import TOOL_NAME_REVIEW, Tool, full_suite
from ..workspace import make_detached_worktree
from .build import started_next
from .hold import RunTable
from .run import RunSpec

REVIEW_STYLES: tuple[str, ...] = ("defects", "design", "security")
DEFAULT_STYLE = "defects"
REVIEW_TOOLS: tuple[str, ...] = ("read_file", "list_dir", "glob", "grep")
_DIFF_CAP_CHARS = 60_000


def style_text(style: str) -> str:
    """The text the reviewer is given for `style`. Raises `ValueError` for an unknown style."""
    if style not in REVIEW_STYLES:
        raise ValueError(f"review: style must be one of {list(REVIEW_STYLES)}; got {style!r}")
    return (files("substrate.topologies.runs") / "review_styles" / f"{style}.md").read_text(
        encoding="utf-8"
    )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def resolve_target(repo: Path, target: str) -> tuple[str, list[str], str]:
    """(the commit to check out, the files under review, the diff or "" for paths)."""
    parts = target.split()
    if parts and all((repo / p).exists() for p in parts):
        return "HEAD", parts, ""
    if ".." in target:
        head = target.split("..")[-1].lstrip(".") or "HEAD"
        span = [target]
    else:
        head = target
        span = [f"HEAD...{target}"]
    changed = _git(repo, "diff", "--name-only", *span).split()
    return head, changed, _git(repo, "diff", *span)


def first_message(style: str, target: str, changed: list[str], diff: str, focus: str) -> str:
    lines = [style_text(style).strip(), ""]
    if focus.strip():
        lines += [f"Look at this first: {focus.strip()}", ""]
    if diff:
        shown = (
            diff
            if len(diff) <= _DIFF_CAP_CHARS
            else diff[:_DIFF_CAP_CHARS] + "\n[diff cut at 60,000 characters]"
        )
        lines += [
            f"Review the change {target}. Files changed: {', '.join(changed)}.",
            "",
            "```diff",
            shown,
            "```",
        ]
    else:
        lines += [f"Review these files: {', '.join(changed)}."]
    lines += [
        "",
        "The working tree is checked out at the change; read what you need. Reply with the review.",
    ]
    return "\n".join(lines)


def start_review(
    table: RunTable,
    *,
    owner: str,
    run_id: str,
    repo: Path,
    target: str,
    styles: list[str],
    focus: str,
    driver_for: Callable[[Path], Any],
    driver_name: str,
    driver_context_tokens: int,
    worktrees: Path,
    records: Path,
) -> list[str]:
    """Start one reviewer per style and return their run ids at once (`<run_id>-<style>`).
    `driver_for(worktree)` gives the reviewer's model, run in its worktree."""
    for s in styles:
        style_text(s)  # refuse an unknown style before anything starts
    head, changed, diff = resolve_target(Path(repo), target)
    run_ids: list[str] = []
    for style in styles:
        rid = f"{run_id}-{style}"
        wt = make_detached_worktree(Path(repo), head, worktrees / rid)
        tools = {name: tool for name, tool in full_suite(wt).items() if name in REVIEW_TOOLS}
        factory = session_topology(
            driver=driver_for(wt),
            driver_name=driver_name,
            driver_context_tokens=driver_context_tokens,
            seed="",
            tools=tools,
            session_id=f"s_{rid}",
            workspace_path=str(wt),
            run=RunSpec(
                worktree=wt,
                base=_git(wt, "rev-parse", "HEAD").strip(),
                first_message=first_message(style, target, changed, diff, focus),
            ),
        )
        root = records / rid
        session = RunSession(session_id=f"s_{rid}", role=RunRole.REVIEWER, record_root=str(root))
        table.start(owner, rid, REVIEW_TOOL_NAME, [session], factory, root)
        run_ids.append(rid)
    return run_ids


REVIEW_TOOL_NAME = TOOL_NAME_REVIEW
_REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "what to review: a branch or commit, a range base..head, or file paths",
        },
        "styles": {
            "type": "array",
            "items": {"type": "string", "enum": list(REVIEW_STYLES)},
            "description": (
                "one reviewer per style: defects (bugs, missing tests), design (structure, "
                f"naming, complexity), security (OWASP-style flaws); default {DEFAULT_STYLE}"
            ),
        },
        "focus": {
            "type": "string",
            "description": "what the reviewer should look at first, in a sentence; optional",
        },
    },
    "required": ["target"],
    "x-args-passthrough": True,
}


def make_review_tool(start: Callable[[str, list[str], str], list[str]]) -> Tool:
    """The `review` tool. `start(target, styles, focus)` starts the runs for the calling session
    (the daemon binds the session, its model and its repository) and returns their run ids."""

    def _run(args: list[Any]) -> dict[str, Any]:
        a = (
            dict(args[0])
            if args and isinstance(args[0], dict)
            else {"target": str(args[0])}
            if args
            else {}
        )
        target = str(a.get("target", "")).strip()
        if not target:
            raise ValueError("review: say what to review (target): a branch, a range or files")
        styles = [str(s) for s in (a.get("styles") or [DEFAULT_STYLE])]
        runs = start(target, styles, str(a.get("focus", "")))
        return {"runs": runs, "styles": styles, "next": started_next(runs, "reviewer")}

    return Tool(
        name=REVIEW_TOOL_NAME,
        describe=(
            "review(target, styles?, focus?): have a separate reviewer read a branch, a range or "
            "files and write a review, one reviewer per style (defects, design, security). Name "
            "the target exactly; add a focus sentence when you know where the risk is. It returns "
            "at once; each review comes back to you when it is written."
        ),
        deterministic=False,
        run=_run,
        schema=_REVIEW_SCHEMA,
    )


__all__ = [
    "DEFAULT_STYLE",
    "REVIEW_STYLES",
    "REVIEW_TOOLS",
    "REVIEW_TOOL_NAME",
    "first_message",
    "make_review_tool",
    "resolve_target",
    "start_review",
    "style_text",
]

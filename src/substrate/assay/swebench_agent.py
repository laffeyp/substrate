# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Container-backend coding AGENT — a read/edit/bash loop that solves inside the live instance container.

The executing arm: unlike the host backend's single blind file pick, the agent can read several files, edit,
and run tests/bash to check its work, iterating up to a step budget — all inside the locked-down container
(`ContainerWorkspace`). The patch is `git diff` in-container at the end. Any model drops in via `Responder`.

Action protocol (one action per step, parsed from the model's reply):
    ACTION: read_file   PATH: <path>
    ACTION: edit_file   PATH: <path>  + a SEARCH/REPLACE block
    ACTION: bash        CMD: <shell>
    ACTION: done
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from ..topologies.swebench_solver.firewall import firewall_check
from .swebench_container import ContainerWorkspace
from .swebench_workspace import graded_test_files

_ACTION = re.compile(r"ACTION:\s*(\w+)", re.IGNORECASE)
_PATH = re.compile(r"PATH:\s*(\S+)", re.IGNORECASE)
_CMD = re.compile(r"CMD:\s*(.+)")
_SR = re.compile(r"<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE", re.DOTALL)


_MAX_VIEW = 16000  # chars of the currently-viewed file shown in full (most target files fit)


class _Responder(Protocol):
    def respond(self, prompt: str) -> str: ...


def _prompt(
    issue: str,
    skeleton: str,
    view: tuple[str, str] | None,
    log: list[str],
    *,
    force_edit: bool = False,
) -> str:
    """The agent prompt: the issue, the file list, the FULL content of the file currently being viewed
    (so the model can write an exact SEARCH), and a short action log. The current view is shown in full
    rather than buried/truncated in the log — the bug that made the agent re-read forever (#12 debug).
    `force_edit` (set after repeated reads) demands an edit_file action — open-ended one-action loops let a
    model dither (read, read, read) instead of committing; the host backend works because it's forced."""
    if view is None:
        viewing = "(no file open yet — read_file one first)"
    else:
        viewing = f"# {view[0]}\n```\n{view[1][:_MAX_VIEW]}\n```"
    recent = "\n".join(log[-8:]) if log else "(none yet)"
    demand = (
        "You have read enough. Output an `ACTION: edit_file` for the file you are viewing NOW — a "
        "SEARCH/REPLACE that fixes the issue. Do NOT read_file again.\n\n"
        if force_edit and view is not None
        else "Once you have read the relevant file, EDIT it — do not keep re-reading.\n"
    )
    return (
        "You are fixing a bug in a checked-out repository. Output EXACTLY ONE action per turn, NOTHING else, "
        f"starting with `ACTION:`. {demand}"
        "ACTION: read_file\nPATH: <repo path>\n\n"
        "ACTION: edit_file\nPATH: <repo path>\n<<<<<<< SEARCH\n<exact lines copied from the file above>\n"
        "=======\n<replacement lines>\n>>>>>>> REPLACE\n\n"
        "ACTION: bash\nCMD: <shell, e.g. run a test>\n\nACTION: done\n\n"
        f"## issue\n{issue}\n\n## repository files\n{skeleton}\n\n## file you are viewing\n{viewing}\n\n"
        f"## recent actions\n{recent}\n\nYour next action:"
    )


def _apply_edit(ws: ContainerWorkspace, path: str, search: str, replace: str) -> str:
    """Apply a SEARCH/REPLACE to a file in the container (exact first-occurrence). Returns a status note."""
    content = ws.read_file(path)
    if not content:
        return f"edit_file {path}: file not found or empty"
    if search not in content:
        return f"edit_file {path}: SEARCH text not found (copy the exact current lines)"
    ws.write_file(path, content.replace(search, replace, 1))
    return f"edit_file {path}: applied"


def solve_in_container(
    instance: dict[str, Any], responder: _Responder, *, max_steps: int = 8, verbose: bool = False
) -> str:
    """Run the agent loop in the instance container and return the model_patch (`git diff` in-container,
    graded-test edits dropped). "" if nothing applied. Env-gated (Docker + the eval image + a live model)."""
    ok, reason = firewall_check(instance)  # precondition: firewall-screened (#71 NET 3)
    if not ok:
        raise ValueError(
            f"instance {instance.get('instance_id')} is not firewall-screened: {reason}"
        )
    with ContainerWorkspace(instance["instance_id"]) as ws:
        _, skeleton = ws.exec("git ls-files | head -400")
        issue = str(instance["problem_statement"])
        view: tuple[str, str] | None = None  # (path, full content) of the file currently open
        log: list[str] = []
        reads_since_edit = 0
        for step in range(max_steps):
            reply = responder.respond(
                _prompt(issue, skeleton, view, log, force_edit=reads_since_edit >= 2)
            )
            am = _ACTION.search(reply)
            action = am.group(1).lower() if am else ""
            if verbose:
                print(f"  [step {step}] action={action or '(none)'} | {reply[:90]!r}", flush=True)
            if action == "done":
                break
            if action == "read_file":
                pm = _PATH.search(reply)
                path = pm.group(1) if pm else ""
                content = ws.read_file(path) if path else ""
                view = (path, content)
                reads_since_edit += 1
                log.append(f"read_file {path} ({len(content)} chars)")
            elif action == "edit_file":
                pm, sr = _PATH.search(reply), _SR.search(reply)
                if pm and sr:
                    note = _apply_edit(ws, pm.group(1), sr.group(1), sr.group(2))
                    log.append(note)
                    if "applied" in note:  # refresh the view to the edited file
                        view = (pm.group(1), ws.read_file(pm.group(1)))
                        reads_since_edit = 0
                else:
                    log.append("edit_file: malformed (need PATH + a SEARCH/REPLACE block)")
            elif action == "bash":
                cm = _CMD.search(reply)
                if cm:
                    rc, out = ws.exec(cm.group(1).strip())
                    log.append(f"bash {cm.group(1).strip()} (rc={rc}) -> {out[-600:]}")
                else:
                    log.append("bash: missing CMD")
            else:
                log.append(f"unparseable (no ACTON:); head: {reply[:80]}")
        return ws.diff(drop_files=frozenset(graded_test_files(str(instance.get("test_patch", "")))))


__all__ = ["solve_in_container"]

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Host backend — run a coding step on the host so its edits land in a clone, then `workspace_diff`.

The first, non-executing arm, deliberately minimal: a model picks the file to change from the repo skeleton,
reads it, and emits SEARCH/REPLACE edits; the existing applier writes them into the host clone; the general
`workspace_diff` is the patch; the official harness grades it. Low quality is the honest starting point —
the point is that the HOST BRIDGE (clone → a real model edits → diff → official grader) works end to end.

This is a plain function (not yet a substrate topology) so the first real score is unblocked; wrapping a
coding topology around the same workspace seam (and the container backend for executing agents) is the next
step. The model interface is a `Responder`, so any model/producer drops in.
"""

from __future__ import annotations

import shutil
from typing import Any, Protocol

from ..topologies.swebench_solver.applier import apply_candidate
from ..topologies.swebench_solver.firewall import firewall_check
from .swebench_workspace import graded_test_files, host_clone, workspace_diff


class _Responder(Protocol):
    def respond(self, prompt: str) -> str: ...


def _pick_file(responder: _Responder, issue: str, known: list[str]) -> str | None:
    """Ask the model which ONE repo file most likely needs editing. Keep only a path that is actually in the
    repo (the model can't invent one)."""
    listing = "\n".join(known)
    prompt = (
        "Which ONE file in this repository most likely needs to be edited to fix the issue?\n\n"
        f"## issue\n{issue}\n\n## repository files\n{listing}\n\n"
        "Reply with exactly one file path from the list above, nothing else."
    )
    lines = responder.respond(prompt).strip().splitlines()
    cand = lines[0].strip().strip("`").strip() if lines else ""
    return cand if cand in known else None


def _edit(responder: _Responder, issue: str, path: str, content: str) -> str:
    """Ask the model for SEARCH/REPLACE edits to `path` (it sees the real content, so SEARCH can match)."""
    return responder.respond(
        "Fix the issue by editing the file below. Output ONE OR MORE edit blocks in EXACTLY this format:\n"
        f"# path: {path}\n<<<<<<< SEARCH\n<exact lines to find>\n=======\n<replacement lines>\n>>>>>>> REPLACE\n\n"
        f"## issue\n{issue}\n\n## file: {path}\n```\n{content}\n```\n\nOutput only the edit blocks."
    )


def solve_on_host(instance: dict[str, Any], responder: _Responder) -> str:
    """Produce a `model_patch` for one instance via the host backend: clone at base_commit → the model picks
    a file, reads it, emits edits → apply into the clone → `workspace_diff`. Returns "" if no file is chosen
    or nothing applies (graded not-resolved). The clone is removed afterward."""
    import subprocess

    # precondition: the instance must be firewall-screened (no held-out test reachable in the base repo the
    # model reads). Selection screens it; re-assert here so a standalone call can't silently leak (#71 NET 3).
    ok, reason = firewall_check(instance)
    if not ok:
        raise ValueError(
            f"instance {instance.get('instance_id')} is not firewall-screened: {reason}"
        )

    clone = host_clone(f"https://github.com/{instance['repo']}", instance["base_commit"])
    try:
        known = subprocess.run(
            ["git", "-C", clone, "ls-files"], capture_output=True, text=True
        ).stdout.split()
        issue = str(instance["problem_statement"])
        path = _pick_file(responder, issue, known)
        if path is None:
            return ""
        with open(f"{clone}/{path}", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        edits = _edit(responder, issue, path, content)
        apply_candidate(
            edits, clone
        )  # writes the edits into the clone (or no-ops if SEARCH doesn't match)
        # drop edits to the GRADE's test files (from test_patch — harness-side, never shown to the model):
        # a collision with the held-out test_patch is a false fail; a weakened graded test is a false pass.
        drop = frozenset(graded_test_files(str(instance.get("test_patch", ""))))
        return workspace_diff(clone, drop_files=drop)
    finally:
        shutil.rmtree(clone, ignore_errors=True)


__all__ = ["solve_on_host"]

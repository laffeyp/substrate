# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The session's environment baseline (session vocabulary § P.2, sprint K273).

`session_baseline` reads the facts a model needs about where it runs: the workspace, the git
repository it sits in, the platform, the driver, the date, and the project's own context file.
It reads git, the clock and the file system, so the daemon calls it, not the topology; the
topology records the dict it is given (`RunStarted.baseline`, `SessionStarted.baseline`) and
writes `render_baseline`'s text as the `baseline` fragment on the system channel.

Product spec §7 and tech spec §1.6.5 designed this baseline; it was not built until K273.
"""

from __future__ import annotations

import datetime as _dt
import platform as _platform
import socket
import subprocess
from pathlib import Path
from typing import Any

README_HEAD_BYTES = 8 * 1024
GIT_DIFF_BYTES = 32 * 1024
CONTEXT_FILE_BYTES = 8 * 1024
_GIT_TIMEOUT_S = 5.0


def _git(workspace: Path, *args: str) -> str | None:
    """One git command's stdout, stripped; None when git fails, times out or is missing."""
    try:
        proc = subprocess.run(  # noqa: S603 — fixed git arguments, no shell
            ["git", *args],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _capped(text: str, limit: int) -> str:
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    cut = data[:limit].decode("utf-8", errors="ignore")
    return f"{cut}\n… {len(data) - limit} more bytes not shown"


def _read_capped(path: Path, limit: int) -> str | None:
    try:
        return _capped(path.read_text(encoding="utf-8", errors="replace"), limit)
    except OSError:
        return None


def model_id(driver_name: str, driver_command: tuple[str, ...]) -> str:
    """The model a driver runs: the value after `--model` in a CLI command, else the driver's
    name (an Ollama tag names its model)."""
    if "--model" in driver_command:
        i = driver_command.index("--model")
        if i + 1 < len(driver_command):
            return driver_command[i + 1]
    return driver_name


def session_baseline(
    workspace: Path | str,
    driver_name: str,
    driver_command: tuple[str, ...] = (),
    *,
    today: _dt.date | None = None,
) -> dict[str, Any]:
    """The environment facts for a session opening in `workspace`. A fact that cannot be read is
    left out; reading never raises. `today` is injectable for tests."""
    ws = Path(workspace)
    out: dict[str, Any] = {"workspace": str(ws)}
    root = _git(ws, "rev-parse", "--show-toplevel")
    if root:
        out["repo_root"] = root
        for key, args in (
            ("branch", ("rev-parse", "--abbrev-ref", "HEAD")),
            ("commit", ("rev-parse", "HEAD")),
        ):
            value = _git(ws, *args)
            if value:
                out[key] = value
        readme = _read_capped(Path(root) / "README.md", README_HEAD_BYTES)
        if readme:
            out["readme_head"] = readme
        diff = _git(ws, "diff", "HEAD")
        if diff:
            out["git_diff"] = _capped(diff, GIT_DIFF_BYTES)
    else:
        out["cwd"] = str(ws)
        out["hostname"] = socket.gethostname()
    out["platform"] = f"{_platform.system()} {_platform.release()} ({_platform.machine()})"
    out["driver"] = driver_name
    out["model_id"] = model_id(driver_name, driver_command)
    out["date"] = (today or _dt.date.today()).isoformat()
    context_root = Path(root) if root else ws
    context = _read_capped(context_root / ".substrate" / "context.md", CONTEXT_FILE_BYTES)
    if context:
        out["project_context"] = context
    return out


_LABELS = (
    ("workspace", "Workspace"),
    ("repo_root", "Git repository"),
    ("branch", "Branch"),
    ("commit", "Commit"),
    ("cwd", "Working directory"),
    ("hostname", "Host"),
    ("platform", "Platform"),
    ("driver", "Driver"),
    ("model_id", "Model"),
    ("date", "Today's date"),
)


def render_baseline(baseline: dict[str, Any]) -> str:
    """The text the model reads: one line per fact, then the README head, the diff and the
    project context, each under its own heading."""
    lines = ["# Environment"]
    lines += [f"- {label}: {baseline[key]}" for key, label in _LABELS if baseline.get(key)]
    for key, heading in (
        ("project_context", "Project context (.substrate/context.md)"),
        ("readme_head", "README.md (head)"),
        ("git_diff", "Uncommitted changes (git diff HEAD)"),
    ):
        if baseline.get(key):
            lines += ["", f"## {heading}", str(baseline[key])]
    return "\n".join(lines)


__all__ = ["model_id", "render_baseline", "session_baseline"]

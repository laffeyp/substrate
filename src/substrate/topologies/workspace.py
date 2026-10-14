# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""A session's workspace as a git repository (kernel sprint 315).

Every workspace is a git repository: a session opened on a folder that is not inside one gets
`git init` and a first commit of what it holds, so branches, worktrees and diffs are always there
for the session and for any run it starts (research `RESEARCH-2026-10-13-core-topologies-r8.md`
§ 3.7). A folder already inside a repository is left as it is; nothing is committed on the user's
behalf there, and no repository is nested in another.

A run that asks for its own branch gets a worktree: a checkout on that branch beside the repository,
so its work never touches the user's working tree and shows as a diff. These moved here from
`substrate-ui/server.py` (`_session_worktree`, `_worktree_diff`) so the kernel's registry can make
them.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

# The identity of the first commit when the user has none configured; their own is used otherwise.
_FALLBACK_NAME = "Substrate"
_FALLBACK_EMAIL = "substrate@localhost"
_FIRST_COMMIT_MESSAGE = "Substrate: the workspace as it was when the session opened"

# One lock per workspace path: two sessions opening on one folder at once would both `git init`, and
# the second commit would hit the first's index.lock. Substrate is one app per machine, so a
# process-wide lock covers it.
_LOCKS: dict[Path, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(path, threading.Lock())


def _git(
    path: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, env=env, timeout=600
    )


def is_inside_repository(path: Path) -> bool:
    """Whether `path` is inside a git working tree."""
    result = _git(path, "rev-parse", "--is-inside-work-tree")
    return result.returncode == 0 and result.stdout.strip() == "true"


def _commit_env(path: Path) -> dict[str, str]:
    env = dict(os.environ)
    if not _git(path, "config", "user.email").stdout.strip():
        env.update(
            GIT_AUTHOR_NAME=_FALLBACK_NAME,
            GIT_AUTHOR_EMAIL=_FALLBACK_EMAIL,
            GIT_COMMITTER_NAME=_FALLBACK_NAME,
            GIT_COMMITTER_EMAIL=_FALLBACK_EMAIL,
        )
    return env


def ensure_repository(path: Path) -> bool:
    """Make `path` a git repository with one commit of what it holds, unless it is already inside
    one. Returns whether it made one: False also when git is not installed, so a machine without git
    still opens sessions, on a plain folder. Raises `RuntimeError` naming git's error when git
    fails."""
    path = Path(path).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    if shutil.which("git") is None:
        return False
    with _lock_for(path):
        return _init_with_first_commit(path)


def _init_with_first_commit(path: Path) -> bool:
    if is_inside_repository(path):
        return False
    for args in (("init", "-q"), ("add", "-A")):
        result = _git(path, *args)
        if result.returncode != 0:
            raise RuntimeError(f"git {args[0]} in {path} failed: {result.stderr.strip()}")
    result = _git(
        path, "commit", "-q", "--allow-empty", "-m", _FIRST_COMMIT_MESSAGE, env=_commit_env(path)
    )
    if result.returncode != 0:
        raise RuntimeError(f"git commit in {path} failed: {result.stderr.strip()}")
    return True


def make_worktree(repo: Path, branch: str, dest: Path) -> Path:
    """A worktree of `repo` at `dest` on `branch`, made from the repository's HEAD. Reuses `dest`
    when it exists. Raises `ValueError` when `repo` is not a git repository."""
    repo = Path(repo).expanduser().resolve()
    dest = Path(dest).expanduser().resolve()
    if not repo.is_dir() or not is_inside_repository(repo):
        raise ValueError(f"{repo} is not a git repository")
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = _git(repo, "worktree", "add", "-B", branch, str(dest), "HEAD")
    if result.returncode != 0:
        raise RuntimeError(f"git worktree add {dest} failed: {result.stderr.strip()}")
    return dest


def worktree_diff(wt: Path) -> dict[str, object]:
    """What changed in a worktree: `git diff` including new files, and the changed-file list.
    Read-only: new files are marked intent-to-add in a scratch copy of the index
    (`GIT_INDEX_FILE`), so the worktree's own index is never written (lens audit F301)."""
    wt = Path(wt).expanduser().resolve()
    if not (wt / ".git").exists():
        raise ValueError(f"{wt} is not a git worktree")
    index = _git(wt, "rev-parse", "--git-path", "index").stdout.strip()
    index_path = (wt / index) if index and not Path(index).is_absolute() else Path(index)
    with tempfile.TemporaryDirectory(prefix="substrate-wtdiff-") as tmp:
        scratch = Path(tmp) / "index"
        if index_path.is_file():
            shutil.copyfile(index_path, scratch)
        env = {**os.environ, "GIT_INDEX_FILE": str(scratch)}
        _git(wt, "add", "-A", "--intent-to-add", env=env)
        diff = _git(wt, "diff", env=env).stdout
        names = _git(wt, "diff", "--name-status", env=env).stdout
    return {"diff": diff, "files": names.strip().splitlines()}


def make_detached_worktree(repo: Path, ref: str, dest: Path) -> Path:
    """A worktree of `repo` at `dest`, checked out at `ref` with no branch, so reading it moves no
    branch (a review's view of its target, K331). Reuses `dest` when it exists. Raises
    `ValueError` when `repo` is not a git repository."""
    repo = Path(repo).expanduser().resolve()
    dest = Path(dest).expanduser().resolve()
    if not repo.is_dir() or not is_inside_repository(repo):
        raise ValueError(f"{repo} is not a git repository")
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = _git(repo, "worktree", "add", "--detach", str(dest), ref)
    if result.returncode != 0:
        raise RuntimeError(f"git worktree add {dest} at {ref} failed: {result.stderr.strip()}")
    return dest


__all__ = ["ensure_repository", "is_inside_repository", "make_worktree", "worktree_diff"]

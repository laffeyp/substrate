# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Supervised background commands for the bash tool (UI sprint 103).

The reference is Claude Code's Bash tool (code.claude.com/docs/en/tools-reference, "Background
commands"): `run_in_background` returns a task id at once; output streams to a file; a task is read
and stopped by id; a foreground command that reaches its timeout moves to the background instead of
dying, unless it starts with `sleep`; a subagent's tasks end with the subagent; everything is cleaned
up at exit, including processes that left the task's process group. Research and decisions:
substrate-ui/process/planning/RESEARCH-2026-10-02-background-commands.md.

A task belongs to an *owner*: a session id, or a delegated child's workspace. Only the owner's tools
see it, and `stop_owner` ends all of them. A task's status is read from the process when asked,
never stored at start: Claude Code's own reports #12302, #13091 and #14049 are tasks that kept saying
"running" after they had ended.
"""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

# Claude Code kills a background command whose output passes 5 GB.
OUTPUT_CAP_BYTES = 5 * 1024**3
_MONITOR_INTERVAL_S = 1.0


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _descendants(root_pids: set[int], pgid: int) -> set[int]:
    """Every live process in `pgid`, plus every process whose parent chain reaches one of
    `root_pids` or a member of the group. Catches a child that called setsid() itself (it left the
    group but is still the shell's descendant)."""
    try:
        out = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,pgid="], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return set()
    parent: dict[int, int] = {}
    members: set[int] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        pid, ppid, pg = (int(p) for p in parts)
        parent[pid] = ppid
        if pg == pgid:
            members.add(pid)
    found = set(members)
    seeds = root_pids | members
    for pid in parent:
        cur, hops = pid, 0
        while cur in parent and hops < 64:
            if cur in seeds:
                found.add(pid)
                break
            cur, hops = parent[cur], hops + 1
    return found


class TaskStatus(StrEnum):
    """A background task's state, read from its processes. UI sprint 107: these were bare strings
    compared in eight places across the kernel and retyped in the client; `scripts/gen_kinds.py`
    now generates the client's copy from this class."""

    RUNNING = "running"
    EXITED = "exited"
    STOPPED = "stopped"


@dataclass
class Task:
    task_id: str
    owner: str
    command: str
    pid: int
    pgid: int
    stdout_file: Path
    stderr_file: Path
    started_at: float
    proc: subprocess.Popen[bytes] | None = None  # None for adopted leftovers
    ended_at: float | None = None
    exit_code: int | None = None
    stopped_because: str = ""
    # UI sprint 104: whether the owner's model has been told this task ended. A stop the model
    # asked for (bash_stop) starts out reported.
    reported: bool = False

    def poll(self) -> TaskStatus:
        """The task's state, read from the processes now."""
        if self.stopped_because:
            return TaskStatus.STOPPED
        leader_done = self.proc is None or self.proc.poll() is not None
        if self.proc is not None and self.proc.returncode is not None:
            self.exit_code = self.proc.returncode
        if leader_done and not _group_alive(self.pgid):
            if self.ended_at is None:
                self.ended_at = time.time()
            return TaskStatus.EXITED
        return TaskStatus.RUNNING

    def output_bytes(self) -> int:
        size = 0
        for f in (self.stdout_file, self.stderr_file):
            try:
                size += f.stat().st_size
            except OSError:
                pass
        return size

    def describe(self) -> dict[str, Any]:
        status = self.poll()
        return {
            "task_id": self.task_id,
            "command": self.command,
            "status": status,
            "exit": self.exit_code if status == TaskStatus.EXITED else None,
            "stopped_because": self.stopped_because or None,
            "pid": self.pid,
            "runtime_s": round((self.ended_at or time.time()) - self.started_at, 1),
            "stdout_file": str(self.stdout_file),
            "stderr_file": str(self.stderr_file),
        }


class TaskTable:
    """Every background task this process supervises, by owner."""

    def __init__(self, base: Path | None = None, output_cap_bytes: int = OUTPUT_CAP_BYTES) -> None:
        self._base = base
        self._cap = output_cap_bytes
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        self._monitor: threading.Thread | None = None

    # ── files ───────────────────────────────────────────────────────────────

    def _dir_for(self, owner: str) -> Path:
        if self._base is None:
            from ... import api

            self._base = api.substrate_home() / "bash"
        d = self._base / hashlib.sha1(owner.encode(), usedforsecurity=False).hexdigest()[:16]
        d.mkdir(parents=True, exist_ok=True)
        return d

    def new_files(self, owner: str) -> tuple[str, Path, Path]:
        """A fresh task id and its stdout/stderr paths (created empty)."""
        task_id = "bg_" + uuid.uuid4().hex[:8]
        d = self._dir_for(owner)
        out, err = d / f"{task_id}.out", d / f"{task_id}.err"
        out.touch()
        err.touch()
        return task_id, out, err

    # ── registration ────────────────────────────────────────────────────────

    def add(self, task: Task) -> Task:
        with self._lock:
            self._tasks[task.task_id] = task
        self._ensure_monitor()
        return task

    def get(self, owner: str, task_id: str) -> Task:
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None or task.owner != owner:
            raise KeyError(f"no background task {task_id!r} in this session")
        return task

    def tasks_of(self, owner: str) -> list[Task]:
        with self._lock:
            return [t for t in self._tasks.values() if t.owner == owner]

    # ── stopping ────────────────────────────────────────────────────────────

    def stop(self, task: Task, because: str = "stopped", *, by_model: bool = False) -> None:
        if task.poll() != TaskStatus.RUNNING:
            return
        if by_model:
            task.reported = True
        pids = _descendants({task.pid}, task.pgid)
        try:
            os.killpg(task.pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        if task.proc is not None:
            try:
                task.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        task.stopped_because = because
        task.ended_at = time.time()

    def stop_owner(self, owner: str, because: str = "its owner ended") -> int:
        tasks = [t for t in self.tasks_of(owner) if t.poll() == TaskStatus.RUNNING]
        for t in tasks:
            self.stop(t, because)
        return len(tasks)

    def stop_all(self, because: str = "the daemon shut down") -> int:
        with self._lock:
            tasks = list(self._tasks.values())
        running = [t for t in tasks if t.poll() == TaskStatus.RUNNING]
        for t in running:
            self.stop(t, because)
        return len(running)

    # ── the output cap ──────────────────────────────────────────────────────

    def _ensure_monitor(self) -> None:
        with self._lock:
            if self._monitor is not None and self._monitor.is_alive():
                return
            self._monitor = threading.Thread(target=self._watch, daemon=True)
            self._monitor.start()

    def _watch(self) -> None:
        while True:
            time.sleep(_MONITOR_INTERVAL_S)
            with self._lock:
                tasks = list(self._tasks.values())
            for t in tasks:
                if t.poll() == TaskStatus.RUNNING and t.output_bytes() > self._cap:
                    note = f"\n[bash: stopped after its output passed {self._cap} bytes]\n"
                    try:
                        with t.stderr_file.open("a") as f:
                            f.write(note)
                    except OSError:
                        pass
                    self.stop(t, f"its output passed {self._cap} bytes")

    # ── telling the model (UI sprint 104) ──────────────────────────────────

    def drain_ended(self, owner: str, tail_chars: int = 500) -> list[dict[str, Any]]:
        """Every task of `owner` that ended and has not been reported, each once: its description
        plus the last `tail_chars` characters of stdout and of stderr."""
        out: list[dict[str, Any]] = []
        for t in self.tasks_of(owner):
            if t.reported or t.poll() == TaskStatus.RUNNING:
                continue
            t.reported = True
            info = t.describe()
            info["stdout_tail"] = _tail(t.stdout_file, tail_chars)
            info["stderr_tail"] = _tail(t.stderr_file, tail_chars)
            out.append(info)
        return out


def _tail(path: Path, chars: int) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            f.seek(max(0, size - chars * 4))
            return f.read().decode("utf-8", "replace")[-chars:]
    except OSError:
        return ""


TABLE = TaskTable()


def read_since(path: Path, offset: int, limit: int) -> tuple[str, int]:
    """Text appended to `path` after byte `offset`, at most `limit` bytes, and the next offset."""
    try:
        with path.open("rb") as f:
            f.seek(offset)
            data = f.read(limit)
    except OSError:
        return "", offset
    return data.decode("utf-8", "replace"), offset + len(data)

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""tool_loop's tool suite — the real tools a tool-using agent has available (Wave 14b).

Designed by reading the SOURCE of three reference agents (not blog summaries) — opencode's
`packages/core/src/tool/`, Cline's `sdk/packages/core/src/extensions/tools/definitions.ts` +
`apps/cli/src/runtime/tool-policies.ts`, and aider's `coders/editblock_coder.py` (findings in
docs/tool-loop/tool-loop-tool-suite.md). The tool SHAPE is adopted from all three: a tool is a typed `name` +
schema + an `execute` that returns a STRUCTURED result OR a typed failure the model reads (errors
are observations, never a crash — the loop catches a tool exception OR a non-encodable return
alike); output is CAPPED to protect the context; surgical `edit_file` (search/replace) is the
primary code tool, `write_file` for new files.

WHERE WE DIVERGE — PERMISSIONS. The three references gate mutation behind human approval by default
(Cline auto-runs only a SAFE read/search/fetch set; opencode decorates each tool with a permission
check; aider suggests shell for the human to run). THIS SUITE DOES NOT. By default it runs with NO
permission gate — full autonomy, equivalent to a coding agent in auto-accept mode, or more
permissive. That is deliberate: the substrate's end state is the LLM running these topologies ITSELF
(the self-reflecting / self-running direction in the backlog), so the default is autonomy, not a
human in the loop. Approval-gating is an OPT-IN capability — gate any tool behind `pause_await_input`
(R-2) when an operator wants one — never the default.

The one partition that IS load-bearing is DETERMINISM, not approval: pure tools keep the committed CI
record byte-reproducible; real-I/O tools are `deterministic=False`.

  - PURE       : add, mul                                  (deterministic — the CI demo)
  - READ-ONLY  : read_file, list_dir, grep, web_fetch      (deterministic=False — real I/O)
  - WRITE/EXEC : edit_file, write_file, bash               (deterministic=False — mutates the host, ungated)

A real agent topology passes `FULL_SUITE`; the committed CI demo uses `CALCULATOR` (pure) so the
record stays replayable. NEXT (docs/tool-loop/tool-loop-tool-suite.md): per-tool msgspec input schemas; an
OPT-IN `pause_await_input` gate for operators who want one; a substrate-native `delegate` tool.

SAFETY: `edit_file`/`write_file`/`bash` mutate the host — by design, ungated by default. An operator
runs FULL_SUITE knowing it is autonomous; sandbox the run if that autonomy is unwanted.
"""

from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any, Final, NamedTuple

# Sprint 072 (2026-09-02): tool-name Final[str] constants. Every tool
# registration and every predicate that compares against a tool name
# imports from here. `TOOL_NAMES` frozenset covers the full set.
TOOL_NAME_ADD: Final[str] = "add"
TOOL_NAME_MUL: Final[str] = "mul"
TOOL_NAME_READ_FILE: Final[str] = "read_file"
TOOL_NAME_LIST_DIR: Final[str] = "list_dir"
TOOL_NAME_GLOB: Final[str] = "glob"
TOOL_NAME_GREP: Final[str] = "grep"
TOOL_NAME_WEB_FETCH: Final[str] = "web_fetch"
TOOL_NAME_EDIT_FILE: Final[str] = "edit_file"
TOOL_NAME_WRITE_FILE: Final[str] = "write_file"
TOOL_NAME_BASH: Final[str] = "bash"
TOOL_NAME_BASH_OUTPUT: Final[str] = "bash_output"
TOOL_NAME_BASH_STOP: Final[str] = "bash_stop"
TOOL_NAME_BASH_TASKS: Final[str] = "bash_tasks"
TOOL_NAME_DELEGATE: Final[str] = "delegate"
# Substrate tools (implementations at substrate_tools.py).
TOOL_NAME_INSPECT_RECORD: Final[str] = "inspect_record"
TOOL_NAME_LIST_RECORDS: Final[str] = "list_records"
TOOL_NAME_LIST_SESSIONS: Final[str] = "list_sessions"
TOOL_NAME_LIST_TOPOLOGIES: Final[str] = "list_topologies"
TOOL_NAME_LIST_APPLICATIONS: Final[str] = "list_applications"
TOOL_NAME_RUN_TOPOLOGY: Final[str] = "run_topology"
TOOL_NAME_RUN_TOPOLOGY_POLL: Final[str] = "run_topology_poll"

TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        TOOL_NAME_ADD,
        TOOL_NAME_MUL,
        TOOL_NAME_READ_FILE,
        TOOL_NAME_LIST_DIR,
        TOOL_NAME_GLOB,
        TOOL_NAME_GREP,
        TOOL_NAME_WEB_FETCH,
        TOOL_NAME_EDIT_FILE,
        TOOL_NAME_WRITE_FILE,
        TOOL_NAME_BASH,
        TOOL_NAME_BASH_OUTPUT,
        TOOL_NAME_BASH_STOP,
        TOOL_NAME_BASH_TASKS,
        TOOL_NAME_DELEGATE,
        TOOL_NAME_INSPECT_RECORD,
        TOOL_NAME_LIST_RECORDS,
        TOOL_NAME_LIST_SESSIONS,
        TOOL_NAME_LIST_TOPOLOGIES,
        TOOL_NAME_LIST_APPLICATIONS,
        TOOL_NAME_RUN_TOPOLOGY,
        TOOL_NAME_RUN_TOPOLOGY_POLL,
    }
)


_MAX_READ_LINES = 2000  # read_file window cap — paginated, never a silent mid-content cut
_MAX_GREP_HITS = 100  # grep match cap — reported when hit, never a silent drop
_MAX_GLOB_HITS = (
    200  # glob result cap — a huge match set would blob-offload the ToolResult and wedge the loop
)


import contextvars as _contextvars  # noqa: E402  # kept adjacent to the _BASH_PROGRESS_CTX below

# Phase 8 item 8: the tool_loop's run_tool wrapper sets this before entering
# asyncio.to_thread with the tool body; _bash reads it to emit ToolProgress
# per stdout line. The ctx is a small tuple (call_id, tool_name, step) —
# everything ToolProgress needs beyond the chunk + offset. Absent when a
# tool runs outside a substrate runtime (direct entry.run test call); the
# tool then behaves exactly as before (no progress, full ToolResult).
_BASH_PROGRESS_CTX: _contextvars.ContextVar[tuple[str, str, int] | None] = _contextvars.ContextVar(
    "_BASH_PROGRESS_CTX", default=None
)


def _emit_bash_progress(ctx: tuple[str, str, int], *, chunk: str, offset: int, eof: bool) -> None:
    """Post one ToolProgress envelope through the module-level helper in
    tool_loop/__init__.py (which reads the current Runtime from the
    kernel's _CURRENT_RUNTIME contextvar and enqueues via
    call_soon_threadsafe on the runtime's loop). Keeping the wrapper
    here lets _bash stay ignorant of the substrate helper's import
    path — a future non-bash streaming tool imports the same helper."""
    from . import emit_tool_progress

    call_id, tool, step = ctx
    emit_tool_progress(
        call_id=call_id,
        tool=tool,
        step=step,
        chunk=chunk,
        offset=offset,
        eof=eof,
    )


class Tool(NamedTuple):
    name: str
    describe: str  # one line for the model's prompt — its available tool surface
    deterministic: bool
    run: Callable[[list[Any]], Any]  # run(args) -> a structured result; raise on failure
    # Optional JSON-schema for the tool's parameters. A tool authored OUTSIDE tools.py (the documented
    # extension seam — a caller-composed suite) carries its schema HERE, and the schema helpers below
    # fall back to it when the name is absent from the closed `_TOOL_SCHEMAS` literal. Without this a
    # third tool is invisible to native tool-calling (dropped by ollama_tools, args unmappable) with no
    # error — the sprint-141 delegate bug, fixed at the CLASS level this time (review C-10, Addendum D4).
    schema: dict[str, Any] | None = None


# ── PURE (deterministic — the CI demo) ────────────────────────────────────────
def _add(a: list[Any]) -> int:
    return int(a[0]) + int(a[1])


def _mul(a: list[Any]) -> int:
    return int(a[0]) * int(a[1])


# ── the workspace root ────────────────────────────────────────────────────────
# Every path-taking tool resolves relative paths against a per-conversation WORKSPACE root — the
# directory you start a chat in, the way Claude Code operates inside a repo. This is ERGONOMICS, not
# a jail: an ABSOLUTE path still goes exactly where the model names it (pathlib's `root / "/abs"`
# yields `/abs`), so the autonomy is unchanged — the root just gives relative paths and `bash` a home
# instead of resolving against wherever the server process happened to launch. `full_suite(root)`
# binds the root into each tool; `FULL_SUITE` (root=".") preserves the old cwd-relative behavior.
def _resolve(root: Path, p: Any) -> Path:
    """A path arg resolved against the workspace root; an absolute path overrides it (pathlib rule)."""
    return root / Path(str(p))


def _as_bool(v: Any) -> bool:
    """Coerce a bool tool arg the value-preserving way `int()` coerces add/mul's numbers. A small
    local model routinely STRINGIFIES scalars, and `bool("false")` is True — so a naive `bool(arg)`
    would read "false"/"0"/"no" as True and silently DISABLE edit_file's unique-or-error guard (the
    destructive mis-splice class). Treat the falsey spellings as False."""
    if isinstance(v, str):
        return v.strip().lower() not in ("", "false", "0", "no", "off")
    return bool(v)


# ── READ-ONLY (real I/O — deterministic=False) ────────────────────────────────
def _read_file(root: Path, a: list[Any]) -> str:
    # canonical `read`: line-numbered ("<n>\t<line>") so the model can cite and edit precise lines,
    # with an optional 1-based `offset` line and a `limit` count. No silent byte truncation — when
    # the window doesn't reach EOF, a trailing marker says how to page the rest (old code cut at 8000
    # chars mid-content and said nothing).
    path = _resolve(root, a[0])
    offset = positive_int(a[1] if len(a) > 1 else None, "offset", 1)
    limit = positive_int(a[2] if len(a) > 2 else None, "limit", _MAX_READ_LINES)
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        # an empty read must say so — a bare "" reads as "the read failed" to the model, which then
        # retries or gives up. An explicit marker is unambiguous (Claude Code does the same).
        return "(file is empty)"
    start = max(offset, 1)
    window = lines[start - 1 : start - 1 + max(limit, 0)]
    if not window:
        # an out-of-range offset (past EOF) or limit<=0 yields an EMPTY window — which without this
        # would return a bare "" (the same ambiguity the empty-file marker kills) or a pagination
        # marker pointing back to the same offset (a re-page loop). Say what actually happened.
        return f"(no lines at offset {start}; the file has {len(lines)} line(s))"
    out = [f"{start + i}\t{line}" for i, line in enumerate(window)]
    shown_end = start - 1 + len(window)
    if shown_end < len(lines):
        out.append(
            f"… {len(lines) - shown_end} more line(s); read_file(path, {shown_end + 1}) for the rest"
        )
    return "\n".join(out)


# A tool-call argument list whose only element is {ARG_ERROR_KEY: message} means the model's
# named arguments could not be mapped; the tool runner reports the message as ok=False.
ARG_ERROR_KEY: Final[str] = "__arg_error__"


def positive_int(value: Any, name: str, default: int) -> int:
    """A count argument a model supplied (`limit`, `offset`): absent means `default`; anything
    below 1 is an error the model can read and correct (errors-as-observations). Silently
    honoring `limit: 0` returned an empty result as a success; a real model sent exactly
    that to list_records on 2026-10-01 (UI sprint 097 / real-model tier)."""
    if value is None:
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{name} must be a whole number >= 1 (got {value!r}); omit it for {default}"
        ) from None
    if n < 1:
        raise ValueError(f"{name} must be >= 1 (got {n}); omit it for {default}")
    return n


def _list_dir(root: Path, a: list[Any]) -> list[str]:
    p = _resolve(root, a[0]) if a else root
    return sorted(e.name + ("/" if e.is_dir() else "") for e in p.iterdir())


class ToolCancelled(Exception):
    """The user's interrupt reached a walking tool (glob, grep) between two directories."""


def _walk_files(where: Path) -> Any:
    """Every file under `where`, lazily, in a stable sorted order, stopping when the call is
    cancelled. UI sprint 107: glob sorted the whole match set and grep sorted `rglob("*")` before
    capping, so a model's `glob("**/*", "/")` walked the entire disk; and the walk ran in a worker
    thread the interrupt could not reach. This walks one directory at a time and checks the
    cancel event `run_tool` sets on interrupt (see `on_tool_cancel`). Symlinked dirs are not
    followed (no cycles); unreadable dirs are skipped."""
    import os
    import threading

    stop = threading.Event()
    on_tool_cancel(stop.set)
    if where.is_file():
        yield where
        return
    for dirpath, dirnames, filenames in os.walk(where, followlinks=False):
        if stop.is_set():
            raise ToolCancelled("cancelled")
        dirnames.sort()
        for name in sorted(filenames):
            yield Path(dirpath) / name


def _glob_parts_match(pat: list[str], parts: tuple[str, ...]) -> bool:
    """`pathlib` glob semantics on path segments: `**` spans zero or more directories, every
    other segment is an fnmatch pattern (dotfiles included, as `Path.glob` includes them)."""
    import fnmatch

    if not pat:
        return not parts
    if pat[0] == "**":
        return any(_glob_parts_match(pat[1:], parts[i:]) for i in range(len(parts) + 1))
    return (
        bool(parts)
        and fnmatch.fnmatchcase(parts[0], pat[0])
        and _glob_parts_match(pat[1:], parts[1:])
    )


def _glob(root: Path, a: list[Any]) -> list[str]:
    # canonical `glob`: fast pattern file-find (e.g. "**/*.py"), CAPPED. Uncapped, a match over a big
    # tree ("**/*.py" in a repo) returns 100s of KB, which blob-offloads the whole ToolResult payload
    # and strips the loop-control fields off the frame — wedging the loop. Cap + report instead; the
    # walk stops at the cap (UI sprint 107), so the cost is bounded by the hits, not the tree.
    pattern, where = str(a[0]), (_resolve(root, a[1]) if len(a) > 1 and a[1] is not None else root)
    pat = [seg for seg in pattern.split("/") if seg not in ("", ".")]
    hits: list[str] = []
    for f in _walk_files(where):
        if _glob_parts_match(pat, f.relative_to(where).parts):
            if len(hits) == _MAX_GLOB_HITS:
                return [*hits, f"… (more than {_MAX_GLOB_HITS} files; narrow the pattern or root)"]
            hits.append(str(f))
    return hits


def _grep(root: Path, a: list[Any]) -> list[str]:
    # canonical `grep`: a real REGEX, not a substring test. An invalid pattern is a typed failure the
    # model reads, not a crash. Files walked in sorted order so the hit list is stable across runs.
    pat_s, where = str(a[0]), (_resolve(root, a[1]) if len(a) > 1 and a[1] is not None else root)
    try:
        pat = re.compile(pat_s)
    except re.error as e:
        raise ValueError(f"grep: invalid regex {pat_s!r}: {e}") from e
    hits: list[str] = []
    for f in _walk_files(where):
        try:
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if pat.search(line):
                    hits.append(f"{f}:{n}: {line.strip()[:120]}")
                    if len(hits) >= _MAX_GREP_HITS:
                        hits.append(
                            f"… (capped at {_MAX_GREP_HITS} matches; narrow the pattern or path)"
                        )
                        return hits
        except (UnicodeDecodeError, OSError):
            continue
    return hits


def _web_fetch(a: list[Any]) -> str:  # no path arg — the workspace root doesn't apply
    req = urllib.request.Request(str(a[0]), headers={"User-Agent": "substrate-tool-loop"})
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 — explicit agent tool
        return str(r.read(20000).decode("utf-8", "replace"))


# ── WRITE / EXEC (side effects — deterministic=False) ─────────────────────────
def _edit_file(root: Path, a: list[Any]) -> str:
    # the primary code tool across all three agents: a surgical search/replace, not a full rewrite
    # (aider EditBlock / Cline edit_file). Canonical `str_replace` semantics: replace EXACTLY ONE
    # occurrence — error on 0 OR >1. A first-occurrence replace silently edits the WRONG region when
    # `search` is not unique (the `y = 1` corrupting `y = 1234` class); rejecting is the fix the
    # swebench applier already made (KIT_DIARY #15). A missing/ambiguous search is a typed failure,
    # not a crash and not a silent mis-splice.
    path, search, replace = _resolve(root, a[0]), str(a[1]), str(a[2])
    replace_all = _as_bool(a[3]) if len(a) > 3 and a[3] is not None else False
    text = path.read_text(encoding="utf-8")
    n = text.count(search)
    if n == 0:
        raise ValueError(f"edit_file: search text not found in {path}")
    if n > 1 and not replace_all:
        # default stays UNIQUE-or-error (guards the `y = 1` corrupting `y = 1234` mis-splice class);
        # replace_all is the explicit opt-out for a deliberate rename-everywhere (Claude Code parity).
        raise ValueError(
            f"edit_file: search text is not unique in {path} ({n} occurrences) — add surrounding "
            "context to match one place, or pass replace_all=true to change every occurrence"
        )
    path.write_text(text.replace(search, replace), encoding="utf-8")
    return f"edited {path} ({n} replacement{'s' if n != 1 else ''})"


def _write_file(root: Path, a: list[Any]) -> str:
    path = _resolve(root, a[0])
    path.parent.mkdir(parents=True, exist_ok=True)  # a nested path in a fresh workspace just works
    path.write_text(str(a[1]), encoding="utf-8")
    return f"wrote {len(str(a[1]))} bytes to {path}"


# UI sprint 101: bash's deadline. Claude Code's Bash tool is the reference: each call takes an
# optional timeout, 2 minutes by default and 10 at most, measured over the whole command. Before
# this, the 60 s limit applied only after stdout closed, so a background process holding the pipe
# (`server &`) blocked the tool, and with it the whole turn, until something outside killed it.
BASH_DEFAULT_TIMEOUT_S: Final[float] = 120.0
BASH_MAX_TIMEOUT_S: Final[float] = 600.0

# What stops the current tool call's work. run_tool (tool_loop/__init__.py) sets a fresh list per
# call and, when the call is cancelled (the user's interrupt, a shutdown), runs every hook in it:
# cancelling the task that awaits `asyncio.to_thread` does not stop the thread, the processes it
# started, or the child runs it is waiting on (UI sprints 101-102). bash registers a process-group
# kill; delegate registers a stop for each child it starts.
_TOOL_CANCEL_HOOKS: _contextvars.ContextVar[list[Callable[[], None]] | None] = (
    _contextvars.ContextVar("_TOOL_CANCEL_HOOKS", default=None)
)


def on_tool_cancel(hook: Callable[[], None]) -> None:
    """Register `hook` to run if the current tool call is cancelled. No-op outside run_tool."""
    hooks = _TOOL_CANCEL_HOOKS.get()
    if hooks is not None:
        hooks.append(hook)


def kill_process_group(proc: subprocess.Popen[Any]) -> None:
    """SIGKILL the process group `proc` leads (the shell and everything it started)."""
    import os
    import signal

    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _bash(root: Path, owner: str, a: list[Any]) -> dict[str, Any]:
    """Bash tool: `bash(cmd, timeout_s?, run_in_background?)` (UI sprints 101, 103).

    The command runs in its own process group with stdout and stderr written to files (never
    pipes, which a backgrounded child can hold open). The behaviour follows Claude Code's Bash
    tool (code.claude.com/docs/en/tools-reference, "Background commands"):

    - `run_in_background=true`: returns `{task_id, status, stdout_file, stderr_file, pid}` at
      once; read it with `bash_output`, stop it with `bash_stop`.
    - foreground: returns `{exit, stdout, stderr}` when the shell exits, posting each stdout line as
      ToolProgress while it runs. `timeout_s` (default 120, max 600) bounds the wait. At the
      deadline a command moves to the background (`moved_to_background: true` and a `task_id`),
      unless it starts with `sleep`, which is killed (`timed_out: true`).
    - a shell that exits while processes it started are still alive (`server &`): those processes
      become a background task named in `background_task_id`, so they can be read, stopped, and are
      stopped with the session.
    """
    import time

    from .background import TABLE, Task, TaskStatus, read_since

    command = str(a[0])
    timeout_s = BASH_DEFAULT_TIMEOUT_S
    if len(a) > 1 and a[1] is not None:
        timeout_s = float(a[1])
        if not 0 < timeout_s <= BASH_MAX_TIMEOUT_S:
            raise ValueError(
                f"bash: timeout_s must be in (0, {BASH_MAX_TIMEOUT_S:g}], got {a[1]!r}"
            )
    background = len(a) > 2 and a[2] is not None and _as_bool(a[2])
    task_id, out_path, err_path = TABLE.new_files(owner)
    with out_path.open("wb") as out_f, err_path.open("wb") as err_f:
        proc = subprocess.Popen(  # noqa: S602 — explicit agent shell tool (opt-in, not CI)
            command,
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=out_f,
            stderr=err_f,
            cwd=str(root),
            start_new_session=True,  # own process group: a kill reaches backgrounded children
        )
    task = Task(
        task_id=task_id,
        owner=owner,
        command=command,
        pid=proc.pid,
        pgid=proc.pid,
        stdout_file=out_path,
        stderr_file=err_path,
        started_at=time.time(),
        proc=proc,
    )
    if background:
        TABLE.add(task)
        return {
            "task_id": task_id,
            "status": TaskStatus.RUNNING,
            "pid": proc.pid,
            "stdout_file": str(out_path),
            "stderr_file": str(err_path),
        }

    in_foreground = {"yes": True}

    def _cancel() -> None:  # the user's interrupt: stop a command still in the foreground
        if in_foreground["yes"]:
            kill_process_group(proc)

    on_tool_cancel(_cancel)
    ctx = _BASH_PROGRESS_CTX.get()
    offset = 0  # bytes read from the stdout file so far
    emitted = 0  # characters already posted as ToolProgress: the next chunk's offset
    pending = ""
    deadline = time.monotonic() + timeout_s

    def _pump() -> None:
        nonlocal offset, emitted, pending, ctx
        chunk, offset = read_since(out_path, offset, 1 << 20)
        if not chunk or ctx is None:
            return
        pending += chunk
        *lines, pending = pending.split("\n")
        for line in lines:
            try:
                _emit_bash_progress(ctx, chunk=line + "\n", offset=emitted, eof=False)
            except Exception:  # noqa: BLE001 — progress is advisory; a broken emitter must NOT sink the tool
                ctx = None
                return
            emitted += len(line) + 1

    while proc.poll() is None and time.monotonic() < deadline:
        _pump()
        time.sleep(0.05)
    _pump()
    shell_done = proc.poll() is not None
    if not shell_done and command.lstrip().startswith("sleep"):
        # Claude Code's exception: a timed-out `sleep` is stopped, not backgrounded.
        kill_process_group(proc)
        proc.wait(timeout=5)
        shell_done = True
        timed_out = True
    else:
        timed_out = False
    in_foreground["yes"] = False
    if ctx is not None and (shell_done or timed_out):
        try:
            _emit_bash_progress(ctx, chunk=pending, offset=emitted, eof=True)
        except Exception:  # noqa: BLE001 — see above
            pass
    stdout_text, _ = read_since(out_path, 0, 8000)
    stderr_full = err_path.read_text(encoding="utf-8", errors="replace")
    result: dict[str, Any] = {"exit": proc.returncode, "stdout": stdout_text}
    if timed_out:
        result["timed_out"] = True
        stderr_full += (
            f"\n[bash: killed after {timeout_s:g} s, with every process it started; pass a larger "
            f"timeout_s (max {BASH_MAX_TIMEOUT_S:g}) or run_in_background=true]"
        )
    elif not shell_done:
        TABLE.add(task)
        result.update({"exit": None, "moved_to_background": True, "task_id": task_id})
        stderr_full += (
            f"\n[bash: still running after {timeout_s:g} s; moved to the background as {task_id}. "
            "Read it with bash_output, stop it with bash_stop]"
        )
    elif task.poll() == TaskStatus.RUNNING:
        TABLE.add(task)
        result["background_task_id"] = task_id
        stderr_full += (
            f"\n[bash: the shell exited but processes it started are still running, now background "
            f"task {task_id}. Read them with bash_output, stop them with bash_stop]"
        )
    result["stderr"] = stderr_full[-2000:]
    return result


def _offset_arg(a: list[Any], i: int, name: str) -> int:
    if len(a) <= i or a[i] is None:
        return 0
    value = int(a[i])
    if value < 0:
        raise ValueError(f"bash_output: {name} must be >= 0, got {a[i]!r}")
    return value


def _bash_output(owner: str, a: list[Any]) -> dict[str, Any]:
    """`bash_output(task_id, offset=0, err_offset=0)`: a background task's status and its output
    after the given byte offsets (8 KB each at most); pass back `next_offset` to read on."""
    from .background import TABLE, read_since

    task = TABLE.get(owner, str(a[0]))
    offset = _offset_arg(a, 1, "offset")
    err_offset = _offset_arg(a, 2, "err_offset")
    out, next_offset = read_since(task.stdout_file, offset, 8000)
    err, next_err = read_since(task.stderr_file, err_offset, 8000)
    info = task.describe()
    return {
        "task_id": task.task_id,
        "status": info["status"],
        "exit": info["exit"],
        "stopped_because": info["stopped_because"],
        "runtime_s": info["runtime_s"],
        "stdout": out,
        "stderr": err,
        "next_offset": next_offset,
        "next_err_offset": next_err,
    }


def _bash_stop(owner: str, a: list[Any]) -> dict[str, Any]:
    """`bash_stop(task_id)`: kill the task's process group and everything it started."""
    from .background import TABLE

    task = TABLE.get(owner, str(a[0]))
    TABLE.stop(task, "stopped with bash_stop", by_model=True)
    return task.describe()


def _bash_tasks(owner: str, a: list[Any]) -> list[dict[str, Any]]:
    """`bash_tasks()`: this session's background tasks, running and ended."""
    from .background import TABLE

    del a
    return [t.describe() for t in TABLE.tasks_of(owner)]


CALCULATOR: dict[str, Tool] = {
    "add": Tool(TOOL_NAME_ADD, "add(a, b) -> a+b", True, _add),
    "mul": Tool(TOOL_NAME_MUL, "mul(a, b) -> a*b", True, _mul),
}


def full_suite(root: Path | str = ".", *, owner: str | None = None) -> dict[str, Tool]:
    """The full tool suite rooted at a WORKSPACE directory (default: the process cwd, the old behavior).
    Relative paths and `bash` resolve against `root`; absolute paths still go where named. Pass the
    per-conversation workspace here so the agent operates inside it, the way Claude Code works in a repo.

    `owner` names who the bash tool's background tasks belong to (UI sprint 103): the daemon passes
    the session id, so the session's tools see only its tasks and ending the session stops them.
    Default: the workspace path."""
    r = Path(root)
    who = owner if owner is not None else str(r.resolve())
    return {
        **CALCULATOR,
        "read_file": Tool(
            TOOL_NAME_READ_FILE,
            "read_file(path, offset=1, limit) -> line-numbered text ('<n>\\t<line>'); offset is a 1-based line. Output is capped at ~12 KB inline; if the file is larger, the tail is a marker '… <N> more line(s); read_file(path, <next>) for the rest' — call it with that <next> offset to page.",
            False,
            partial(_read_file, r),
        ),
        "list_dir": Tool(
            TOOL_NAME_LIST_DIR, "list_dir(path) -> directory entries", False, partial(_list_dir, r)
        ),
        "glob": Tool(
            TOOL_NAME_GLOB,
            "glob(pattern, root='.') -> file paths matching a glob like '**/*.py' (sorted)",
            False,
            partial(_glob, r),
        ),
        "grep": Tool(
            TOOL_NAME_GREP,
            "grep(regex, path='.') -> matching 'file:line: text' (a real regex, not a substring)",
            False,
            partial(_grep, r),
        ),
        "web_fetch": Tool(
            TOOL_NAME_WEB_FETCH, "web_fetch(url) -> the page text", False, _web_fetch
        ),
        "edit_file": Tool(
            TOOL_NAME_EDIT_FILE,
            "edit_file(path, search, replace, replace_all=false) -> surgical search/replace; `search` "
            "must match the file's exact bytes EXACTLY ONE place or it errors (add context to "
            "disambiguate, or pass replace_all=true to change every occurrence, e.g. a rename). Match "
            "file content only — do NOT include read_file's leading '<n>\\t' line-number prefix; keep "
            "`search` minimal (1-3 lines, just enough to be unique) (SIDE EFFECT)",
            False,
            partial(_edit_file, r),
        ),
        "write_file": Tool(
            TOOL_NAME_WRITE_FILE,
            "write_file(path, text) -> create/overwrite a file (SIDE EFFECT)",
            False,
            partial(_write_file, r),
        ),
        "bash": Tool(
            TOOL_NAME_BASH,
            "bash(cmd, timeout_s?=120 max 600, run_in_background?=false) -> {exit, stdout, stderr}; "
            "a command still running at timeout_s moves to the background (task_id); "
            "run_in_background=true returns a task_id at once — use it for servers, watchers and "
            "long builds (SIDE EFFECT)",
            False,
            partial(_bash, r, who),
        ),
        "bash_output": Tool(
            TOOL_NAME_BASH_OUTPUT,
            "bash_output(task_id, offset?=0, err_offset?=0) -> a background task's status (running | "
            "exited | stopped), exit code, and output after those byte offsets; pass back next_offset",
            False,
            partial(_bash_output, who),
        ),
        "bash_stop": Tool(
            TOOL_NAME_BASH_STOP,
            "bash_stop(task_id) -> stop a background task and every process it started (SIDE EFFECT)",
            False,
            partial(_bash_stop, who),
        ),
        "bash_tasks": Tool(
            TOOL_NAME_BASH_TASKS,
            "bash_tasks() -> this session's background tasks: command, status, runtime",
            False,
            partial(_bash_tasks, who),
        ),
    }


# the default rooted at the process cwd — preserves the pre-workspace behavior for existing call sites.
FULL_SUITE: dict[str, Tool] = full_suite(".")


def suite_describe(suite: dict[str, Tool]) -> str:
    """One line per tool — the available-tool surface to hand a model in its prompt."""
    return "\n".join(f"  {t.describe}" for t in suite.values())


# ── native tool-calling: per-tool JSON schemas + a robust dual-path parser ────────────────────────
# Per-tool input schemas (canonical function-tool `parameters`). PROPERTY ORDER IS THE ARG ORDER: a
# model tool-call arrives as a NAMED dict, and `_named_to_positional` maps it back to the positional
# `run(args)` list in this order. Required params are always the leading, contiguous ones.
_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "add": {
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["a", "b"],
    },
    "mul": {
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["a", "b"],
    },
    "read_file": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer", "minimum": 1},
            "limit": {"type": "integer", "minimum": 1},
        },
        "required": ["path"],
    },
    "list_dir": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    "glob": {
        "type": "object",
        "properties": {"pattern": {"type": "string"}, "root": {"type": "string"}},
        "required": ["pattern"],
    },
    "grep": {
        "type": "object",
        "properties": {"regex": {"type": "string"}, "path": {"type": "string"}},
        "required": ["regex"],
    },
    "web_fetch": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    "edit_file": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "search": {"type": "string"},
            "replace": {"type": "string"},
            "replace_all": {"type": "boolean"},
        },
        "required": ["path", "search", "replace"],
    },
    "write_file": {
        "type": "object",
        "properties": {"path": {"type": "string"}, "text": {"type": "string"}},
        "required": ["path", "text"],
    },
    # UI sprint 103: timeout_s (sprint 101) was missing here, so a native tool call could not pass it.
    "bash": {
        "type": "object",
        "properties": {
            "cmd": {"type": "string"},
            "timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": 600},
            "run_in_background": {"type": "boolean"},
        },
        "required": ["cmd"],
    },
    "bash_output": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "offset": {"type": "integer", "minimum": 0},
            "err_offset": {"type": "integer", "minimum": 0},
        },
        "required": ["task_id"],
    },
    "bash_stop": {
        "type": "object",
        "properties": {"task_id": {"type": "string"}},
        "required": ["task_id"],
    },
    "bash_tasks": {"type": "object", "properties": {}},
    # tools authored OUTSIDE this module (e.g. delegate — make_delegate) do NOT register here; they carry
    # their schema on the Tool itself and the helpers above fall back to it (review C-10). This literal is
    # only the built-in suite; it deliberately does not know about caller-composed tools.
}


def _schema_for(name: str, suite: dict[str, Tool] | None = None) -> dict[str, Any] | None:
    """The parameter schema for a tool: the closed `_TOOL_SCHEMAS` literal first, else the tool's own
    `schema` field (a tool authored outside tools.py — review C-10). None if neither has one."""
    if name in _TOOL_SCHEMAS:
        return _TOOL_SCHEMAS[name]
    if suite is not None and name in suite:
        return suite[name].schema
    return None


def ollama_tools(suite: dict[str, Tool]) -> list[dict[str, Any]]:
    """The suite as Ollama `/api/chat` function tools — name + one-line description + JSON schema. A tool
    with no schema (neither in `_TOOL_SCHEMAS` nor on the Tool) is skipped — it cannot be presented for
    native tool-calling — rather than silently dropped with no trace."""
    out: list[dict[str, Any]] = []
    for t in suite.values():
        params = _schema_for(t.name, suite)
        if params is None:
            continue
        out.append(
            {
                "type": "function",
                "function": {"name": t.name, "description": t.describe, "parameters": params},
            }
        )
    return out


def _loads_obj(s: Any) -> Any:
    """Parse the FIRST balanced JSON object out of a string; None if there isn't one. Scans from the
    first `{` to its matching `}` (brace depth, respecting string literals + escapes) rather than
    grabbing first-`{`-to-last-`}`. That old greedy span broke on a real qwen behavior the arena
    surfaced: a model that BATCHES several tool calls into one message emits `{..}\\n{..}\\n{..}`, whose
    outer span is invalid JSON -> the call degraded to a no-op FinalAnswer and zero tools ran. Taking
    the first balanced object turns that into the first tool call; the loop runs it and the model
    continues sequentially (KIT_DIARY #28 — parse REAL model output, not the canned single-object shape)."""
    if not isinstance(s, str):
        return None
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start : i + 1])
                except (ValueError, TypeError):
                    return None
    return None


def required_params(name: str, suite: dict[str, Tool] | None = None) -> list[str]:
    """The tool's required parameter names (schema order) — used to turn a model's under-specified
    call (too few args) into a CLEAR typed error the model can act on, instead of a raw IndexError
    from the tool body. Surfaced by a live llama3.2:1b run that re-called write_file with no args.
    Falls back to a caller-composed tool's own schema (review C-10).

    Sprint 052 fix: a schema carrying `x-args-passthrough: true` produces a positional args list
    of exactly ONE element (the whole named-args dict) via `_named_to_positional`. Its `required`
    field is per-JSON-schema-property, not per-positional-arg — walking it directly here would
    check the length-1 args list against a length-N required list and fail the model's call every
    time (surfaced live: run_topology + run_topology_poll both required ≥1 named field, so the
    check tripped even when the call was well-formed). For passthrough schemas, required = 1
    (the passthrough dict); the impl validates the DICT keys itself."""
    schema = _schema_for(name, suite) or {}
    if schema.get("x-args-passthrough"):
        return ["<args>"] if schema.get("required") else []
    return list(schema.get("required", []))


def _named_to_positional(
    name: str, args: dict[str, Any], suite: dict[str, Tool] | None = None
) -> list[Any]:
    """Map a model's NAMED tool args back to the positional list `Tool.run` expects, in schema order.
    Stops at the first missing param so a later arg can never mis-align onto an earlier slot (required
    params are contiguous leading ones, so a trailing optional the model omitted just isn't passed).
    Falls back to a caller-composed tool's own schema (review C-10).

    A tool whose schema carries `"x-args-passthrough": true` bypasses the iteration and receives
    the full named-args dict as a single positional element: `[args]`. This is the delegate seam
    (sprint 212): delegate's five optional kwargs (`model`, `child_session_name`, `context`,
    `baseline`, `timeout_seconds`) don't survive the "stop at first missing" contract — a model
    that skipped `model` but sent `timeout_seconds` would lose the trailing arg. The passthrough
    marker keeps every arg the model set."""
    schema = _schema_for(name, suite) or {}
    if schema.get("x-args-passthrough"):
        return [dict(args)]
    props = list(schema.get("properties", {}))
    # UI sprint 097: arguments the mapping cannot place are reported, not dropped. A real model
    # called grep(pattern=...) because a prompt described `pattern`; the schema names `regex`,
    # the old loop dropped the unknown key, and the tool saw [] three times in a row.
    unknown = sorted(k for k in args if k not in props)
    if props and unknown:
        return [
            {ARG_ERROR_KEY: f"{name}: unknown argument(s) {unknown}; it takes {', '.join(props)}"}
        ]
    # A later argument given without an earlier optional one keeps its place: the gap is None,
    # which every tool reads as "use the default" (the old loop stopped at the gap and silently
    # dropped e.g. read_file's `limit` when `offset` was omitted).
    last = max((i for i, p in enumerate(props) if p in args), default=-1)
    return [args.get(p) for p in props[: last + 1]]


def parse_tool_call(message: dict[str, Any], suite: dict[str, Tool]) -> tuple[str, Any]:
    """Turn one Ollama chat message into the loop's next action, ROBUST across models (verified
    against real output: llama3.2 returns native `tool_calls`; qwen2.5-coder puts the same call as a
    JSON object in `content`). Native `tool_calls` first, then a JSON-in-content fallback; anything
    else is a final answer. Returns ("tool", (name, positional_args)) or ("answer", text)."""
    for call in message.get("tool_calls") or []:
        fn = call.get("function", {})
        name = str(fn.get("name", ""))
        raw = fn.get("arguments", {})
        args = raw if isinstance(raw, dict) else _loads_obj(raw)
        if name in suite and isinstance(args, dict):
            return "tool", (name, _named_to_positional(name, args, suite))
    content = str(message.get("content", "")).strip()
    obj = _loads_obj(content)
    if (
        isinstance(obj, dict)
        and str(obj.get("name", "")) in suite
        and isinstance(obj.get("arguments"), dict)
    ):
        return "tool", (
            str(obj["name"]),
            _named_to_positional(str(obj["name"]), obj["arguments"], suite),
        )
    return "answer", content

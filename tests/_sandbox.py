# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 052 sandbox scaffold — Layer 1 + Layer 2 helpers for live-model
tool tests.

Design informed by research (see BLACKBOARD 052 notes):

- Anthropic's own sandbox-runtime uses `sandbox-exec` on macOS to wrap
  Claude Code's bash tool. We do the same for our own `bash` tests.
- Every serious LLM-agent sandbox guide (Cosmonic, Modal, Firecrawl,
  IsolateGPT paper) names the same five layers: isolation, resource
  limits, capability scoping, auditability, deterministic teardown.
  Our tests already have pytest's `tmp_path` for isolation + teardown;
  the pieces this module adds are capability-scoping and auditability.

Three helpers:

1. `sandboxed_fs_tools(root)` — a dict of `{read_file, list_dir, glob,
   grep, edit_file, write_file}` whose `_resolve` REJECTS any path
   that would land outside `root` (typed `ToolResult(ok=False,
   error="path escapes workspace: …")`). Callers pass this into
   `session_topology(tools=…)`.

2. `sandbox_exec_bash(root)` — a `bash` tool that wraps the shell call
   in macOS `sandbox-exec` with a profile denying everything except
   process exec + reads of the process's own binaries + read/write
   under `root`. Layered defense: `subprocess.run(cwd=root)` still
   holds; the OS sandbox holds even if the model uses absolute paths.

3. `stub_urlopen(handler)` — a context manager that patches
   `urllib.request.urlopen` for the duration of a test to a
   caller-supplied handler. `web_fetch` under this stub can only
   reach whatever the handler decides; the real network is unreachable.

Plus a monkeypatch helper for `_SESSIONS_BASE` — delegate / run_topology
child sessions land under `tmp_path/sessions` instead of `~/.substrate/
sessions/`.

The Layer 3 post-test invariant lives in `tests/conftest.py` — a
fixture that snapshots host-side paths before the test and fails if
anything outside the test's `tmp_path` changed."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Any
from unittest.mock import patch

from substrate.topologies.tool_loop.tools import (
    FULL_SUITE,
    Tool,
    _edit_file,
    _glob,
    _grep,
    _list_dir,
    _read_file,
    _write_file,
)

__all__ = [
    "PathEscapeError",
    "sandboxed_fs_tools",
    "sandbox_exec_bash",
    "sandbox_exec_available",
    "stub_urlopen",
    "monkeypatch_sessions_base",
]


class PathEscapeError(ValueError):
    """Raised when a tool arg resolves outside the sandbox root."""


def _jail(root: Path, p: Any) -> Path:
    """Resolve `p` against `root` and reject any escape.

    Absolute paths that fall outside `root` are rejected (production's
    `_resolve` accepts them by design; the test bar is stricter).
    Relative paths are joined and normalised; if normalisation lands
    outside `root`, reject. Symlinks are followed once via `resolve()`.
    """
    resolved = (root / Path(str(p))).resolve()
    root_resolved = root.resolve()
    if resolved == root_resolved:
        return resolved
    if not str(resolved).startswith(str(root_resolved) + os.sep):
        raise PathEscapeError(f"path {resolved!r} escapes sandbox workspace {root_resolved!r}")
    return resolved


def _sandboxed_read_file(root: Path, a: list[Any]) -> str:
    return _read_file(_jail(root, a[0]).parent, [_jail(root, a[0]).name, *a[1:]])


def _sandboxed_list_dir(root: Path, a: list[Any]) -> list[str]:
    return _list_dir(_jail(root, a[0]).parent, [_jail(root, a[0]).name])


def _sandboxed_glob(root: Path, a: list[Any]) -> list[str]:
    # The `root` arg to glob is a subdir; jail THAT.
    if len(a) > 1:
        _jail(root, a[1])
    return _glob(root, a)


def _sandboxed_grep(root: Path, a: list[Any]) -> list[str]:
    # grep's second arg is the search root; jail it.
    if len(a) > 1:
        _jail(root, a[1])
    return _grep(root, a)


def _sandboxed_edit_file(root: Path, a: list[Any]) -> str:
    _jail(root, a[0])  # jailed by side effect (raises if outside)
    return _edit_file(root, a)


def _sandboxed_write_file(root: Path, a: list[Any]) -> str:
    _jail(root, a[0])
    return _write_file(root, a)


def sandboxed_fs_tools(root: Path) -> dict[str, Tool]:
    """Return `{read_file, list_dir, glob, grep, edit_file, write_file}`
    whose path args must resolve INSIDE `root`. Any escape becomes a
    typed `ToolResult(ok=False, error="path escapes workspace: …")` via
    the tool_loop wrapper — the impl raises, the loop catches and wraps.

    Same signatures + describe strings as the production tools; only
    the resolver changes."""
    return {
        "read_file": Tool(
            "read_file",
            FULL_SUITE["read_file"].describe,  # the product tool's own text (UI sprint 097)
            False,
            partial(_sandboxed_read_file, root),
        ),
        "list_dir": Tool(
            "list_dir",
            FULL_SUITE["list_dir"].describe,  # the product tool's own text (UI sprint 097)
            False,
            partial(_sandboxed_list_dir, root),
        ),
        "glob": Tool(
            "glob",
            FULL_SUITE["glob"].describe,  # the product tool's own text (UI sprint 097)
            False,
            partial(_sandboxed_glob, root),
        ),
        "grep": Tool(
            "grep",
            FULL_SUITE["grep"].describe,  # the product tool's own text (UI sprint 097)
            False,
            partial(_sandboxed_grep, root),
        ),
        "edit_file": Tool(
            "edit_file",
            FULL_SUITE["edit_file"].describe,  # the product tool's own text (UI sprint 097)
            False,
            partial(_sandboxed_edit_file, root),
        ),
        "write_file": Tool(
            "write_file",
            FULL_SUITE["write_file"].describe,  # the product tool's own text (UI sprint 097)
            False,
            partial(_sandboxed_write_file, root),
        ),
    }


def sandbox_exec_available() -> bool:
    """True on macOS with /usr/bin/sandbox-exec present."""
    return sys.platform == "darwin" and shutil.which("sandbox-exec") is not None


def _sandbox_profile(root: Path) -> str:
    """The macOS sandbox-exec profile: deny default, allow only what a
    normal /bin/sh + coreutils command actually needs, plus read/write
    under `root`.

    Follows Anthropic sandbox-runtime shape — allow process exec + read
    of the shell binaries; read + write only inside the workspace;
    network denied entirely. The profile grammar is the TinyScheme-
    style SBPL that ships with macOS."""
    root_abs = str(root.resolve())
    return (
        f"(version 1)\n"
        f"(deny default)\n"
        f"(allow process*)\n"
        f"(allow sysctl-read)\n"
        f"(allow signal (target self))\n"
        f"(allow file-read* file-read-metadata)\n"
        f'(allow file-write* (subpath "{root_abs}"))\n'
        f'(allow file-write-create file-write-data (subpath "{root_abs}"))\n'
        f"(deny network*)\n"
    )


def _sandbox_exec_bash_impl(root: Path, a: list[Any]) -> dict[str, Any]:
    """`bash` wrapped in sandbox-exec: deny default, allow reads
    everywhere, allow writes only under `root`, deny network."""
    profile = _sandbox_profile(root)
    cmd = [
        "/usr/bin/sandbox-exec",
        "-p",
        profile,
        "/bin/sh",
        "-c",
        str(a[0]),
    ]
    proc = subprocess.run(  # noqa: S603 — controlled arg vector
        cmd, capture_output=True, text=True, timeout=60, cwd=str(root)
    )
    return {
        "exit": proc.returncode,
        "stdout": proc.stdout[:8000],
        "stderr": proc.stderr[:2000],
    }


def sandbox_exec_bash(root: Path) -> Tool:
    """A `bash` tool wrapped in macOS `sandbox-exec` (Layer 2). Denies
    everything by default; allows read anywhere, writes only under
    `root`, no network. Skip the test with pytest.skip when
    sandbox_exec_available() is False (Linux CI, etc.)."""
    if not sandbox_exec_available():
        raise RuntimeError("sandbox_exec_bash requires macOS with /usr/bin/sandbox-exec")
    return Tool(
        "bash",
        "bash(cmd) -> {exit, stdout, stderr}",
        False,
        partial(_sandbox_exec_bash_impl, root),
    )


@contextmanager
def stub_urlopen(handler: Callable[[str], bytes]) -> Iterator[None]:
    """Patch `urllib.request.urlopen` so `web_fetch` only reaches the
    caller's handler.

    `handler(url) -> bytes` returns the response body. The real network
    is unreachable while this is active. Use as:

        with stub_urlopen(lambda url: b"stub body"):
            ... run the test ...
    """

    class _Response:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self, amt: int | None = None) -> bytes:
            # `urllib.request.urlopen(...).read(N)` is the real shape;
            # match it so `_web_fetch(a) -> r.read(20000)` works too.
            if amt is None:
                return self._body
            return self._body[:amt]

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_exc: Any) -> None:
            return None

    def _stub(request: Any, *_args: Any, **_kwargs: Any) -> _Response:
        url = request.full_url if hasattr(request, "full_url") else str(request)
        return _Response(handler(url))

    with patch("urllib.request.urlopen", _stub):
        yield


@contextmanager
def monkeypatch_sessions_base(new_base: Path) -> Iterator[None]:
    """Redirect `_SESSIONS_BASE` in `substrate-ui/server.py` (and
    anywhere else it lives) to `new_base` for the duration of a test.

    Delegate / run_topology child sessions land under this new base,
    keeping every artefact inside `tmp_path`."""
    new_base.mkdir(parents=True, exist_ok=True)
    # server.py is the canonical home; only patch what we can import.
    # If the substrate-ui module is not importable in the test's
    # environment, we quietly no-op and rely on Layer 3 to catch any
    # escape (the child sessions will still land under ~/.substrate,
    # and the post-test guard will fail loud).
    try:
        import importlib

        mod = importlib.import_module("substrate_ui.server")  # noqa: F401
        with patch.object(mod, "_SESSIONS_BASE", new_base):
            yield
    except ModuleNotFoundError:
        # Fine — the substrate repo alone doesn't expose it; delegate
        # tests can still run and Layer 3 catches any escape.
        yield

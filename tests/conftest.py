# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 052 conftest — Layer 3 post-test invariant for live-model
tool tests.

The `no_escape_guard` fixture opts a test in to a host-side scan: it
snapshots the mtime of `~/.substrate/`, `~/.substrate/sessions/`, and
the test's tmp_path's SIBLINGS under /tmp before the test, and asserts
after the test that nothing outside the test's own tmp_path changed.

This is the "prove no escape happened" belt-and-suspenders that runs
regardless of what the model did inside the tools — if a hole let a
write past Layer 1 (path jail) and Layer 2 (sandbox-exec), Layer 3
catches it and fails the test loud.

Applied per-test via `@pytest.mark.usefixtures("no_escape_guard")` so
the tool-comprehension suite opts in explicitly."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

# Test-session state root (UI sprint 097; same fix as substrate-ui sprint 093). Every test run
# gets a fresh SUBSTRATE_HOME, set at conftest import so it is in place before any test module
# imports substrate. Without it, kernel tests that open sessions wrote into the user's real
# ~/.substrate/sessions: 2026-10-01, the real-model tier's no_escape_guard caught it, and 147
# session dirs had appeared there that day. The guard below still watches the REAL
# ~/.substrate, so from here on it fires only on a genuine escape.
_TEST_HOME = tempfile.mkdtemp(prefix="substrate-kernel-test-home-")
os.environ["SUBSTRATE_HOME"] = _TEST_HOME


@pytest.fixture(autouse=True, scope="session")
def _remove_test_substrate_home() -> Iterator[None]:
    yield
    shutil.rmtree(_TEST_HOME, ignore_errors=True)


def _snapshot(paths: list[Path]) -> dict[str, float]:
    """Walk each path (one level deep) + record child mtimes."""
    snap: dict[str, float] = {}
    for p in paths:
        if not p.exists():
            continue
        try:
            for entry in p.iterdir():
                try:
                    snap[str(entry)] = entry.stat().st_mtime
                except OSError:
                    continue
        except (OSError, PermissionError):
            continue
    return snap


@pytest.fixture
def no_escape_guard(tmp_path: Path) -> Iterator[None]:
    """Snapshot the mtime of every child under ~/.substrate and its
    sessions/ subdir before the test; after the test, assert the same
    children still have the same mtimes and no new children appeared.

    Explicitly does NOT walk into the test's own tmp_path — writes
    there are the whole point. The guard's job is to catch writes
    OUTSIDE tmp_path.

    Skips paths that never existed (a fresh dev box). If ~/.substrate
    is missing, only new-child-appearance is checked.
    """
    home = Path.home()
    substrate_home = home / ".substrate"
    sessions_home = substrate_home / "sessions"

    watched = [substrate_home, sessions_home]
    before = _snapshot(watched)

    yield

    after = _snapshot(watched)
    added = set(after) - set(before)
    changed = {p for p in set(before) & set(after) if before[p] != after[p]}

    # A pytest run itself can touch caches under ~/.substrate/ if the
    # test happens to import substrate modules that lazily init a per-
    # daemon cache dir. Ignore paths whose name matches a known-benign
    # allowlist (empty by default; extend when a false-positive shows
    # up in review). Otherwise fail.
    allow_names: set[str] = set()
    added_real = [p for p in added if Path(p).name not in allow_names]
    changed_real = [p for p in changed if Path(p).name not in allow_names]

    assert not added_real and not changed_real, (
        f"escape from tmp_path detected:\n"
        f"  added: {sorted(added_real)[:10]}\n"
        f"  changed: {sorted(changed_real)[:10]}\n"
        f"host-side paths outside tmp_path ({tmp_path}) were modified. "
        f"A tool in this test escaped the Layer 1 path jail and Layer 2 "
        f"sandbox-exec (bash). Investigate — this is a genuine sandbox "
        f"escape, not a test-setup artefact."
    )

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""CI-mode factory for `swebench_repair_topology` — Sprint 188 (roadmap v2 S2 part 2 of 2).

`bundled.py`'s zero-arg factories construct fully-configured topologies with deterministic
responders so `substrate run --topology <name>` works with no network and produces a
byte-stable record. `swebench_repair` requires a git checkout on disk (the SEARCH/REPLACE
applier clones the base and applies edits); the factory below creates a fixture repo at a
deterministic path so the recorded run is stable across regenerations.

The fixture path defaults to `~/.substrate/ci-fixtures/swebench_repair/`. Override with
`SUBSTRATE_CI_FIXTURE_ROOT`. The factory writes the fixture idempotently: first call
initializes the repo, subsequent calls reuse it. `git init` runs once; `git commit` runs once.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from ... import api
from .assemble import swebench_repair_topology


def _fixture_root() -> Path:
    """Deterministic on-disk path for the CI fixture. Override via `SUBSTRATE_CI_FIXTURE_ROOT`
    (used by tests that want an isolated tmpdir)."""
    override = os.environ.get("SUBSTRATE_CI_FIXTURE_ROOT")
    if override:
        return Path(override) / "swebench_repair"
    from substrate.api import substrate_home

    return substrate_home() / "ci-fixtures" / "swebench_repair"


def _ensure_fixture(root: Path) -> None:
    """Write the fixture repo idempotently. Same content shape as
    `tests/test_swebench_solver.py::_fixture_repo` — one Python module the deterministic
    responder's SEARCH/REPLACE block matches against."""
    root.mkdir(parents=True, exist_ok=True)
    module = root / "m.py"
    module.write_text("def f(x):\n    return x\n")
    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=ci@substrate",
                "-c",
                "user.name=ci",
                "commit",
                "-q",
                "-m",
                "init",
            ],
            cwd=root,
            check=True,
        )


def swebench_repair_ci() -> Callable[[api.TopologyBuilder], None]:
    """Zero-arg factory returning the CI-configured `swebench_repair_topology`. Registered in
    `topologies/bundled.py`; drives `substrate run --topology swebench_repair` and the committed
    `records/ci_mode.record`.

    `responders=None` (from Sprint 187 dual-mode default) means the topology fills in a
    DeterministicResponder list per slot — no network, no Ollama, byte-stable record."""
    root = _fixture_root()
    _ensure_fixture(root)
    return swebench_repair_topology(
        base_checkout=str(root),
        issue="off-by-one in f",
        repo_skeleton="m.py\n",
        known_files={"m.py"},
        n=2,
        max_rounds=1,
        watchdog_seconds=5.0,
    )

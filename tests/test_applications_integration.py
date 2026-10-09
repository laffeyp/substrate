# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""W1.INT — the application library, mounted end-to-end (sprint 140).

The wave-boundary proof (technique #16): all three W1 applications build and run to their terminal
as a SET, on one invocation, deterministically. Each individual app has its own contract test;
this asserts the wave is wired together — nothing regressed the set as a whole.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.applications import (
    best_of_n_verified_topology,
    fanout_review_topology,
    research_sweep_topology,
)
from substrate.topologies.code_review import DEFAULT_ROLES


def _repo_with_change(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    for cmd in (
        ["git", "init", "-q", str(repo)],
        ["git", "-C", str(repo), "config", "user.email", "t@t"],
        ["git", "-C", str(repo), "config", "user.name", "t"],
    ):
        subprocess.run(cmd, check=True)
    (repo / "f.py").write_text("def g(a, b):\n    return a / b\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    (repo / "f.py").write_text("def g(a, b):\n    return a / b  # no guard\n")
    return repo


def _run(topo, root: Path):
    result = asyncio.run(api.Runtime(root).run(topo))
    kinds = [e["kind"] for e in api.read_record(root)]
    return result, kinds


def test_w1_library_mounts_end_to_end(tmp_path: Path) -> None:
    # fanout_review — the review panel on a real diff (composes code_review)
    repo = _repo_with_change(tmp_path)
    fr_result, fr_kinds = _run(
        fanout_review_topology(
            repo,
            ref="HEAD",
            responders={r: DeterministicResponder(seed=i) for i, r in enumerate(DEFAULT_ROLES)},
            judge=DeterministicResponder(seed=99),
            quorum=3,
        ),
        tmp_path / "fanout",
    )
    assert fr_result.status == "finalised" and "VerdictRendered" in fr_kinds

    # best_of_n_verified — generate N, verify, select (composes best_of_n)
    bon_result, bon_kinds = _run(
        best_of_n_verified_topology(
            "name a prime",
            drafter=DeterministicResponder(seed=0),
            verify=lambda response: (True, "ok"),
            n=3,
            max_rounds=2,
        ),
        tmp_path / "bon",
    )
    assert bon_result.status == "finalised" and "Solved" in bon_kinds

    # research_sweep — map readers over docs, critique, synthesize (authored from primitives)
    rs_result, rs_kinds = _run(
        research_sweep_topology(
            "what colors?",
            [("a.md", "sky is blue"), ("b.md", "grass is green")],
            reader=DeterministicResponder(seed=0),
            critic=DeterministicResponder(seed=1),
            synthesizer=DeterministicResponder(seed=2),
        ),
        tmp_path / "sweep",
    )
    assert rs_result.status == "finalised" and "Synthesis" in rs_kinds

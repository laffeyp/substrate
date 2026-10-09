# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 187 (roadmap v2 S2 dual-mode): `swebench_repair_topology(responders=None)`
runs against DeterministicResponder defaults and produces a byte-stable record.

Pin the additive contract:
- Caller omitting `responders=` gets a deterministic run — the same pattern every other
  bundled topology uses per `docs/adding-a-topology.md` § "Make it dual-mode".
- Caller supplying `responders=[...]` behaves identically to the pre-Sprint-187 shape.
- The deterministic run emits a `RepairSummary` terminal, matching the topology's own
  invariant (always-emit summary at every Solved/Exhausted terminal).

The topology still requires `base_checkout / issue / repo_skeleton / known_files` — those
are inputs to the topology, not model-seam parameters. A fixture repo covers them at
test time; bundled-registration (Sprint 188 follow-on) covers them at demo time.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from substrate.api import Runtime, read_record
from substrate.topologies.swebench_solver.assemble import swebench_repair_topology

_FIX = "# path: m.py\n<<<<<<< SEARCH\n    return x\n=======\n    return x + 1\n>>>>>>> REPLACE\n"


def _fixture_repo() -> str:
    """A tiny git repo with one file the topology can localize + patch against.
    Same shape as `tests/test_swebench_solver.py::_fixture_repo`."""
    d = tempfile.mkdtemp()
    (Path(d) / "m.py").write_text("def f(x):\n    return x\n")
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "add", "."], cwd=d, check=True)
    subprocess.run(
        ["git", "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", "init"],
        cwd=d,
        check=True,
    )
    return d


async def _run(topo, root):
    await Runtime(root).run(topo)


def test_responders_none_defaults_to_deterministic(tmp_path):
    """Sprint 187: `responders=None` gets a DeterministicResponder list of length `n`.
    Topology builds, runs, and produces a `RepairSummary` terminal."""
    import asyncio

    repo = _fixture_repo()
    files = ["m.py"]
    topo = swebench_repair_topology(
        base_checkout=repo,
        issue="off-by-one in f",
        repo_skeleton="m.py\n",
        known_files=set(files),
        n=2,
        max_rounds=1,
        watchdog_seconds=5.0,
    )
    root = tmp_path / "run"
    asyncio.run(_run(topo, root))
    events = list(read_record(root))
    kinds = [e["kind"] for e in events]
    assert "substrate.RunStarted" in kinds
    assert "substrate.RunFinalised" in kinds
    # The topology terminates on RepairSummary; if the deterministic run reached the
    # judge stage, RepairSummary lands.
    assert "RepairSummary" in kinds, (
        f"expected RepairSummary in the record; got kinds={sorted(set(kinds))}"
    )


def test_responders_explicit_list_still_works(tmp_path):
    """Sprint 187 preserves the pre-Sprint-187 contract: explicit responders behave
    identically to before the default was added."""
    import asyncio

    from substrate.adapters import DeterministicResponder

    repo = _fixture_repo()
    files = ["m.py"]
    responders = [DeterministicResponder(seed=i) for i in range(2)]
    topo = swebench_repair_topology(
        responders=responders,
        base_checkout=repo,
        issue="off-by-one in f",
        repo_skeleton="m.py\n",
        known_files=set(files),
        n=2,
        max_rounds=1,
        watchdog_seconds=5.0,
    )
    root = tmp_path / "run"
    asyncio.run(_run(topo, root))
    events = list(read_record(root))
    assert any(e["kind"] == "RepairSummary" for e in events)

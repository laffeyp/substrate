# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Pressure + end-to-end tests for the bundled Phase-2 topologies.

Beyond the happy-path structural tests, this exercises: the CLI end-to-end over the committed
records (CliRunner, real exit codes); determinism (two independent runs are D-8 log-equivalent
via first_divergence); LIVENESS (a topology finalises under reviewer FAILURES even when the
quorum is unreachable — all_completed finalises on every Producer ending, see the corrected
per-test note); and the negative paths (a failing model, boundary quorums, single / deep /
high-fanout shapes, runaway recursion at the shallowest depth).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from substrate.api import Runtime, first_divergence, read_record
from substrate.cli import EXIT_OK, main
from substrate.reference._models import DeterministicResponder
from substrate.topologies.code_review import DEFAULT_ROLES, code_review_topology
from substrate.topologies.pair_coding import pair_coding_topology
from substrate.topologies.recursive_decomposition import recursive_decomposition_topology

_PKG = Path(__file__).resolve().parent.parent / "src" / "substrate" / "topologies"
_RECORDS = {
    name: _PKG / name / "records" / "ci_mode.record"
    for name in ("code_review", "pair_coding", "recursive_decomposition")
}


class _FailingResponder:
    """A model that is unavailable — respond() raises. Used to prove a Producer failure becomes
    a recorded substrate.ProducerFailed (not a crash) and the run still terminates."""

    def respond(self, prompt: str) -> str:
        raise RuntimeError("model unavailable")


def _reviewers(seed0: int = 0) -> dict[str, DeterministicResponder]:
    return {r: DeterministicResponder(seed=seed0 + i) for i, r in enumerate(DEFAULT_ROLES)}


# ── End-to-end: the real CLI over the committed records ─────────────────────────
@pytest.mark.parametrize("name", list(_RECORDS))
def test_cli_replay_committed_record_level_2(name):
    record = _RECORDS[name]
    assert record.exists(), f"committed record missing: {record} (run gen_topology_records.py)"
    res = CliRunner().invoke(main, ["replay", str(record), "--level", "2"])
    assert res.exit_code == EXIT_OK, res.output
    assert "Level 2" in res.output and "verified" in res.output


@pytest.mark.parametrize("name", list(_RECORDS))
def test_cli_inspect_and_tail_committed_record(name):
    record = str(_RECORDS[name])
    runner = CliRunner()
    tail = runner.invoke(main, ["tail", record])
    assert tail.exit_code == EXIT_OK, tail.output
    assert "RunStarted" in tail.output and "RunFinalised" in tail.output


# ── Determinism: two independent runs are D-8 log-equivalent ────────────────────
@pytest.mark.timeout(20)
@pytest.mark.parametrize(
    "name,thunk",
    [
        (
            "code_review",
            lambda: code_review_topology(
                "x", responders=_reviewers(), judge=DeterministicResponder(seed=99), quorum=3
            ),
        ),
        (
            "pair_coding",
            lambda: pair_coding_topology(
                "t",
                driver_model=DeterministicResponder(seed=1),
                navigator_model=DeterministicResponder(seed=2),
                chunks=["def a():\n", "    return 1\n", "def b():\n    return 2\n"],
            ),
        ),
        (
            "recursive",
            lambda: recursive_decomposition_topology(
                "r", solver_model=DeterministicResponder(seed=3), max_depth=2, fanout=2
            ),
        ),
    ],
)
async def test_topology_runs_are_log_equivalent(tmp_path, name, thunk):
    await Runtime(tmp_path / "a").run(thunk())
    await Runtime(tmp_path / "b").run(thunk())
    div = first_divergence(tmp_path / "a", tmp_path / "b")
    assert div is None, f"{name} is non-deterministic: first divergence {div}"


# ── Liveness: the topology finalises under reviewer failures (quorum unreachable) ─
@pytest.mark.timeout(10)
async def test_code_review_finalises_under_reviewer_failures(tmp_path):
    # 4 of 5 reviewers' models are unavailable (respond raises -> substrate.ProducerFailed); the
    # 1 survivor emits a single critique, so quorum=3 is never reached and the judge never fires.
    # The run must still finalise (not hang). CORRECTION (review #16, verified by running): this
    # is NOT a case all_completed would hang on — TermContext.completed == ended_total counts
    # failures as ends (runtime.py:631, sequencer.py:226-232), so all_completed ALONE finalises
    # here too (running==0 once every reviewer ends). The watchdog is redundant for THIS path; it
    # is load-bearing only for the zero-started-Producer case. This test proves "the topology
    # finalises under failures", NOT "the watchdog is what finalises it".
    responders: dict[str, object] = {r: _FailingResponder() for r in DEFAULT_ROLES}
    responders["security"] = DeterministicResponder(seed=1)  # the lone survivor
    topo = code_review_topology(
        "code",
        responders=responders,  # type: ignore[arg-type]
        judge=DeterministicResponder(seed=99),
        quorum=3,
    )
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"  # the watchdog/quiescence finalises; did NOT hang
    envs = list(read_record(tmp_path / "run"))
    failed = [e for e in envs if e["kind"] == "substrate.ProducerFailed"]
    assert len(failed) == 4  # the 4 unavailable reviewers failed (ended), not hung
    assert not [e for e in envs if e["kind"] == "VerdictRendered"]  # quorum never met, no verdict
    assert envs[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.timeout(15)
async def test_code_review_survives_a_failing_reviewer(tmp_path):
    # one reviewer's model is unavailable (respond raises) -> substrate.ProducerFailed, not a
    # crash; the other 4 still meet quorum=3, the judge fires, the run finalises.
    responders: dict[str, object] = dict(_reviewers())
    responders["security"] = _FailingResponder()
    topo = code_review_topology(
        "code",
        responders=responders,  # type: ignore[arg-type]
        judge=DeterministicResponder(seed=99),
        quorum=3,
    )
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    failed = [e for e in envs if e["kind"] == "substrate.ProducerFailed"]
    assert any(e["payload"]["producer"]["kind"] == "reviewer-security" for e in failed)
    assert [e for e in envs if e["kind"] == "VerdictRendered"]  # quorum still met by the other 4


# ── Boundary shapes ─────────────────────────────────────────────────────────────
@pytest.mark.timeout(15)
@pytest.mark.parametrize("quorum", [1, 5])
async def test_code_review_boundary_quorums(tmp_path, quorum):
    topo = code_review_topology(
        "code", responders=_reviewers(), judge=DeterministicResponder(seed=9), quorum=quorum
    )
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    verdict = [e for e in envs if e["kind"] == "VerdictRendered"]
    assert len(verdict) == 1 and verdict[0]["payload"]["n_critiques"] >= quorum


@pytest.mark.timeout(15)
async def test_pair_coding_single_chunk(tmp_path):
    topo = pair_coding_topology(
        "t",
        driver_model=DeterministicResponder(seed=1),
        navigator_model=DeterministicResponder(seed=2),
        chunks=["print('hi')\n"],
    )
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    assert sum(1 for e in envs if e["kind"] == "CodeChunk") == 1
    # one chunk -> one suggestion -> next-chunk predicate (len<1) false -> no second driver
    assert not [
        e
        for e in envs
        if e["kind"] == "substrate.TriggerFired" and e["payload"].get("trigger_id") == "next-chunk"
    ]


@pytest.mark.timeout(20)
async def test_pair_coding_many_chunks(tmp_path):
    chunks = [f"line_{i} = {i}\n" for i in range(10)]
    topo = pair_coding_topology(
        "t",
        driver_model=DeterministicResponder(seed=1),
        navigator_model=DeterministicResponder(seed=2),
        chunks=chunks,
    )
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    assert sum(1 for e in envs if e["kind"] == "CodeChunk") == 10
    assert [e["payload"]["chunk_index"] for e in envs if e["kind"] == "CodeChunk"] == list(
        range(10)
    )


@pytest.mark.timeout(15)
async def test_recursive_depth_one_is_all_leaves(tmp_path):
    topo = recursive_decomposition_topology(
        "r", solver_model=DeterministicResponder(seed=3), max_depth=1, fanout=3
    )
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    # depth-1 == max_depth -> every solver is a leaf; planner fans to 3, all solve, no depth 2
    assert sum(1 for e in envs if e["kind"] == "SolutionReached") == 3
    assert max(e["payload"]["depth"] for e in envs if e["kind"] == "SubtaskProposed") == 1


@pytest.mark.timeout(15)
async def test_recursive_runaway_at_shallowest_depth_is_bounded(tmp_path):
    # max_depth=1, runaway: depth-1 solvers try to emit depth-2 subtasks; the budget catches all
    # of them at the very first boundary. Pressure on the bound at its tightest setting.
    topo = recursive_decomposition_topology(
        "r", solver_model=DeterministicResponder(seed=3), max_depth=1, fanout=2, runaway=True
    )
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    exceeded = [e for e in envs if e["kind"] == "DepthBudgetExceeded"]
    assert exceeded and all(e["payload"]["depth"] == 2 for e in exceeded)
    # no solver ever ran at depth 2
    solver_depths = [
        f["payload"]["resolved_input"]["depth"]
        for f in envs
        if f["kind"] == "substrate.TriggerFired"
        and f["payload"].get("trigger_id") == "spawn-solver"
    ]
    assert max(solver_depths) == 1


@pytest.mark.timeout(30)
async def test_recursive_high_fanout_stress(tmp_path):
    # fanout=4, depth=3: 4 + 16 + 64 = 84 subtasks, 84 solvers, 64 leaf solutions — a wide, deep
    # tree from ONE recursive Trigger; the run must finalise on quiescence without hanging.
    topo = recursive_decomposition_topology(
        "r", solver_model=DeterministicResponder(seed=3), max_depth=3, fanout=4
    )
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    assert sum(1 for e in envs if e["kind"] == "SolutionReached") == 64
    solver_starts = sum(
        1
        for e in envs
        if e["kind"] == "substrate.ProducerStarted" and e["payload"]["producer"]["kind"] == "solver"
    )
    assert solver_starts == 4 + 16 + 64

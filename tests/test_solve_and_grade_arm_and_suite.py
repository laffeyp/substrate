# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 197 (roadmap v2 S6 consumer): arm + suite builders for the solve-and-grade topology.

`swebench_solve_and_grade_arm` returns an Arm whose `build(case)` produces a topology that
emits `GradeResult` on the cell's record. `swebench_solve_and_grade_suite` returns a Suite
whose oracle is `SwebenchLogProjectionOracle` — reads `GradeResult` off each cell's record
instead of running the harness externally.

Substance tests without live Docker: build a Case with a fixture payload, build an arm,
verify `arm.build(case)` returns a callable topology; verify the suite's oracle is the
projection variant; verify the arm registers the grader producer.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def _fixture_repo() -> str:
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


def _fixture_case():
    from substrate.assay.suite import Case

    payload = {
        "base_checkout": _fixture_repo(),
        "repo_skeleton": "m.py\n",
        "known_files": ["m.py"],
        "regression_files": [],
        "exclude": [],
        "spec": {},
        "passed_at_base": [],
        "image": "swebench.eval.test.instance.hash",
        "issue": "off by one",
    }
    ground_truth = {"instance_id": "test__instance", "patch": ""}
    # Case.case_id must not contain '__' (path-segment separator). Use safe_case_id's convention.
    return Case(case_id="test_1776_instance", payload=payload, ground_truth=ground_truth)


def test_solve_and_grade_arm_build_returns_a_topology(tmp_path):
    """The arm's `build(case)` returns a callable topology function."""
    from substrate.assay.suite import FULL
    from substrate.assay.swebench_suite import swebench_solve_and_grade_arm

    arm = swebench_solve_and_grade_arm(
        name="solve_grade_test",
        role=FULL,
        models=["deterministic:test"],
        report_root=tmp_path / "reports",
        dataset_name="princeton-nlp/SWE-bench_Lite",
        grade_timeout_seconds=60,
        n=1,
        max_rounds=1,
    )
    case = _fixture_case()
    topo = arm.build(case)
    assert callable(topo)


def test_solve_and_grade_arm_registers_grader_producer(tmp_path):
    """Building the arm's topology on a fresh TopologyBuilder registers the grader
    producer kind — the piece Sprint 195 landed that emits `GradeResult`."""
    from substrate.assay.suite import FULL
    from substrate.assay.swebench_suite import swebench_solve_and_grade_arm
    from substrate.kernel.topology import TopologyBuilder

    arm = swebench_solve_and_grade_arm(
        name="solve_grade_test",
        role=FULL,
        models=["deterministic:test"],
        report_root=tmp_path / "reports",
        dataset_name="princeton-nlp/SWE-bench_Lite",
        grade_timeout_seconds=60,
        n=1,
        max_rounds=1,
    )
    case = _fixture_case()
    topo = arm.build(case)
    b = TopologyBuilder()
    topo(b)
    kinds = b._reg.producer_kinds
    assert "grader" in kinds, f"expected 'grader' producer kind; got {sorted(kinds)}"
    assert "GradeResult" in kinds["grader"].schemas


def test_solve_and_grade_suite_uses_log_projection_oracle(tmp_path):
    """The suite's oracle is `SwebenchLogProjectionOracle` — reads GradeResult off the
    record instead of running the harness externally."""
    from substrate.assay.suite import FULL
    from substrate.assay.swebench import SwebenchLogProjectionOracle
    from substrate.assay.swebench_suite import (
        swebench_solve_and_grade_arm,
        swebench_solve_and_grade_suite,
    )

    arm = swebench_solve_and_grade_arm(
        name="solve_grade_test",
        role=FULL,
        models=["deterministic:test"],
        report_root=tmp_path / "reports",
        dataset_name="princeton-nlp/SWE-bench_Lite",
        grade_timeout_seconds=60,
    )
    case = _fixture_case()
    suite = swebench_solve_and_grade_suite(
        cases=[case],
        arms=[arm],
        control_arm="solve_grade_test",
    )
    assert isinstance(suite.oracle, SwebenchLogProjectionOracle)


def test_solve_and_grade_arm_and_suite_exported():
    """Both new symbols land in `swebench_suite.__all__` per hard rule F-API discipline."""
    from substrate.assay import swebench_suite

    assert "swebench_solve_and_grade_arm" in swebench_suite.__all__
    assert "swebench_solve_and_grade_suite" in swebench_suite.__all__

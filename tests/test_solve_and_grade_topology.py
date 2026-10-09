# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 196 (roadmap v2 S6 part 2 of 2): `swebench_solve_and_grade_topology` runs the
repair loop + grade producer end-to-end; `SwebenchLogProjectionOracle` projects
`GradeResult` off the record.

The end-to-end path (fixture repo + deterministic responders + real `run_swebench_one`)
would require Docker + the swebench harness install. The tests here cover:

- The topology builds without error and registers the grader producer with the correct
  schemas.
- `SwebenchLogProjectionOracle.grade` reads a `GradeResult` off a synthetic record and
  returns a `Result` whose verdict + reason + replayable match.
- The oracle's fallback (no `GradeResult` on the record) returns `Verdict.FAIL` with the
  expected detail — the honest "arm produced no patch to grade" state that Exhausted or
  no-SelectedPatch paths produce.
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


def test_solve_and_grade_topology_builds(tmp_path):
    """The topology function returns a callable that the TopologyBuilder consumes without
    error. Registers the grader producer with the correct schemas (GradeResult)."""
    from substrate.assay.swebench_solve_and_grade import swebench_solve_and_grade_topology
    from substrate.kernel.topology import TopologyBuilder

    build = swebench_solve_and_grade_topology(
        base_checkout=_fixture_repo(),
        issue="off by one",
        repo_skeleton="m.py\n",
        known_files={"m.py"},
        instance_id="test__instance",
        dataset_name="princeton-nlp/SWE-bench_Lite",
        model_name="test-model",
        run_id="test-run",
        report_dir=tmp_path / "reports",
        grade_timeout_seconds=60,
        n=1,
        max_rounds=1,
    )
    b = TopologyBuilder()
    build(b)

    # Grader is registered as a producer kind alongside the repair-topology producers.
    kinds = b._reg.producer_kinds
    assert "grader" in kinds, f"expected 'grader' producer_kind; got {sorted(kinds)}"
    grader_reg = kinds["grader"]
    assert "GradeResult" in grader_reg.schemas


def test_log_projection_oracle_reads_grade_result_pass(tmp_path):
    """A record with one `GradeResult(verdict="pass")` → oracle returns Verdict.PASS,
    replayable=True."""
    from substrate.assay.oracle import LOG_PROJECTION, Verdict
    from substrate.assay.swebench import swebench_log_projection_oracle

    oracle = swebench_log_projection_oracle()
    record = [
        {"kind": "substrate.RunStarted", "payload": {}},
        {
            "kind": "GradeResult",
            "payload": {"instance_id": "test__instance", "verdict": "pass", "reason": ""},
        },
        {"kind": "substrate.RunFinalised", "payload": {}},
    ]
    result = oracle.grade(record, {"instance_id": "test__instance", "patch": "diff --git"})
    assert result.verdict is Verdict.PASS
    assert result.score == 1.0
    assert result.oracle_class == LOG_PROJECTION
    assert result.replayable is True
    assert result.reason == ""


def test_log_projection_oracle_reads_grade_result_fail_with_reason(tmp_path):
    """A record with `GradeResult(verdict="no_verdict", reason="timed_out")` →
    Verdict.NO_VERDICT with the reason surfaced."""
    from substrate.assay.oracle import Verdict
    from substrate.assay.swebench import swebench_log_projection_oracle

    oracle = swebench_log_projection_oracle()
    record = [
        {
            "kind": "GradeResult",
            "payload": {
                "instance_id": "test__instance",
                "verdict": "no_verdict",
                "reason": "timed_out",
            },
        },
    ]
    result = oracle.grade(record, {"instance_id": "test__instance", "patch": ""})
    assert result.verdict is Verdict.NO_VERDICT
    assert result.score == 0.0
    assert result.reason == "timed_out"
    assert "reason=timed_out" in result.detail


def test_log_projection_oracle_no_grade_result_returns_fail():
    """A record with no `GradeResult` — the topology never selected a patch — returns
    Verdict.FAIL with the "no GradeResult on record" detail."""
    from substrate.assay.oracle import Verdict
    from substrate.assay.swebench import swebench_log_projection_oracle

    oracle = swebench_log_projection_oracle()
    record = [
        {"kind": "substrate.RunStarted", "payload": {}},
        {"kind": "RepairSummary", "payload": {"outcome": "no_localization"}},
        {"kind": "substrate.RunFinalised", "payload": {}},
    ]
    result = oracle.grade(record, {"instance_id": "test__instance", "patch": ""})
    assert result.verdict is Verdict.FAIL
    assert result.score == 0.0
    assert "no GradeResult on record" in result.detail
    assert result.replayable is True

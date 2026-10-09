# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 199d (roadmap v2 S7b follow-on): `container_solve_and_grade_arm` +
`_backend_topology_with_grade`.

Container_arm's pre-Sprint-199d topology emitted only `SelectedPatch` — no in-topology
grade — so a matrix run that included the container arm had to use `SwebenchRecordOracle`
(external harness call from the oracle). Sprint 199d adds a grade producer that fires on
`SelectedPatch` and emits `GradeResult`; the arm can now join `SWEBENCH_ARMS=solve_and_grade`
mode under `swebench_log_projection_oracle` — the log-projection path Sprint 197 landed.

Tests pin the extracted contract:
- `_backend_topology_with_grade` declares BOTH `solve` (SelectedPatch) and `grader` (GradeResult)
  producer kinds.
- The trigger fires the grader on SelectedPatch.
- Termination waits for GradeResult, not just SelectedPatch (so the grader completes before
  the run finalises).
- `container_solve_and_grade_arm` returns an Arm whose `build(case)` reproduces the shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from substrate.assay.suite import Case
from substrate.assay.swebench_matrix import (
    _backend_topology_with_grade,
    container_solve_and_grade_arm,
)


class _RecordingBuilder:
    """Minimal builder that records producer_kind, trigger, and termination for shape assertions.
    Same pattern as tests/test_assay_swebench_matrix.py's fixture."""

    def __init__(self) -> None:
        self.producer_kinds: dict[str, dict[str, Any]] = {}
        self.initials: list[tuple[str, Any]] = []
        self.triggers: list[dict[str, Any]] = []
        self.termination_str: str = ""

    def producer_kind(
        self,
        kind: str,
        *,
        schemas,
        schema_version,
        factory=None,
        start=None,
        deterministic=False,
        author_version=None,
        budget=None,
    ) -> None:
        self.producer_kinds[kind] = {
            "schemas": [s.__name__ for s in schemas],
            "deterministic": deterministic,
        }

    def initial(self, kind: str, *, input: Any) -> None:
        self.initials.append((kind, input))

    def trigger(self, tid: str, *, subscription, predicate, starts, input_builder, policy) -> None:
        self.triggers.append(
            {
                "id": tid,
                "kinds": sorted(subscription.kinds),
                "starts": starts,
                "policy": type(policy).__name__,
            }
        )

    def termination(self, policy: Any) -> None:
        # TerminationPolicy carries a `.name` attribute; `threshold_count("GradeResult", 1)`
        # names itself `"threshold_count(GradeResult,1)"` and `any_of(a, b)` composes both
        # names in its own. Read that instead of repr(policy), which is the default
        # `<TerminationPolicy object at 0x...>`.
        self.termination_str = getattr(policy, "name", repr(policy))


def _dummy_solve() -> str:
    return "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"


def test_backend_topology_with_grade_declares_solve_and_grader():
    topo = _backend_topology_with_grade(
        _dummy_solve,
        instance_id="pallets__flask-4045",
        dataset_name="princeton-nlp/SWE-bench_Lite",
        model_name="substrate",
        run_id="test-run",
        report_dir=Path("/tmp/does-not-matter"),
        grade_timeout_seconds=60,
    )
    b = _RecordingBuilder()
    topo(b)
    assert "solve" in b.producer_kinds, "solve producer missing"
    assert "grader" in b.producer_kinds, "grader producer missing"
    assert b.producer_kinds["solve"]["schemas"] == ["SelectedPatch"]
    assert b.producer_kinds["grader"]["schemas"] == ["GradeResult"]


def test_backend_topology_with_grade_triggers_grader_on_selected_patch():
    topo = _backend_topology_with_grade(
        _dummy_solve,
        instance_id="pallets__flask-4045",
        dataset_name="princeton-nlp/SWE-bench_Lite",
        model_name="substrate",
        run_id="test-run",
        report_dir=Path("/tmp/does-not-matter"),
        grade_timeout_seconds=60,
    )
    b = _RecordingBuilder()
    topo(b)
    grade_triggers = [t for t in b.triggers if t["starts"] == "grader"]
    assert len(grade_triggers) == 1, f"expected one grade trigger; got {b.triggers}"
    assert "SelectedPatch" in grade_triggers[0]["kinds"]
    assert grade_triggers[0]["policy"] == "Once"


def test_backend_topology_with_grade_terminates_on_grade_result():
    topo = _backend_topology_with_grade(
        _dummy_solve,
        instance_id="pallets__flask-4045",
        dataset_name="princeton-nlp/SWE-bench_Lite",
        model_name="substrate",
        run_id="test-run",
        report_dir=Path("/tmp/does-not-matter"),
        grade_timeout_seconds=60,
    )
    b = _RecordingBuilder()
    topo(b)
    # Termination is `any_of(threshold_count("GradeResult", 1), quiescence(...))`.
    assert "GradeResult" in b.termination_str, (
        f"termination policy must wait for GradeResult, not just SelectedPatch; "
        f"got: {b.termination_str}"
    )
    assert "quiescence" in b.termination_str, (
        f"termination must include quiescence fallback for the no-patch path; "
        f"got: {b.termination_str}"
    )


def test_container_solve_and_grade_arm_build_returns_topology_with_grader():
    arm = container_solve_and_grade_arm(
        "tool_loop_container",
        "ablation",
        model="qwen2.5-coder:7b",
        report_root=Path("/tmp/does-not-matter"),
        dataset_name="princeton-nlp/SWE-bench_Lite",
        max_steps=8,
    )
    case = Case(
        case_id="pallets_1776_flask-4045",
        payload={},
        ground_truth={"instance_id": "pallets__flask-4045"},
    )
    topo = arm.build(case)
    b = _RecordingBuilder()
    topo(b)
    assert "grader" in b.producer_kinds, (
        "container_solve_and_grade_arm must build a topology declaring the grader kind — "
        "otherwise it cannot join SWEBENCH_ARMS=solve_and_grade mode."
    )
    assert "solve" in b.producer_kinds
    assert "GradeResult" in b.termination_str

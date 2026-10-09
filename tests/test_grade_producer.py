# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 195 (roadmap v2 S6 part 1 of 2): `grade_producer_factory` wraps
`run_swebench_one` as a Substrate producer emitting `GradeResult` on the record.

The empty-patch fast path exits `run_swebench_one` with `Verdict.FAIL` before any
subprocess spawns — deterministic under any environment. This test verifies the producer
yields a single `GradeResult` with the mapped wire strings when given an empty patch;
Sprint 196's consumer sprint verifies the wire-into-a-topology shape.
"""

from __future__ import annotations

import asyncio


def test_empty_patch_grade_producer_yields_one_grade_result_fail(tmp_path):
    """Empty patch → run_swebench_one fast-path FAIL → GradeResult(verdict="fail")."""
    from substrate.assay.swebench_grade_producer import grade_producer_factory
    from substrate.topologies.swebench_solver.records import GradeResult

    factory = grade_producer_factory(
        instance_id="test__instance",
        dataset_name="princeton-nlp/SWE-bench_Lite",
        model_name="test-model",
        run_id="test-run",
        report_dir=tmp_path / "reports",
        timeout_seconds=60,
    )
    producer = factory()

    async def _collect() -> list[GradeResult]:
        return [ev async for ev in producer({"model_patch": ""})]

    events = asyncio.run(_collect())
    assert len(events) == 1, f"expected one GradeResult; got {len(events)}"
    assert isinstance(events[0], GradeResult)
    assert events[0].instance_id == "test__instance"
    assert events[0].verdict == "fail"  # empty patch is definite fail per run_swebench_one
    assert events[0].reason == ""


def test_grade_producer_maps_verdict_enum_to_wire_string(tmp_path, monkeypatch):
    """The producer maps `HarnessOutcome.verdict` (a Verdict enum) to the wire strings the
    GradeResult event carries (`"pass"` / `"fail"` / `"no_verdict"`). Same three strings
    the vocab v0.3 § E.1 Verdict enum's `.value` field carries. Monkeypatch
    `run_swebench_one` to return each of the three verdicts and verify the mapping."""
    from substrate.assay import swebench_grade_producer as grader_module
    from substrate.assay.oracle import Verdict as V
    from substrate.assay.swebench import HarnessOutcome
    from substrate.assay.swebench_grade_producer import grade_producer_factory

    mapping = [
        (HarnessOutcome(verdict=V.PASS, reason="", detail="ok"), "pass", ""),
        (HarnessOutcome(verdict=V.FAIL, reason="", detail="ok"), "fail", ""),
        (
            HarnessOutcome(verdict=V.NO_VERDICT, reason="timed_out", detail="ok"),
            "no_verdict",
            "timed_out",
        ),
    ]

    for outcome, expected_verdict, expected_reason in mapping:
        monkeypatch.setattr(grader_module, "run_swebench_one", lambda *a, o=outcome, **kw: o)
        factory = grade_producer_factory(
            instance_id="test__instance",
            dataset_name="princeton-nlp/SWE-bench_Lite",
            model_name="test-model",
            run_id=f"test-run-{expected_verdict}",
            report_dir=tmp_path / f"reports-{expected_verdict}",
            timeout_seconds=60,
        )
        producer = factory()

        async def _collect(p=producer):
            return [ev async for ev in p({"model_patch": "any"})]

        events = asyncio.run(_collect())
        assert len(events) == 1
        assert events[0].verdict == expected_verdict, (
            f"HarnessOutcome({outcome.verdict}) → expected wire {expected_verdict!r}, "
            f"got {events[0].verdict!r}"
        )
        assert events[0].reason == expected_reason


def test_grade_result_exported_from_records():
    """`GradeResult` is importable from the swebench_solver.records module and appears in
    its `__all__`."""
    from substrate.topologies.swebench_solver import records

    assert hasattr(records, "GradeResult")
    assert "GradeResult" in records.__all__

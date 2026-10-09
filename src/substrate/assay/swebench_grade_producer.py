# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Grade producer factory — Sprint 195 (roadmap v2 S6, part 1 of 2).

A substrate producer that wraps `assay/swebench.py::run_swebench_one` and emits a single
`GradeResult` event onto the run's bus after the harness call terminates. Consumers wire
this producer via a trigger on `SelectedPatch` so the topology's own record carries the
grade rather than an external oracle running Docker after the fact.

`run_swebench_one` is a blocking subprocess call (Sprint 193 already emits typed harness
events to stderr for the boundary). The producer runs the blocking call via
`asyncio.to_thread` so the topology's event loop stays live during grade wall-clock.

Consumer sprint (Sprint 196) wires this producer into `swebench_solve_and_grade_topology`
and adds `SwebenchLogProjectionOracle` reading `GradeResult`. This sprint lands the
primitive; Sprint 196 lands the live consumer per WORKING_AGREEMENT § Primitive-plus-consumer.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from ..topologies.swebench_solver.records import GradeResult
from .oracle import Verdict as _V
from .swebench import HarnessOutcome, run_swebench_one

_Factory = Callable[[], Any]


def grade_producer_factory(
    *,
    instance_id: str,
    dataset_name: str,
    model_name: str,
    run_id: str,
    report_dir: Path | str,
    timeout_seconds: int,
    split: str = "test",
    namespace: str = "swebench",
) -> _Factory:
    """A Substrate Producer that grades one `SelectedPatch` and emits `GradeResult`.

    The producer's input carries the `model_patch` field from `SelectedPatch`; `run_swebench_one`
    handles the empty-patch fast path directly. The `HarnessCallFired / Completed / Timeout /
    Error` events at the swebench-harness boundary already emit to stderr from Sprint 193; this
    producer's job is only the record-side event (`GradeResult`) the oracle projects off.

    Wire-up (consumer, Sprint 196):
        b.producer_kind(
            "grader",
            schemas=[GradeResult],
            factory=grade_producer_factory(instance_id=..., dataset_name=..., ...),
            deterministic=False,  # subprocess to Docker; run-and-observe
        )
        b.trigger(
            "grade",
            subscription=api.Subscription(kinds=frozenset({"SelectedPatch"})),
            starts="grader",
            input_builder=lambda ctx: {"model_patch": ctx.event.payload["model_patch"]},
            policy=api.Once(),
        )
    """

    async def grade(inp: Any) -> AsyncIterator[GradeResult]:
        model_patch = str(inp.get("model_patch", "")) if hasattr(inp, "get") else ""

        # Blocking harness call runs in a thread so the outer event loop stays live.
        outcome: HarnessOutcome = await asyncio.to_thread(
            run_swebench_one,
            instance_id,
            model_patch,
            dataset_name=dataset_name,
            model_name=model_name,
            run_id=run_id,
            report_dir=report_dir,
            timeout_seconds=timeout_seconds,
            split=split,
            namespace=namespace,
        )

        # Verdict enum → wire string per § E.1. `outcome.reason` already carries the closed-set
        # string from `_HARNESS_REASONS` (empty on pass/fail).
        verdict_wire = {
            _V.PASS: "pass",
            _V.FAIL: "fail",
            _V.NO_VERDICT: "no_verdict",
        }[outcome.verdict]
        yield GradeResult(
            instance_id=instance_id,
            verdict=verdict_wire,
            reason=outcome.reason,
        )

    return lambda: grade

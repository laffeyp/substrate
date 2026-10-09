"""The solve-and-grade topology: the swebench solver plus a grade producer on its SelectedPatch.

An evaluation composition, so it lives in assay with the grade producer it adds (lens audit F199:
it sat in `topologies/swebench_solver`, which then imported assay while assay imported the solver,
a package cycle).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .. import api
from ..protocols import Responder
from ..topologies.swebench_solver.assemble import swebench_repair_topology
from ..topologies.swebench_solver.records import GradeResult


def swebench_solve_and_grade_topology(
    *,
    responders: list[Responder] | None = None,
    base_checkout: str,
    issue: str,
    repo_skeleton: str,
    known_files: set[str],
    instance_id: str,
    dataset_name: str,
    model_name: str,
    run_id: str,
    report_dir: Any,
    grade_timeout_seconds: int,
    split: str = "test",
    namespace: str = "swebench",
    n: int = 3,
    max_rounds: int = 2,
    top_k: int = 5,
    firewall_instance: Any = None,
) -> Callable[[api.TopologyBuilder], None]:
    """Sprint 196 (roadmap v2 S6, part 2 of 2): the solve-and-grade topology. Wraps
    `swebench_repair_topology` (which emits `SelectedPatch` after the best-of-N + correction
    loop) and adds a grade producer triggered on `SelectedPatch`. The producer calls
    `run_swebench_one` via `grade_producer_factory` and emits `GradeResult` — the topology
    terminates on `GradeResult` (not `RepairSummary`), so the cell's record carries the
    full solve-through-grade path with one terminal event the oracle projects off.

    The `SwebenchLogProjectionOracle` at `assay/swebench.py::swebench_log_projection_oracle`
    reads the `GradeResult` and returns a `Result` with `replayable=True` for the audit —
    the AUDIT of the grade re-derives from the record deterministically. The GRADE ITSELF
    (pytest inside Docker) remains non-deterministic per the roadmap v2 § "Consequences"
    audit-vs-grade distinction (Sprint 181 correction).

    Every existing arm helper that wires `swebench_repair_topology` remains unchanged; this
    is a new topology consumers opt into. Sprint 196 also lands `swebench_log_projection_oracle`
    in `assay/swebench.py` — the oracle side of the projection.
    """
    from .swebench_grade_producer import grade_producer_factory

    # Build the repair topology's contents onto the same builder; then add the grade producer +
    # trigger + new termination. The nested-call shape (`build_repair(b)`) reuses every producer
    # kind + view + trigger the repair topology declares, keeping the wire form identical.
    build_repair = swebench_repair_topology(
        responders=responders,
        base_checkout=base_checkout,
        issue=issue,
        repo_skeleton=repo_skeleton,
        known_files=known_files,
        n=n,
        max_rounds=max_rounds,
        top_k=top_k,
        firewall_instance=firewall_instance,
    )

    def topo(b: api.TopologyBuilder) -> None:
        build_repair(b)
        b.producer_kind(
            "grader",
            schemas=[GradeResult],
            schema_version=1,
            factory=grade_producer_factory(
                instance_id=instance_id,
                dataset_name=dataset_name,
                model_name=model_name,
                run_id=run_id,
                report_dir=report_dir,
                timeout_seconds=grade_timeout_seconds,
                split=split,
                namespace=namespace,
            ),
            deterministic=False,  # subprocess to Docker + swebench harness; run-and-observe
        )
        b.trigger(
            "grade",
            subscription=api.Subscription(kinds=frozenset({"SelectedPatch"})),
            predicate=lambda ctx: True,
            starts="grader",
            input_builder=lambda ctx: {"model_patch": ctx.event.payload["model_patch"]},
            policy=api.Once(),  # one grade per cell — every future SelectedPatch (there is one) grades once
        )
        # Override the repair topology's `RepairSummary | quiescence` termination with a shape
        # that leaves room for the grader to fire after SelectedPatch. RepairSummary lands
        # BEFORE the grader completes (outcome-ok fires on SelectedPatch, same event that
        # triggers the grader — so RepairSummary races the grade). A pure
        # `threshold_count("RepairSummary", 1)` terminal would race-cancel the grader.
        # Solve_and_grade uses `GradeResult` as the post-solve terminal AND falls back to
        # `quiescence` when no SelectedPatch was ever emitted (Exhausted path —
        # RepairSummary emits but no grade runs; quiescence wins because the topology is idle).
        b.termination(
            api.any_of(
                api.threshold_count("GradeResult", 1),
                api.quiescence(),
            )
        )

    return topo


__all__ = ["swebench_solve_and_grade_topology"]

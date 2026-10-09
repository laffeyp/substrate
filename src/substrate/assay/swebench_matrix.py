# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The SWE-bench matrix — run the backends as Arms over a frozen set and compare them with the real stats.

Each backend (host / container) becomes a one-producer substrate topology: a producer runs the backend's
solve and emits its patch as a `SelectedPatch`. That makes them genuine Arms, so the existing assay control
plane drives everything unchanged — `run_suite` runs each (Arm × Case × Trial), `swebench_record_oracle`
grades the SelectedPatch via the official harness, and `build_report` gives the paired McNemar / two-level
bootstrap + the equivalence power floor (n<~90 can't claim equivalence). The first DEFENSIBLE comparison,
not n=5 anecdotes.

Token/time note: these arms call the model directly (not the metered Responder path), so no `ModelUsage`
lands on the record yet — the report's token totals are 0 for them; the real wall-clock (`elapsed_ms`) IS
measured (it times the whole solve). Wiring metered calls is a later refinement.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any, cast

from .. import api
from ..adapters import OllamaResponder, ProviderQuota, RateLimitedResponder, Responder
from ..adapters.rate_limit import OllamaQuota
from ..topologies.swebench_solver.assemble import swebench_repair_topology
from ..topologies.swebench_solver.firewall import FirewallViolation, firewall_check
from ..topologies.swebench_solver.records import SelectedPatch
from .suite import Arm, Case, Suite
from .swebench import swebench_record_oracle
from .swebench_agent import solve_in_container
from .swebench_host import solve_on_host
from .swebench_suite import PreparedPayload, safe_case_id

_Factory = Callable[[], Any]


def _ollama_quota_from_env() -> ProviderQuota:
    """Read SWEBENCH_OLLAMA_TIER and return the matching ProviderQuota. Default `local`
    (16 concurrent per model) because unset env means "no cloud tier declared, we're
    running locally." Cloud fires MUST set SWEBENCH_OLLAMA_TIER=pro|max explicitly so
    `RateLimitedResponder` caps concurrency at the paid tier's actual limit. Design step 4."""
    tier = os.environ.get("SWEBENCH_OLLAMA_TIER", "local").lower()
    if tier == "free":
        return OllamaQuota.free()
    if tier == "pro":
        return OllamaQuota.pro()
    if tier == "max":
        return OllamaQuota.max_tier()
    if tier == "local":
        return OllamaQuota.local()
    raise SystemExit(
        f"SWEBENCH_OLLAMA_TIER={tier!r} unknown — must be one of free | pro | max | local."
    )


def _wrap_ollama(model: str, quota: ProviderQuota, max_tokens: int) -> Responder:
    """Return an OllamaResponder wrapped in RateLimitedResponder so the per-(provider,
    model) semaphore caps concurrent in-flight requests at the tier's declared limit.
    Every arm's construction routes through here so wrappers for the same model share
    one gate — design DESIGN-2026-08-11-responder-rate-limit.md §"Two things the
    wrapper must do"."""
    inner = OllamaResponder(model, max_tokens=max_tokens)
    return RateLimitedResponder(inner, key=f"ollama:{model}", quota=quota)


def _solve_factory(solve: Callable[[], str]) -> _Factory:
    """A producer that runs `solve()` (a blocking backend call, off-thread) and emits its patch as a
    SelectedPatch. The same factory shape the swebench_solver producers use."""

    async def produce(_inp: Any) -> AsyncIterator[SelectedPatch]:
        patch = await asyncio.to_thread(solve)
        yield SelectedPatch(slot=0, model_patch=patch, reason="backend")

    return lambda: produce


def _backend_topology(solve: Callable[[], str]) -> Callable[[api.TopologyBuilder], None]:
    """A trivial one-producer topology that emits the backend's patch as a SelectedPatch. Terminates the
    instant the patch lands, or on quiescence if the producer ends without one."""

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "solve",
            schemas=[SelectedPatch],
            schema_version=1,
            factory=_solve_factory(solve),
            deterministic=False,
        )
        b.initial("solve", input=None)
        b.termination(
            api.any_of(
                api.threshold_count("SelectedPatch", 1),
                api.quiescence(),
            )
        )

    return topo


def _backend_topology_with_grade(
    solve: Callable[[], str],
    *,
    instance_id: str,
    dataset_name: str,
    model_name: str,
    run_id: str,
    report_dir: Any,
    grade_timeout_seconds: int,
    split: str = "test",
    namespace: str = "swebench",
) -> Callable[[api.TopologyBuilder], None]:
    """Sprint 199d (roadmap v2 S7b follow-on): the backend topology + grade producer.

    Mirrors `swebench_solve_and_grade_topology` for the container/host backend shape:
    a solve producer emits `SelectedPatch`, a trigger fires the grader on that event, and
    the grader calls `run_swebench_one` and emits `GradeResult` (via
    `grade_producer_factory`). Termination is `GradeResult | quiescence` so a solve that
    never lands a patch still finalises cleanly.

    Lets `container_arm` (and `host_arm`) join `SWEBENCH_ARMS=solve_and_grade` mode — the
    log-projection oracle reads GradeResult off the record, no external harness call
    from the oracle. Same discipline as Sprint 196: audit-vs-grade split preserved, grade
    itself remains non-deterministic (pytest inside Docker), the audit re-derives from
    the record."""
    from ..topologies.swebench_solver.records import GradeResult
    from .swebench_grade_producer import grade_producer_factory

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "solve",
            schemas=[SelectedPatch],
            schema_version=1,
            factory=_solve_factory(solve),
            deterministic=False,
        )
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
            deterministic=False,
        )
        b.initial("solve", input=None)
        b.trigger(
            "grade",
            subscription=api.Subscription(kinds=frozenset({"SelectedPatch"})),
            predicate=lambda ctx: True,
            starts="grader",
            input_builder=lambda ctx: {"model_patch": ctx.event.payload["model_patch"]},
            policy=api.Once(),
        )
        b.termination(
            api.any_of(
                api.threshold_count("GradeResult", 1),
                api.quiescence(),
            )
        )

    return topo


def host_arm(name: str, role: str, *, model: str, max_tokens: int = 2048) -> Arm:
    """Host backend as an Arm (model picks a file, edits it, host_clone -> workspace_diff)."""

    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        inst, resp = case.ground_truth, OllamaResponder(model, max_tokens=max_tokens)
        return _backend_topology(lambda: solve_on_host(inst, resp))

    return Arm(name=name, role=role, build=build)


def container_arm(
    name: str, role: str, *, model: str, max_steps: int = 8, max_tokens: int = 2048
) -> Arm:
    """Container backend as an Arm (read/edit/bash agent loop in the locked eval container)."""

    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        inst, resp = case.ground_truth, OllamaResponder(model, max_tokens=max_tokens)
        return _backend_topology(lambda: solve_in_container(inst, resp, max_steps=max_steps))

    return Arm(name=name, role=role, build=build)


def container_solve_and_grade_arm(
    name: str,
    role: str,
    *,
    model: str,
    report_root: Any,
    dataset_name: str,
    model_name: str = "substrate",
    grade_timeout_seconds: int = 1800,
    max_steps: int = 8,
    max_tokens: int = 2048,
    split: str = "test",
    namespace: str = "swebench",
) -> Arm:
    """Sprint 199d (roadmap v2 S7b follow-on): container_arm with an in-topology grade
    producer. Builds `_backend_topology_with_grade` so the topology emits both `SelectedPatch`
    (from the agent loop's patch) and `GradeResult` (from the harness call). Lets
    `container_arm` join `SWEBENCH_ARMS=solve_and_grade` mode under
    `swebench_log_projection_oracle`; pre-Sprint-199d the container arm required
    `SwebenchRecordOracle` and forced the whole matrix off the projection oracle path.

    `run_id` binds (arm, instance) so parallel grades don't collide on `report_dir`;
    matches the shape at `swebench_solve_and_grade_arm`.
    """

    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        inst = case.ground_truth
        resp = OllamaResponder(model, max_tokens=max_tokens)
        instance_id = str(inst["instance_id"]) if isinstance(inst, dict) else str(inst)
        return _backend_topology_with_grade(
            lambda: solve_in_container(inst, resp, max_steps=max_steps),
            instance_id=instance_id,
            dataset_name=dataset_name,
            model_name=model_name,
            run_id=f"{name}-{safe_case_id(instance_id)}",
            report_dir=report_root,
            grade_timeout_seconds=grade_timeout_seconds,
            split=split,
            namespace=namespace,
        )

    return Arm(name=name, role=role, build=build)


def _build_solver_arm_from_payload(
    case: Case,
    models: Sequence[str],
    *,
    n: int,
    max_rounds: int,
    max_tokens: int,
    repro_k: int = 1,
) -> Callable[[api.TopologyBuilder], None]:
    """Common body for every Sprint 159 matrix arm.

    Every arm builds `swebench_repair_topology` — the LIGHT topology (localize + best-of-N
    repair + emit the first patch that applied). `select_exec` and the in-topology
    test-execution apparatus stay OUT: they duplicated the grader's work in-topology,
    doubled per-cell Docker minutes, and produced the 517-silent-fails shape the
    2026-08-10 postmortem records. The graded verdict is what the OFFICIAL swebench
    harness reports; the topology produces a candidate patch, nothing more.

    Sprint 199b (roadmap v2 S7b) retired the `include_test_selection=True` opt-in.
    The heavy topology `swebench_solver_topology_with_test_selection` lives on under
    `_deprecated/` for the record; no live caller reaches it. `swebench_solver_arm`
    (pre-Sprint-197 arm) still uses the heavy path via `solver_topology_from_payload`
    directly — the S7b fold does not touch that separate module boundary.

    Requires the Case to have gone through `prepare_swebench_case` upstream so
    `case.payload` is a populated PreparedPayload. Firewall check at build is a third
    defense layer on top of the prep-time firewall pass; no cost.
    """
    inst = case.ground_truth
    ok, reason = firewall_check(inst)
    if not ok:
        raise FirewallViolation(str(inst.get("instance_id", "?")), reason)
    payload = cast(PreparedPayload, case.payload)
    if "base_checkout" not in payload:
        raise ValueError(
            f"matrix arm on case {case.case_id!r}: `case.payload` is empty. Cases fed into a "
            "sprint-159 matrix arm must go through `prepare_swebench_case` upstream so the "
            "PreparedPayload is populated (image, spec, regression_files, passed_at_base, ...)."
        )
    _ = repro_k  # kept in signature for source-compat with pre-Sprint-199b callers
    quota = _ollama_quota_from_env()
    responders: list[Responder] = [
        _wrap_ollama(models[i % len(models)], quota, max_tokens) for i in range(n)
    ]
    return swebench_repair_topology(
        responders=responders,
        base_checkout=str(payload["base_checkout"]),
        issue=str(payload["issue"]),
        repo_skeleton=str(payload["repo_skeleton"]),
        known_files=set(payload["known_files"]),
        n=n,
        max_rounds=max_rounds,
    )


def swebench_repair_arm(
    name: str,
    *,
    models: Sequence[str],
    n: int,
    max_rounds: int,
    role: str = "full",
    max_tokens: int = 2048,
    repro_k: int = 1,
) -> Arm:
    """The parametric SWE-bench arm factory. Every arm that wraps
    `swebench_repair_topology` at different (models, n, max_rounds) is a call to this
    factory. Structurally distinct arms (`container_arm`, `host_arm`) get their own
    factories because they build a different topology shape.

    Sprint 199b (roadmap v2 S7b) removed the `include_test_selection` parameter — the
    heavy `swebench_solver_topology_with_test_selection` opt-in is retired.

    `n` must be >= 1 — a zero-slot arm has nothing to draft. `repro_k` is the parallel
    reproduction-sample count per candidate (F4 fix, review 2026-08-08)."""
    if n < 1:
        raise ValueError(f"n must be >= 1; got {n}")

    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        return _build_solver_arm_from_payload(
            case,
            list(models),
            n=n,
            max_rounds=max_rounds,
            max_tokens=max_tokens,
            repro_k=repro_k,
        )

    return Arm(name=name, role=role, build=build)


def swebench_matrix_suite(
    instances: Sequence[dict[str, Any]],
    arms: Sequence[Arm],
    *,
    report_root: str,
    dataset_name: str,
    control_arm: str,
    name: str = "swebench-matrix",
    version: str = "0.1",
    equivalence_margin: float = 0.2,
    pass_k: int = 1,
) -> Suite:
    """A frozen SWE-bench Suite over the backend Arms, graded by the record oracle. Cases carry the instance
    as ground_truth; the case_id is the path-safe label."""
    cases = tuple(
        Case(case_id=safe_case_id(inst["instance_id"]), payload={}, ground_truth=inst)
        for inst in instances
    )
    return Suite(
        name=name,
        version=version,
        cases=cases,
        arms=tuple(arms),
        oracle=swebench_record_oracle(report_root=report_root, dataset_name=dataset_name),
        control_arm=control_arm,
        primary_metric="resolved",
        null_rule=(
            "primary endpoint = instances resolved (official held-out grade). A non-control Arm is "
            "compared to the control by paired McNemar + a two-level bootstrap on Delta-pass^k; "
            "'equivalent' requires the CI inside +/-margin AND n at the power floor (~90 at margin .20) — "
            "below it the verdict is 'underpowered', never read as equivalence."
        ),
        equivalence_margin=equivalence_margin,
        pass_k=pass_k,
    )


__all__ = [
    "container_arm",
    "host_arm",
    "swebench_matrix_suite",
    "swebench_repair_arm",
]

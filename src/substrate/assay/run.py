# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The control plane — run each Arm on each Case, grade, collect (Sprint 4 execution).

Each Arm is a normal top-level run at its OWN minted root — not a meta-topology — and the Oracle reads
the resulting record. `embedded_substrate` is for a topology that embeds a sub-substrate; the harness
does not need it. NB: the design doc contradicts itself here — §A1 sketches arms-via-embedded_substrate
with two records, §A5 argues no outer topology. This implementation takes the plain-Runtime path as the
simpler one; the choice is deferred to open-decision §8.3. Do not cite the design as cleanly mandating
either form.

Two TIME axes, kept distinct because conflating them inverts the concurrency benefit: the REAL
elapsed wall-clock of each run (timed around `Runtime.run` — this is where N concurrent Producers show
up as a DROP), and the SUM of per-call inference latencies (a work measure that OVERCOUNTS when calls
overlap, so it must never be read as latency). Tokens and both times are measurements, not a cost
(there is no money here).

Sprint 199 (roadmap v2 S7a) — the assay layer's generic per-cell orchestrator:
`run_suite_with_salvage` runs a Suite over its (arm, case, trial) triples with concurrency,
per-cell wall-clock (`PerCellBudget`), a salvage short-circuit that regrades a finished record
without new model calls, and typed exception classification. The runner writes the JSONL rows via
an `on_outcome` callback — the loop does not own disk. Sprint 199b then rewrites the confirmatory
runner around `run_suite_with_salvage`, cutting it from 1045 lines to ~350.
"""

from __future__ import annotations

import asyncio
import enum
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from msgspec import Struct

from .. import api
from .oracle import Oracle, Result, Verdict
from .suite import Arm, Case, Suite


class CellSource(enum.StrEnum):
    """Sprint 199 (canonical-home move from `assay/cells.py`, SDD vocabulary-as-contract):
    the closed lexicon naming HOW a cell landed on disk. Str-subclass so the wire form on
    cells.jsonl stays `"run"` / `"salvage"` / `"error"` — reader compatibility with every
    existing row is exact. Pre-Sprint-199 the enum lived in `cells.py` and the new
    `run_suite_with_salvage` loop would have retyped the same string literals — the SDD
    Gap 6 shape (2026-08-09 conformance review) recurring under a different filename.
    Moved here because `CellOutcome.source` is its primary consumer; `cells.py` re-exports
    for existing readers of `from .cells import CellSource`.

    - RUN — the topology built + ran, oracle graded; usage/timing measured.
    - SALVAGE — a prior run's record was regraded without new model calls; usage null.
    - ERROR — the cell raised before/around the grade; classifier wrote a typed reason on
      the row. Usage null."""

    RUN = "run"
    SALVAGE = "salvage"
    ERROR = "error"


class UsageTotals(Struct, frozen=True):
    """Per-run token totals + total INFERENCE time, summed from the ModelUsage events on the record.

    `inference_ms` is the SUM of per-call inference latencies — a work/throughput measure, NOT elapsed
    wall-clock: when N model calls run concurrently their per-call latencies OVERLAP, so the sum
    overcounts the real elapsed time and must never be read as latency. The real wall-clock of the
    whole run is `CaseResult.elapsed_ms` (timed around the run), which is where concurrency shows up.
    `estimated` is True if ANY usage on the record was a word-count stand-in rather than provider truth."""

    prompt_tokens: int
    completion_tokens: int
    inference_ms: int  # SUM of per-call inference latencies (work) — NOT elapsed wall-clock
    model_calls: int
    estimated: bool


def _sum_usage(record: Sequence[Mapping[str, Any]]) -> UsageTotals:
    usages = [e["payload"] for e in record if e["kind"] == "ModelUsage"]
    return UsageTotals(
        prompt_tokens=sum(int(u["prompt_tokens"]) for u in usages),
        completion_tokens=sum(int(u["completion_tokens"]) for u in usages),
        inference_ms=sum(
            int(u["wall_ms"]) for u in usages
        ),  # per-call wall_ms summed = work, not latency
        model_calls=len(usages),
        estimated=any(bool(u.get("estimated", False)) for u in usages),
    )


def project_reproduction_for_selected(record: Sequence[Mapping[str, Any]]) -> str:
    """The `reproduction` status the SWE-bench SELECT reported for the winning slot — projected
    off the record for sprint 158's 2x2 vs. held-out grade. Returns one of `"reproduced"` /
    `"resolved"` / `"other"` (the `Reproduction` enum's wire values) or `""` when the record
    carries no `SelectedPatch` or no matching `TestResults` (a coding-assay record, an errored
    run, an Arm that never emitted a patch — all legitimately no-signal states).

    Reads the LAST `SelectedPatch`'s `slot` and matches it to the LAST `TestResults` with the
    same slot — the topology can re-emit both on retry / loop rounds, and only the terminal
    verdict counts. Empty when either is absent."""
    selected = [e["payload"] for e in record if e["kind"] == "SelectedPatch"]
    if not selected:
        return ""
    slot = int(selected[-1].get("slot", -1))
    matching = [
        e["payload"]
        for e in record
        if e["kind"] == "TestResults" and int(e["payload"].get("slot", -2)) == slot
    ]
    if not matching:
        return ""
    return str(matching[-1].get("reproduction", ""))


@dataclass(frozen=True)
class CaseResult:
    """The graded outcome of one Arm running one Case on one Trial, plus the run's token/inference
    totals, the REAL elapsed wall-clock of the run (`elapsed_ms` — the latency axis, where concurrency
    shows up), the root its record sits at (so a reader can open the inner record behind any number),
    and the SWE-bench SELECT's reproduction verdict for the winning slot (sprint 158, projected off
    the record via `project_reproduction_for_selected`). `reproduction` is `""` for coding assays and
    for SWE-bench runs that produced no SelectedPatch / TestResults — a legitimate no-signal state
    that sprint 158's 2x2 aggregation reads as "no repro data for this cell"."""

    arm: str
    role: str
    case_id: str
    trial: int
    result: Result
    usage: UsageTotals
    elapsed_ms: int
    root: str
    reproduction: str = ""


async def run_arm_on_case(
    arm: Arm, case: Case, oracle: Oracle, root: Path | str, *, trial: int = 0
) -> CaseResult:
    """Run one Arm on one Case at `root`: build the topology, run it as a top-level run, grade the
    record with the Oracle. `elapsed_ms` times the actual run (the wall-clock/latency axis); the usage
    totals carry tokens + summed inference time (work). The record stays on disk at `root` as evidence."""
    topology = arm.build(case)
    started = time.monotonic()
    await api.Runtime(root).run(topology)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    record: list[Mapping[str, Any]] = list(api.read_record(root))
    # oracle.grade may be a heavy sync call (SwebenchRecordOracle -> run_swebench_one shells
    # out to Docker for up to `timeout_for_instance` seconds). asyncio.to_thread hands it to
    # the default thread pool so the event loop stays free for sibling cells at CONCURRENCY>1.
    # Trivial oracles (LogProjectionOracle) pay one thread hop, which is negligible.
    result = await asyncio.to_thread(oracle.grade, record, case.ground_truth)
    return CaseResult(
        arm=arm.name,
        role=arm.role,
        case_id=case.case_id,
        trial=trial,
        result=result,
        usage=_sum_usage(record),
        elapsed_ms=elapsed_ms,
        root=str(root),
        reproduction=project_reproduction_for_selected(record),
    )


async def run_suite(suite: Suite, root_dir: Path | str, *, trials: int = 1) -> list[CaseResult]:
    """Run every (Arm, Case, Trial) at a unique minted root and return all CaseResults. Trials repeat
    a (non-deterministic, real-model) Arm to build a distribution; for a deterministic Arm the trials
    are identical, so the per-Arm variance is honestly zero."""
    base = Path(root_dir)
    results: list[CaseResult] = []
    for arm in suite.arms:
        for case in suite.cases:
            for t in range(trials):
                root = base / f"{arm.name}__{case.case_id}__t{t}"
                results.append(await run_arm_on_case(arm, case, suite.oracle, root, trial=t))
    return results


# ── Sprint 199 (roadmap v2 S7a): per-cell budget + generic salvage-mode loop ────────────


class PerCellBudget(Struct, frozen=True):
    """Per-cell wall-clock cap the harness enforces around `run_arm_on_case`.

    `time_s` is the ceiling in seconds; `reason` names the source so a caller reading a NO_VERDICT
    row can trace which knob set the deadline (`per-repo table`, `operator ceiling`, `default`).
    Assay-level primitive — distinct from the kernel `Budget.wall_seconds` cap, which enforces on
    ONE producer instance inside the run. `PerCellBudget` wraps the whole `Runtime.run(topology)`
    call for one cell; a topology can also declare its own per-producer `Budget` for finer control.
    """

    time_s: float
    reason: str = ""


# The classifier callback: given the exception a cell raised, return (typed_reason, halt).
# `halt=True` re-raises out of the loop so `asyncio.gather` propagates and the sweep stops.
# `halt=False` writes the cell as an ERROR outcome and the sweep continues past a flake.
# Runners keep the classifier because the taxonomy is benchmark-specific (SWE-bench distinguishes
# docker_error / git_error / rate_limited / firewall_violation from unclassified). The library
# owns the CONTROL FLOW; the runner owns the TAXONOMY.
CellClassifier = Callable[[BaseException], tuple[str, bool]]

# The row-hook callback: awaited once per completed cell (RUN / SALVAGE / ERROR alike). The runner
# uses it to shape the outcome into its cells-JSONL row and append under a lock. Absent = the loop
# accumulates outcomes and returns them without side effects.
OutcomeHook = Callable[["CellOutcome"], Awaitable[None]]


@dataclass(frozen=True)
class CellOutcome:
    """The outcome of running one (arm, case, trial). Uniform across the three sources: a fresh RUN
    that reached the oracle, a SALVAGE that regraded an existing record, or an ERROR whose exception
    the classifier assigned a typed reason and non-halt disposition.

    `source` narrows what is present: RUN carries `result` + `usage` + `elapsed_ms` + `reproduction`;
    SALVAGE carries `result` (regraded off the record) with `usage=_ZERO` + `elapsed_ms=0`; ERROR
    carries `exception` + `exception_reason` + `halt` and `result` is None. Every outcome carries
    `root` (the record path the loop targeted for this cell), so the runner can label the row and a
    reader can open the underlying record."""

    arm: Arm
    case: Case
    trial: int
    source: CellSource
    root: str
    result: Result | None = None
    usage: UsageTotals | None = None
    elapsed_ms: int = 0
    reproduction: str = ""
    exception: BaseException | None = None
    exception_reason: str = ""
    halt: bool = False
    budget: PerCellBudget | None = None


_ZERO_USAGE = UsageTotals(0, 0, 0, 0, False)


def _default_budget_for_cell(_arm: Arm, _case: Case) -> PerCellBudget:
    """The default cell budget: 30 min per cell, `reason='default'`. Matches the pre-Sprint-199
    `RUN_TIMEOUT=1800` hard-coded ceiling; a runner that needs per-repo timeouts (SWE-bench) passes
    its own callback."""
    return PerCellBudget(time_s=1800.0, reason="default")


async def run_suite_with_salvage(
    suite: Suite,
    root_dir: Path | str,
    *,
    trials: int = 1,
    concurrency: int = 1,
    salvage_dir: Path | str | None = None,
    budget_for_cell: Callable[[Arm, Case], PerCellBudget] | None = None,
    classify_exception: CellClassifier | None = None,
    on_outcome: OutcomeHook | None = None,
    skip: Callable[[Arm, Case, int], bool] | None = None,
) -> list[CellOutcome]:
    """Run a Suite's (arm × case × trial) triples with per-cell wall-clock, optional salvage-mode
    regrade, and typed exception classification. Generic across benchmarks — coding assays, SWE-bench,
    log-projection assays all share this shape (Sprint 199, roadmap v2 S7a).

    - `concurrency` gates concurrent cells via `asyncio.Semaphore`; a Docker-heavy suite runs at
      8, an in-process coding assay runs at CONCURRENCY = cpu_count.
    - `salvage_dir` when set is checked for a per-cell record at `{arm}__{case}__t{trial}`; if the
      record exists, the loop regrades via the suite's oracle with NO model calls and yields a
      SALVAGE outcome. Absent-record cells fall through to a fresh run.
    - `budget_for_cell(arm, case)` returns the `PerCellBudget` the loop wraps around the run. On
      TimeoutError the classifier decides halt-or-continue (a SWE-bench runner classifies as
      `timed_out` and continues; a coding runner may halt).
    - `classify_exception(exc)` returns `(typed_reason, halt)`. `halt=True` re-raises so
      `asyncio.gather` propagates and the sweep aborts with the traceback; `halt=False` emits an
      ERROR outcome and the sweep continues. Absent = every exception halts (the conservative
      default; a runner overrides only when it knows which flakes to skip past).
    - `on_outcome(outcome)` fires once per cell (RUN / SALVAGE / ERROR), awaited under the loop's
      internal lock so the runner can append a JSONL row atomically. Absent = the loop just
      collects outcomes and returns them.
    - `skip(arm, case, trial)` returns True to skip a triple entirely (the resume-from-JSONL
      guard: the runner's `_load_rows` builds the set, `skip` returns True on membership).

    Returns the list of outcomes for cells that ran/salvaged/errored (skipped cells are NOT in the
    list — the caller already has them from disk)."""
    base = Path(root_dir)
    salv_root = Path(salvage_dir) if salvage_dir else None
    budget_fn = budget_for_cell or _default_budget_for_cell
    sem = asyncio.Semaphore(max(1, concurrency))
    lock = asyncio.Lock()
    outcomes: list[CellOutcome] = []

    todo: list[tuple[Arm, Case, int]] = [
        (arm, case, t)
        for arm in suite.arms
        for case in suite.cases
        for t in range(trials)
        if skip is None or not skip(arm, case, t)
    ]

    async def _one(arm: Arm, case: Case, trial: int) -> None:
        async with sem:
            cell_name = f"{arm.name}__{case.case_id}__t{trial}"
            salv: Path | None = (salv_root / cell_name) if salv_root is not None else None
            root = base / cell_name
            budget = budget_fn(arm, case)
            outcome: CellOutcome

            if salv is not None and salv.exists():
                # Salvage: regrade the existing record with NO model calls. A salvage failure is
                # a real bug (the record already exists — either it reads or it does not); the
                # exception surfaces via the classifier just like a fresh-run exception.
                try:
                    events: list[Mapping[str, Any]] = list(api.read_record(salv))
                    grade = suite.oracle.grade(events, case.ground_truth)
                    outcome = CellOutcome(
                        arm=arm,
                        case=case,
                        trial=trial,
                        source=CellSource.SALVAGE,
                        root=str(salv),
                        result=grade,
                        usage=_ZERO_USAGE,
                        reproduction=project_reproduction_for_selected(events),
                        budget=budget,
                    )
                except Exception as exc:  # noqa: BLE001 — the cell boundary: any arm or oracle error is classified into the report or halts the sweep
                    reason, halt = _classify_or_halt(classify_exception, exc)
                    outcome = CellOutcome(
                        arm=arm,
                        case=case,
                        trial=trial,
                        source=CellSource.ERROR,
                        root=str(salv),
                        exception=exc,
                        exception_reason=reason,
                        halt=halt,
                        budget=budget,
                    )
            else:
                try:
                    cr = await asyncio.wait_for(
                        run_arm_on_case(arm, case, suite.oracle, root, trial=trial),
                        timeout=budget.time_s,
                    )
                    outcome = CellOutcome(
                        arm=arm,
                        case=case,
                        trial=trial,
                        source=CellSource.RUN,
                        root=cr.root,
                        result=cr.result,
                        usage=cr.usage,
                        elapsed_ms=cr.elapsed_ms,
                        reproduction=cr.reproduction,
                        budget=budget,
                    )
                except Exception as exc:  # noqa: BLE001 — the cell boundary: any arm or oracle error is classified into the report or halts the sweep
                    reason, halt = _classify_or_halt(classify_exception, exc)
                    outcome = CellOutcome(
                        arm=arm,
                        case=case,
                        trial=trial,
                        source=CellSource.ERROR,
                        root=str(root),
                        exception=exc,
                        exception_reason=reason,
                        halt=halt,
                        budget=budget,
                    )

            async with lock:
                outcomes.append(outcome)
                if on_outcome is not None:
                    await on_outcome(outcome)

            if outcome.source is CellSource.ERROR and outcome.halt:
                # Re-raise the classified-as-halt exception so asyncio.gather propagates and the
                # sweep unwinds with the original traceback (not a synthetic RuntimeError).
                if outcome.exception is None:
                    raise RuntimeError("a halting cell outcome carries no exception")
                raise outcome.exception

    if todo:
        await asyncio.gather(*(_one(a, c, t) for a, c, t in todo))
    return outcomes


def _classify_or_halt(classifier: CellClassifier | None, exc: BaseException) -> tuple[str, bool]:
    """Apply the runner's classifier; absent = every exception halts (the conservative default)."""
    if classifier is None:
        return ("unclassified_error", True)
    return classifier(exc)


def verdict_for_outcome(outcome: CellOutcome) -> Verdict:
    """The wire verdict for a cell outcome: PASS/FAIL from a graded RUN or SALVAGE; NO_VERDICT for
    an ERROR (the topology never produced a definitive answer)."""
    if outcome.result is not None:
        return outcome.result.verdict
    return Verdict.NO_VERDICT

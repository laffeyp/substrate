# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Report + paired statistics — Sprint 4 output.

Per-Arm pass-rate over the Suite; each non-control Arm compared to the control by an EXACT McNemar
test PAIRED across Cases (design §4.6 — pairing removes between-Case variance; the exact binomial
handles the small discordant counts a real run produces). Measurements are reported SEPARATELY:
quality (pass rate), completion tokens, elapsed wall-clock (`elapsed_ms` — the latency axis, where N
concurrent Producers show up as a DROP), and summed inference time (`inference_ms` — a work measure
that overcounts under concurrency, never read as latency). Never fused; none is a cost. The
delta-vs-control is GATED by the control-ran conformance check (Sprint 3): no control on the log, no
delta — the value stays None and the check state says why.

The PRIMARY significance surface is a PAIRED two-level bootstrap on Δ-pass^k (`stats`): resample Cases,
then trials within each Case, so trial-level uncertainty is CARRIED, not collapsed. A TOST equivalence
verdict against the Suite's PRE-REGISTERED margin distinguishes superior / equivalent (CI inside
±margin — a REAL null) / inferior / inconclusive — non-significance is never silently read as "no
effect" (the crack the external review caught). Multiplicity across the arm matrix is controlled by
Benjamini-Hochberg FDR. The exact McNemar p-value is kept as a SECONDARY binary cross-check. The
bootstrap is seeded, so the Report is REPEATABLE (same results -> same CI).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from .conformance import PASS, ControlRanCheck, check_control_ran
from .run import CaseResult
from .stats import DeltaCI, benjamini_hochberg, bootstrap_delta_pass_k
from .suite import Suite
from .swebench import REASON_HARNESS_ERROR


def exact_mcnemar_p(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value over discordant pairs (binomial on min(b, c), p=0.5). b =
    control passed & arm failed; c = control failed & arm passed. n = b + c = 0 -> 1.0 (no evidence)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5**n)
    return min(1.0, 2.0 * tail)


@dataclass(frozen=True)
class ArmReport:
    """One Arm's line in the Report. `delta_vs_control` / `discordant_*` / `p_value` are None for the
    control Arm itself AND whenever the control did not run (gated by the conformance check). `p_value`
    is RAW (uncorrected — see module docstring). `elapsed_ms` is the real wall-clock (latency, where
    concurrency shows up); `inference_ms` is summed per-call latency (work, overcounts under
    concurrency). Token/time totals are separate fields; `estimated_usage` flags them as estimates.

    `model_ensemble_id` + `split_id` (sprint 154, ratified 2026-08-08) qualify the delta so a reader
    knows which (models, dataset split) the number belongs to — a delta is a property of
    (topology, model, split), not the topology alone (Tran & Kiela; docs/benchmarking/benchmarking-design-round2.md).
    Stable strings the run entrypoint reads from the pre-registration file; default empty strings so
    existing callers are unchanged and coding reports without an ensemble/split still print.

    `repro_2x2` + `repro_kappa` + `repro_agreement_rate` (sprint 158) aggregate the SWE-bench
    solver's reproduction verdict for the winning slot vs. the oracle's held-out grade — the number
    that decides whether the model-generated repro is a trustworthy tiebreak, per
    docs/swebench/swebench-solver-design.md §5. The 2x2 keys `resolved_and_passed` /
    `resolved_and_failed` / `reproduced_and_passed` / `reproduced_and_failed` name the intersection
    of (repro verdict, oracle grade); `other`-verdict cells are EXCLUDED (they carry no signal for
    the tiebreak question). `repro_kappa` is Cohen's κ over the 2x2 (chance-corrected agreement —
    the honest number, distinct from raw agreement which COLLAPSES TO THE ORACLE'S PASS RATE
    whenever the repro is constant, giving a repro that always says RESOLVED a spuriously-high
    agreement score anchored to how often the oracle happened to pass). `repro_agreement_rate`
    is the raw diagonal share for continuity. All three are `None` on rows with no repro data
    (coding assays, the pre-158 no-column shape, or SWE-bench cells with all-`other` verdicts)."""

    arm: str
    role: str
    n_cases: int
    passes: int
    pass_rate: (
        float  # pass^k-COLLAPSED reliable-solve rate (a cell counts only if ALL trials passed)
    )
    pass_at_1: float  # per-trial (pass@1) success rate — the OTHER currency; the gap to pass_rate is flakiness
    complete: (
        bool  # graded EVERY suite Case — a verdict is gated on this (no claim off a partial run)
    )
    delta_vs_control: (
        float | None
    )  # pass^k-collapsed Δ (same currency as `passes`) — the harsher, honest one
    discordant_control_only: int | None  # b: control passed, arm failed
    discordant_arm_only: int | None  # c: control failed, arm passed
    p_value: float | None  # exact McNemar (binary) — SECONDARY cross-check
    # PRIMARY surface: paired two-level bootstrap on Δ-pass^k + TOST verdict + BH-FDR. None for the
    # control Arm itself and whenever the control did not run.
    delta_pass_k: float | None  # arm pass^k minus control pass^k (bootstrap point estimate)
    ci_low: float | None
    ci_high: float | None
    bootstrap_p: float | None  # RAW two-sided; `fdr_significant` applies BH across the arm matrix
    equivalence: str | None  # superior | equivalent | inferior | inconclusive (vs the margin)
    fdr_significant: bool | None  # BH-FDR reject across the non-control arms
    completion_tokens: int
    elapsed_ms: int  # real wall-clock summed over the arm's runs — the latency axis
    inference_ms: int  # summed per-call inference time — work, NOT latency
    model_calls: int
    estimated_usage: bool
    model_ensemble_id: str = ""  # sprint 154: names the model set the delta belongs to
    split_id: str = ""  # sprint 154: names the dataset split the delta was measured on
    # sprint 158: SWE-bench repro-vs-oracle 2x2 + Cohen's kappa. All None for rows with no repro
    # data. Defaults keep coding assays and pre-158 callers unchanged.
    repro_2x2: dict[str, int] | None = None
    repro_kappa: float | None = None
    repro_agreement_rate: float | None = None
    # sprint 159: resolve-per-call efficiency (Kapoor & Narayanan 2024, "AI Agents That
    # Matter"). Secondary endpoint alongside the primary pass_rate — an ensemble that beats a
    # baseline while spending 3x the model calls is a compute win, not a mechanism win. The
    # sprint 160 writeup plots this as an efficiency frontier so a caller can distinguish
    # mechanism-driven gains from compute-driven ones. `None` when `model_calls == 0` (no
    # metered calls this run — a salvage/fail cell would set this state per bench_coding
    # semantics); otherwise `passes / model_calls`, the honest denominator.
    resolve_per_call: float | None = None
    # F2 fix (review 2026-08-08): localization diagnostics banked per arm — mean fractional
    # recall over the arm's graded cells + the boolean "full-recall" rate (fraction of cells
    # where the suspect set contained EVERY gold file). Sprint 160-pass2's writeup needs these
    # to attribute a low resolve rate to localization vs repair. `None` on arms whose Results
    # never carried the fields (a coding assay, an arm with no SuspectFiles emit).
    mean_recall_at_k: float | None = None
    full_recall_at_k_rate: float | None = None
    # Design v3 §"The report contract" (ratified 2026-08-10): the three-number headline —
    # N attempted, K resolved (`passes` above), M graded. Resolve rate is K/M; K/N gets a
    # `(M/N graded)` qualifier so a reader sees the gap between attempted and graded before
    # dividing. `n_attempted` is len(suite.cases) — every Case in the pre-registered set,
    # trials collapsed to one cell. `n_no_verdict` counts cells where any trial carried
    # NO_VERDICT (silence at the grader); those cells drop out of the resolve-rate
    # denominator instead of into it. `graded_rate` is (n_attempted - n_no_verdict)/n_attempted.
    n_attempted: int = 0
    n_no_verdict: int = 0
    graded_rate: float = 0.0
    # verdict counts across CELLS (not trials): {"pass", "fail", "no_verdict"}. A cell that is
    # not-yet-run (Arm didn't grade this case) counts under `not_run`. reason_counts is a
    # map from every reason string that appeared on any cell to its count — the shared
    # closed set at assay/swebench._HARNESS_REASONS names the wire form; a reader can count
    # timed_out / container_crashed / harness_error / docker_error / git_error /
    # firewall_violation directly from the report.
    verdict_counts: dict[str, int] = field(default_factory=dict)
    reason_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RunUnpublishable:
    """One arm's below-floor entry in `Report.unpublishable` (Sprint 170, F3 fold; design v3
    § "The report contract"). A confirmatory run whose graded rate on any arm falls below the
    pre-registered floor refuses to publish the delta; this entry names WHICH arm and WHY,
    so a reader sees the completion gap on the report's face instead of inferring it from
    `reason_counts={rate_limited: N}` or similar.

    `arm` — the arm name whose graded rate fell short.
    `graded_rate` — the observed fraction of attempted cells that produced a definitive
        (PASS or FAIL) verdict. Matches `ArmReport.graded_rate`.
    `threshold` — the pre-registered floor the run declared it would meet. From
        `Preregistration.graded_rate_floor` (default 1.0 when no pre-reg is passed, matching
        the pre-Sprint-170 arm-completeness gate).
    `reason` — human-readable naming the gap: e.g. "graded 210 of 300 attempted cells (0.70)
        below pre-registered floor 0.80 — 90 cells carried NO_VERDICT; run is not confirmatory."
    """

    arm: str
    graded_rate: float
    threshold: float
    reason: str


@dataclass(frozen=True)
class Report:
    """The whole comparison. `control_check` is the three-state guard; if it is not `pass`, every
    Arm's delta is None — there is no delta number without a control that ran.

    `unpublishable` (Sprint 170, F3 fold): non-empty when any arm's graded rate fell below the
    pre-registered floor. Every entry names an arm + the gap; the corresponding `ArmReport`'s
    delta / CI / equivalence / fdr fields collapse to None so a downstream reader cannot
    accidentally cite a below-threshold delta as a confirmatory number. A pass-through when
    every arm meets the floor (empty tuple).
    """

    suite: str
    version: str
    primary_metric: str
    null_rule: str
    control_check: ControlRanCheck
    arms: tuple[ArmReport, ...]
    control_arm: str | None = None
    unpublishable: tuple[RunUnpublishable, ...] = ()


def _cell_passed(results: Sequence[CaseResult]) -> bool | None:
    """pass^k reliability for one (Arm, Case) cell: passes iff every trial passed. None if the
    cell has no results (the Arm did not run this Case) OR if any trial carries a NO_VERDICT
    verdict (design v3, ratified 2026-08-10: silence is not fail; a NO_VERDICT cell is
    ungraded and drops out of the resolve-rate denominator, not into it). Old-shape rows read
    off pre-v3 cells never carry NO_VERDICT, so this is a no-op there."""
    from .oracle import Verdict

    if not results:
        return None
    if any(r.result.verdict is Verdict.NO_VERDICT for r in results):
        return None
    return all(r.result.passed for r in results)


@dataclass(frozen=True)
class _Mid:
    """Per-Arm intermediate, computed before BH-FDR (which needs every non-control arm's p at once)."""

    arm: str
    role: str
    n_cases: int
    passes: int
    pass_rate: float
    pass_at_1: float
    complete: bool
    delta_vs_control: float | None
    b: int | None
    c: int | None
    mcnemar_p: float | None
    dci: DeltaCI | None
    completion: int
    elapsed: int
    inference: int
    calls: int
    estimated: bool
    repro_2x2: dict[str, int] | None
    repro_kappa: float | None
    repro_agreement_rate: float | None
    mean_recall_at_k: float | None
    full_recall_at_k_rate: float | None
    n_attempted: int = 0
    n_no_verdict: int = 0
    graded_rate: float = 0.0
    verdict_counts: dict[str, int] = field(default_factory=dict)
    reason_counts: dict[str, int] = field(default_factory=dict)


_REPRODUCED = "reproduced"
_RESOLVED = "resolved"


def _extract_reason(detail: str) -> str:
    """Pull the trailing `reason=<name>` marker out of a Result.detail line (the shape
    `SwebenchRecordOracle.grade` writes when the harness returned NO_VERDICT). Empty string
    if no marker is present; the caller falls back to a safe default."""
    marker = " reason="
    if marker in detail:
        return detail.rsplit(marker, 1)[1].strip()
    return ""


def _repro_aggregate(
    results: Sequence[CaseResult],
) -> tuple[dict[str, int] | None, float | None, float | None]:
    """Aggregate the SWE-bench repro-vs-oracle 2x2 for one arm's CaseResults (sprint 158).

    Keys: `resolved_and_passed` / `resolved_and_failed` / `reproduced_and_passed` /
    `reproduced_and_failed`. Cells with `reproduction == "other"` (or unset — coding rows, pre-158
    rows) are excluded — they carry no signal for the tiebreak question the number answers.

    Cohen's κ:
        p_o = (a+d) / n  (observed agreement — the diagonal)
        p_e = ((a+b)(a+c) + (c+d)(b+d)) / n^2   (chance agreement from the marginals)
        κ = (p_o - p_e) / (1 - p_e)
    Returns `None` on any degenerate case:
      - n == 0 (no repro-signalling cells at all)
      - 1 - p_e == 0 (both marginals collapse to a single row/col — the marginals promise 100%
        chance agreement, so κ is undefined; the classic Cohen 1960 degenerate case)

    Raw agreement rate (a+d)/n is returned alongside κ for continuity. Both are `None` when the
    2x2 itself is `None` (no repro data) so downstream readers can distinguish "no signal" from
    "signal was zero".
    """
    a = b = c = d = 0
    for r in results:
        # Compare against the enum's canonical wire form ONLY (Reproduction.RESOLVED.value =
        # "resolved"; Reproduction.REPRODUCED.value = "reproduced"). Sprint 158 review F2:
        # `.lower()` was hiding a real drift signal (a non-canonical case on the wire is a
        # vocabulary_change_required-shaped event, not a typo the aggregator should paper over).
        # Every WRITER goes through msgspec.to_builtins on a Reproduction enum, so lowercase is
        # the contract; anything else was produced out-of-band and must not enter the 2x2.
        repro = r.reproduction or ""
        if repro == _RESOLVED and r.result.passed:
            a += 1
        elif repro == _RESOLVED and not r.result.passed:
            b += 1
        elif repro == _REPRODUCED and r.result.passed:
            c += 1
        elif repro == _REPRODUCED and not r.result.passed:
            d += 1
        # "other" / "" / any non-canonical value: excluded from the 2x2 (no signal or drift).

    n = a + b + c + d
    if n == 0:
        return None, None, None

    twox2 = {
        "resolved_and_passed": a,
        "resolved_and_failed": b,
        "reproduced_and_passed": c,
        "reproduced_and_failed": d,
    }
    agreement = (a + d) / n
    p_e = ((a + b) * (a + c) + (c + d) * (b + d)) / (n * n)
    if abs(1.0 - p_e) < 1e-12:
        # Marginals collapse to one row or column — chance agreement is 100%, κ undefined. Report
        # the 2x2 + raw agreement, leave κ as None (Cohen 1960 degenerate case).
        return twox2, None, agreement
    kappa = (agreement - p_e) / (1.0 - p_e)
    return twox2, kappa, agreement


def _arm_trial_bools(
    results: Sequence[CaseResult], arm_name: str, case_ids: Sequence[str]
) -> dict[str, list[bool]]:
    """case_id -> per-trial pass booleans for (arm, case), trial-ordered. Cases the Arm never ran are
    omitted, so the bootstrap pairs only Cases both arms graded."""
    out: dict[str, list[bool]] = {}
    for cid in case_ids:
        cell = sorted(
            (r for r in results if r.arm == arm_name and r.case_id == cid), key=lambda r: r.trial
        )
        if cell:
            out[cid] = [r.result.passed for r in cell]
    return out


def build_report(
    suite: Suite,
    results: Sequence[CaseResult],
    *,
    model_ensemble_id: str = "",
    split_id: str = "",
    graded_rate_floor: float | None = None,
) -> Report:
    """Build the paired comparison Report. `model_ensemble_id` and `split_id` (sprint 154) are stamped
    on every ArmReport so a reader can qualify the delta by (topology, model, split). Empty strings
    are the honest default — coding assays without a formal ensemble/split id still print.

    `graded_rate_floor` (Sprint 170, F3 fold; design v3 § "The report contract"): the minimum
    per-arm graded rate for the report to publish a delta. When set, every arm whose
    `graded_rate < floor` produces a `RunUnpublishable` entry in `Report.unpublishable` AND
    has its delta / CI / equivalence / fdr fields collapsed to None. Default `None` preserves
    the pre-Sprint-170 arm-completeness gate exactly (an arm graded on every case is required
    for a delta; anything short → None). Callers with a pre-registration pass the pre-reg's
    `graded_rate_floor` here so the report enforces the pre-declared discipline."""
    check = check_control_ran(results, suite)
    case_ids = [c.case_id for c in suite.cases]

    def cell_map(arm_name: str) -> dict[str, bool | None]:
        return {
            cid: _cell_passed([r for r in results if r.arm == arm_name and r.case_id == cid])
            for cid in case_ids
        }

    # Sprint 201: a solo-arm suite (control_arm is None) skips paired-delta framing entirely.
    # REVIEW-2026-08-28 Q1: the `_has_control` boolean did not narrow `suite.control_arm`
    # from `str | None` to `str` for mypy across the boolean-and-attribute test. Split
    # into an explicit-narrow branch so both accesses see `str`.
    control_arm_name = suite.control_arm
    _has_control = check.state == PASS and control_arm_name is not None
    if _has_control and control_arm_name is not None:
        control_map = cell_map(control_arm_name)
        control_bools = _arm_trial_bools(results, control_arm_name, case_ids)
    else:
        control_map = {}
        control_bools = {}
    # ARM-COMPLETENESS gate: a verdict needs every Case graded in BOTH the arm AND the control
    # — a half-finished run (the live sweep) must not yield a confirmatory delta/CI/verdict.
    # Sprint 170 (F3): the caller may relax "every Case" to "graded_rate >= floor" by passing
    # `graded_rate_floor`. Default `None` preserves the strict gate (floor = 1.0). The
    # `_meets_floor` helper below encodes both regimes in one predicate.
    effective_floor = 1.0 if graded_rate_floor is None else float(graded_rate_floor)
    n_cases_total = len(case_ids)

    def _meets_floor(cells: dict[str, bool | None]) -> bool:
        """True iff the fraction of graded (PASS or FAIL) cells across `case_ids` meets or
        exceeds `effective_floor`. Empty suite trivially meets any floor."""
        if n_cases_total == 0:
            return True
        n_graded = sum(1 for cid in case_ids if cells.get(cid) is not None)
        return (n_graded / n_cases_total) >= effective_floor

    control_meets_floor = _has_control and _meets_floor(control_map)

    mids: list[_Mid] = []
    for arm in suite.arms:
        cells = cell_map(arm.name)
        graded = [cid for cid in case_ids if cells[cid] is not None]
        passes = sum(1 for cid in graded if cells[cid])
        n = len(graded)
        arm_complete = n == len(case_ids)  # this arm graded every Case in the suite
        # Sprint 170 (F3): arm meets the pre-registered floor (or 1.0 by default). This
        # generalizes the pre-Sprint-170 arm_complete gate — at floor=1.0 the two are
        # equivalent; at any looser floor, arm_meets_floor admits arms with some NO_VERDICT
        # cells while still refusing to publish a delta below the pre-declared discipline.
        arm_meets_floor = _meets_floor(cells)
        arm_results = [r for r in results if r.arm == arm.name]

        delta_vs_control: float | None = None
        b_val: int | None = None
        c_val: int | None = None
        p_val: float | None = None
        dci: DeltaCI | None = None
        # GATE: a delta/verdict exists only if the control ran on every Case (check PASS), this is not
        # the control, AND both this arm and the control meet the pre-registered graded-rate floor
        # (default 1.0 = every Case graded, matching the pre-Sprint-170 completeness gate). Any arm
        # below the floor lands in Report.unpublishable and its delta stays None.
        if (
            _has_control
            and arm.name != suite.control_arm
            and arm_meets_floor
            and control_meets_floor
        ):
            # McNemar on the pass^k-collapsed cells — PAIRED over the Cases both arms graded.
            b = c = control_passes = arm_passes = paired = 0
            for cid in case_ids:
                cm = control_map.get(cid)
                am = cells.get(cid)
                if cm is None or am is None:
                    continue
                paired += 1
                control_passes += 1 if cm else 0
                arm_passes += 1 if am else 0
                if cm and not am:
                    b += 1
                elif (not cm) and am:
                    c += 1
            if paired:
                delta_vs_control = (arm_passes - control_passes) / paired
                b_val, c_val, p_val = b, c, exact_mcnemar_p(b, c)
            # PRIMARY: paired two-level bootstrap on Δ-pass^k + TOST verdict (carries trial variance).
            dci = bootstrap_delta_pass_k(
                _arm_trial_bools(results, arm.name, case_ids),
                control_bools,
                k=suite.pass_k,
                margin=suite.equivalence_margin,
                seed=0,
            )

        # sprint 158: repro-vs-oracle 2x2 + kappa across this arm's cells. `_repro_aggregate`
        # returns (None, None, None) when the arm has no repro-signalling cells (coding assays,
        # pre-158 rows, all-`other` verdicts) — the ArmReport fields stay None accordingly.
        twox2, kappa, agree = _repro_aggregate(arm_results)
        # F2 fix (review 2026-08-08): mean recall + full-recall rate across the arm's graded
        # cells. Cells whose Result carries no recall (coding assays, an arm with no
        # SuspectFiles emit) are excluded from the mean; if NO cell carries recall, both stay None.
        recall_vals = [
            r.result.recall_at_k for r in arm_results if r.result.recall_at_k is not None
        ]
        full_vals = [
            r.result.full_recall_at_k for r in arm_results if r.result.full_recall_at_k is not None
        ]
        mean_recall = sum(recall_vals) / len(recall_vals) if recall_vals else None
        full_recall_rate = sum(1 for x in full_vals if x) / len(full_vals) if full_vals else None

        # Design v3 §"The report contract": count verdicts + reasons across this arm's cells.
        # A cell is (arm, case); its verdict is the collapse of its per-trial verdicts:
        # PASS iff every trial PASSed; NO_VERDICT iff any trial is NO_VERDICT; else FAIL.
        # not_run counts cases the arm never ran (topology never started, salvage-only mode).
        from .oracle import Verdict as _V

        cell_verdicts: list[str] = []
        cell_reasons: list[str] = []
        for cid in case_ids:
            trials = [r for r in arm_results if r.case_id == cid]
            if not trials:
                cell_verdicts.append("not_run")
                continue
            if any(r.result.verdict is _V.NO_VERDICT for r in trials):
                cell_verdicts.append(_V.NO_VERDICT.value)
                # Reasons are per-trial; collect every NO_VERDICT trial's reason so the
                # count reads the honest distribution (a cell with two trials, one timed_out
                # one container_crashed, contributes to both reason counts).
                for r in trials:
                    if r.result.verdict is _V.NO_VERDICT:
                        # Reason lives as a first-class field on Result (fold-2026-08-10);
                        # legacy rows without one fall back to the detail-string marker.
                        # Sprint 171 (F4): the final fallback is REASON_HARNESS_ERROR, the
                        # named constant from the shared closed set — never the raw literal.
                        cell_reasons.append(
                            r.result.reason
                            or _extract_reason(r.result.detail)
                            or REASON_HARNESS_ERROR
                        )
                continue
            if all(r.result.passed for r in trials):
                cell_verdicts.append(_V.PASS.value)
            else:
                cell_verdicts.append(_V.FAIL.value)
        verdict_ct = dict(Counter(cell_verdicts))
        reason_ct = dict(Counter(cell_reasons))
        n_attempted_v = len(case_ids)
        n_no_verdict_v = verdict_ct.get(_V.NO_VERDICT.value, 0)
        graded_denom = max(1, n_attempted_v)
        graded_rate_v = (n_attempted_v - n_no_verdict_v) / graded_denom

        mids.append(
            _Mid(
                arm=arm.name,
                role=arm.role,
                n_cases=n,
                passes=passes,
                pass_rate=passes / n if n else 0.0,
                pass_at_1=(sum(1 for r in arm_results if r.result.passed) / len(arm_results))
                if arm_results
                else 0.0,
                complete=arm_complete,
                delta_vs_control=delta_vs_control,
                b=b_val,
                c=c_val,
                mcnemar_p=p_val,
                dci=dci,
                completion=sum(r.usage.completion_tokens for r in arm_results),
                elapsed=sum(r.elapsed_ms for r in arm_results),
                inference=sum(r.usage.inference_ms for r in arm_results),
                calls=sum(r.usage.model_calls for r in arm_results),
                estimated=any(r.usage.estimated for r in arm_results),
                repro_2x2=twox2,
                repro_kappa=kappa,
                repro_agreement_rate=agree,
                mean_recall_at_k=mean_recall,
                full_recall_at_k_rate=full_recall_rate,
                n_attempted=n_attempted_v,
                n_no_verdict=n_no_verdict_v,
                graded_rate=graded_rate_v,
                verdict_counts=verdict_ct,
                reason_counts=reason_ct,
            )
        )

    # BH-FDR across the non-control arms' bootstrap p-values (the multiplicity correction).
    nonctrl = [(i, m.dci) for i, m in enumerate(mids) if m.dci is not None]
    rejects = benjamini_hochberg([dci.p_two_sided for _, dci in nonctrl], alpha=0.05)
    fdr = {nonctrl[j][0]: rejects[j] for j in range(len(nonctrl))}

    arm_reports = tuple(
        ArmReport(
            arm=m.arm,
            role=m.role,
            n_cases=m.n_cases,
            passes=m.passes,
            pass_rate=m.pass_rate,
            pass_at_1=m.pass_at_1,
            complete=m.complete,
            delta_vs_control=m.delta_vs_control,
            discordant_control_only=m.b,
            discordant_arm_only=m.c,
            p_value=m.mcnemar_p,
            delta_pass_k=(m.dci.delta if m.dci else None),
            ci_low=(m.dci.ci_low if m.dci else None),
            ci_high=(m.dci.ci_high if m.dci else None),
            bootstrap_p=(m.dci.p_two_sided if m.dci else None),
            equivalence=(m.dci.verdict if m.dci else None),
            fdr_significant=(fdr.get(i) if m.dci else None),
            completion_tokens=m.completion,
            elapsed_ms=m.elapsed,
            inference_ms=m.inference,
            model_calls=m.calls,
            estimated_usage=m.estimated,
            model_ensemble_id=model_ensemble_id,
            split_id=split_id,
            repro_2x2=m.repro_2x2,
            repro_kappa=m.repro_kappa,
            repro_agreement_rate=m.repro_agreement_rate,
            # sprint 159: passes / model_calls. Zero calls (a salvage/fail cell chain) -> None
            # rather than 0/0 -> ZeroDivisionError; the efficiency-frontier plot in sprint 160
            # then simply omits the point rather than treating "no compute" as "infinite
            # efficiency".
            resolve_per_call=(m.passes / m.calls) if m.calls > 0 else None,
            mean_recall_at_k=m.mean_recall_at_k,
            full_recall_at_k_rate=m.full_recall_at_k_rate,
            n_attempted=m.n_attempted,
            n_no_verdict=m.n_no_verdict,
            graded_rate=m.graded_rate,
            verdict_counts=m.verdict_counts,
            reason_counts=m.reason_counts,
        )
        for i, m in enumerate(mids)
    )

    # Sprint 170 (F3): build the RunUnpublishable tuple naming every arm below the
    # graded_rate_floor. Only fires when the caller explicitly passed a floor — the default
    # (None → floor=1.0) matches the historical arm-completeness gate exactly, and callers
    # that don't opt into the publish-refusal branch see an empty tuple like before.
    unpublishable_entries: tuple[RunUnpublishable, ...] = ()
    if graded_rate_floor is not None:
        entries: list[RunUnpublishable] = []
        floor = float(graded_rate_floor)
        for m in mids:
            if m.graded_rate < floor:
                n_missing = m.n_attempted - (m.n_attempted - m.n_no_verdict)
                # n_missing == m.n_no_verdict; naming both keeps the arithmetic legible in the
                # reason string for a reader without the ArmReport in front of them.
                entries.append(
                    RunUnpublishable(
                        arm=m.arm,
                        graded_rate=m.graded_rate,
                        threshold=floor,
                        reason=(
                            f"graded {m.n_attempted - n_missing} of {m.n_attempted} attempted "
                            f"cells ({m.graded_rate:.3f}) below pre-registered floor "
                            f"{floor:.3f} — {n_missing} cells carried NO_VERDICT; run is not "
                            "confirmatory."
                        ),
                    )
                )
        unpublishable_entries = tuple(entries)

    return Report(
        suite=suite.name,
        version=suite.version,
        primary_metric=suite.primary_metric,
        control_arm=suite.control_arm,
        null_rule=suite.null_rule,
        control_check=check,
        arms=arm_reports,
        unpublishable=unpublishable_entries,
    )

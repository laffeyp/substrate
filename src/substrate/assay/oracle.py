# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The Oracle taxonomy — Sprint 2 of the objective-validation ("assay") layer.

An Oracle grades ONE inner run (an Arm's run on a Case) against that Case's ground truth and returns
a typed Result. The round-1 design (docs/benchmarking/benchmarking-design-round1.md §3) splits Oracles into two
classes, and the split is load-bearing for honesty:

  - LogProjectionOracle — grades by reading a typed terminal-state value off the inner RECORD and
    comparing it to ground truth. No external system runs; the record IS the evidence, so the grade
    re-derives identically on replay. replayable=True.
  - ExternalGraderOracle — grades by running an EXTERNAL system (a test harness, a Docker image, a
    benchmark DB) against the run's output, then recording its verdict. The truth source is an
    external, non-deterministic process (exactly coding_flow's gate), so the grade is a real
    measurement captured ONCE: replay reproduces the orchestration, not this verdict. replayable=False.

The `replayable` flag rides on every Result so a reader can never mistake a run-and-observe grade for
a reproducible one — the honesty the design demands, enforced in the data rather than a comment.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Protocol, runtime_checkable

from msgspec import Struct

# A record is what `substrate.api.read_record` yields: an ordered sequence of envelope dicts, each
# with at least "kind" and "payload". The Oracle reads it; it does not depend on how it was produced.
Envelope = Mapping[str, Any]
Record = Iterable[Envelope]

LOG_PROJECTION = "log-projection"
EXTERNAL_GRADER = "external-grader"


class Verdict(enum.StrEnum):
    """The three-state grade outcome for one inner run (H-1 ratified 2026-08-10; see
    `docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v3.md` and `process/BLACKBOARD.md`
    ## Decisions 2026-08-10). `PASS` and `FAIL` are the ordinary outcomes — the graded run
    produced a definitive verdict. `NO_VERDICT` is the honest third state — the graded run
    completed with no reliable answer (harness timeout, container crash, docker error, harness
    exception). Names `PASS/FAIL` (not `RESOLVED/NOT_RESOLVED`) because `Result` is the general
    assay contract; the enum reads correctly for every oracle class, not only SWE-bench.

    Silence at any grader layer becomes a typed `NO_VERDICT` at the oracle, so the runner and
    the report can count what happened. The old shape rolled harness silence into `passed=False`;
    the 2026-08-10 postmortem records the cost of that shape (517 silent fails on Verified pass
    1). This enum closes the gap at the vocabulary layer."""

    PASS = "pass"  # noqa: S105 — a verdict word, not a credential
    FAIL = "fail"
    NO_VERDICT = "no_verdict"


class Result(Struct, frozen=True):
    """The grade for one inner run against one Case's ground truth.

    `verdict` is the typed outcome (H-1 ratified 2026-08-10) — one of `PASS`, `FAIL`,
    `NO_VERDICT`. `passed` is a derived property returning `verdict is Verdict.PASS` so every
    existing `.passed` reader keeps working; the underlying fact lives in one field, `verdict`.
    `score` is the primary numeric the Report aggregates (1.0/0.0 for a pass/fail oracle, or a
    metric value in [0, 1]); `metric` names what `score` measures ("resolved", "exact_match",
    ...). `oracle_class` and `replayable` record HOW the grade was reached, so a downstream
    Report can label run-and-observe grades honestly. `detail` is a short human-readable note
    (observed vs target, or the external grader's summary; for `NO_VERDICT` it carries the
    reason from the shared `_HARNESS_REASONS` closed set at `assay/swebench.py`).

    `grader_error_band` (sprint 153, ratified 2026-08-08) is the known residual oracle error for
    this benchmark — the fraction of `verdict=PASS` verdicts that are actually incorrect per
    external validation. Xia & Chen (2025, "Are 'Solved Issues' in SWE-bench Really Solved
    Correctly?", arxiv 2503.15223) put ~0.078 on SWE-bench Lite; SWE-Bench+ (Aleithan et al.
    2024, arxiv 2410.06992) reports a considerably larger contamination rate (~0.30) on a
    different axis — cite whichever residual matches the specific claim. SWE-bench Verified is
    ~0.02; SWE-bench-Live is `None` (not published). The value rides on the Result so a headline
    that reports 108 resolved can honestly print `108 ± 0.078 * 108 ≈ 108 ± 8` — a bare `108`
    reads as ground truth when it isn't. `None` = no residual known/asserted for this oracle;
    the reader should not compute an error band. Additive with default `None`; existing callers
    unchanged."""

    score: float
    metric: str
    oracle_class: str
    replayable: bool
    verdict: Verdict = Verdict.NO_VERDICT
    detail: str = ""
    # H-3 first-class (F8/F4-fold, holistic review 2026-08-10): when verdict is NO_VERDICT,
    # `reason` names WHY from the shared closed set at `assay/swebench._HARNESS_REASONS`
    # (timed_out, container_crashed, docker_error, harness_error, git_error,
    # firewall_violation). Empty string on PASS/FAIL. Pre-fold shape encoded reason inside
    # detail via a ` reason=<name>` marker so the row/report layer had to parse a string —
    # a shape leak the N=300 Lite pass caught (harness_error mis-counted for 315
    # firewall_violation rows). One field, one place; no parsing.
    reason: str = ""
    grader_error_band: float | None = None
    # F2 fix (review 2026-08-08, sprint 160): per-instance localization recall for SWE-bench arms.
    # `recall_at_k` = |gold_files ∩ suspect_files| / |gold_files| ∈ [0, 1] — the fractional consensus
    # IR/localization metric. `full_recall_at_k` = gold_files ⊆ suspect_files — the boolean
    # "did the suspect set contain EVERY gold file" that names the localization ceiling on the
    # whole pipeline (you cannot repair a file you never localized, design §5). Computed at
    # grade time by the SWE-bench oracle from the SuspectFiles event on the record + the gold
    # patch's touched files in the harness metadata (neither entered the solver's context).
    # `None` for oracles that don't emit a localization signal (coding assay, log-projection).
    # Design docstring commits this pair — without it, sprint 160-pass2 cannot attribute a low
    # resolve rate to localization vs repair.
    recall_at_k: float | None = None
    full_recall_at_k: bool | None = None

    @property
    def passed(self) -> bool:
        """H-2 (ratified 2026-08-10): derived from `verdict`. `Result.passed` returns True iff
        the verdict is `PASS`; every existing `.passed` reader keeps working. One field, one
        fact — no invariant to maintain by convention across two fields that could drift."""
        return self.verdict is Verdict.PASS


@runtime_checkable
class Oracle(Protocol):
    """Grade one inner run's record against a Case's ground truth -> Result."""

    def grade(self, record: Record, ground_truth: Any) -> Result: ...


class LogProjectionOracle:
    """Deterministic, replayable (design §3, log-projection class).

    Grade by projecting a value off the inner record — a typed terminal-state event the topology put
    on the log — and comparing it to ground truth. `extract` pulls the observed value from the record
    (e.g. the FinalAnswer text, a final-state event); `compare` decides pass (default: equality). No
    external system, so the grade is a pure function of the record and re-derives on replay."""

    def __init__(
        self,
        *,
        extract: Callable[[list[Envelope]], Any],
        metric: str = "match",
        compare: Callable[[Any, Any], bool] | None = None,
    ) -> None:
        self._extract = extract
        self._metric = metric
        self._compare: Callable[[Any, Any], bool] = compare or (
            lambda observed, target: bool(observed == target)
        )

    def grade(self, record: Record, ground_truth: Any) -> Result:
        envelopes = list(record)
        observed = self._extract(envelopes)
        passed = self._compare(observed, ground_truth)
        return Result(
            verdict=Verdict.PASS if passed else Verdict.FAIL,
            score=1.0 if passed else 0.0,
            metric=self._metric,
            oracle_class=LOG_PROJECTION,
            replayable=True,
            detail=f"observed={observed!r} target={ground_truth!r}",
        )


class ExternalGraderOracle:
    """Run-and-observe, NOT replayable (design §3, external-grader class).

    Grade by running an EXTERNAL system against the run's output and reading its verdict. `grader`
    receives the inner record and the Case ground truth, runs the external process (a test harness, a
    Docker image, a benchmark DB), and returns (passed, detail). The truth source is external and
    non-deterministic, so the grade is captured once; the Result is stamped replayable=False so it is
    never mistaken for a reproducible log-projection grade."""

    def __init__(
        self,
        *,
        grader: Callable[[list[Envelope], Any], tuple[bool, str]],
        metric: str,
    ) -> None:
        self._grader = grader
        self._metric = metric

    def grade(self, record: Record, ground_truth: Any) -> Result:
        envelopes = list(record)
        passed, detail = self._grader(envelopes, ground_truth)
        return Result(
            verdict=Verdict.PASS if passed else Verdict.FAIL,
            score=1.0 if passed else 0.0,
            metric=self._metric,
            oracle_class=EXTERNAL_GRADER,
            replayable=False,
            detail=detail,
        )

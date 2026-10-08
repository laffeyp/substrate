# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The 17-check conformance suite — the v1.0 release gate (product §7; CT-5 spine).

Each check builds the smallest canonical topology that exercises one product-§7 property,
runs it, and asserts the property over the resulting RECORD (the product surface), returning
a typed CheckResult. Most properties are already proven per-wave in the test suite; this
module ASSEMBLES them behind one runnable gate (`substrate conformance`).

Three-state status — honesty over green-ness (the whole point of the A1 amendment):
  - PASS     the property holds.
  - FAIL     the property does not hold (the suite, and the CLI, exit non-zero).
  - DEFERRED the check is an explicit, spec-amended deferral (check 6, Level-3b byte-identity
             — product amendment A1.1). A DEFERRED check is NOT a pass and NOT a fail: it is
             surfaced distinctly, and the release-gate caller decides (v1.0 ships with
             check 6 deferred per A1.1). A deferred check must NEVER read as green — that is
             exactly the silent-pass the amendment exists to prevent.

The suite is pure-async and self-contained (it constructs its own topologies in a temp
dir); `substrate conformance` drives it via the CLI.
"""

from __future__ import annotations

import enum
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from msgspec import Struct

# Direct concrete-module imports (NOT via substrate.api): conformance is an internal module,
# and importing api here would form a cycle (api re-exports run_conformance for the CLI).
from ..constants import (
    INPUT_BUILD_FAILED,
    PREDICATE_QUARANTINED,
    PRODUCER_COMPLETED,
    PRODUCER_EMITTED_INVALID,
    PRODUCER_FAILED,
    PRODUCER_STARTED,
    RUN_FINALISED,
    TERMINATION_MATCHED,
    TRIGGER_FIRED,
)
from ..kernel.composition import embedded_substrate
from ..errors import BusLockedError, ProducerNotFound
from ..projections.inspect import first_divergence, trace_ancestry, view_at
from ..kernel.policies import Decision, TerminationPolicy, quiescence_with_watchdog, threshold_count
from ..constants import RunStatus
from ..projections.replay import replay
from ..record.record import read_record
from ..kernel.runtime import Runtime
from ..kernel.triggers import Once, PerEvent
from ..types import Subscription
from ..kernel.views import KindCount


class Status(enum.Enum):
    """The outcome of one conformance check: PASS, FAIL, DEFERRED (spec-amended "not shippable
    in v1.0" — only check 6's Level-3b clause, A1.1), or SKIPPED (not exercised on this
    invocation, e.g. check 15 under --no-perf). DEFERRED and SKIPPED are deliberately distinct
    so a skip never reads as a ruled deferral."""

    PASS = "PASS"
    FAIL = "FAIL"
    # DEFERRED is reserved for a SPEC-AMENDED deferral (check 6's Level-3b clause, A1.1) — a
    # real, ruled "not shippable in v1.0" state. SKIPPED is for a run-time skip (e.g. check 15
    # under --no-perf) — NOT spec-amended, just not exercised on this invocation. Keeping them
    # distinct so a --no-perf skip never reads as the spec-amended deferral (review #5 FIX B).
    DEFERRED = "DEFERRED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class CheckResult:
    number: int
    name: str
    status: Status
    detail: str


@dataclass(frozen=True)
class ConformanceReport:
    results: tuple[CheckResult, ...]

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status is Status.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status is Status.FAIL)

    @property
    def deferred(self) -> int:
        return sum(1 for r in self.results if r.status is Status.DEFERRED)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status is Status.SKIPPED)

    @property
    def all_non_failing(self) -> bool:
        """True iff no check FAILED (deferred/skipped checks do not fail the gate — but they
        are reported DISTINCTLY; the release-gate caller owns the deferred/skipped policy)."""
        return self.failed == 0


# ── shared fixtures ────────────────────────────────────────────────────────────
class CountReached(Struct, frozen=True):
    n: int


class FailReason(Struct, frozen=True):
    reason: str


async def _counter(_input: Any) -> Any:
    for n in range(1, 4):
        yield CountReached(n=n)


def _basic_topo(b: Any) -> None:
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: _counter)
    b.initial("counter", input=None)
    b.termination(threshold_count(PRODUCER_COMPLETED, 1))


# ── the checks (each returns a CheckResult) ─────────────────────────────────────
async def _check_1_retry_enrichment(root: Path) -> CheckResult:
    # A Trigger fired by ProducerFailed sees the failure reason staged from the same event.
    async def failing(_input: Any) -> Any:
        raise RuntimeError("boom")
        yield  # pragma: no cover

    async def retrier(inp: Any) -> Any:
        yield CountReached(n=len(str(inp.get("reason", "") if hasattr(inp, "get") else "")))

    def topo(b: Any) -> None:
        b.producer_kind("p", schemas=[CountReached], schema_version=1, factory=lambda: failing)
        b.producer_kind("retry", schemas=[CountReached], schema_version=1, factory=lambda: retrier)
        b.initial("p", input=None)
        b.trigger(
            "on-fail",
            subscription=Subscription(kinds=frozenset({PRODUCER_FAILED})),
            predicate=lambda ctx: True,
            starts="retry",
            input_builder=lambda ctx: {"reason": ctx.event.payload.get("error", "")},
            policy=PerEvent(),
        )
        b.termination(quiescence_with_watchdog(seconds=2))

    await Runtime(root).run(topo)
    envs = list(read_record(root))
    failed = [e for e in envs if e["kind"] == PRODUCER_FAILED]
    fired = [
        e
        for e in envs
        if e["kind"] == TRIGGER_FIRED and e["payload"].get("trigger_id") == "on-fail"
    ]
    # §7 check 1: the retry Trigger must see the failure reason STAGED FROM THE SAME EVENT —
    # not merely fire. The input_builder reads event.payload["error"]; assert that the failed
    # producer's error reached the retry's RECORDED resolved input (the enrichment is on the
    # log, citable), not just that a firing happened.
    if failed and fired:
        failure_error = failed[0]["payload"].get("error", "")
        resolved = fired[0]["payload"].get("resolved_input") or {}
        if isinstance(resolved, dict) and resolved.get("reason") == failure_error and failure_error:
            return CheckResult(
                1,
                "Retry enrichment",
                Status.PASS,
                "retry firing's resolved input carried the failure reason from the same event",
            )
        return CheckResult(
            1,
            "Retry enrichment",
            Status.FAIL,
            f"firing did not carry the failure reason: {resolved!r}",
        )
    return CheckResult(1, "Retry enrichment", Status.FAIL, "no retry firing on ProducerFailed")


async def _check_2_single_cascade(root: Path) -> CheckResult:
    # Cascade order is total + recorded; resolved inputs recorded in TriggerFired.
    async def doubler(inp: Any) -> Any:
        yield CountReached(n=inp["n"] * 2)

    def topo(b: Any) -> None:
        b.producer_kind(
            "counter", schemas=[CountReached], schema_version=1, factory=lambda: _counter
        )
        b.producer_kind(
            "doubler", schemas=[CountReached], schema_version=1, factory=lambda: doubler
        )
        b.initial("counter", input=None)
        b.trigger(
            "double",
            subscription=Subscription(kinds=frozenset({"CountReached"})),
            predicate=lambda ctx: ctx.event.payload["n"] == 1,
            starts="doubler",
            input_builder=lambda ctx: {"n": ctx.event.payload["n"]},
            policy=Once(),
        )
        b.termination(quiescence_with_watchdog(seconds=2))

    await Runtime(root).run(topo)
    envs = list(read_record(root))
    seqs = [e["seq"] for e in envs]
    fired = [
        e for e in envs if e["kind"] == TRIGGER_FIRED and e["payload"].get("trigger_id") == "double"
    ]
    if seqs == list(range(len(seqs))) and len(fired) == 1 and "input_sha256" in fired[0]["payload"]:
        return CheckResult(
            2, "Single legal cascade", Status.PASS, "dense seq; one firing; input hash recorded"
        )
    return CheckResult(
        2, "Single legal cascade", Status.FAIL, f"seqs={seqs[:5]}.. fired={len(fired)}"
    )


async def _check_3_backpressure(root: Path) -> CheckResult:
    # N+1 appends through a bound-1 admission queue all complete; log intact.
    await Runtime(root, admission=1).run(_basic_topo)
    counted = [e for e in read_record(root) if e["kind"] == "CountReached"]
    if [e["payload"]["n"] for e in counted] == [1, 2, 3]:
        return CheckResult(3, "Backpressure liveness", Status.PASS, "all emissions through bound-1")
    return CheckResult(3, "Backpressure liveness", Status.FAIL, "emissions lost under bound-1")


async def _check_4_invalid_emission(root: Path) -> CheckResult:
    class Undeclared(Struct, frozen=True):
        x: int

    async def bad(_input: Any) -> Any:
        yield Undeclared(x=1)

    def topo(b: Any) -> None:
        b.producer_kind("p", schemas=[CountReached], schema_version=1, factory=lambda: bad)
        b.initial("p", input=None)
        b.termination(quiescence_with_watchdog(seconds=2))

    await Runtime(root).run(topo)
    envs = list(read_record(root))
    inv = [e for e in envs if e["kind"] == PRODUCER_EMITTED_INVALID]
    if (
        inv
        and inv[0]["payload"]["reason"] == "unknown_kind"
        and not any(e["kind"] == "Undeclared" for e in envs)
    ):
        return CheckResult(
            4, "Invalid-emission cascade", Status.PASS, "undeclared kind -> sequenced invalid event"
        )
    return CheckResult(4, "Invalid-emission cascade", Status.FAIL, "invalid emission not recorded")


async def _check_5_quiescence(root: Path) -> CheckResult:
    # A logical-cooldown run finalises via quiescence-with-watchdog.
    result = await Runtime(root).run(_basic_topo)
    envs = list(read_record(root))
    if result.status == RunStatus.FINALISED and envs[-1]["kind"] == RUN_FINALISED:
        return CheckResult(
            5, "Quiescence", Status.PASS, "logical-cooldown run finalised on quiescence"
        )
    return CheckResult(5, "Quiescence", Status.FAIL, f"status={result.status}")


async def _check_6_replay_roundtrip(root: Path) -> CheckResult:
    # The deferral is SCOPED to the Level-3(b) byte-identity clause ONLY (spec amendment
    # A1.1 — needs a t-replay writer). Level 2 SHIPS and MUST pass: it reproduces every
    # decision + resolved input. So a genuine Level-2 mismatch here is a FAIL (review #5
    # FIX A) — NOT masked as DEFERRED; only the 3(b) clause is deferred.
    await Runtime(root).run(_basic_topo)
    r2 = replay(root, level="2")
    if r2.mismatches:
        return CheckResult(
            6,
            "Replay round-trip",
            Status.FAIL,
            f"Level 2 (which SHIPS, not deferred) had {len(r2.mismatches)} mismatch(es): "
            f"first at seq {r2.mismatches[0].seq}",
        )
    try:
        replay(root, level="3b")
        # 3b returning instead of raising would mean it shipped — that is NOT the deferred
        # state and would be a real surprise; flag it rather than silently calling it deferred.
        return CheckResult(
            6, "Replay round-trip", Status.FAIL, "Level 3(b) unexpectedly did not defer"
        )
    except NotImplementedError:
        pass
    # Level 2 PASSED; only the 3(b) byte-identity clause is deferred (A1.1).
    return CheckResult(
        6,
        "Replay round-trip",
        Status.DEFERRED,
        f"Level 2 PASSED ({r2.decisions_verified} decisions verified); "
        f"Level 3(b) byte-identity deferred (spec amendment A1.1)",
    )


async def _check_7_export_boundary(root: Path) -> CheckResult:
    class OuterTick(Struct, frozen=True):
        n: int

    def inner(b: Any) -> None:
        b.producer_kind(
            "counter", schemas=[CountReached], schema_version=1, factory=lambda: _counter
        )
        b.initial("counter", input=None)
        b.termination(threshold_count(PRODUCER_COMPLETED, 1))

    inner_root = root.parent / "c7-inner"

    def outer(b: Any) -> None:
        b.producer_kind(
            "embedded",
            schemas=[OuterTick],
            schema_version=1,
            factory=lambda: embedded_substrate(inner, exports={"CountReached": OuterTick}),
        )
        b.initial("embedded", input={"inner_root": str(inner_root)})
        b.termination(quiescence_with_watchdog(seconds=2))

    await Runtime(root).run(outer)
    outer_kinds = [e["kind"] for e in read_record(root)]
    crossed = [e for e in read_record(root) if e["kind"] == "OuterTick"]
    if crossed and "CountReached" not in outer_kinds:
        return CheckResult(
            7, "Export boundary", Status.PASS, "only mapped kinds crossed; inner kinds did not"
        )
    return CheckResult(7, "Export boundary", Status.FAIL, "boundary leaked or dropped mapped kinds")


async def _check_8_quarantine(root: Path) -> CheckResult:
    def slow_pred(ctx: Any) -> bool:
        time.sleep(0.0005)  # ~500us, over the 100us budget
        return False

    def topo(b: Any) -> None:
        b.producer_kind(
            "counter", schemas=[CountReached], schema_version=1, factory=lambda: _counter
        )
        b.producer_kind("noop", schemas=[CountReached], schema_version=1, factory=lambda: _counter)
        b.initial("counter", input=None)
        b.trigger(
            "slow",
            subscription=Subscription(kinds=frozenset({"CountReached"})),
            predicate=slow_pred,
            starts="noop",
            input_builder=lambda ctx: None,
            policy=PerEvent(),
        )
        # §7 check 8 requires "a TerminationPolicy that ESCALATES on it" — finalise the run
        # the moment a PredicateQuarantined lands (escalation driven by the quarantine, not by
        # quiescence). This proves the quarantine is matchable by a policy, not just visible.
        b.termination(
            TerminationPolicy(
                "escalate_on_quarantine",
                lambda c: (
                    Decision.FINALISE_RUN
                    if c.counts(PREDICATE_QUARANTINED) >= 1
                    else Decision.CONTINUE
                ),
            )
        )

    await Runtime(root).run(topo)
    envs = list(read_record(root))
    q = [e for e in envs if e["kind"] == PREDICATE_QUARANTINED]
    tm = [e for e in envs if e["kind"] == TERMINATION_MATCHED]
    quarantined_ok = bool(q) and q[0]["payload"]["reason"] == "budget" and q[0]["payload"]["k"] == 3
    # the escalation: a TerminationMatched (the escalate-on-quarantine policy) appears AFTER
    # the quarantine, and the run finalised because of it.
    escalated = bool(tm) and bool(q) and tm[0]["seq"] > q[0]["seq"]
    if quarantined_ok and escalated:
        return CheckResult(
            8,
            "Quarantine visibility",
            Status.PASS,
            "over-budget predicate quarantined after k=3; TerminationPolicy escalated on it",
        )
    return CheckResult(
        8,
        "Quarantine visibility",
        Status.FAIL,
        f"quarantine_ok={quarantined_ok} escalated={escalated}",
    )


async def _check_9_determinism(root: Path) -> CheckResult:
    # Same record replayed twice at Level 1/2 is byte-identical (N-DET-1) — and two runs of the
    # same deterministic topology are D-8-equivalent.
    await Runtime(root).run(_basic_topo)
    r_a = replay(root, level="1")
    r_b = replay(root, level="1")
    second = root.parent / "c9-b"
    await Runtime(second).run(_basic_topo)
    if r_a.counts == r_b.counts and first_divergence(root, second) is None:
        return CheckResult(9, "Determinism", Status.PASS, "replay stable; two runs D-8-equivalent")
    return CheckResult(9, "Determinism", Status.FAIL, "replay or D-8 equivalence broken")


async def _check_10_locking(root: Path) -> CheckResult:
    from ..record import locking

    persist = root.parent / "c10-persist"
    fd = locking.acquire_lock(persist, start_time=time.time())
    try:
        Runtime(persist, persistent=True)  # construction is fine; run() acquires
        try:
            await Runtime(persist, persistent=True).run(_basic_topo)
            return CheckResult(
                10, "Persistent-bus locking", Status.FAIL, "second runtime did not fail fast"
            )
        except BusLockedError:
            return CheckResult(
                10,
                "Persistent-bus locking",
                Status.PASS,
                "second runtime failed fast (BusLockedError)",
            )
    finally:
        locking.release_lock(fd)


async def _check_11_provenance(root: Path) -> CheckResult:
    async def doubler(inp: Any) -> Any:
        yield CountReached(n=inp["n"] * 2)

    def topo(b: Any) -> None:
        b.producer_kind(
            "counter", schemas=[CountReached], schema_version=1, factory=lambda: _counter
        )
        b.producer_kind(
            "doubler", schemas=[CountReached], schema_version=1, factory=lambda: doubler
        )
        b.initial("counter", input=None)
        b.trigger(
            "d",
            subscription=Subscription(kinds=frozenset({"CountReached"})),
            predicate=lambda ctx: True,
            starts="doubler",
            input_builder=lambda ctx: {"n": ctx.event.payload["n"]},
            policy=PerEvent(),
        )
        b.termination(quiescence_with_watchdog(seconds=2))

    await Runtime(root).run(topo)
    envs = list(read_record(root))
    started = [e for e in envs if e["kind"] == PRODUCER_STARTED]
    try:
        for st in started:
            inst = st["payload"]["producer"]["instance"]
            chain = trace_ancestry(root, inst)
            if chain[-1].cause != "RunStarted":
                return CheckResult(
                    11, "Provenance closure", Status.FAIL, f"{inst} does not trace to RunStarted"
                )
    except ProducerNotFound as exc:
        return CheckResult(11, "Provenance closure", Status.FAIL, f"dangling producer: {exc}")
    return CheckResult(
        11, "Provenance closure", Status.PASS, f"all {len(started)} producers trace to RunStarted"
    )


async def _check_12_view_at(root: Path) -> CheckResult:
    await Runtime(root).run(_basic_topo)
    envs = list(read_record(root))
    cr_seqs = [e["seq"] for e in envs if e["kind"] == "CountReached"]
    at_2 = view_at(root, cr_seqs[1], KindCount("CountReached"))
    at_last = view_at(root, max(e["seq"] for e in envs), KindCount("CountReached"))
    if at_2 == 2 and at_last == 3:
        return CheckResult(
            12, "View-at fidelity", Status.PASS, "view_at folds match observed counts"
        )
    return CheckResult(
        12, "View-at fidelity", Status.FAIL, f"view_at(2)={at_2} view_at(last)={at_last}"
    )


async def _check_13_divergence(root: Path) -> CheckResult:
    async def from_list(inp: Any) -> Any:
        for n in inp["values"]:
            yield CountReached(n=n)

    def topo(values: list[int]) -> Callable[[Any], None]:
        def t(b: Any) -> None:
            b.producer_kind(
                "c", schemas=[CountReached], schema_version=1, factory=lambda: from_list
            )
            b.initial("c", input={"values": values})
            b.termination(threshold_count(PRODUCER_COMPLETED, 1))

        return t

    b_root = root.parent / "c13-b"
    await Runtime(root).run(topo([1, 2, 3]))
    await Runtime(b_root).run(topo([1, 2, 99]))
    div = first_divergence(root, b_root)
    if div is not None and div.hash_a != div.hash_b:
        return CheckResult(
            13,
            "Divergence localization",
            Status.PASS,
            f"localized at index {div.index} (seq {div.seq})",
        )
    return CheckResult(
        13, "Divergence localization", Status.FAIL, "perturbed decision not localized"
    )


async def _check_14_diagnostic_invariance(root: Path) -> CheckResult:
    on_root = root.parent / "c14-on"
    await Runtime(root).run(_basic_topo)
    await Runtime(on_root, diagnostics=True).run(_basic_topo)
    if first_divergence(root, on_root) is None:
        return CheckResult(
            14, "Diagnostic invariance", Status.PASS, "bus D-8-identical with diagnostics on/off"
        )
    return CheckResult(14, "Diagnostic invariance", Status.FAIL, "diagnostics perturbed the bus")


async def _check_15_perf(root: Path) -> CheckResult:
    # A LIGHTWEIGHT floor probe (the full pytest-benchmark gate + regression-vs-previous-tag
    # is the dedicated benchmark, test_perf.py). Here: measure append throughput at the
    # F-PRED-1 filtered reference shape and report the REAL number. v1.0 first release has no
    # previous tag, so the regression clause is N/A; the floor is the gate. Honest: if the
    # floor is not met on THIS hardware, FAIL with the measured rate (do not fudge).
    # Floor = 40,000 appends/sec per product amendment A2.1 (the original 100K was derived from
    # a prototype that did not measure the required RFC-8785 canonical encoding; recalibrated
    # to a ~28% margin under the measured ~56K). The dominant per-append cost is the
    # pure-Python rfc8785 encoder (D-7-required, unchanged); a compiled JCS encoder is the
    # post-1.0 lever if a deterministic firehose ever needs more.
    from .conformance_perf import measure_append_rate

    rate, n = await measure_append_rate(root)
    floor = 40_000  # product amendment A2.1 (was 100K)
    if rate >= floor:
        return CheckResult(
            15,
            "Performance floor (N-PERF-1)",
            Status.PASS,
            f"{rate:,.0f} appends/sec (n={n}, floor {floor:,})",
        )
    return CheckResult(
        15,
        "Performance floor (N-PERF-1)",
        Status.FAIL,
        f"{rate:,.0f} appends/sec < floor {floor:,} on this hardware (n={n}) — measured, not fudged",
    )


async def _check_16_torn_tail(root: Path) -> CheckResult:
    await Runtime(root).run(_basic_topo)
    hot = next(p for p in root.glob("events-*.jsonl"))
    data = hot.read_bytes()
    # truncate mid-final-frame (simulate a crash): keep all but the last 5 bytes of the tail
    lines = data.splitlines(keepends=True)
    torn = b"".join(lines[:-1]) + lines[-1][:-5]
    hot.write_bytes(torn)
    recovered = list(read_record(root))
    # §7 check 16: recover to EXACTLY the last complete frame, AND replay Levels 1 AND 2
    # SUCCEED on the recovered record. Assert both levels (not just Level 1).
    r1 = replay(recovered, level="1")
    r2 = replay(recovered, level="2")
    recovered_exactly = r1.frame_count == len(recovered) and len(recovered) == len(lines) - 1
    levels_ok = r1.frame_count == len(recovered) and not r2.mismatches
    if recovered_exactly and levels_ok:
        return CheckResult(
            16,
            "Torn-tail recovery",
            Status.PASS,
            f"recovered to last complete frame ({len(recovered)}); replay Levels 1+2 succeed",
        )
    return CheckResult(
        16,
        "Torn-tail recovery",
        Status.FAIL,
        "did not recover to last complete frame / replay failed",
    )


async def _check_17_input_build_failed(root: Path) -> CheckResult:
    async def producer_ok(_input: Any) -> Any:
        yield CountReached(n=1)

    def topo(b: Any) -> None:
        b.producer_kind("a", schemas=[CountReached], schema_version=1, factory=lambda: producer_ok)
        b.producer_kind("c", schemas=[CountReached], schema_version=1, factory=lambda: producer_ok)
        b.initial("a", input=None)

        def _raise(ctx: Any) -> Any:
            raise ValueError("input builder boom")

        b.trigger(
            "t",
            subscription=Subscription(kinds=frozenset({"CountReached"})),
            predicate=lambda ctx: True,
            starts="c",
            input_builder=_raise,
            policy=PerEvent(),
        )
        b.termination(quiescence_with_watchdog(seconds=2))

    await Runtime(root).run(topo)
    envs = list(read_record(root))
    ibf = [
        e for e in envs if e["kind"] == INPUT_BUILD_FAILED and e["payload"].get("trigger_id") == "t"
    ]
    started_c = [
        e for e in envs if e["kind"] == PRODUCER_STARTED and e["payload"]["producer"]["kind"] == "c"
    ]
    if ibf and not started_c:
        return CheckResult(
            17,
            "InputBuildFailed visibility",
            Status.PASS,
            "input_builder raise -> sequenced event; no Producer started",
        )
    return CheckResult(
        17,
        "InputBuildFailed visibility",
        Status.FAIL,
        "InputBuildFailed not recorded or Producer started",
    )


_CHECKS: tuple[Callable[[Path], Awaitable[CheckResult]], ...] = (
    _check_1_retry_enrichment,
    _check_2_single_cascade,
    _check_3_backpressure,
    _check_4_invalid_emission,
    _check_5_quiescence,
    _check_6_replay_roundtrip,
    _check_7_export_boundary,
    _check_8_quarantine,
    _check_9_determinism,
    _check_10_locking,
    _check_11_provenance,
    _check_12_view_at,
    _check_13_divergence,
    _check_14_diagnostic_invariance,
    _check_15_perf,
    _check_16_torn_tail,
    _check_17_input_build_failed,
)


async def run_conformance(*, include_perf: bool = True) -> ConformanceReport:
    """Run all 17 conformance checks, each in its own temp record root. Returns a typed
    report; the caller (the CLI / CI) decides the exit policy. `include_perf=False` skips the
    perf floor probe (check 15) — used where the dedicated benchmark covers it."""
    results: list[CheckResult] = []
    with tempfile.TemporaryDirectory(prefix="substrate-conformance-") as tmp:
        base = Path(tmp)
        for i, check in enumerate(_CHECKS, start=1):
            if i == 15 and not include_perf:
                # SKIPPED (run-time skip), NOT DEFERRED (spec-amended) — a --no-perf skip is
                # not a ruled deferral (review #5 FIX B). The default `substrate conformance`
                # (no --no-perf) DOES run it and FAILs honestly if the floor is unmet.
                results.append(
                    CheckResult(
                        15,
                        "Performance floor (N-PERF-1)",
                        Status.SKIPPED,
                        "skipped on this invocation (--no-perf); the dedicated benchmark + the "
                        "default `substrate conformance` measure it for real",
                    )
                )
                continue
            root = base / f"check-{i:02d}"
            try:
                results.append(await check(root))
            except Exception as exc:  # a check raising is itself a FAIL, with the error
                results.append(
                    CheckResult(i, check.__name__, Status.FAIL, f"check raised: {exc!r}")
                )
    return ConformanceReport(results=tuple(results))

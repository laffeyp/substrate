# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Base-fails-first reproduction validator — sprint 155.

Observation contract for `repro_base_validate_factory`: given a repro code and a fake runner
that emulates the base-checkout run's stdout, the producer emits ONE `ReproductionTest` that
is either a passthrough of the original (when the base run cleanly says "Issue reproduced" —
the repro discriminates) or an overwrite with `code=""` (when the base run says "Issue
resolved" — trivially-passing — or errors — "Other issues"). Empty input passes through with
no runner call. Runner exception passes through unchanged (death-resilience per KIT_DIARY 16).
"""

from __future__ import annotations

from typing import Any

from substrate import api
from substrate.api import Runtime, read_record
from substrate.topologies.swebench_solver.records import ReproductionTest
from substrate.topologies.swebench_solver.repro_base_validate import (
    repro_base_validate_factory,
)


class _StubRunner:
    """A runner that returns a scripted (rc, output) — the exact interface `repro_base_validate`
    calls at repro_base_validate.py:76-77 (`.run(patch, command, files)`). Records the invocations
    so a test can assert the empty-patch (base-run) contract holds."""

    def __init__(self, rc: int = 0, output: str = "") -> None:
        self.rc = rc
        self.output = output
        self.calls: list[tuple[str, str, dict[str, str] | None]] = []

    def run(
        self, model_patch: str, command: str, extra_files: dict[str, str] | None = None
    ) -> tuple[int, str]:
        self.calls.append((model_patch, command, extra_files))
        return self.rc, self.output


class _DyingRunner:
    """A runner whose `.run` raises — for the death-resilience test. A Docker hiccup must never
    wedge the topology; the original repro passes through unchanged."""

    def run(
        self, model_patch: str, command: str, extra_files: dict[str, str] | None = None
    ) -> tuple[int, str]:
        raise RuntimeError("docker exploded")


async def _run(tmp_path, runner: Any, incoming_code: str) -> list[dict]:  # type: ignore[no-untyped-def]
    """Wire the producer as a topology: emit the incoming ReproductionTest, trigger
    `repro_base_validate` on it, terminate on the second ReproductionTest (the overwrite or
    passthrough). Reads the record back so an observation contract can inspect the emitted code."""

    async def _seed(_inp: Any):
        yield ReproductionTest(code=incoming_code)

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "seed",
            schemas=[ReproductionTest],
            schema_version=1,
            factory=lambda: _seed,
            deterministic=True,
        )
        b.producer_kind(
            "validate",
            schemas=[ReproductionTest],
            schema_version=1,
            factory=repro_base_validate_factory(runner),
            deterministic=False,
        )
        b.view("reproduction", api.KindBuffer("ReproductionTest"))
        b.initial("seed", input=None)
        b.trigger(
            "gate",
            subscription=api.Subscription(kinds=frozenset({"ReproductionTest"})),
            # same predicate as the assemble.py wiring — fire once on the ORIGINAL, never on
            # the overwrite (else the overwrite would trigger a second validation).
            predicate=lambda ctx: len(ctx.views["reproduction"].value()) == 1,
            starts="validate",
            input_builder=lambda ctx: {"code": ctx.event.payload["code"]},
            policy=api.PerEvent(),
        )
        b.termination(
            api.any_of(
                api.threshold_count("ReproductionTest", 2),
                api.quiescence(),
            )
        )

    await Runtime(tmp_path / "run").run(topo)
    return list(read_record(tmp_path / "run"))


def _emitted_codes(events: list[dict]) -> list[str]:
    return [str(e["payload"]["code"]) for e in events if e["kind"] == "ReproductionTest"]


async def test_reproduced_on_base_keeps_the_repro(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # The repro correctly detects the bug on the unmodified base → discriminates → keep it.
    runner = _StubRunner(rc=0, output="Issue reproduced\ntraceback details...\n")
    events = await _run(tmp_path, runner, "assert broken()")
    codes = _emitted_codes(events)
    assert codes == ["assert broken()", "assert broken()"]  # original + passthrough
    # exactly one runner invocation, with empty patch (base_commit) + the repro script.
    assert len(runner.calls) == 1
    assert runner.calls[0][0] == ""  # empty patch → base
    assert runner.calls[0][2] == {"repro.py": "assert broken()"}


async def test_resolved_on_base_overwrites_with_empty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # The repro says "Issue resolved" on the unpatched base → trivially-passing (the exact
    # KIT_DIARY finding 21 failure mode on flask-4045). Overwrite with empty code so SELECT
    # falls back to regression-only.
    runner = _StubRunner(rc=0, output="Issue resolved\n")
    events = await _run(tmp_path, runner, "assert wrong_repro()")
    codes = _emitted_codes(events)
    assert codes == ["assert wrong_repro()", ""]  # original then the empty overwrite


async def test_other_status_on_base_overwrites_with_empty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # The repro errored ("Other issues") or printed neither marker → no discriminating signal
    # will ever come from it. Same demote path as RESOLVED.
    runner = _StubRunner(rc=1, output="Traceback (most recent call last)...\nOther issues")
    events = await _run(tmp_path, runner, "import broken_thing")
    codes = _emitted_codes(events)
    assert codes == ["import broken_thing", ""]


async def test_empty_incoming_code_passes_through_without_runner(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Empty incoming code means the generator already gave up (a failed model call, per
    # KIT_DIARY 16). No runner call needed; passthrough of the empty state.
    runner = _StubRunner(rc=0, output="Issue reproduced\n")
    events = await _run(tmp_path, runner, "")
    codes = _emitted_codes(events)
    assert codes == ["", ""]  # both empty
    assert runner.calls == []  # no wasted Docker call on an empty repro


async def test_runner_exception_records_producer_failed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # 2026-08-09 halt-on-error contract: a Docker runner exception in repro_base_validate
    # propagates. The producer dies, the kernel records ProducerFailed, no second
    # ReproductionTest emits. Runner halts. A "Docker hiccup" is a real error, not something
    # to silently pass around.
    events = await _run(tmp_path, _DyingRunner(), "assert original()")
    assert any(e["kind"] == "substrate.ProducerFailed" for e in events), (
        "runner exception must record ProducerFailed"
    )
    # Only the seed emit (the original ReproductionTest) is on the record — no validator overwrite.
    codes = _emitted_codes(events)
    assert codes == ["assert original()"], "validator must not emit after a runner exception"


async def test_adversarial_output_with_tied_markers_reads_as_reproduced_and_keeps(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # F4 fix (review 2026-08-08): `reproduction_status` now majority-votes over marker counts,
    # and ties go to REPRODUCED (the safe direction — a repro must not win on equal signal).
    # One "Issue reproduced" + one "Issue resolved" is a tie -> REPRODUCED -> validator KEEPS
    # the original. Pre-F4 the first-match rule read this as RESOLVED and demoted; the new
    # tiebreak is the honest one for the KIT_DIARY 21 failure mode.
    runner = _StubRunner(rc=0, output="Issue reproduced\nActually wait — Issue resolved\n")
    events = await _run(tmp_path, runner, "assert ambiguous()")
    codes = _emitted_codes(events)
    assert codes == ["assert ambiguous()", "assert ambiguous()"]  # tie -> REPRODUCED -> keep


async def test_output_with_majority_resolved_demotes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Clear RESOLVED majority (2 vs 1) on the base run -> demote per the F4 majority-vote rule.
    runner = _StubRunner(rc=0, output="Issue resolved\nIssue reproduced\nIssue resolved\n")
    events = await _run(tmp_path, runner, "assert ambiguous()")
    codes = _emitted_codes(events)
    assert codes == ["assert ambiguous()", ""]  # majority RESOLVED -> overwrite


async def test_predicate_fires_only_on_original_not_on_overwrite(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # The trigger's predicate `len(reproduction.value()) == 1` guards against a fanout loop —
    # the overwrite this producer emits ALSO matches the ReproductionTest subscription. Confirm
    # the terminal count is exactly 2 (original + one overwrite), not 3+.
    runner = _StubRunner(rc=0, output="Issue resolved\n")
    events = await _run(tmp_path, runner, "the-original")
    repro_count = sum(1 for e in events if e["kind"] == "ReproductionTest")
    assert repro_count == 2, "the trigger predicate must not re-fire on the overwrite"

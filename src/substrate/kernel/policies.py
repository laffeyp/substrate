# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""TerminationPolicy + the standard recipe set (kernel §8; F-TERM-1, F-LIFE-2).

A TerminationPolicy interprets the run state (the just-processed event, the
completion/failure counts, quiescence) into a Decision. The contract is the callback;
the recipes ship on top as named convenience functions (kernel §8). Per-Producer and
per-run scoping compose per the kernel; v0.1 ships the run-scoped recipes the
reference topologies need.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class Decision(enum.StrEnum):
    """The verdict a TerminationPolicy returns each cycle. v1.0 ships four of the kernel §8
    outcomes: CONTINUE (do nothing), FINALISE_RUN (end the run), CANCEL_OTHERS (cancel every
    other live Producer), PAUSE_AWAIT_INPUT (halt, resumable). Recorded on
    substrate.TerminationMatched. (The fifth kernel outcome, `let-finish` — drain in-flight then
    finalise — is DEFERRED post-1.0: it has no runtime dispatch branch yet, so shipping the enum
    value would be a silent no-op. See CONTRIBUTING.md's deferral list.)"""

    CONTINUE = "continue"
    FINALISE_RUN = "finalise-run"
    CANCEL_OTHERS = "cancel-others"
    PAUSE_AWAIT_INPUT = "pause-await-input"


@dataclass(frozen=True)
class TermContext:
    """What a TerminationPolicy sees. `event` is the just-appended event (or None on a
    pure quiescence check). `counts(kind)` returns the run's count of that event kind."""

    event: Any
    quiescent: bool
    running: int
    started: int
    completed: int
    counts: Callable[[str], int]


class TerminationPolicy:
    """A named decision callback. `name` is recorded in substrate.TerminationMatched.

    `finalisation`, when set, is a callable run at finalise-run time that produces the
    run's final output payload; it is recorded in substrate.RunFinalised.finalisation_payload
    and surfaced on RunResult.finalisation_payload. None → no payload (an empty RunFinalised).
    The payload must be canonical (§4.2); a non-canonical payload is dropped to None with the
    failure noted, never crashing finalisation."""

    def __init__(
        self,
        name: str,
        fn: Callable[[TermContext], Decision],
        resume_condition: str | None = None,
        finalisation: Callable[[TermContext], Any] | None = None,
    ) -> None:
        self.name = name
        self._fn = fn
        self.resume_condition = resume_condition
        self.finalisation = finalisation

    def decide(self, ctx: TermContext) -> Decision:
        return self._fn(ctx)

    def finalisation_payload(self, ctx: TermContext) -> Any | None:
        """The run's final output payload at finalise time, or None if the policy declares
        none. Exceptions propagate to the caller (which records the failure, not silently)."""
        return self.finalisation(ctx) if self.finalisation is not None else None


def threshold_count(kind: str, n: int) -> TerminationPolicy:
    """Finalise once `n` events of `kind` have been appended."""
    return TerminationPolicy(
        f"threshold_count({kind},{n})",
        lambda c: Decision.FINALISE_RUN if c.counts(kind) >= n else Decision.CONTINUE,
    )


def finalise_on(kind: str) -> TerminationPolicy:
    """Finalise when the event just appended is of `kind`.

    For a terminal event a RESUMABLE run can see more than once. `threshold_count(kind, 1)` reads
    the run's count of `kind`, which a resume restores from the whole log, so a record that
    already holds one such event finalises the resumed run on its first new event. This policy
    reads only the event that just landed: an earlier one in the record never ends the run (lens
    audit F309: the console rebuilt the session's termination with a raised threshold, counted
    by reading the whole record on every turn)."""
    return TerminationPolicy(
        f"finalise_on({kind})",
        lambda c: (
            Decision.FINALISE_RUN
            if c.event is not None and getattr(c.event, "kind", None) == kind
            else Decision.CONTINUE
        ),
    )


def all_completed() -> TerminationPolicy:
    """Finalise on quiescence once every started Producer has ended.

    NOT for a RESUMABLE run: this compares started vs ended COUNTS, which are restored from the
    whole log on resume — but a pause leaves the emitting Producer started-without-a-durable-end
    across the pause, so on resume `completed >= started` can never be met and the run would
    hang. A pausable topology MUST finalise on a process-local terminal instead (quiescence /
    threshold); see `pause_await_input`. (The runtime fails such a run loudly, not silently.)"""
    return TerminationPolicy(
        "all_completed",
        lambda c: (
            Decision.FINALISE_RUN
            if (c.quiescent and c.running == 0 and c.started > 0 and c.completed >= c.started)
            else Decision.CONTINUE
        ),
    )


def cancel_all_others(when: Callable[[TermContext], bool]) -> TerminationPolicy:
    """Cancel every OTHER running Producer (all but the subject — the producer of the
    just-appended event) when `when(ctx)` holds (kernel §8; F-LIFE-2). CANCEL_OTHERS does NOT
    finalise: the cancelled Producers emit substrate.ProducerCancelled on the log and the run
    continues (typically to quiescence). The canonical R-1 use: fire on the adjudicator's
    completion, cancel the still-running candidates, then a quiescence/all-completed policy
    finalises. Compose: any_of(cancel_all_others(adjudicated), all_completed())."""
    return TerminationPolicy(
        "cancel_all_others",
        lambda c: Decision.CANCEL_OTHERS if when(c) else Decision.CONTINUE,
    )


def quiescence() -> TerminationPolicy:
    """Finalise when the run goes quiescent: no Producer running, nothing queued.

    This was `quiescence_with_watchdog(seconds)`. No watchdog ever existed: `seconds` only
    capped the writer's 10 ms idle poll, so every value of 0.01 or more did nothing, and call
    sites passing 2400 s or `watchdog_seconds + grade_timeout_seconds` expected a deadline
    the kernel never set (lens audit F021). A deadline on one Producer is
    `Budget(wall_seconds=Cap(...))`."""
    return TerminationPolicy(
        "quiescence",
        lambda c: Decision.FINALISE_RUN if (c.quiescent and c.running == 0) else Decision.CONTINUE,
    )


def pause_await_input(
    when: Callable[[TermContext], bool], resume_condition: str
) -> TerminationPolicy:
    """Pause and emit a typed resume_condition when `when` holds (kernel halt-with-resume).

    RESUMABLE-TERMINAL CONSTRAINT: a topology that can PAUSE here and later resume MUST pair
    this with a PROCESS-LOCAL finalisation terminal — quiescence (`quiescence`)
    or a count threshold (`threshold_count`) — NOT `all_completed`. `all_completed` compares
    started vs ended COUNTS, but a pause trips while the emitting Producer is still inflight, so
    its ProducerStarted has no durable end across the pause: on resume the restored started >
    ended and `completed >= started` can never be met, so the resumed run would never finalise.
    The runtime guards this (a stuck-quiescent resumed run is recorded as a RunFinalised with
    reason "stuck_quiescent" and FAILS loudly rather than hanging), but the fix is to choose a
    process-local terminal. The reference R-2 pipeline does exactly this (quiescence, not
    all_completed) and documents why."""
    return TerminationPolicy(
        "pause_await_input",
        lambda c: Decision.PAUSE_AWAIT_INPUT if when(c) else Decision.CONTINUE,
        resume_condition=resume_condition,
    )


def any_of(*policies: TerminationPolicy) -> TerminationPolicy:
    """Finalise/pause when any composed policy returns a non-CONTINUE decision."""
    name = "any_of(" + ",".join(p.name for p in policies) + ")"

    def fn(ctx: TermContext) -> Decision:
        for p in policies:
            d = p.decide(ctx)
            if d is not Decision.CONTINUE:
                return d
        return Decision.CONTINUE

    # Surface a composed member's resume_condition so a PAUSE_AWAIT_INPUT decided through the
    # wrapper still records its typed resume_condition on TerminationMatched (observability:
    # the paused run names what input it awaits). The first member that declares one wins.
    resume_condition = next((p.resume_condition for p in policies if p.resume_condition), None)
    return TerminationPolicy(name, fn, resume_condition=resume_condition)


def all_of(*policies: TerminationPolicy) -> TerminationPolicy:
    """Finalise only when all composed policies agree to finalise."""
    name = "all_of(" + ",".join(p.name for p in policies) + ")"

    def fn(ctx: TermContext) -> Decision:
        decisions = [p.decide(ctx) for p in policies]
        if decisions and all(d is Decision.FINALISE_RUN for d in decisions):
            return Decision.FINALISE_RUN
        return Decision.CONTINUE

    return TerminationPolicy(name, fn)

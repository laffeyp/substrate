# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Per-run mutable state for the Runtime (extracted from the Runtime God-class).

`RunPhase` replaces the four ad-hoc booleans (terminated/paused/failed/record_closed)
with one explicit lifecycle enum; `RunState` holds the ~two-dozen per-run mutable fields
the append cycle and the writer loop share, so the Runtime no longer carries them as
instance attributes built in two phases. `run()` constructs one RunState per call; the
Sequencer (substrate.sequencer.AppendCycle) and the Runtime both operate on it.

This is a behavior-preserving extraction: the field set and their semantics are exactly
what lived on the Runtime instance before — only their HOME changed.
"""

from __future__ import annotations

import asyncio
import enum
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..constants import RunStatus

if TYPE_CHECKING:
    from ..types import Event


class RunPhase(enum.StrEnum):
    """The run's lifecycle phase. Legal transitions: RUNNING -> {FINALISED, PAUSED,
    FAILED}; PAUSED is a non-terminal rest (a resume re-enters RUNNING, handled by the
    caller). Terminal phases (FINALISED, FAILED) forbid any further bus append (the
    RUN-BOUNDARY at-most-once rule). `record_closed` is tracked separately because it is
    an I/O fact (the fd state), orthogonal to the logical phase."""

    RUNNING = "running"
    # The outcome phases carry RunStatus's strings, the one copy (lens audit F022).
    PAUSED = RunStatus.PAUSED.value
    FINALISED = RunStatus.FINALISED.value
    FAILED = RunStatus.FAILED.value

    @property
    def is_terminal(self) -> bool:
        """A terminal phase forbids further bus appends (RunFinalised is last-if-present)."""
        return self in (RunPhase.FINALISED, RunPhase.FAILED)


@dataclass
class RunState:
    """All per-run mutable state. Constructed once per Runtime.run() call.

    Queues/scheduling: `inbox` (credit-gated emissions + control), `credits` (admission
    semaphore), `control` (the writer-internal FIFO drained in append-cycle step 6),
    `scheduled` (Producers awaiting a task), `tasks` (live Producer tasks).
    Sequencing: `next_seq` (the dense seq counter), `in_cycle` (reentrancy guard),
    `staged` (Route messages, persistent across cycles by kernel Decision #8).
    Bookkeeping: kind `counts`, `inflight`/`started_total`/`ended_total`, predicate
    `quarantined`/`pred_violations`, the trigger cooldown match counters.
    Outcome: `phase`, `record_closed`, `kernel_error`, `last_event`/`final_event`,
    `final_payload`, `replay_ceiling`, `run_id`, `poll_s`.
    """

    run_id: str
    replay_ceiling: str
    poll_s: float
    admission_bound: int

    inbox: asyncio.Queue[Any] = field(default_factory=asyncio.Queue)
    credits: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1))
    control: deque[Any] = field(default_factory=deque)
    scheduled: list[tuple[str, Any, str, str | None]] = field(default_factory=list)
    tasks: set[asyncio.Task[None]] = field(default_factory=set)
    # live Producer instance_id -> its task, so a cancel-others policy can spare the subject
    # and cancel the rest (kernel §8 cancel-others).
    task_by_instance: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    # Reverse map: instance_id -> producer kind name. Populated alongside task_by_instance
    # in _flush_scheduled; read by cancel bookkeeping to look up a task's kind.
    kind_by_instance: dict[str, str] = field(default_factory=dict)
    # instance_id -> its parent's instance id (None for a root), beside kind_by_instance, so
    # `Runtime.cancel_producer` returns the real ProducerRef (lens audit F016).
    parent_by_instance: dict[str, str | None] = field(default_factory=dict)
    # instance_id -> {"cause": str, "caller": str | None}. Written synchronously by
    # `Runtime.cancel_producer` and by the `_cancel_others` policy path BEFORE the
    # target task's `task.cancel()` fires. Read by `_producer_task`'s CancelledError
    # handler and threaded into the `substrate.ProducerCancelled` payload so the
    # record carries who cancelled the producer and why (v0.3 vocabulary extension).
    cancel_reasons: dict[str, dict[str, Any]] = field(default_factory=dict)

    next_seq: int = 0
    in_cycle: bool = False
    staged: dict[str, Any] = field(default_factory=dict)

    counts: dict[str, int] = field(default_factory=dict)
    inflight: int = 0
    started_total: int = 0
    ended_total: int = 0
    quarantined: set[int] = field(default_factory=set)
    pred_violations: dict[int, int] = field(default_factory=dict)
    trigger_match_count: dict[int, int] = field(default_factory=dict)
    trigger_last_fired_match: dict[int, int] = field(default_factory=dict)

    phase: RunPhase = RunPhase.RUNNING
    record_closed: bool = False
    kernel_error: str | None = None
    last_event: Event | None = None
    final_event: Event | None = None
    final_payload: Any | None = None

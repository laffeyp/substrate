# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""R-2 — Pipeline with structured error cascade + halt-with-resume (product §8; §0.1).

This is the integrated error-handling demonstration, run on a PERSISTENT bus so the
halt-with-resume crosses a process boundary. It exercises, on its OWN run record, every
mechanism it names:

  1. ProducerEmittedInvalidEvent — the transform stage, on its FIRST attempt at the seeded
     fault row, emits an UNDECLARED event kind. The bus boundary rejects it: no fabricated
     Transformed reaches the log, a substrate.ProducerEmittedInvalidEvent is sequenced
     instead (technical §8.1). This is a REAL fault (an undeclared emission), not a
     valid-but-empty row.
  2. Retry enriched via a Route (the conformance check-1 pattern) — a Route subscribed to
     ProducerEmittedInvalidEvent stages the failure reason into a slot; the retry Trigger's
     input_builder reads that staged reason (the enrichment is on the log, citable via the
     firing's recorded resolved input) and re-fires the transform with attempt=2, which
     succeeds.
  3. RetryExhausted escalation — a per-row invalid-count View bounds retries. Past the cap,
     the retry Trigger stops and an escalation Trigger fires an escalator Producer that emits
     a RetryExhausted application event (the cascade escalates rather than looping forever).
  4. input_builder-raise -> InputBuildFailed — a deliberately malformed row makes a guarded
     input_builder raise; the kernel records substrate.InputBuildFailed (no Producer starts)
     rather than crashing the writer (technical §6.3 / F-TRIG-5).
  5. pause_await_input -> resume — RetryExhausted trips a pause_await_input TerminationPolicy:
     the run PAUSES awaiting a human decision. A `substrate resume --input ...:operator_override`
     (or Runtime.resume) injects an OperatorOverride event that fires a recovery Producer and
     the run finalises. Because the bus is persistent, the pause survives a process restart.

CI mode uses deterministic stand-ins so the whole cascade is reproducible and gates every
commit; the walkthrough swaps a real local LLM into the transform stage. CI mode proves the
WIRING — it does not stand in for the demonstration (the spec is explicit on that).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from msgspec import Struct

from .. import api
from ..types import Event
from ._models import Responder, call_responder

_Factory = Callable[[], Any]

# the per-row retry budget: attempts beyond this escalate to RetryExhausted instead of looping.
MAX_RETRIES = 1


class Row(Struct, frozen=True):
    row: int
    raw: str


class Transformed(Struct, frozen=True):
    row: int
    out: str
    attempt: int


class RetryExhausted(Struct, frozen=True):
    row: int
    reason: str
    attempts: int


class Recovered(Struct, frozen=True):
    row: int
    by: str


class OperatorOverride(Struct, frozen=True):
    """The external resume event a human supplies to a paused run (producer=null on the bus:
    it is externally injected, not Producer-emitted)."""

    row: int
    note: str


# A Producer-undeclared event kind: the transform stage yields THIS on the fault row's first
# attempt. The transform kind only declares Transformed, so emitting BadEmission is rejected at
# the bus boundary -> substrate.ProducerEmittedInvalidEvent (NOT a fabricated Transformed).
class BadEmission(Struct, frozen=True):
    row: int
    junk: str


class _InvalidByRow:
    """A custom View counting substrate.ProducerEmittedInvalidEvent per source row. The retry
    budget reads it; deterministic (a pure projection of the bus). The row is carried on the
    invalid event's raw_payload (the offending BadEmission's row field)."""

    deterministic = True

    def __init__(self) -> None:
        self.subscription = api.Subscription(kinds=frozenset({api.PRODUCER_EMITTED_INVALID}))
        self._by_row: dict[int, int] = {}

    def update(self, event: Event) -> None:
        payload = event.payload if isinstance(event.payload, dict) else {}
        raw = payload.get("raw_payload")
        row = raw.get("row") if isinstance(raw, dict) else None
        if isinstance(row, int):
            self._by_row[row] = self._by_row.get(row, 0) + 1

    def value(self) -> dict[int, int]:
        return dict(self._by_row)


def _parser_factory(rows: list[str]) -> _Factory:
    async def parse(_input: Any) -> AsyncIterator[Row]:
        for i, raw in enumerate(rows):
            yield Row(row=i, raw=raw)

    return lambda: parse


def _transform_factory(
    responder: Responder, fault_row: int | None, hard_fault_row: int | None
) -> _Factory:
    async def transform(inp: Any) -> AsyncIterator[Any]:
        row = inp.get("row", 0)
        raw = inp.get("raw", "")
        attempt = int(inp.get("attempt", 1))
        # A RECOVERABLE fault: the FIRST attempt at fault_row emits an UNDECLARED kind (rejected
        # at the bus -> ProducerEmittedInvalidEvent); the retry-with-enrichment re-fire (attempt
        # >= 2) succeeds. Demonstrates retry SUCCESS.
        if row == fault_row and attempt == 1:
            yield BadEmission(row=row, junk="<<invalid>>")
            return
        # An UNRECOVERABLE fault: every attempt emits the undeclared kind, so the retry budget is
        # exhausted -> escalation. Demonstrates RetryExhausted.
        if row == hard_fault_row:
            yield BadEmission(row=row, junk="<<persistently-invalid>>")
            return
        # send the bare row value, not "transform: {raw}" — a weak model told to "uppercase the input
        # word" uppercases the literal label "transform" and ignores the row. The caller's system
        # prompt defines the transform; the user message is just the thing to transform.
        yield Transformed(row=row, out=await call_responder(responder, raw), attempt=attempt)

    return lambda: transform


def _escalator_factory() -> _Factory:
    async def escalate(inp: Any) -> AsyncIterator[RetryExhausted]:
        yield RetryExhausted(
            row=int(inp.get("row", -1)),
            reason=str(inp.get("reason", "")),
            attempts=int(inp.get("attempts", 0)),
        )

    return lambda: escalate


def _recovery_factory() -> _Factory:
    async def recover(inp: Any) -> AsyncIterator[Recovered]:
        yield Recovered(row=int(inp.get("row", -1)), by=str(inp.get("by", "operator")))

    return lambda: recover


def operator_override(row: int = 1) -> OperatorOverride:
    """The resume-event factory (`substrate resume --input r2_pipeline.py:operator_override`)."""
    return OperatorOverride(row=row, note="operator approved manual recovery")


def pipeline_topology(
    rows: list[str],
    *,
    transform_model: Responder,
    fault_row: int | None = 1,
    hard_fault_row: int | None = None,
    malformed_row: int | None = None,
    deterministic: bool = True,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the R-2 pipeline. `rows` are the input rows; `transform_model` is the Responder
    for the transform stage.

    `fault_row` (default 1) is a RECOVERABLE fault: its first transform attempt emits an
    undeclared kind (-> ProducerEmittedInvalidEvent), and the retry-with-enrichment re-fire
    succeeds (mechanisms 1, 2). `hard_fault_row`, if set, is an UNRECOVERABLE fault: every
    attempt emits the undeclared kind, exhausting the retry budget -> RetryExhausted ->
    pause_await_input (mechanisms 3, 5). `malformed_row`, if set, is a row whose to-transform
    input_builder raises (-> InputBuildFailed, mechanism 4). `deterministic` flags kinds for
    Level-3(a) replay (True in CI)."""

    def _to_transform_input(ctx: Any) -> Any:
        row = ctx.event.payload["row"]
        # the deliberate input_builder-raise demonstration (mechanism 4): a malformed row makes
        # the builder raise -> the kernel records InputBuildFailed (no transform starts).
        if malformed_row is not None and row == malformed_row:
            raise ValueError(f"malformed row {row}: cannot build transform input")
        return {"row": row, "raw": ctx.event.payload["raw"], "attempt": 1}

    def _retry_input(ctx: Any) -> Any:
        # mechanism 2: enrichment via a Route. The failure reason was staged into "failure" by
        # the failure-context Route from the SAME ProducerEmittedInvalidEvent; the retry input
        # carries it (citable in the firing's recorded resolved input — the check-1 pattern).
        failure = ctx.staged.get("failure", {})
        raw = ctx.event.payload.get("raw_payload", {})
        row = raw.get("row") if isinstance(raw, dict) else None
        return {
            "row": row,
            "raw": failure.get("raw", ""),
            "attempt": 2,
            "prior_reason": failure.get("reason", ""),
        }

    def _escalate_input(ctx: Any) -> Any:
        failure = ctx.staged.get("failure", {})
        raw = ctx.event.payload.get("raw_payload", {})
        row = raw.get("row") if isinstance(raw, dict) else None
        return {
            "row": row,
            "reason": failure.get("reason", "invalid emission"),
            "attempts": MAX_RETRIES + 1,
        }

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "parser",
            schemas=[Row],
            schema_version=1,
            factory=_parser_factory(rows),
            deterministic=deterministic,
        )
        b.producer_kind(
            "transform",
            schemas=[Transformed],
            schema_version=1,
            factory=_transform_factory(transform_model, fault_row, hard_fault_row),
            deterministic=deterministic,
        )
        b.producer_kind(
            "escalator",
            schemas=[RetryExhausted],
            schema_version=1,
            factory=_escalator_factory(),
            deterministic=deterministic,
        )
        b.producer_kind(
            "recovery",
            schemas=[Recovered],
            schema_version=1,
            factory=_recovery_factory(),
            deterministic=deterministic,
        )
        b.initial("parser", input=None)
        # per-row invalid-emission count (the retry budget reads it).
        b.view("invalid_by_row", _InvalidByRow())
        # parser -> transform (PerEvent: one transform per row). The to-transform input_builder
        # raises on a malformed row (mechanism 4).
        b.trigger(
            "to-transform",
            subscription=api.Subscription(kinds=frozenset({"Row"})),
            predicate=lambda ctx: True,
            starts="transform",
            input_builder=_to_transform_input,
            policy=api.PerEvent(),
        )
        # the failure-context Route (mechanism 2): stage the failure reason from the invalid
        # event into the "failure" slot, so the retry/escalation input_builders can enrich.
        b.route(
            "failure-context",
            subscription=api.Subscription(kinds=frozenset({api.PRODUCER_EMITTED_INVALID})),
            slot="failure",
            transform=lambda event: {
                "reason": event.payload.get("reason", ""),
                "raw": (event.payload.get("raw_payload") or {}).get("junk", ""),
                "row": (event.payload.get("raw_payload") or {}).get("row"),
            },
        )
        # retry within budget (mechanism 2): on an invalid emission, if this row is still under
        # the retry cap, re-fire the transform (attempt=2) enriched with the staged reason.
        b.trigger(
            "retry",
            subscription=api.Subscription(kinds=frozenset({api.PRODUCER_EMITTED_INVALID})),
            predicate=lambda ctx: _under_cap(ctx.event, ctx.views),
            starts="transform",
            input_builder=_retry_input,
            policy=api.PerEvent(),
        )
        # escalate past budget (mechanism 3): once the cap is exceeded, fire the escalator,
        # which emits RetryExhausted.
        b.trigger(
            "escalate",
            subscription=api.Subscription(kinds=frozenset({api.PRODUCER_EMITTED_INVALID})),
            predicate=lambda ctx: not _under_cap(ctx.event, ctx.views),
            starts="escalator",
            input_builder=_escalate_input,
            policy=api.PerEvent(),
        )
        # operator override resumes a paused run (mechanism 5): the external OperatorOverride
        # fires the recovery Producer.
        b.trigger(
            "on-override",
            subscription=api.Subscription(kinds=frozenset({"OperatorOverride"})),
            predicate=lambda ctx: True,
            starts="recovery",
            input_builder=lambda ctx: {
                "row": ctx.event.payload["row"],
                "by": "operator",
            },
            policy=api.PerEvent(),
        )
        # PAUSE on RetryExhausted (mechanism 5), UNLESS the operator has already overridden it
        # (so the resumed run drives to a terminal instead of re-pausing). Else, finalise on
        # QUIESCENCE (no work in flight). Quiescence — not all_completed — is the right terminal
        # here because a resume runs in a fresh process: the started/ended COUNTS carry the whole
        # prior record (incl. the escalator that was mid-completion when the pause tripped, whose
        # completion never lands in the resumed process), so a completed>=started terminal could
        # never be met across the pause boundary. `running == 0` is process-local and correct for
        # both the initial pause and the resumed finalise.
        b.termination(
            api.any_of(
                api.pause_await_input(
                    lambda c: c.counts("RetryExhausted") >= 1 and c.counts("OperatorOverride") == 0,
                    resume_condition="OperatorOverride",
                ),
                api.quiescence(),
            )
        )

    return topo


def _under_cap(event: Any, views: Any) -> bool:
    """True if the row of this invalid emission is still within the retry budget. Reads the
    per-row invalid count View; the Nth invalid (N <= MAX_RETRIES) retries, beyond escalates."""
    raw = event.payload.get("raw_payload") if isinstance(event.payload, dict) else None
    row = raw.get("row") if isinstance(raw, dict) else None
    if row is None:
        return False
    seen = int(views["invalid_by_row"].value().get(row, 0))
    return seen <= MAX_RETRIES

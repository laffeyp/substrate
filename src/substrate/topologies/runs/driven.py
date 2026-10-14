# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The driven session (kernel sprint 318; session vocabulary § X.5, research r8 § 3.5).

A driven session is the session topology with one change at a turn's end: where a session pauses on
`Returned` for a person, a driven session runs its checks and writes the next message itself, or
writes its report and ends. It is composed onto the one session topology (`session_topology(driven=
...)`), not built on a copy (kernel board Decisions, 2026-10-13).

- `card` writes `CardAccepted` and the first `UserMessage`. It starts with the run, or after the
  session prompt when the session has one (`card-on-session-prompt`).
- `checks-on-returned` starts `checks`, which runs the card's checks in the worktree and checks the
  session's events (`runs.checks.run_checks`), and writes `ChecksRun` with the worktree's commit.
- `continue-on-checks`: the checks did not pass and the limits allow another turn; `continue` writes
  the next `UserMessage`, naming what failed.
- `report-on-checks`: the checks passed, the limits are reached, or the turn ended on a model error
  or an interrupt; `report` writes `ReportWritten` (done, stuck, failed or stopped), and the run
  finalises on it.

Every decision is a function of the record: the triggers read the `ChecksRun` events and the latest
`Returned` through the `driven_checks` view.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import msgspec

from ... import api
from ..session import CardAccepted, ChecksRun, ModelReply, ReportWritten, UserMessage
from ..session.views import producer_kind_from_lifecycle_payload
from ..session.vocabulary import (
    CARD_ACCEPTED,
    CHECKS_RUN,
    DRIVEN_SLASH_SOURCE,
    MODEL_REPLY,
    PRODUCER_KIND_CARD,
    PRODUCER_KIND_CHECKS,
    PRODUCER_KIND_CONTINUE,
    PRODUCER_KIND_REPORT,
    PRODUCER_KIND_SESSION_PROMPT,
    RETURNED,
    RUN_PAUSED,
    RUN_RESUMED,
    TRIGGER_ID_CARD_ON_SESSION_PROMPT,
    TRIGGER_ID_CHECKS_ON_RETURNED,
    TRIGGER_ID_CONTINUE_ON_CHECKS,
    TRIGGER_ID_CONTINUE_ON_RESUMED,
    TRIGGER_ID_REPORT_ON_CHECKS,
    USER_MESSAGE,
    CheckKind,
    ReturnReason,
    RunOutcome,
    StopReason,
)
from .checks import run_checks, write_report

VIEW_DRIVEN_CHECKS = "driven_checks"
_FAILED_TAIL_LINES = 20


@dataclass(frozen=True)
class DrivenRun:
    """What a driven session needs that its record does not hold at the start: the card it is given,
    the worktree it works in, the commit the work starts from, the checks' time limit, and its first
    message. Everything after is read from the record."""

    card: CardAccepted
    worktree: Path
    base: str
    check_timeout_s: float
    first_message: str


class DrivenChecks:
    """Each `ChecksRun` as (passed, head, what its results say), the latest `ChecksRun` itself, the
    latest `Returned`'s reason and detail, whether a pause is asked for (v0.12.3), and whether the
    run awaits its next turn (its latest checks have no message after them), in record order."""

    deterministic = True

    def __init__(self) -> None:
        self.subscription = api.Subscription(
            kinds=frozenset({CHECKS_RUN, RETURNED, RUN_PAUSED, RUN_RESUMED, USER_MESSAGE})
        )
        self._checks: list[tuple[bool, str | None, str]] = []
        self._last: dict[str, Any] = {}
        self._returned: tuple[str, str] = (ReturnReason.REPLIED, "")
        self._pauses = 0
        self._awaiting = False

    def update(self, event: Any) -> None:
        payload = event.payload if isinstance(event.payload, dict) else {}
        if event.kind == RETURNED:
            self._returned = (str(payload.get("reason", "")), str(payload.get("detail", "")))
        elif event.kind == RUN_PAUSED:
            self._pauses += 1
        elif event.kind == RUN_RESUMED:
            self._pauses -= 1
        elif event.kind == USER_MESSAGE:
            self._awaiting = False
        elif event.kind == CHECKS_RUN:
            signature = msgspec.json.encode(
                [
                    (r.get("index"), r.get("passed"), r.get("exit"))
                    for r in payload.get("results", [])
                ]
            ).decode()
            self._checks.append((bool(payload.get("passed")), payload.get("head"), signature))
            self._last = dict(payload)
            self._awaiting = True

    def value(self) -> dict[str, Any]:
        return {
            "checks": list(self._checks),
            "last": dict(self._last),
            "returned": self._returned,
            "paused": self._pauses > 0,
            "awaiting": self._awaiting,
        }


def _ended_by(card: CardAccepted, state: dict[str, Any]) -> tuple[RunOutcome, str] | None:
    """How the run ends after its latest checks, or None when it takes another turn."""
    checks: list[tuple[bool, str | None, str]] = state["checks"]
    reason, detail = state["returned"]
    if reason == ReturnReason.MODEL_ERROR:
        return RunOutcome.FAILED, f"the model failed: {detail}"
    if reason == ReturnReason.INTERRUPTED:
        return RunOutcome.STOPPED, "the turn was interrupted"
    if checks and checks[-1][0]:
        return RunOutcome.DONE, ""
    limits = card.limits
    if len(checks) >= limits.max_stops:
        return RunOutcome.STUCK, f"the checks did not pass in {limits.max_stops} turns"
    recent = checks[-limits.stall_stops :]
    if len(recent) == limits.stall_stops and len({(head, sig) for _, head, sig in recent}) == 1:
        return (
            RunOutcome.STUCK,
            f"{limits.stall_stops} turns in a row with no new commit and the same checks",
        )
    return None


def _read_card(root: Path) -> tuple[CardAccepted, list[dict[str, Any]]]:
    events = list(api.read_record(root, resolve_blobs=True))
    card_env = next(e for e in events if e["kind"] == CARD_ACCEPTED)
    return msgspec.convert(card_env["payload"], CardAccepted), events


def _failed_text(checks: ChecksRun, card: CardAccepted) -> str:
    lines = ["The checks did not pass yet:"]
    for r in checks.results:
        if r.kind is CheckKind.COMMAND and not r.passed:
            check = card.checks[r.index]
            tail = "\n".join(r.output_tail.splitlines()[-_FAILED_TAIL_LINES:])
            got = "timed out" if r.exit is None else f"exit {r.exit}"
            lines.append(f"- `{check.text}`: {got} (expected {check.expect_exit})")
            if tail:
                lines.append(tail)
    lines += [f"- {p}" for p in checks.record_problems]
    lines.append("Keep working on the card until its checks pass, committing as you go.")
    return "\n".join(lines)


def _factory(body: Any) -> Callable[[], Any]:
    """A producer factory for `body`, typed as the session topology's own factories are."""
    return lambda: body


def compose_driven(
    b: api.TopologyBuilder,
    run: DrivenRun,
    *,
    own_record: Callable[[], Path],
    user_turns: Callable[[Any], int],
    has_session_prompt: bool,
) -> None:
    """Register the driven session's producers, view and triggers on the session topology's
    builder. The caller sets the termination (finalise on `ReportWritten` or `SessionEnded`)."""

    async def _card(_inp: Any) -> AsyncIterator[Any]:
        yield run.card
        yield UserMessage(
            text=run.first_message,
            turn_index=0,
            assembled_prompt="",
            slash_source=DRIVEN_SLASH_SOURCE,
        )

    async def _checks(inp: Any) -> AsyncIterator[ChecksRun]:
        card, events = _read_card(own_record())
        yield run_checks(
            card,
            run.worktree,
            events,
            after_seq=int(inp["after_seq"]),
            timeout_s=run.check_timeout_s,
        )

    async def _continue(inp: Any) -> AsyncIterator[UserMessage]:
        yield UserMessage(
            text=str(inp["text"]),
            turn_index=int(inp["turn_index"]),
            assembled_prompt="",
            slash_source=DRIVEN_SLASH_SOURCE,
        )

    async def _report(inp: Any) -> AsyncIterator[ReportWritten]:
        card, events = _read_card(own_record())
        checks = [
            msgspec.convert(e["payload"], ChecksRun) for e in events if e["kind"] == CHECKS_RUN
        ]
        last = (
            checks[-1]
            if checks
            else ChecksRun(after_seq=-1, results=[], record_problems=[], passed=False)
        )
        replies = [
            msgspec.convert(e["payload"], ModelReply) for e in events if e["kind"] == MODEL_REPLY
        ]
        said = next((r.text for r in reversed(replies) if r.stop_reason != StopReason.TOOL_USE), "")
        yield write_report(
            card,
            RunOutcome(str(inp["outcome"])),
            last,
            done=said,
            worktree=run.worktree,
            base=run.base,
            left=str(inp["left"]),
        )

    b.producer_kind(
        PRODUCER_KIND_CARD,
        schemas=[CardAccepted, UserMessage],
        schema_version=1,
        factory=_factory(_card),
        deterministic=True,
    )
    b.producer_kind(
        PRODUCER_KIND_CHECKS,
        schemas=[ChecksRun],
        schema_version=1,
        factory=_factory(_checks),
        deterministic=False,  # runs commands and reads git
    )
    b.producer_kind(
        PRODUCER_KIND_CONTINUE,
        schemas=[UserMessage],
        schema_version=1,
        factory=_factory(_continue),
        deterministic=True,
    )
    b.producer_kind(
        PRODUCER_KIND_REPORT,
        schemas=[ReportWritten],
        schema_version=1,
        factory=_factory(_report),
        deterministic=False,  # reads git
    )
    b.view(VIEW_DRIVEN_CHECKS, DrivenChecks())

    if has_session_prompt:
        b.trigger(
            TRIGGER_ID_CARD_ON_SESSION_PROMPT,
            subscription=api.Subscription(
                kinds=frozenset({api.PRODUCER_COMPLETED, api.PRODUCER_FAILED})
            ),
            predicate=lambda ctx: (
                producer_kind_from_lifecycle_payload(ctx.event.payload or {})
                == PRODUCER_KIND_SESSION_PROMPT
                and user_turns(ctx) == 0
            ),
            starts=PRODUCER_KIND_CARD,
            input_builder=lambda ctx: {},
            policy=api.Once(),
        )
    else:
        b.initial(PRODUCER_KIND_CARD, input={})

    b.trigger(
        TRIGGER_ID_CHECKS_ON_RETURNED,
        subscription=api.Subscription(kinds=frozenset({RETURNED})),
        predicate=lambda ctx: True,
        starts=PRODUCER_KIND_CHECKS,
        input_builder=lambda ctx: {"after_seq": int(ctx.event.seq)},
        policy=api.PerEvent(),
    )

    def _state(ctx: Any) -> dict[str, Any]:
        return dict(ctx.views[VIEW_DRIVEN_CHECKS].value())

    b.trigger(
        TRIGGER_ID_CONTINUE_ON_CHECKS,
        subscription=api.Subscription(kinds=frozenset({CHECKS_RUN})),
        # v0.12.3: a paused run takes no next turn; it pauses when it goes quiet.
        predicate=lambda ctx: (
            _ended_by(run.card, _state(ctx)) is None and not _state(ctx)["paused"]
        ),
        starts=PRODUCER_KIND_CONTINUE,
        input_builder=lambda ctx: {
            "turn_index": user_turns(ctx),
            "text": _failed_text(msgspec.convert(ctx.event.payload, ChecksRun), run.card),
        },
        policy=api.PerEvent(),
    )

    b.trigger(
        TRIGGER_ID_CONTINUE_ON_RESUMED,
        subscription=api.Subscription(kinds=frozenset({RUN_RESUMED})),
        predicate=lambda ctx: (
            _state(ctx)["awaiting"]
            and not _state(ctx)["paused"]
            and _ended_by(run.card, _state(ctx)) is None
        ),
        starts=PRODUCER_KIND_CONTINUE,
        input_builder=lambda ctx: {
            "turn_index": user_turns(ctx),
            "text": _failed_text(msgspec.convert(_state(ctx)["last"], ChecksRun), run.card),
        },
        policy=api.PerEvent(),
    )

    def _report_input(ctx: Any) -> dict[str, Any]:
        ended = _ended_by(run.card, _state(ctx))
        if ended is None:  # the trigger's predicate holds, so this is a wiring error
            raise RuntimeError("report-on-checks fired on checks that do not end the run")
        return {"outcome": ended[0].value, "left": ended[1]}

    b.trigger(
        TRIGGER_ID_REPORT_ON_CHECKS,
        subscription=api.Subscription(kinds=frozenset({CHECKS_RUN})),
        predicate=lambda ctx: _ended_by(run.card, _state(ctx)) is not None,
        starts=PRODUCER_KIND_REPORT,
        input_builder=_report_input,
        policy=api.Once(),
    )


__all__ = ["VIEW_DRIVEN_CHECKS", "DrivenChecks", "DrivenRun", "compose_driven"]

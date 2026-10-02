# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Code review topology — N-LLM ensemble with role-distinct system prompts (Sprint 130).

Five reviewer Producers (security, performance, style, correctness, clarity) stream
critiques in parallel; a Bus-view Predicate ("≥ quorum critiques") fires a single judge
Producer (Once) that renders a verdict grounded in the critiques it saw; on the judge's
completion, cancel-all-others cancels any reviewers still running; all-completed finalises.

This is R-1's ensemble+adjudicator shape with role differentiation: the members are no longer
interchangeable candidates answering one question, they are role-specialized reviewers, and
the adjudicator is a judge that renders a typed decision citing the roles that critiqued.

Dual-mode (the §8 discipline): hand each reviewer a DeterministicResponder (CI — proves the
wiring; every kind flagged deterministic so the record's replay ceiling stays "3a") or a real
local LLM per role (walkthrough — proves the role-distinct critique claim). The cancellation
facet is demonstrated on the topology's OWN record: designate `slow_roles` that linger before
yielding, so when the fast quorum fires the judge, the lingerers are still running and become
real victims for cancel-all-others (substrate.ProducerCancelled lands for each).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

from msgspec import Struct

from ... import api
from ...adapters import ModelUsage, Responder, call_responder_metered

# A Producer factory: a zero-arg callable returning the `start` async-generator. Typed as
# Callable[[], Any] for the same reason as r1_ensemble — an async-generator function does not
# structurally match the Producer Protocol under mypy --strict though it satisfies it at runtime.
_Factory = Callable[[], Any]

DEFAULT_ROLES: tuple[str, ...] = ("security", "performance", "style", "correctness", "clarity")


class CritiquePosted(Struct, frozen=True):
    role: str
    severity: int  # 1 (nit) .. 5 (blocker)
    summary: str
    line_refs: tuple[int, ...] = ()


class VerdictRendered(Struct, frozen=True):
    decision: str  # "approve" | "request-changes" | "block"
    cited_roles: tuple[str, ...]  # the roles whose critiques grounded the decision
    n_critiques: int  # how many critiques were on the bus when the judge fired


def _severity_of(text: str) -> int:
    # deterministic 1..5 derived from the critique text (so CI severities are reproducible).
    return (sum(text.encode()) % 5) + 1


def _reviewer_factory(
    role: str, code: str, responder: Responder, linger_seconds: float = 0.0
) -> _Factory:
    async def reviewer(_input: Any) -> AsyncIterator[CritiquePosted | ModelUsage]:
        # A lingering reviewer (linger_seconds > 0) sleeps BEFORE yielding, so it is still
        # running — and has NOT contributed a critique to the quorum — when the fast quorum
        # fires the judge. That makes it a live victim for cancel-all-others on the judge's
        # completion, which is the cancellation this topology demonstrates on its own record.
        if linger_seconds > 0:
            await asyncio.sleep(linger_seconds)
        # role-SPECIFIC steering: "report the worst issue" made every reviewer latch onto the single
        # most glaring bug (SQLi, a div-by-zero) regardless of role — no divergence, the whole point
        # of a multi-role panel lost. Constrain each reviewer to its OWN lens so the panel genuinely
        # diverges (security finds the injection, performance the O(n²), style the naming, ...).
        text, usage = await call_responder_metered(
            responder,
            f"You are the {role.upper()} reviewer. Review this code for {role} problems ONLY and name "
            f"the single most important {role} issue in one sentence; ignore issues outside {role}.\n{code}",
        )
        yield usage  # every model call metered onto the record (review C-7) so the panel is assayable
        yield CritiquePosted(role=role, severity=_severity_of(text), summary=text[:200])

    return lambda: reviewer


_DECISIONS = ("approve", "request-changes", "block")


def _decision_in(text: str) -> str | None:
    """The verdict word the judge's reply ends on: the decision whose last mention comes latest."""
    low = text.lower()
    found = [(low.rfind(d), d) for d in _DECISIONS if d in low]
    return max(found)[1] if found else None


def _judge_factory(responder: Responder) -> _Factory:
    async def judge(inp: Any) -> AsyncIterator[VerdictRendered | ModelUsage]:
        # inp carries the accumulated critiques (the input_builder reads the Bus-view buffer).
        crits = inp.get("critiques", []) if hasattr(inp, "get") else []
        roles = tuple(c["role"] for c in crits)
        max_sev = max((int(c["severity"]) for c in crits), default=0)
        # the judge adjudicates: in CI the decision is a deterministic function of the critiques'
        # severities; in the walkthrough the real model reads the critique summaries and names the
        # verdict. UI sprint 099: the model's reply used to be discarded and the severity rule
        # decided anyway, and severity is a hash of the critique text, so the walkthrough verdict
        # was noise. The rule now decides only when no model ran or its reply named no verdict.
        model_decision = None
        if responder is not None and roles:
            # the judge must see the critique CONTENT to adjudicate, not just the role names.
            text, usage = await call_responder_metered(
                responder,
                "Adjudicate these code-review critiques. Name the most serious in one sentence, "
                "then end with exactly one verdict word: block, request-changes, or approve.\n"
                + "\n".join(f"- {c['role']}: {c.get('summary', '')}" for c in crits),
            )
            yield usage  # metered onto the record (C-7)
            model_decision = _decision_in(text)
        decision = model_decision or (
            "block" if max_sev >= 4 else "request-changes" if max_sev >= 2 else "approve"
        )
        yield VerdictRendered(decision=decision, cited_roles=roles, n_critiques=len(crits))

    return lambda: judge


def code_review_topology(
    code: str,
    *,
    responders: Mapping[str, Responder],
    judge: Responder,
    roles: tuple[str, ...] = DEFAULT_ROLES,
    quorum: int = 3,
    deterministic: bool = True,
    slow_roles: frozenset[str] = frozenset(),
    linger_seconds: float = 0.0,
    watchdog_seconds: float = 60.0,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the code-review topology. `responders` maps role -> its reviewer Responder;
    `judge` is the adjudicating Responder. `quorum` is the Bus-view threshold (≥K critiques)
    that fires the judge. `deterministic` flags the Producer kinds for Level-3(a) replay (True
    in CI; False in the walkthrough since a real LLM is not author-deterministic).

    `slow_roles` names reviewers that LINGER (sleep `linger_seconds` before yielding their
    critique). With a quorum of fast reviewers, the judge fires and completes while the lingerers
    are still running, so cancel-all-others has real victims — substrate.ProducerCancelled lands
    for each lingerer, demonstrating the cancellation facet on this topology's own log.
    """

    def topo(b: api.TopologyBuilder) -> None:
        for role in roles:
            linger = linger_seconds if role in slow_roles else 0.0
            b.producer_kind(
                f"reviewer-{role}",
                schemas=[CritiquePosted, ModelUsage],
                schema_version=1,
                factory=_reviewer_factory(role, code, responders[role], linger),
                deterministic=deterministic,
            )
            b.initial(f"reviewer-{role}", input=None)
        b.producer_kind(
            "judge",
            schemas=[VerdictRendered, ModelUsage],
            schema_version=1,
            factory=_judge_factory(judge),
            deterministic=deterministic,
        )
        # a Bus-view of all critiques (a KindBuffer over the CritiquePosted KIND, since the
        # role reviewers are distinct Producer kinds all emitting CritiquePosted); the predicate
        # gates on its size — the "≥ quorum critiques in" fan-in this topology demonstrates.
        b.view("critiques", api.KindBuffer("CritiquePosted"))
        b.trigger(
            "adjudicate",
            subscription=api.Subscription(kinds=frozenset({"CritiquePosted"})),
            predicate=lambda ctx: len(ctx.views["critiques"].value()) >= quorum,
            starts="judge",
            input_builder=lambda ctx: {"critiques": list(ctx.views["critiques"].value())},
            policy=api.Once(),  # exactly one adjudication
        )
        # cancel the still-running reviewers when the judge completes; all_completed then finalises
        # once every started Producer has ENDED. VERIFIED semantics (runtime.py:631 +
        # sequencer.py:226-232, and by running — review #16): TermContext.completed == ended_total,
        # which counts substrate.ProducerCompleted, ProducerFailed AND ProducerCancelled
        # IDENTICALLY as "ended". So all_completed (quiescent ∧ running==0 ∧ completed>=started)
        # ALREADY finalises the failure path: if reviewers FAIL before emitting (a model is
        # unavailable) the quorum may be unreachable and the judge never fires, but every reviewer
        # still ENDS, so running==0 and all_completed finalises — no hang. quiescence_with_watchdog
        # is therefore a DEFENSIVE backstop, REDUNDANT with all_completed for the failure path; its
        # one non-redundant role is the zero-started-Producer case (where all_completed's started>0
        # guard fails). The ONE genuine liveness gap NEITHER policy closes is a Producer stuck
        # RUNNING forever (inflight never decrements → running never 0); v1.0 does not
        # force-finalise that (the stuck_quiescent backstop only fires at inflight==0) — liveness
        # there rests on the model adapter timeout (OllamaResponder 120s → raises → ProducerFailed →
        # ends → finalises). In CI (finite DeterministicResponder) it cannot arise. The watchdog is
        # a TerminationPolicy timer, not a Trigger WallClock cooldown, so it does NOT demote the
        # record's replay ceiling below 3a. Kept for the defensive zero-Producer guard.
        b.termination(
            api.any_of(
                api.cancel_all_others(
                    lambda c: (
                        c.event is not None
                        and getattr(c.event, "kind", "") == api.PRODUCER_COMPLETED
                        and isinstance(getattr(c.event, "payload", None), dict)
                        and c.event.payload.get("producer", {}).get("kind") == "judge"
                    )
                ),
                api.all_completed(),
                api.quiescence_with_watchdog(seconds=watchdog_seconds),
            )
        )

    return topo

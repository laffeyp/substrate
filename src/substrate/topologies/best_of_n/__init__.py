# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""best_of_n — the reusable best-of-N + correction loop (Wave-0 shared sub-topology, sprint 136).

Generalizes coding_flow's pattern: a seeder fans out N Drafts; each Candidate is validated by a
CALLER-SUPPLIED validator; when a round's N verdicts land, a judge selects the passing candidate
(-> Solved), feeds every failure back into a fresh round (-> N Drafts), or gives up (-> Exhausted).
The only model work on the DRAFT side is the drafter.

The validator is CODE by default — a gate, the SEARCH/REPLACE applier — never a model grading its OWN
work (the coding consumers: coding_flow, the swebench Repairer, code_evolution). The one sanctioned
exception is an INDEPENDENT judge: a model of a DISJOINT family from the drafter, for prose/design where
no mechanical check exists (finding #42, used by `applications/best_of_n_verified`). "Never a model" is
about SELF-grading; a disjoint-family judge is not self-grading. `Verdict.source` names which it was —
`"gate"` / `"check"` / `"model"` — so a reader can tell a real process exit from a model's 0/1 proxy
(review C-5, field added).

The shared 3-consumer contract (Draft / Candidate / Verdict / Solved / Exhausted, reused from coding_flow
per WORKING_AGREEMENT) lives in ONE place so the loop's currency / determinism invariants cannot diverge
across coding_flow, the swebench Repairer, and code_evolution (KIT_DIARY finding 12). The CALLER supplies
the drafter + validator FACTORIES (the work) and may override the judge (terminal policy), the validator's
extra schemas, and the termination.

coding_flow's migration onto this module is a later behavior-preserving refactor (#43); it is untouched
now — there are at most two copies of the wiring (coding_flow's original + this canonical), never three.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from ... import api
from ...adapters import ModelUsage
from .contracts import Candidate, Draft, Exhausted, Solved, Verdict

__all__ = [
    "Draft",
    "Candidate",
    "Verdict",
    "Solved",
    "Exhausted",
    "best_of_n_correction",
    "seeder_factory",
    "select_first_judge_factory",
]

_Factory = Callable[[], Any]


def seeder_factory(n: int) -> _Factory:
    """The seed round: fan out N Drafts (round 1, empty context)."""

    async def seed(_inp: Any) -> AsyncIterator[Draft]:
        for i in range(n):
            yield Draft(round=1, slot=i, context="")

    return lambda: seed


def select_first_judge_factory(n: int, max_rounds: int) -> _Factory:
    """The DEFAULT terminal: fires once per round, after all N verdicts. Select the first passing
    candidate (-> Solved), else feed every failure back into a fresh round (-> N Drafts), else give up
    (-> Exhausted). 'first' is immaterial to a consumer (e.g. swebench SELECT) that reads ALL of the
    round's candidates after the loop signals Solved."""

    async def judge(inp: Any) -> AsyncIterator[Any]:
        rnd = int(inp.get("round", 1)) if hasattr(inp, "get") else 1
        verdicts = list(inp.get("verdicts", [])) if hasattr(inp, "get") else []
        passing = [v for v in verdicts if v["passed"]]
        if passing:
            yield Solved(round=rnd, slot=int(passing[0]["slot"]))
        elif rnd < max_rounds:
            failures = "\n\n".join(
                f"[candidate {v['slot']}] validation failed (rc {v['returncode']})\n{v['summary']}"
                for v in verdicts
            )
            for i in range(n):
                yield Draft(round=rnd + 1, slot=i, context=failures)
        else:
            yield Exhausted(rounds=rnd)

    return lambda: judge


def _round_verdicts(ctx: api.TriggerContext, rnd: int) -> list[dict[str, Any]]:
    return [v for v in ctx.views["verdicts"].value() if int(v["round"]) == rnd]


def best_of_n_correction(
    b: api.TopologyBuilder,
    *,
    n: int,
    max_rounds: int,
    draft_factory: _Factory,
    validate_factory: _Factory,
    judge_factory: _Factory | None = None,
    validator_schemas: list[type] | None = None,
    judge_schemas: list[type] | None = None,
    termination: Any | None = None,
    deterministic: bool = False,
    seed_on: str | None = None,
    draft_input_extra: Any | None = None,
) -> None:
    """Wire the shared seeder / drafter / validator / judge loop onto `b`.

    The caller provides the work: `draft_factory` (a Draft -> a Candidate [+ ModelUsage]; the ONLY model
    work) and `validate_factory` (a Candidate -> a Verdict [+ any extra records, e.g. swebench's
    AppliedPatch — declare them in `validator_schemas`]). Optionally override `judge_factory` (the
    terminal policy; default selects the first passing candidate), `judge_schemas`, and `termination`
    (default: Solved | Exhausted | quiescence — a consumer that runs phases AFTER the loop, like swebench
    SELECT, passes its own termination so the loop's Solved is an internal hand-off, not the run terminal).

    Sprint 191 (roadmap v2 S3): two additive kwargs for consumers with pre-loop phases (swebench's
    LOCALIZE gates the drafter on `EditLocations`). Both default to the coding_flow shape.
    - `seed_on=None`: seeder is registered as `initial` and fires at run start (coding_flow).
      `seed_on="<kind>"`: seeder becomes a triggered producer that fires on the named kind
      (swebench_repair: `seed_on="EditLocations"` waits for the localizer's output).
    - `draft_input_extra=None`: draft trigger's input_builder returns `{round, slot, context}` only.
      When set, must be a callable `(TriggerContext) -> dict` whose result merges into the draft input
      (swebench_repair passes `edit_context` from the localizer's EditLocations view)."""
    b.producer_kind(
        "seeder",
        schemas=[Draft],
        schema_version=1,
        factory=seeder_factory(n),
        deterministic=deterministic,
    )
    b.producer_kind(
        "drafter",
        schemas=[Candidate, ModelUsage],
        schema_version=1,
        factory=draft_factory,
        deterministic=deterministic,
    )
    b.producer_kind(
        "validator",
        schemas=validator_schemas or [Verdict],
        schema_version=1,
        factory=validate_factory,
        deterministic=deterministic,
    )
    b.producer_kind(
        "judge",
        schemas=judge_schemas or [Solved, Draft, Exhausted],
        schema_version=1,
        factory=judge_factory or select_first_judge_factory(n, max_rounds),
        deterministic=deterministic,
    )
    b.view("verdicts", api.KindBuffer("Verdict"))
    if seed_on is None:
        b.initial("seeder", input=None)
    else:
        b.trigger(
            "seed",
            subscription=api.Subscription(kinds=frozenset({seed_on})),
            predicate=lambda ctx: True,
            starts="seeder",
            input_builder=lambda ctx: None,
            policy=api.PerEvent(),
        )

    def _draft_input(ctx: api.TriggerContext) -> dict[str, Any]:
        base: dict[str, Any] = {
            "round": int(ctx.event.payload["round"]),
            "slot": int(ctx.event.payload["slot"]),
            "context": ctx.event.payload["context"],
        }
        if draft_input_extra is not None:
            base.update(draft_input_extra(ctx))
        return base

    # one Trigger drafts a candidate per Draft (seed OR correction) — the recursive best-of-N loop.
    b.trigger(
        "draft",
        subscription=api.Subscription(kinds=frozenset({"Draft"})),
        predicate=lambda ctx: True,
        starts="drafter",
        input_builder=_draft_input,
        policy=api.PerEvent(),
    )
    b.trigger(
        "validate",
        subscription=api.Subscription(kinds=frozenset({"Candidate"})),
        predicate=lambda ctx: True,
        starts="validator",
        input_builder=lambda ctx: {
            "round": int(ctx.event.payload["round"]),
            "slot": int(ctx.event.payload["slot"]),
            "response": ctx.event.payload["response"],
        },
        policy=api.PerEvent(),
    )
    # a round is done when all N of its verdicts are in; the judge fires ONCE per round at that point.
    b.trigger(
        "judge",
        subscription=api.Subscription(kinds=frozenset({"Verdict"})),
        predicate=lambda ctx: len(_round_verdicts(ctx, int(ctx.event.payload["round"]))) >= n,
        starts="judge",
        input_builder=lambda ctx: {
            "round": int(ctx.event.payload["round"]),
            "verdicts": _round_verdicts(ctx, int(ctx.event.payload["round"])),
        },
        policy=api.PerEvent(),
    )
    b.termination(
        termination
        or api.any_of(
            api.threshold_count("Solved", 1),
            api.threshold_count("Exhausted", 1),
            api.quiescence(),
        )
    )

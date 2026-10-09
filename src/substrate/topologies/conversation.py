# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Conversation topology — the general N-speaker turn-based substrate (Wave 13).

The shape every conversation demo lifted from the recursive_strategy_refinment precursor
(debate, prisoner's dilemma, intel asymmetry, natural conversation) instantiates: N speaker
Producers take turns; each reads the transcript-so-far and emits one Turn; a round-robin
Trigger fires the next speaker; the run is bounded by a round budget and ended early when any
speaker emits Converged. The precursor hand-rolled this as a cascade scheduler; here it falls
out of Producers + one Trigger per speaker + a transcript View + a threshold termination.

Demos are thin configs over this: debate = two opposing-stipulated responders; prisoner's
dilemma = two responders with asymmetric payoff prompts; intel asymmetry = two responders with
private-knowledge inputs. The system prompts live with each demo; this module is the substrate.

Determinism note: this is TURN-BASED (speaker k+1 fires when speaker k's Turn lands), the
deterministic core. The precursor's concurrent chunked-cascade (all N stream at once, next
fires at a chunk boundary) is the pair_coding pattern; a conversation can adopt it later, but
turn-based keeps the CI record deterministic for Level-2 replay.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any, NamedTuple

from msgspec import Struct

from .. import api
from ..adapters import DeterministicResponder, OllamaResponder, Responder, call_responder
from .instruments.repair import (
    REPAIR_OK,
)  # the cue sentinel a speaker reads; instruments live demo-side

_Factory = Callable[[], Any]


# Output cap for one conversational turn (see speakers()).
TURN_MAX_TOKENS = 1024


def speakers(
    systems: list[str], *, walkthrough: bool, model: str, ci_menu: list[str] | None = None
) -> list[Responder]:
    """Build the conversation's speaker Responders from their system prompts — the one helper every
    conversation demo (debate / PD / intel / natural) shares. Walkthrough: a real OllamaResponder per
    speaker carrying its system prompt. CI: a seeded DeterministicResponder per speaker; for a game
    with a typed outcome, `ci_menu` makes the stub emit a real decision-bearing phrase so the
    speaker's outcome function parses a genuine (deterministic) choice — no stand-in fabrication."""
    if walkthrough:
        # One speaker reply is one conversational turn: 1024 tokens (~750 words) is far above any
        # real turn and bounds a looping small model to seconds, not the 300 s read timeout x3
        # that hung test_instrument_ablation_delta for 900 s (UI sprint 097).
        return [OllamaResponder(model, system=s, max_tokens=TURN_MAX_TOKENS) for s in systems]
    return [DeterministicResponder(seed=i, menu=ci_menu) for i, _ in enumerate(systems)]


class Turn(Struct, frozen=True):
    speaker: int
    text: str
    round: int


class Converged(Struct, frozen=True):
    by: int  # the speaker who declared convergence (CONVERGED early-stop)


# A per-game OUTCOME extractor: (text, speaker_id, round) -> a typed outcome event the DECIDING
# speaker emits at its OWN mouth (PD's Decision, intel's JointCall), or None. NOT a downstream
# detector parsing another Producer's prose — the player structures its own output into a typed
# event before the bus validates it (F-OBS-2: the decision is attributed to the player, not a parser).
_OutcomeFn = Callable[[str, int, int], Any]


class Instrument(NamedTuple):
    """A side-Producer the conversation engine installs, fired once per Turn. The CALLER composes
    the instruments it wants (each `factory` pre-bound with its responder + config) and hands the
    engine a list; the engine just installs them. This keeps the engine a turn-taking core that
    knows nothing about common-ground / repair / grading — those are the natural-conversation demo's
    concern, composed in (see `_emergence_instruments`), not flags on this function.

    Shape mirrors `b.instrument` minus the fixed `on="Turn"` and the engine-supplied `deterministic`.
    `into` (+ `via`) stages the instrument's output into a Route slot the next speaker reads; omit
    both for an observation-only instrument (a grader, whose output is scored off the bus)."""

    name: str
    schemas: list[type]
    factory: _Factory
    input_builder: Callable[[api.TriggerContext], Any]
    into: str | None = None
    via: Callable[[Any], Any] | None = None


def _next_round(turn: dict[str, Any], n: int) -> int:
    # the round advances when the round-robin wraps from speaker N back to speaker 1.
    return int(turn["round"]) + 1 if int(turn["speaker"]) >= n else int(turn["round"])


def _after_predicate(k: int, n: int, max_rounds: int) -> Callable[[api.TriggerContext], bool]:
    # fire speaker k+1 after speaker k's Turn, while within the round budget (closure over k/n,
    # so the callback is a clean single-`ctx` lambda — no default-arg trick mypy can't infer).
    return lambda ctx: (
        int(ctx.event.payload["speaker"]) == k and _next_round(ctx.event.payload, n) <= max_rounds
    )


def _after_input(nxt: int, n: int) -> Callable[[api.TriggerContext], Any]:
    return lambda ctx: {
        "round": _next_round(ctx.event.payload, n),
        "speaker_id": nxt,
        "prior_turns": list(ctx.views["transcript"].value()),
        "common_ground": ctx.staged.get("cg"),
        "repair": ctx.staged.get("repair"),
    }


def _speaker_factory(
    speaker_id: int,
    responder: Responder,
    converge_at: tuple[int, int] | None,
    outcome_fn: _OutcomeFn | None = None,
) -> _Factory:
    async def speaker(inp: Any) -> AsyncIterator[Any]:
        rnd = int(inp.get("round", 1)) if hasattr(inp, "get") else 1
        prior = inp.get("prior_turns", []) if hasattr(inp, "get") else []
        cg = inp.get("common_ground") if hasattr(inp, "get") else None
        rep = inp.get("repair") if hasattr(inp, "get") else None
        transcript = "\n".join(f"S{t['speaker']}: {t['text']}" for t in prior)
        # the instruments feed the speaker (this is the emergence wiring): the accreted common
        # ground and any requires-repair cue enter the prompt, so a WITH-instruments run produces
        # different turns than the bare run — the natural-conversation ablation's whole point.
        extra = ""
        if cg:
            extra += f"\nCOMMON GROUND SO FAR: {cg}"
        if rep and rep.get("status") != REPAIR_OK:
            extra += f"\nREQUIRES REPAIR: {rep.get('note', '')}"
        # The user message must INSTRUCT the turn, not just dump the transcript: a real model handed
        # a bare transcript "completes" it by echoing the last line (the round-2 echo bug). In CI the
        # deterministic stub hashes the whole prompt, so any wording yields a unique stub — the bug is
        # invisible there and only a real model exposes it. Frame the speaker's task explicitly.
        if prior:
            user_msg = (
                f"You are speaker {speaker_id}. The conversation so far:\n\n{transcript}\n\n"
                f"Write speaker {speaker_id}'s NEXT turn now — advance your own position and respond "
                f"to what was just said. Do not repeat or copy an earlier turn.{extra}"
            )
        else:
            user_msg = f"You are speaker {speaker_id}. Open the conversation.{extra}"
        text = await call_responder(responder, user_msg)
        # strip any leaked transcript label ("S2:", even doubled "S2: S2:") the model copied from the
        # transcript format into its own output — cosmetic, keeps the recorded turn clean.
        text = re.sub(r"^\s*(S\d+:\s*)+", "", text)
        # converge_at is a deterministic CI test hook for the early-stop (Converged) termination
        # path: it names the (speaker, round) that declares convergence. Real-model convergence is
        # NOT wired — no current demo claims it (debate's claim is the two-sided pressure-test, not
        # convergence). A demo that wanted it would emit Converged from its OWN model output here,
        # the same at-the-mouth pattern as outcome_fn — not via a downstream sentinel parser.
        if converge_at is not None and converge_at == (speaker_id, rnd):
            yield Converged(by=speaker_id)
            return
        # cap the recorded turn — generous enough to retain a trailing decision line (PD's
        # "STAY SILENT / TALK", intel's calibrated %); CI stub text is short, so this bounds only
        # verbose real-model turns.
        yield Turn(speaker=speaker_id, text=text[:700], round=rnd)
        # the deciding speaker structures its OWN output into a typed outcome event and emits it
        # HERE — so the record attributes the decision to this player (F-OBS-2), and the bus
        # validates it (F-BUS-6). The parse happens inside the deciding Producer, not in a
        # downstream detector reading this speaker's prose.
        if outcome_fn is not None:
            outcome = outcome_fn(text, speaker_id, rnd)
            if outcome is not None:
                yield outcome

    return lambda: speaker


def conversation_topology(
    responders: Sequence[Responder],
    *,
    max_rounds: int = 3,
    converge_at: tuple[int, int] | None = None,
    deterministic: bool = True,
    instruments: Sequence[Instrument] = (),
    outcome: tuple[type[Struct], _OutcomeFn] | None = None,
) -> Callable[[api.TopologyBuilder], None]:
    """Build an N-speaker turn-based conversation. `responders` is one Responder per speaker
    (N = len). Speaker 1 opens; a round-robin Trigger fires the next speaker on each Turn until
    `max_rounds` rounds complete; any speaker emitting Converged ends the run early. `converge_at`
    (speaker, round) makes that speaker declare convergence (deterministic early-stop for CI).

    `outcome=(Kind, fn)` lets the deciding speaker emit a typed outcome at its own mouth (PD's
    Decision, intel's JointCall). `instruments` are caller-composed side-Producers fired per Turn
    (common-ground / repair / grader for the natural-conversation ablation); an instrument that
    declares `into` stages its output into a Route slot the next speaker reads on its following turn
    — the same stage-then-read lag as pair_coding (a side Producer for turn T stages AFTER the
    next-speaker Trigger for turn T reads the slot; you react to what was just said, deterministic).
    The engine knows nothing about which instruments exist — the demo composes them."""

    n = len(responders)
    if n < 2:
        raise api.RegistrationError("a conversation needs at least 2 speakers")

    # a speaker that owns an outcome declares that kind too, and emits it at its own mouth.
    outcome_schemas: list[type[Struct]] = [outcome[0]] if outcome else []
    outcome_fn: _OutcomeFn | None = outcome[1] if outcome else None

    def topo(b: api.TopologyBuilder) -> None:
        for i, r in enumerate(responders, start=1):
            b.producer_kind(
                f"speaker-{i}",
                schemas=[Turn, Converged, *outcome_schemas],
                schema_version=1,
                factory=_speaker_factory(i, r, converge_at, outcome_fn),
                deterministic=deterministic,
            )
        b.initial("speaker-1", input={"round": 1, "prior_turns": []})
        # the transcript every speaker reads (Turn events only — not Converged).
        b.view("transcript", api.KindBuffer("Turn"))
        # install whatever instruments the caller composed — one side Producer per Turn. The engine
        # is agnostic about what they are; the demo (natural_conversation) decides.
        for inst in instruments:
            b.instrument(
                inst.name,
                on="Turn",
                schemas=inst.schemas,
                factory=inst.factory,
                deterministic=deterministic,
                input_builder=inst.input_builder,
                into=inst.into,
                via=inst.via,
            )
        # one round-robin Trigger per speaker: after speaker k's Turn, fire speaker k+1 (wrapping
        # N→1), carrying the next round and the transcript-so-far, while within the round budget.
        for k in range(1, n + 1):
            nxt = k + 1 if k < n else 1
            b.trigger(
                f"after-{k}",
                subscription=api.Subscription(kinds=frozenset({"Turn"})),
                predicate=_after_predicate(k, n, max_rounds),
                starts=f"speaker-{nxt}",
                input_builder=_after_input(nxt, n),
                policy=api.PerEvent(),
            )
        # end on the first Converged (early-stop), else on quiescence once the round budget stops
        # the cascade (the watchdog also backstops a wedged speaker — see code_review for the
        # honest bound: quiescence, not a hard deadline).
        b.termination(
            api.any_of(
                api.threshold_count("Converged", 1),
                api.quiescence(),
            )
        )

    return topo

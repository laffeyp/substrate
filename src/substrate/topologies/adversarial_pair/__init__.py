# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Adversarial pair topology — writer vs vulnerability-finder, bounded refinement (Wave 13).

A writer Producer emits an artifact; a vulnerability-finder Producer (fired on each artifact)
emits a typed Challenge; a Route stages the challenge into the writer's NEXT instantiation, which
revises to address it — a refinement loop bounded by an attempt-count predicate. The adversarial
pressure (find the weakness, then fix it) is INSTRUMENTED by the finder + the bounded loop, not
prescribed in a prompt. The precursor's GAN / red-team shape; in substrate it is the pair_coding
route-into-next-instantiation pattern with an adversarial second role and a bounded loop.

CI: deterministic stand-ins (the wiring runs reproducibly, Level-2 replayable). Walkthrough: a
real writer model and a real finder model.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from msgspec import Struct

from ... import api
from ...adapters import Responder, call_responder

_Factory = Callable[[], Any]


class Artifact(Struct, frozen=True):
    text: str
    version: int


class Challenge(Struct, frozen=True):
    issue: str
    severity: int
    version: int


def _writer_factory(responder: Responder) -> _Factory:
    async def write(inp: Any) -> AsyncIterator[Artifact]:
        version = int(inp.get("version", 0)) if hasattr(inp, "get") else 0
        challenge: Any = inp.get("challenge") if hasattr(inp, "get") else None
        prior = str(inp.get("prior", "")) if hasattr(inp, "get") else ""
        if version == 0:
            prompt = "Write a short artifact (a few sentences)."
        else:
            issue = challenge.get("issue") if hasattr(challenge, "get") else challenge
            # revise the PRIOR artifact against the REAL flaw the finder named.
            prompt = (
                f"Here is an artifact:\n{prior}\n\nA reviewer found this flaw: {issue}\n"
                "Revise the artifact to fix it; reply with only the revised artifact."
            )
        text = await call_responder(responder, prompt)
        yield Artifact(text=text[:200], version=version)

    return lambda: write


def _finder_factory(responder: Responder) -> _Factory:
    async def find(inp: Any) -> AsyncIterator[Challenge]:
        version = int(inp.get("version", 0)) if hasattr(inp, "get") else 0
        text = str(inp.get("artifact", "")) if hasattr(inp, "get") else ""
        # the finder OWNS the finding: it emits the model's REAL vulnerability as the Challenge, not
        # a templated placeholder, so the writer revises against an actual flaw (not "issue@vN").
        finding = await call_responder(
            responder, f"Name the single worst flaw in this artifact in one short sentence:\n{text}"
        )
        finding = finding.strip().splitlines()[0][:120] if finding.strip() else "no flaw found"
        severity = (sum(finding.encode()) % 3) + 1  # a deterministic projection of the real finding
        yield Challenge(issue=finding, severity=severity, version=version)

    return lambda: find


def adversarial_pair_topology(
    *,
    writer_model: Responder | None = None,
    finder_model: Responder | None = None,
    max_attempts: int = 3,
    deterministic: bool = True,
    walkthrough: bool = False,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the adversarial-pair topology. The writer drafts; the finder challenges each draft;
    a bounded loop (`max_attempts`) refines the writer against the staged challenge. CI uses
    deterministic stand-ins. Produces `max_attempts + 1` artifacts (v0..v_max) and `max_attempts`
    refinements; the loop stops when a challenge's version reaches the attempt cap."""

    from ...adapters import DeterministicResponder, OllamaResponder

    if walkthrough:
        writer = writer_model or OllamaResponder(
            "llama3.2:1b", system="You write a short artifact."
        )
        finder = finder_model or OllamaResponder("llama3.2:1b", system="You find one flaw.")
    else:
        writer = writer_model or DeterministicResponder(seed=1)
        finder = finder_model or DeterministicResponder(seed=2)

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "writer",
            schemas=[Artifact],
            schema_version=1,
            factory=_writer_factory(writer),
            deterministic=deterministic,
        )
        b.producer_kind(
            "finder",
            schemas=[Challenge],
            schema_version=1,
            factory=_finder_factory(finder),
            deterministic=deterministic,
        )
        b.initial("writer", input={"version": 0, "challenge": None})
        # the artifacts so far — the refine loop reads the latest to revise it against the challenge.
        b.view("artifacts", api.KindBuffer("Artifact"))
        # each artifact is challenged by the finder (the adversary reads the draft).
        b.trigger(
            "to-finder",
            subscription=api.Subscription(kinds=frozenset({"Artifact"})),
            predicate=lambda ctx: True,
            starts="finder",
            input_builder=lambda ctx: {
                "artifact": ctx.event.payload["text"],
                "version": int(ctx.event.payload["version"]),
            },
            policy=api.PerEvent(),
        )
        # stage the challenge into the writer's next instantiation (recorded as InjectionApplied).
        b.route(
            "stage-challenge",
            subscription=api.Subscription(kinds=frozenset({"Challenge"})),
            slot="challenge",
            transform=lambda event: {
                "issue": event.payload["issue"],
                "severity": event.payload["severity"],
            },
        )
        # the bounded refinement loop: revise the writer against the challenge until the attempt
        # cap — the predicate gates the recursion, so it cannot run away.
        b.trigger(
            "refine",
            subscription=api.Subscription(kinds=frozenset({"Challenge"})),
            predicate=lambda ctx: int(ctx.event.payload["version"]) < max_attempts,
            starts="writer",
            input_builder=lambda ctx: {
                "version": int(ctx.event.payload["version"]) + 1,
                "challenge": ctx.staged.get("challenge"),
                "prior": (
                    ctx.views["artifacts"].value()[-1]["text"]
                    if ctx.views["artifacts"].value()
                    else ""
                ),
            },
            policy=api.PerEvent(),
        )
        b.termination(api.quiescence())

    return topo

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""research_sweep — fan out readers over a document set, critique gaps, synthesize (application-parity W1.3).

The map-reduce of the application library: where fanout_review and best_of_n_verified fan out over ONE
input and select/judge, research_sweep fans out over DIFFERENT inputs (a document set) and SYNTHESIZES.
A seeder emits one ReadRequest per document; a reader extracts findings from each for the research
question; a completeness critic names what is still missing across all findings; a synthesizer writes
the answer grounded in findings + gaps.

No existing whole topology composes cleanly for map-reduce (code_review's reviewers share one `code`;
best_of_n's slots all attempt one task), so this is authored from the standard builder primitives — the
same way code_review and best_of_n were. The four Structs below are topology-local application event
kinds (like code_review's CritiquePosted), not the locked lifecycle vocabulary.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from msgspec import Struct

from ... import api
from ...adapters import ModelUsage, Responder, call_responder_metered

_Factory = Callable[[], Any]

# Bound each document so a large corpus cannot blow the reader prompt (the tool-result byte-cap lesson).
_MAX_DOC_CHARS = 8_000


class ReadRequest(Struct, frozen=True):
    """A document handed to one reader: its index in the sweep, a source label, its (bounded) content."""

    index: int
    source: str
    content: str


class Finding(Struct, frozen=True):
    """One reader's finding for the research question, from its own document."""

    index: int
    source: str
    note: str


class Gaps(Struct, frozen=True):
    """The completeness critic's account of what the findings do NOT yet cover."""

    note: str


class Synthesis(Struct, frozen=True):
    """The synthesizer's answer, grounded in the findings and the named gaps."""

    text: str


def gather(paths: list[str | Path]) -> list[tuple[str, str]]:
    """Read each path read-only into (source, bounded-content). A missing path raises FileNotFoundError
    (surfaced, not swallowed). Content over the cap is truncated with a visible marker."""
    out: list[tuple[str, str]] = []
    for p in paths:
        path = Path(p).expanduser()
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > _MAX_DOC_CHARS:
            text = text[:_MAX_DOC_CHARS] + f"\n\n[{path.name} truncated at {_MAX_DOC_CHARS} chars]"
        out.append((path.name, text))
    return out


def _seeder_factory(documents: list[tuple[str, str]]) -> _Factory:
    async def seed(_inp: Any) -> AsyncIterator[ReadRequest]:
        for i, (source, content) in enumerate(documents):
            yield ReadRequest(index=i, source=source, content=content)

    return lambda: seed


def _reader_factory(question: str, reader: Responder) -> _Factory:
    async def read(inp: Any) -> AsyncIterator[Finding | ModelUsage]:
        index = int(inp.get("index", 0)) if hasattr(inp, "get") else 0
        source = str(inp.get("source", "")) if hasattr(inp, "get") else ""
        content = str(inp.get("content", "")) if hasattr(inp, "get") else ""
        # Exactly one Finding per ReadRequest, even on reader failure: the fan-in counts to n, so a
        # single failed/empty read cannot stall the sweep. A dead reader becomes a recorded empty
        # contribution that the completeness critic then names — not a run that finalises with no answer.
        # Every model call is metered onto the record (F-18) so the sweep is assayable.
        try:
            note, usage = await call_responder_metered(
                reader,
                f"Research question: {question}\n\nRead this source and state, in one or two sentences, "
                f"only what it contributes to the question (or that it contributes nothing).\n\n"
                f"SOURCE {source}:\n{content}",
            )
            yield usage
            note = note.strip() or "(no contribution)"
        except Exception as exc:  # noqa: BLE001 — a reader failure is a recorded gap, not a hung run
            note = f"(read failed: {type(exc).__name__})"
        yield Finding(index=index, source=source, note=note)

    return lambda: read


def _critic_factory(question: str, critic: Responder) -> _Factory:
    async def criticize(inp: Any) -> AsyncIterator[Gaps | ModelUsage]:
        findings = list(inp.get("findings", [])) if hasattr(inp, "get") else []
        joined = "\n".join(f"- {f['source']}: {f['note']}" for f in findings)
        # death-resilience, as a SET with the reader (F-4 / KIT_DIARY #16): a failed critic call must
        # still emit Gaps, or the synthesize trigger never fires and the sweep finalises with no answer.
        try:
            note, usage = await call_responder_metered(
                critic,
                f"Research question: {question}\n\nHere are the findings gathered so far:\n{joined}\n\n"
                f"In one or two sentences, name what is still MISSING to answer the question well — the "
                f"gaps these findings do not cover.",
            )
            yield usage  # metered onto the record (F-18)
            note = note.strip() or "(no gaps named)"
        except Exception as exc:  # noqa: BLE001 — a model failure becomes a recorded gap; K254 retires this (ledger F127, F189)
            note = f"(critic failed: {type(exc).__name__})"
        yield Gaps(note=note)

    return lambda: criticize


def _synthesizer_factory(question: str, synthesizer: Responder) -> _Factory:
    async def synthesize(inp: Any) -> AsyncIterator[Synthesis | ModelUsage]:
        findings = list(inp.get("findings", [])) if hasattr(inp, "get") else []
        gaps = str(inp.get("gaps", "")) if hasattr(inp, "get") else ""
        joined = "\n".join(f"- {f['source']}: {f['note']}" for f in findings)
        # the reduce seam gets the same guard: a failed synthesizer call still emits Synthesis (a recorded
        # failure), so the run reaches its terminal with an honest marker rather than silent-no-answer.
        try:
            text, usage = await call_responder_metered(
                synthesizer,
                f"Research question: {question}\n\nFindings:\n{joined}\n\nKnown gaps: {gaps}\n\n"
                f"Write a concise answer to the question grounded in these findings; note where the gaps "
                f"limit the answer.",
            )
            yield usage  # metered onto the record (F-18)
            text = text.strip() or "(empty synthesis)"
        except Exception as exc:  # noqa: BLE001 — a model failure becomes a recorded gap; K254 retires this (ledger F127, F189)
            text = f"(synthesis failed: {type(exc).__name__})"
        yield Synthesis(text=text)

    return lambda: synthesize


def _round_findings(ctx: api.TriggerContext) -> list[dict[str, Any]]:
    return list(ctx.views["findings"].value())


def research_sweep_topology(
    question: str,
    documents: list[tuple[str, str]],
    *,
    reader: Responder,
    critic: Responder,
    synthesizer: Responder,
    deterministic: bool = False,
    watchdog_seconds: float = 30.0,
) -> Callable[[api.TopologyBuilder], None]:
    """Fan a reader over each of `documents` for `question`, run a completeness critic over all the
    findings, then synthesize the answer. `reader`/`critic`/`synthesizer` are Responders (may be the
    same model or different). Authored from primitives — seeder-fan-out (best_of_n shape) + fan-in
    quorum trigger (code_review shape) — with the four topology-local Structs above.

    Raises ValueError on an empty document set: with no documents no Finding is ever emitted, the
    critique fan-in never fires, and the run would finalise via `all_completed` with NO Synthesis — the
    same silent-no-answer class as the reader-failure hole (F-4). The library refuses it at build time,
    matching the guard `scripts/run_research_sweep.py` already applies at the CLI (2026-08-02 review)."""
    if not documents:
        raise ValueError("research_sweep_topology: `documents` is empty — nothing to sweep")
    n = len(documents)

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "seeder",
            schemas=[ReadRequest],
            schema_version=1,
            factory=_seeder_factory(documents),
            deterministic=deterministic,
        )
        b.producer_kind(
            "reader",
            schemas=[Finding, ModelUsage],
            schema_version=1,
            factory=_reader_factory(question, reader),
            deterministic=deterministic,
        )
        b.producer_kind(
            "critic",
            schemas=[Gaps, ModelUsage],
            schema_version=1,
            factory=_critic_factory(question, critic),
            deterministic=deterministic,
        )
        b.producer_kind(
            "synthesizer",
            schemas=[Synthesis, ModelUsage],
            schema_version=1,
            factory=_synthesizer_factory(question, synthesizer),
            deterministic=deterministic,
        )
        b.view("findings", api.KindBuffer("Finding"))
        b.initial("seeder", input=None)
        # map: one reader per document.
        b.trigger(
            "read",
            subscription=api.Subscription(kinds=frozenset({"ReadRequest"})),
            predicate=lambda ctx: True,
            starts="reader",
            input_builder=lambda ctx: {
                "index": int(ctx.event.payload["index"]),
                "source": ctx.event.payload["source"],
                "content": ctx.event.payload["content"],
            },
            policy=api.PerEvent(),
        )
        # fan-in: when all N findings are in, the critic fires ONCE (code_review's quorum shape).
        b.trigger(
            "critique",
            subscription=api.Subscription(kinds=frozenset({"Finding"})),
            predicate=lambda ctx: len(_round_findings(ctx)) >= n,
            starts="critic",
            input_builder=lambda ctx: {"findings": _round_findings(ctx)},
            policy=api.Once(),
        )
        # reduce: the synthesizer fires once on the gaps, reading all findings.
        b.trigger(
            "synthesize",
            subscription=api.Subscription(kinds=frozenset({"Gaps"})),
            predicate=lambda ctx: True,
            starts="synthesizer",
            input_builder=lambda ctx: {
                "findings": _round_findings(ctx),
                "gaps": ctx.event.payload["note"],
            },
            policy=api.Once(),
        )
        b.termination(
            api.any_of(
                api.threshold_count("Synthesis", 1),
                api.all_completed(),
                api.quiescence_with_watchdog(seconds=watchdog_seconds),
            )
        )

    return topo

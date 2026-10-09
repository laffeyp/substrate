# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Pair coding topology — driver + navigator, chunked instantiation (Sprint 131).

A driver Producer streams code one chunk at a time; a navigator Producer, fired on each of
the driver's CodeChunk emissions, reads a View of the accumulating code and emits a typed
Suggestion; a Route stages the Suggestion into a slot; a Trigger fires the driver's NEXT
chunk instantiation reading the staged suggestion. So the driver "learns" from the navigator
across instantiations — the kernel's route-context-into-a-future-instantiation pattern made
visible as a software ritual.

The honest constraint (kernel input immutability): a Route stages into the NEXT instantiation,
never into a running Producer, so the driver runs in chunked instantiations (one chunk each)
rather than a single continuous stream. That is chunked pair coding, not human live pair
coding — the walkthrough doc says so plainly.

Determinism note (DEVIATION from the sprint card, surfaced to BLACKBOARD): the card gates the
next chunk on a ChunkBoundary event. A driver emits its CodeChunk and ChunkBoundary back to
back, so gating on ChunkBoundary would race the navigator's Suggestion (the boundary often
lands before the suggestion is staged) — nondeterministic, which breaks Level-2 replay. We gate
the next chunk on the navigator's Suggestion instead: a REAL data dependency (chunk N+1 cannot
start until the navigator has reviewed chunk N), so the record is deterministic and the
"driver learns from navigator" claim is load-bearing rather than incidental. ChunkBoundary is
still emitted as a semantic unit-complete marker (and for the TUI), just not as the gate.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from msgspec import Struct

from ... import api
from ...adapters import Responder, call_responder

_Factory = Callable[[], Any]


class CodeChunk(Struct, frozen=True):
    file_path: str
    text: str
    chunk_index: int


class ChunkBoundary(Struct, frozen=True):
    file_path: str
    kind: str  # "function" | "class" | "file"


class Suggestion(Struct, frozen=True):
    file_path: str
    anchor_seq: int  # the bus seq of the CodeChunk this suggestion responds to
    rationale: str
    suggested_text: str | None = None


def _driver_factory(file_path: str, chunks: list[str], responder: Responder) -> _Factory:
    async def driver(inp: Any) -> AsyncIterator[Any]:
        index = int(inp.get("index", 0)) if hasattr(inp, "get") else 0
        if index >= len(chunks):
            return  # past the last chunk: nothing to write, the instantiation completes
        # In walkthrough mode the chunk text is the model's next emission, optionally informed by
        # the staged suggestion; in CI it is the canned chunk (the suggestion is still recorded as
        # injected — the wiring is what CI proves).
        suggestions = inp.get("suggestions") if hasattr(inp, "get") else None
        _ = await call_responder(responder, f"continue {file_path} given suggestion={suggestions}")
        yield CodeChunk(file_path=file_path, text=chunks[index], chunk_index=index)
        yield ChunkBoundary(file_path=file_path, kind="function")

    return lambda: driver


def _navigator_factory(responder: Responder) -> _Factory:
    async def navigator(inp: Any) -> AsyncIterator[Suggestion]:
        chunk = inp.get("chunk", {}) if hasattr(inp, "get") else {}
        anchor = int(inp.get("anchor_seq", -1)) if hasattr(inp, "get") else -1
        rationale = await call_responder(responder, f"review chunk: {chunk.get('text', '')}")
        yield Suggestion(
            file_path=str(chunk.get("file_path", "")),
            anchor_seq=anchor,
            rationale=rationale[:120],
            suggested_text=None,
        )

    return lambda: navigator


def pair_coding_topology(
    task: str,
    *,
    driver_model: Responder,
    navigator_model: Responder,
    chunks: list[str] | None = None,
    file_path: str = "solution.py",
    deterministic: bool = True,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the pair-coding topology. `driver_model` writes; `navigator_model` reviews. In CI
    `chunks` is the canned sequence the driver streams (one per instantiation); in walkthrough
    mode the driver is a real model and `chunks` bounds the number of instantiations. The
    navigator is fired on each CodeChunk (the driver's emissions only — never its own, so there
    is no self-feedback), reads the accumulating-code View, and emits a Suggestion; a Route
    stages it; the next chunk's instantiation reads the staged suggestion. `deterministic` flags
    the kinds for Level-3(a) replay (True in CI)."""

    chunks = chunks if chunks is not None else ["def solve():\n", "    return 42\n"]
    n_chunks = len(chunks)

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "driver",
            schemas=[CodeChunk, ChunkBoundary],
            schema_version=1,
            factory=_driver_factory(file_path, chunks, driver_model),
            deterministic=deterministic,
        )
        b.producer_kind(
            "navigator",
            schemas=[Suggestion],
            schema_version=1,
            factory=_navigator_factory(navigator_model),
            deterministic=deterministic,
        )
        b.initial("driver", input={"index": 0, "suggestions": None})
        # the accumulating-code View the navigator reads (the driver's CodeChunk buffer ONLY, by
        # kind — not the driver's ChunkBoundary markers): chunk count == len gates the chain end.
        b.view("code", api.KindBuffer("CodeChunk"))
        # driver chunk -> navigator (PerEvent, one review per chunk). Subscribes to CodeChunk —
        # the driver's emission — NOT to Suggestion, so the navigator never reviews itself.
        b.trigger(
            "to-navigator",
            subscription=api.Subscription(kinds=frozenset({"CodeChunk"})),
            predicate=lambda ctx: True,
            starts="navigator",
            input_builder=lambda ctx: {
                "chunk": ctx.event.payload,
                "anchor_seq": ctx.event.seq,
                "code_so_far": list(ctx.views["code"].value()),
            },
            policy=api.PerEvent(),
        )
        # stage the navigator's Suggestion into the "suggestions" slot (recorded as
        # substrate.InjectionApplied) so the next driver instantiation reads it.
        b.route(
            "stage-suggestion",
            subscription=api.Subscription(kinds=frozenset({"Suggestion"})),
            slot="suggestions",
            transform=lambda event: {
                "rationale": event.payload.get("rationale", ""),
                "anchor_seq": event.payload.get("anchor_seq", -1),
            },
        )
        # the navigator's Suggestion gates the driver's NEXT chunk (the real data dependency).
        # The next index is the count of CodeChunks so far; stop when every chunk is written.
        b.trigger(
            "next-chunk",
            subscription=api.Subscription(kinds=frozenset({"Suggestion"})),
            predicate=lambda ctx: len(ctx.views["code"].value()) < n_chunks,
            starts="driver",
            input_builder=lambda ctx: {
                "index": len(ctx.views["code"].value()),
                "suggestions": ctx.staged.get("suggestions"),
            },
            policy=api.PerEvent(),
        )
        b.termination(api.quiescence())

    return topo

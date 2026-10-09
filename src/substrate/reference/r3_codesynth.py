# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""R-3 — Code synthesis with overlap, composed (product §8).

A writer Producer streams code in chunks; a checker Producer (the "AST" stand-in) emits a
declaration event from a View on the writer's accumulating buffer when a complete declaration
appears (the chunk-boundary/overlap predicate); a typecheck Producer fires on each complete
declaration WHILE the writer is still streaming. The whole inner pipeline is wrapped as an
EMBEDDED SUBSTRATE that exports only `ArtifactReady` onto an OUTER two-stage topology.

Exercises: buffer Views (the checker predicate reads a View over the writer's emitted chunks),
chunk-boundary predicates with overlap (a declaration may span chunks; the predicate fires
once per COMPLETE declaration, not per chunk), composition / export maps (only ArtifactReady
crosses the inner→outer boundary), and `substrate tail` (the outer run is followable).

This is a deterministic STAND-IN, not a real toolchain: the "AST" detector is a `def`-block
splitter over the buffered chunks (no tree-sitter dependency in CI), and the typecheck stage
runs a real but cheap, deterministic `ast.parse()`/`compile()` over the accumulated source —
emitting `ok=False` on a SyntaxError — so it genuinely checks something while staying
reproducible. It does NOT run mypy/pytest/a subprocess. Swap a real type/test checker into the
typecheck Producer in your own topology; the wiring (a checker firing per complete declaration
as the writer streams) is what R-3 demonstrates. Walkthrough mode swaps a real code model
(qwen2.5-coder) into the writer.
"""

from __future__ import annotations

import ast
from collections.abc import AsyncIterator, Callable
from typing import Any

from msgspec import Struct

from .. import api

# R-3's CI mode is fully deterministic (no model); the writer streams a fixed program. The
# walkthrough swaps in a real code model for the writer — see the walkthrough script — so this
# module needs no Responder import (the writer factory takes the chunks directly).

_Factory = Callable[[], Any]


class CodeChunk(Struct, frozen=True):
    text: str


class Declaration(Struct, frozen=True):
    index: int
    source: str


class TypecheckOk(Struct, frozen=True):
    index: int
    ok: bool


class ArtifactReady(Struct, frozen=True):
    declarations: int


# ── inner topology (the composed code-synth pipeline) ──────────────────────────
def _writer_factory(chunks: list[str]) -> _Factory:
    async def write(_input: Any) -> AsyncIterator[CodeChunk]:
        for c in chunks:
            yield CodeChunk(text=c)

    return lambda: write


def _ast_factory() -> _Factory:
    # one Declaration per complete `def ...:` block detected in the accumulated buffer.
    async def ast(inp: Any) -> AsyncIterator[Declaration]:
        idx = inp["index"] if hasattr(inp, "get") else 0
        src = inp.get("source", "") if hasattr(inp, "get") else ""
        yield Declaration(index=idx, source=src)

    return lambda: ast


def _typecheck_factory() -> _Factory:
    async def typecheck(inp: Any) -> AsyncIterator[TypecheckOk]:
        idx = inp.get("index", 0) if hasattr(inp, "get") else 0
        source = inp.get("source", "") if hasattr(inp, "get") else ""
        # A real but cheap, DETERMINISTIC check: parse the declaration's source. ok=False on a
        # SyntaxError (so the stand-in genuinely checks something), without running mypy/pytest/a
        # subprocess. Swap a real type/test checker here in your own topology.
        try:
            ast.parse(source)
            ok = True
        except SyntaxError:
            ok = False
        yield TypecheckOk(index=idx, ok=ok)

    return lambda: typecheck


class _DeclCountKey:
    """A stateful PerKey key fn: accumulates the chunk text it has seen (PerKey calls it once
    per matching CodeChunk, in order) and returns the running count of COMPLETE declarations.
    PerKey dedups on this count, so the AST trigger fires once per newly-completed declaration
    — once when the count first reaches 1, once at 2, … — regardless of how many chunks a
    declaration spanned. (PerKey's key fn only sees the event, not the View, so the running
    buffer is kept here.)"""

    def __init__(self) -> None:
        self._buf = ""

    def __call__(self, event: Any) -> int:
        text = event.payload.get("text", "") if isinstance(event.payload, dict) else ""
        self._buf += text
        return len(_complete_defs([{"text": self._buf}]))


def _complete_defs(buffer_chunks: list[Any]) -> list[str]:
    """The CI chunk-boundary/overlap detector: from the accumulated CodeChunk payloads,
    return the COMPLETE `def ...:`-headed blocks. A declaration may span chunks (overlap); we
    join all buffered text and split on `def ` headers, keeping only blocks that have reached
    the next `def ` or end-of-buffer with a body line — proving the predicate fires once per
    complete declaration, not once per chunk."""
    text = "".join(c.get("text", "") if isinstance(c, dict) else "" for c in buffer_chunks)
    parts = text.split("def ")
    decls: list[str] = []
    for p in parts[1:]:
        block = "def " + p
        # complete = has a colon header AND at least one indented body line
        if ":" in block and "\n " in block:
            decls.append(block.split("def ", 1)[0].join(["def ", p]).strip())
    return decls


def codesynth_inner_topology(
    chunks: list[str], *, deterministic: bool = True
) -> Callable[[api.TopologyBuilder], None]:
    """The inner composed pipeline: writer → (buffer-View chunk-boundary predicate) AST →
    (PerEvent) typecheck → ArtifactReady on completion."""

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "writer",
            schemas=[CodeChunk],
            schema_version=1,
            factory=_writer_factory(chunks),
            deterministic=deterministic,
        )
        b.producer_kind(
            "ast",
            schemas=[Declaration],
            schema_version=1,
            factory=_ast_factory(),
            deterministic=deterministic,
        )
        b.producer_kind(
            "typecheck",
            schemas=[TypecheckOk],
            schema_version=1,
            factory=_typecheck_factory(),
            deterministic=deterministic,
        )
        b.producer_kind(
            "artifact",
            schemas=[ArtifactReady],
            schema_version=1,
            factory=_artifact_factory(),
            deterministic=deterministic,
        )
        b.initial("writer", input=None)  # the writer is the inner run's initial Producer
        # a buffer View over the writer's chunks (the overlap substrate the AST predicate
        # reads): as-of-N, it holds every CodeChunk appended so far, so the predicate sees the
        # accumulating code including the current chunk.
        b.view("code", api.BufferView("writer"))
        # chunk-boundary / overlap predicate: fire the AST producer once per NEWLY-complete
        # declaration. PerKey dedups on the declaration COUNT-so-far (read from the buffer
        # View at fire time, which is stable for a given chunk), so a declaration that spans
        # several chunks fires the AST exactly once — when the chunk that completes it lands —
        # not once per chunk. (CI: the deterministic writer may chunk mid-declaration to
        # exercise the overlap; walkthrough: a real model streams arbitrary chunks and
        # tree-sitter replaces _complete_defs.)
        b.trigger(
            "on-declaration",
            subscription=api.Subscription(kinds=frozenset({"CodeChunk"})),
            predicate=lambda ctx: len(_complete_defs(ctx.views["code"].value())) > 0,
            starts="ast",
            input_builder=lambda ctx: {
                "index": len(_complete_defs(ctx.views["code"].value())) - 1,
                "source": _complete_defs(ctx.views["code"].value())[-1],
            },
            # key on the running complete-declaration count: one firing per distinct count,
            # i.e. once per newly-completed declaration regardless of chunk boundaries.
            policy=api.PerKey(_DeclCountKey()),
        )
        # AST -> typecheck (PerEvent per declaration)
        b.trigger(
            "to-typecheck",
            subscription=api.Subscription(kinds=frozenset({"Declaration"})),
            predicate=lambda ctx: True,
            starts="typecheck",
            input_builder=lambda ctx: {
                "index": ctx.event.payload["index"],
                "source": ctx.event.payload["source"],
            },
            policy=api.PerEvent(),
        )
        # once a typecheck PASSES (ok), the artifact is ready
        b.trigger(
            "to-artifact",
            subscription=api.Subscription(kinds=frozenset({"TypecheckOk"})),
            predicate=lambda ctx: bool(ctx.event.payload.get("ok")),
            starts="artifact",
            input_builder=lambda ctx: {"declarations": ctx.event.payload["index"] + 1},
            policy=api.Once(),
        )
        b.termination(api.all_completed())

    return topo


def _artifact_factory() -> _Factory:
    async def artifact(inp: Any) -> AsyncIterator[ArtifactReady]:
        n = inp["declarations"] if hasattr(inp, "get") else 0
        yield ArtifactReady(declarations=n)

    return lambda: artifact


# ── outer two-stage topology embedding the inner pipeline ──────────────────────
def codesynth_composed_topology(
    chunks: list[str], inner_root: str, *, deterministic: bool = True
) -> Callable[[api.TopologyBuilder], None]:
    """The OUTER topology: a single embedded-substrate Producer running the inner code-synth
    pipeline, exporting ONLY ArtifactReady (composition / export map). The outer run is what
    `substrate tail` follows."""

    class OuterArtifact(Struct, frozen=True):
        declarations: int

    def outer(b: api.TopologyBuilder) -> None:
        # the embedded-substrate Producer factory (returns the embedded `start` callable).
        embedded: _Factory = lambda: api.embedded_substrate(  # noqa: E731
            codesynth_inner_topology(chunks, deterministic=deterministic),
            exports={"ArtifactReady": OuterArtifact},
        )
        b.producer_kind(
            "codesynth",
            schemas=[OuterArtifact],
            schema_version=1,
            factory=embedded,
            deterministic=deterministic,
        )
        # the export map is the single source on the embedded_substrate(exports=...) above;
        # the manifest derives it automatically (no separate b.export declaration).
        b.initial("codesynth", input={"inner_root": inner_root})
        b.termination(api.quiescence())

    return outer

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Structural protocols the user implements: the two kernel primitives (Producer, View),
plus the application-layer model seam (Responder).

These are typing.Protocol so user code satisfies them by shape, not inheritance
(design spec §9.6: factory returns a callable; no class hierarchy required). Signatures
mirror technical spec §16. Producer and View are kernel primitives the runtime drives
directly; Responder is NOT a kernel concept — it is the convenience seam a Producer calls
to turn a prompt into text (the reference topologies' dual-mode CI/walkthrough boundary),
defined here because it is a structural protocol the user implements, like the others.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .types import Event, Subscription


@runtime_checkable
class Producer(Protocol):
    """A callable `(input) -> AsyncIterable[Event]` (kernel §1; design §4.2/§9.6).

    The factory returns this callable per instantiation; the runtime calls it with the
    resolved input (its own copy, decoded from the recorded bytes) and consumes the event stream until the Producer completes,
    fails, or is cancelled — emitting the corresponding lifecycle event. A Producer has
    no runtime-level identity, planning, or goal state (kernel non-goals); state lives
    on the log.

    NOTE (flow-back): technical §16 shows the object-with-`.start()` form; design §9.6
    chooses the callable form deliberately (simpler, asyncio-native, no class
    hierarchy) and rejects the class form. We follow the design spec; technical §16
    should be updated to the callable form to match.
    """

    def __call__(self, input: Any) -> AsyncIterable[Event]: ...


# The type of a Producer FACTORY: a zero-arg callable returning a fresh Producer per
# instantiation (`producer_kind(factory=...)`). Public so authors stop re-declaring a local
# `_Factory = Callable[[], Any]` and so a wrong `factory=fn` (vs `factory=lambda: fn`) is a
# type error at the call site. For the stateless case, prefer `producer_kind(start=fn)`.
ProducerFactory = Callable[[], Producer]


@runtime_checkable
class Responder(Protocol):
    """The application-layer model seam: turn a prompt into a text response. A Producer depends
    on this, not on a concrete model — CI hands it a deterministic stand-in, the walkthrough a
    real local LLM. NOT a kernel primitive (the runtime never sees it); it lives among the
    structural protocols because, like Producer and View, the user implements it by shape.
    The reference adapters (DeterministicResponder, OllamaResponder) live in `substrate.reference`."""

    def respond(self, prompt: str) -> str: ...


@runtime_checkable
class View(Protocol):
    """A deterministic incremental projection over the bus (kernel §4).

    Updated synchronously in append-cycle step 3, before any Route or Predicate.
    `deterministic` declares whether `value()` is composed of RFC-8785-encodable
    types and so participates in N-DET-1 (its state re-derives identically on replay);
    a View holding non-canonical types sets it False and is flagged
    `determinism: excluded` at registration (technical §4.2). (N-DET-1 is View-state
    determinism — distinct from full byte-identical L3b re-execution, which is post-1.0.)
    """

    subscription: Subscription
    deterministic: bool

    def update(self, event: Event) -> None: ...
    def value(self) -> Any: ...


@dataclass(frozen=True)
class TriggerContext:
    """What a Trigger's `predicate` and `input_builder` callbacks receive — both take ONE of
    these: `predicate(ctx) -> bool` decides whether the Trigger fires; `input_builder(ctx) -> input`
    builds the started Producer's input. One context is constructed per appended event and shared
    by every Trigger's callbacks, so it allocates once per event, not per evaluation.

    - `event`  — the just-appended Event that matched the Trigger's subscription.
    - `views`  — the named Views (deterministic projections over the bus); read
                 `ctx.views["name"].value()`.
    - `staged` — the Route slots: data a Route staged forward for this firing; read
                 `ctx.staged.get("slot")`. (A predicate may read it too; usually only the
                 input_builder does.)
    """

    event: Event
    views: Mapping[str, View]
    staged: Mapping[str, Any]

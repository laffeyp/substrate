# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""TopologyBuilder + the registration set + the topology registry (design §4.1).

A topology is a factory function receiving a TopologyBuilder; one builder method per
primitive (the builder methods ARE the vocabulary). Registration is frozen when the
factory returns; the runtime reads the Registration to drive the run. Static checks
that the runtime would otherwise raise at start are caught at build time (design §5.5).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from msgspec import Struct

from ..constants import is_reserved
from ..errors import SubstrateError
from ..protocols import Producer, TriggerContext, View
from ..types import Subscription
from .policies import TerminationPolicy
from .triggers import Cooldown, FiringPolicy, Logical, PerEvent, WallClock, WhileTrue


class RegistrationError(SubstrateError):
    """A topology is malformed (design §6.1). Raised at build time, before any run."""


class Cap(Struct, frozen=True):
    """One named cap in a `Budget`. `limit` is the ceiling value the runtime enforces; `reason`
    is the human-readable string the breach records: a `substrate.ProducerFailed` whose payload
    carries `budget_exceeded: {axis, limit, reason}` (lens audit F023: these docs named a
    `substrate.BudgetExceeded` kind that never existed).
    Named fields keep the enforcement site legible: `budget.wall_seconds.reason` reads as
    the reason for the wall-clock cap, not `budget.wall_seconds[1]` — a positional-tuple
    access that hides which slot is which and can silently swap on refactor.

    `limit` typed `int | float` covers both wall-clock caps (seconds, typically float) and
    event-count caps (integer count of an event kind). msgspec preserves the input type
    on the wire.
    """

    limit: int | float
    reason: str


class Budget(Struct, frozen=True):
    """A producer_kind's declared resource caps. All caps optional; None means unbounded
    on that axis. Additive kernel primitive (Sprint 164, amended Sprint 166 to use the
    named `Cap` struct at the reviewer's F6 request; roadmap v2 S1); every existing
    producer without a budget behaves identically.

    `wall_seconds` — `Cap(limit=cap_seconds, reason=...)`. Max elapsed wall-clock from
    `substrate.ProducerStarted` to any terminal for this producer instance. On overrun the
    Producer is stopped and recorded as `substrate.ProducerFailed` with
    `budget_exceeded: {axis: "wall_seconds", limit, reason}`.

    `event_counts` — `{event_kind_name: Cap(limit=cap_count, reason=...)}`. Per-kind cap
    on events of that name that this producer instance may emit; names are the event
    Struct's class name. The emission that would pass the cap is not recorded; the Producer
    stops with `substrate.ProducerFailed` carrying
    `budget_exceeded: {axis: "event_counts", kind, limit, reason}`.
    """

    wall_seconds: Cap | None = None
    event_counts: dict[str, Cap] | None = None


@dataclass(frozen=True)
class ProducerKindReg:
    kind: str
    schemas: dict[str, tuple[type, int]]  # event-kind name -> (Struct type, schema_version)
    factory: Callable[[], Producer]
    deterministic: bool
    author_version: str | None
    # composition export map {inner_kind -> outer_schema_name}, derived from the embedded
    # substrate's own map (the SINGLE source of truth) — None for a non-embedded kind. The
    # manifest reads this; there is no parallel hand-maintained copy.
    export_map: dict[str, str] | None = None
    # declared resource budget (Sprint 164, additive). None means unbounded — every
    # existing producer_kind. Enforcement is a follow-on runtime sprint; Sprint 164
    # only stores the declaration.
    budget: Budget | None = None


@dataclass(frozen=True)
class TriggerReg:
    id: str
    subscription: Subscription
    predicate: Callable[[TriggerContext], bool]
    starts: str
    input_builder: Callable[[TriggerContext], Any]
    policy: FiringPolicy
    cooldown: Cooldown


@dataclass(frozen=True)
class RouteReg:
    id: str
    subscription: Subscription
    slot: str
    transform: Callable[[Any], Any]


@dataclass(frozen=True)
class InitialReg:
    kind: str
    input: Any


@dataclass
class Registration:
    producer_kinds: dict[str, ProducerKindReg] = field(default_factory=dict)
    views: dict[str, View] = field(default_factory=dict)
    triggers: list[TriggerReg] = field(default_factory=list)
    routes: list[RouteReg] = field(default_factory=list)
    initials: list[InitialReg] = field(default_factory=list)
    termination: TerminationPolicy | None = None
    baseline: dict[str, Any] = field(default_factory=dict)
    has_wall_clock_cooldown: bool = False


class TopologyBuilder:
    """Declares a topology — the Producers, Triggers, Routes, Views, and TerminationPolicy a run
    is built from. A `topology(b)` function receives one of these and calls its methods; the
    runtime builds + statically validates it (`build`) before the run opens. This is the primary
    authoring surface."""

    def __init__(self) -> None:
        self._reg = Registration()

    def producer_kind(
        self,
        kind: str,
        *,
        schemas: Sequence[type],
        schema_version: int,
        factory: Callable[[], Producer] | None = None,
        start: Producer | None = None,
        deterministic: bool = False,
        author_version: str | None = None,
        budget: Budget | None = None,
    ) -> None:
        """Register a Producer kind: its name, the frozen msgspec Struct event schemas it may
        emit (+ schema_version), and the Producer to run. Give EITHER `start=` — the Producer
        callable itself, for the stateless case (sugar for `factory=lambda: start`) — OR
        `factory=` — a zero-arg callable returning a fresh Producer per instantiation, for the
        stateful/configured case. Exactly one is required. Set `deterministic=True` if the same
        input always yields the same events (it gates Level-3a replay). Names using the reserved
        `substrate.` prefix are rejected.

        Optional `budget=Budget(...)` declares resource caps the runtime enforces at run time
        (roadmap v2 Sprint 1b). `None` (the default) means unbounded on every axis and
        preserves the pre-Sprint-164 behaviour. See `Budget` for the cap shapes."""
        if (factory is None) == (start is None):
            raise RegistrationError(
                f'producer_kind "{kind}": provide exactly one of start= (the Producer) or '
                f"factory= (a zero-arg callable returning one)."
            )
        if start is not None:
            captured = start  # bind for the closure; `start` is Optional at the type level

            def _factory() -> Producer:
                return captured

            # carry the Producer's identity onto the synthesized factory, so the RunStarted
            # manifest names the actual producer (e.g. `reviewer`) rather than an opaque
            # wrapper — better provenance than `factory=lambda: fn` (which records `<lambda>`).
            _factory.__qualname__ = getattr(start, "__qualname__", _factory.__qualname__)
            _factory.__name__ = getattr(start, "__name__", _factory.__name__)
            factory = _factory
        if is_reserved(kind):
            raise RegistrationError(
                f'producer_kind "{kind}": Producer kinds MUST NOT use the reserved '
                f'"substrate." prefix (F-OBS-5).'
            )
        schema_map: dict[str, tuple[type, int]] = {}
        for s in schemas:
            if not (isinstance(s, type) and issubclass(s, Struct)):
                raise RegistrationError(
                    f'producer_kind "{kind}": schema {s!r} is not a msgspec Struct.'
                )
            if not getattr(s, "__struct_config__").frozen:
                raise RegistrationError(
                    f'producer_kind "{kind}".schemas: {s.__name__} is not frozen.\n'
                    f"  Producer event schemas must be declared with frozen=True so the\n"
                    f"  runtime can enforce input immutability by construction (F-PROD-3)."
                )
            if is_reserved(s.__name__):
                raise RegistrationError(
                    f'producer_kind "{kind}": event kind "{s.__name__}" collides with the '
                    f"reserved namespace."
                )
            schema_map[s.__name__] = (s, schema_version)
        if (
            factory is None
        ):  # the exactly-one check above rules this out; say so if it ever does not
            raise RegistrationError(f'producer_kind "{kind}": no factory')
        # Derive the composition export map from the embedded substrate's OWN map (single
        # source of truth): an embedded_substrate `start` callable carries
        # __substrate_export_map__, so the factory is built once here to read it. A factory
        # builds a closure and runs nothing (the runtime builds one per instance), so one that
        # raises is a broken topology, refused now; it used to be swallowed, losing the export
        # map without a word (lens audit F028).
        export_map: dict[str, str] | None = None
        try:
            built = factory()
        except Exception as exc:  # noqa: BLE001 — any error from author code becomes a RegistrationError naming the kind
            raise RegistrationError(
                f'producer_kind "{kind}": its factory raised when built ({exc!r}); a factory '
                "returns the Producer's start callable and must build without side effects"
            ) from exc
        raw = getattr(built, "__substrate_export_map__", None)
        if isinstance(raw, dict):
            export_map = dict(raw)
        self._reg.producer_kinds[kind] = ProducerKindReg(
            kind, schema_map, factory, deterministic, author_version, export_map, budget
        )

    def view(self, name: str, view: View) -> None:
        """Register a named View — a deterministic incremental projection over the bus (e.g.
        KindBuffer, KindCount) that Predicates read. The View declares what it subscribes to; an
        empty subscription is rejected (never an implicit subscribe-to-everything)."""
        if view.subscription.is_empty():
            raise RegistrationError(
                f'view "{name}": subscription is empty; subscribe to a kind/producer '
                f"(both empty is never an implicit subscribe-to-everything)."
            )
        self._reg.views[name] = view

    def trigger(
        self,
        id: str,
        *,
        subscription: Subscription,
        predicate: Callable[[TriggerContext], bool],
        starts: str,
        input_builder: Callable[[TriggerContext], Any],
        policy: FiringPolicy | None = None,
        cooldown: Cooldown | None = None,
    ) -> None:
        """Register a Trigger: when an event matching `subscription` is appended and `predicate`
        (over the Views) holds, start a `starts` Producer with the input from `input_builder`.
        `policy` (default PerEvent) controls how often it fires — Once, PerEvent, PerKey,
        WhileTrue; `cooldown` throttles it. The firing and its resolved input are recorded."""
        if subscription.is_empty():
            raise RegistrationError(
                f'trigger "{id}": subscription is empty; subscribe to a kind/producer.'
            )
        pol = policy or PerEvent()
        # Cooldown is a single trigger-level concept enforced once by the runtime. A
        # WhileTrue policy may carry its cooldown as a constructor arg; lift it to the
        # trigger level when no explicit cooldown= is given, so there is exactly one
        # enforcement point (no double-throttle).
        cd = cooldown
        if cd is None and isinstance(pol, WhileTrue):
            cd = pol.cooldown
        cd = cd or Logical(0)
        if isinstance(cd, WallClock):
            self._reg.has_wall_clock_cooldown = True
        self._reg.triggers.append(
            TriggerReg(id, subscription, predicate, starts, input_builder, pol, cd)
        )

    def route(
        self, id: str, *, subscription: Subscription, slot: str, transform: Callable[[Any], Any]
    ) -> None:
        """Register a Route: on an event matching `subscription`, stage `transform(event)` into
        the named `slot` so a later Trigger's input_builder can read it (carrying context — e.g.
        a failure reason — forward into the Producer it starts). The staging is recorded."""
        if subscription.is_empty():
            raise RegistrationError(f'route "{id}": subscription is empty.')
        self._reg.routes.append(RouteReg(id, subscription, slot, transform))

    def instrument(
        self,
        name: str,
        *,
        on: str,
        schemas: Sequence[type],
        input_builder: Callable[[TriggerContext], Any],
        factory: Callable[[], Producer] | None = None,
        start: Producer | None = None,
        schema_version: int = 1,
        deterministic: bool = False,
        into: str | None = None,
        via: Callable[[Any], Any] | None = None,
    ) -> None:
        """Wire a side-Producer INSTRUMENT in one call — the common observe-(and-stage) pattern.

        Collapses the identical `producer_kind` + `trigger` + (optional) `route` triple the
        emergence instruments repeat: a Producer `name` started once per `on` event (predicate
        always-true, PerEvent), built from `input_builder`; if `into` is given, a Route stages
        the instrument's emitted output into that slot for a later Trigger to read.

        Give `start=` (the Producer) or `factory=` (a zero-arg callable returning one), exactly
        as `producer_kind`. To stage the output: `into` is the slot and `via` transforms the
        event (defaults to its payload). The Route is scoped to THIS instrument's own producer
        (not the emitted kind), so a second producer emitting the same kind never cross-stages.
        Omit `into` for an observation-only instrument (no Route — e.g. a grader, whose Grades
        are scored off the bus, not fed forward).

        For a non-trivial predicate or firing policy — or to stage only ONE of a multi-schema
        instrument's kinds — use the explicit `producer_kind` + `trigger` + `route`; this helper
        deliberately covers the always-fire, stage-everything-it-emits common case.
        """
        self.producer_kind(
            name,
            schemas=schemas,
            schema_version=schema_version,
            factory=factory,
            start=start,
            deterministic=deterministic,
        )
        self.trigger(
            name,
            subscription=Subscription(kinds=frozenset({on})),
            predicate=lambda ctx: True,
            starts=name,
            input_builder=input_builder,
            policy=PerEvent(),
        )
        if into is not None:
            # scope the stage Route to the instrument's OWN producer (review #27): subscription
            # matching is OR over kinds/producers, so a kind-scoped route would also stage a
            # DIFFERENT producer's same-kind event. `producers={name}` stages only what THIS
            # instrument emits (its producer only emits its declared schemas).
            self.route(
                f"{name}-stage",
                subscription=Subscription(producers=frozenset({name})),
                slot=into,
                transform=via or (lambda event: event.payload),
            )

    def initial(self, kind: str, *, input: Any = None) -> None:
        """Declare an initial Producer started at run open (seq 0), with `input`. A topology
        needs at least one initial Producer (or it has nothing to do)."""
        self._reg.initials.append(InitialReg(kind, input))

    def termination(self, policy: TerminationPolicy, *, scope: str = "run") -> None:
        """Set the TerminationPolicy that decides when the run ends (see the termination recipes:
        quiescence, threshold_count, all_completed, pause_await_input, ...). Only
        run-scoped termination ships; per-Producer / subtree scoping is deferred post-1.0 (product
        amendment A3.2). A non-"run" scope RAISES rather than being silently ignored (it used to be
        a no-op trap — the caller thought they had scoped termination and didn't)."""
        if scope != "run":
            raise RegistrationError(
                f"termination scope={scope!r} is not supported — only run-scoped termination ships; "
                "per-Producer / subtree scoping is deferred to post-1.0 (product amendment A3.2)"
            )
        self._reg.termination = policy

    # NOTE: there is deliberately NO `b.export`. The composition export map is declared ONCE,
    # at the embedded Producer kind via `embedded_substrate(exports=...)` (F-COMP-1 / §20: the
    # ExportMap is part of the EmbeddedSubstrate kind's declaration). The RunStarted manifest
    # DERIVES its exports section from that single source (producer_kind reads the embedded
    # substrate's own export map), so the recorded boundary can never drift from the map the
    # translator actually uses. (Earlier there was a parallel `b.export` copy — removed; it was
    # the two-source-of-truth flagged in review.)

    def baseline(self, **metadata: Any) -> None:
        """Attach run metadata (fixtures, seeds, environment identifiers) recorded in the
        RunStarted manifest, so every record is interpretable from a known baseline."""
        self._reg.baseline.update(metadata)

    def build(self) -> Registration:
        """Freeze and statically validate (design §5.5). Raises RegistrationError."""
        for t in self._reg.triggers:
            if t.starts not in self._reg.producer_kinds:
                raise RegistrationError(
                    f'trigger "{t.id}": starts="{t.starts}" — unknown Producer kind.'
                )
        for init in self._reg.initials:
            if init.kind not in self._reg.producer_kinds:
                raise RegistrationError(f'initial "{init.kind}" — unknown Producer kind.')
        return self._reg


# ── registry (CLI looks topologies up by name) ─────────────────────────────────
_REGISTRY: dict[str, Callable[[TopologyBuilder], None]] = {}


def register_topology(name: str, factory: Callable[[TopologyBuilder], None]) -> None:
    """Register a topology factory under a name so the CLI can run it by `--topology <name>`."""
    _REGISTRY[name] = factory


def get_topology(name: str) -> Callable[[TopologyBuilder], None]:
    """Look up a topology factory registered with `register_topology`; raises KeyError if
    unknown (naming the registered topologies)."""
    if name not in _REGISTRY:
        raise KeyError(f"unknown topology {name!r}; registered: {sorted(_REGISTRY)}")
    return _REGISTRY[name]

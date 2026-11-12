"""Candidate frozen topology declaration, translated onto today's TopologyBuilder."""
from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import msgspec
from substrate import api
from substrate.kernel.triggers import FiringPolicy


def _kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower().replace("_", "-")


class Body[In, Out](Protocol):
    def __call__(self, input: In, /) -> AsyncIterator[Out]: ...


@dataclass(frozen=True)
class Producer[In, Out]:
    """The kind on the wire is derived from the body's function name, plus `key` for N copies."""
    body: Body[In, Out]
    emits: tuple[type[Out], ...]
    key: object = None
    deterministic: bool = False
    name: StrEnum | None = None

    @property
    def kind(self) -> str:
        if self.name is not None:
            return self.name.value
        name = _kebab(getattr(self.body, "__name__", type(self.body).__name__).lstrip("_"))
        return name if self.key is None else f"{name}-{self.key}"


@dataclass(frozen=True)
class View[T]:
    name: str
    make: Callable[[], api.View]
    decode: Callable[[Any], T]


def kind_buffer[E: msgspec.Struct](of: type[E], name: StrEnum | None = None) -> View[tuple[E, ...]]:
    return View(name.value if name is not None else f"kind-buffer-{_kebab(of.__name__)}", lambda: api.KindBuffer(of.__name__),
                lambda raw: msgspec.convert(raw, tuple[of, ...]))  # type: ignore[valid-type]


class Ctx[E]:
    def __init__(self, raw: api.TriggerContext, on: type[E]) -> None:
        self._raw, self._on = raw, on

    @property
    def event(self) -> E:
        return msgspec.convert(self._raw.event.payload, self._on)

    def __getitem__[T](self, view: View[T]) -> T:
        return view.decode(self._raw.views[view.name].value())


def _always(_c: Any) -> bool:
    return True


@dataclass(frozen=True)
class Trigger[E, In]:
    """The id on the wire is derived from the event, the started Producer and a named `when`."""
    on: type[E]
    start: Producer[In, Any]
    input: Callable[[Ctx[E]], In]
    when: Callable[[Ctx[E]], bool] = _always
    policy: FiringPolicy | None = None
    name: StrEnum | None = None

    @property
    def id(self) -> str:
        if self.name is not None:
            return self.name.value
        when = getattr(self.when, "__name__", "<lambda>")
        qualifier = "" if when in ("_always", "<lambda>") else f"-{_kebab(when)}"
        return f"{self.start.kind}{qualifier}-on-{_kebab(self.on.__name__)}"


@dataclass(frozen=True)
class Initial[In]:
    producer: Producer[In, Any]
    input: In


@dataclass(frozen=True)
class Topology:
    producers: tuple[Producer[Any, Any], ...]
    views: tuple[View[Any], ...]
    triggers: tuple[Trigger[Any, Any], ...]
    initial: tuple[Initial[Any], ...]
    termination: api.TerminationPolicy

    def __post_init__(self) -> None:
        kinds = [p.kind for p in self.producers]
        if len(set(kinds)) != len(kinds):
            raise ValueError(f"duplicate producer kinds: {kinds}")
        emitted = {e.__name__ for p in self.producers for e in p.emits}
        ids = [t.id for t in self.triggers]
        if len(set(ids)) != len(ids):
            raise ValueError(f"two Triggers derive one id; name their `when` functions: {ids}")
        for t in self.triggers:
            if t.start not in self.producers:
                raise ValueError(f"trigger {t.id}: starts undeclared producer {t.start.kind}")
            if t.on.__name__ not in emitted:
                raise ValueError(f"trigger {t.id}: no producer emits {t.on.__name__}")
        if not self.initial:
            raise ValueError("no initial producer")

    def __call__(self, b: api.TopologyBuilder) -> None:
        for p in self.producers:
            b.producer_kind(p.kind, schemas=list(p.emits), schema_version=1,
                            start=p.body, deterministic=p.deterministic)  # type: ignore[arg-type]
        for i in self.initial:
            b.initial(i.producer.kind, input=i.input)
        for v in self.views:
            b.view(v.name, v.make())
        for t in self.triggers:
            b.trigger(t.id, subscription=api.Subscription(kinds=frozenset({t.on.__name__})),
                      predicate=_lower(t.when, t.on), starts=t.start.kind,
                      input_builder=_lower(t.input, t.on), policy=t.policy)
        b.termination(self.termination)


def _lower[E, R](f: Callable[[Ctx[E]], R], on: type[E]) -> Callable[[api.TriggerContext], R]:
    def call(raw: api.TriggerContext) -> R:
        return f(Ctx(raw, on))
    return call


def completed(p: Producer[Any, Any]) -> Callable[[Any], bool]:
    def when(c: Any) -> bool:
        return (c.event is not None and c.event.kind == api.PRODUCER_COMPLETED
                and c.event.payload["producer"]["kind"] == p.kind)
    return when

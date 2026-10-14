# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""A plan as a kernel topology (session vocabulary § AA; kernel sprint K336).

One producer kind per step, named by its id and writing its kind; one trigger per kind a step
waits on; views for what the triggers read; the plan's end as the termination. The plan itself
goes into the record's `RunStarted.baseline`, so the record says what ran.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any, Final

import msgspec

from ... import api
from ...constants import TRIGGER_FIRED
from ...types import Event, Subscription
from .parts import Deps, event_class, main_field, producer
from .vocabulary import COLLECT_ALL, INPUT, End, EndWhen, Part, Plan, Step, Test, TestOp, kind_of

FIRED_VIEW: Final[str] = "fired"
PLACEHOLDER: Final[re.Pattern[str]] = re.compile(
    r"\{(input|[A-Z][A-Za-z0-9]*)(?:\.([a-z_][a-z0-9_]*))?\}"
)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    built = msgspec.to_builtins(value)
    return built if isinstance(built, dict) else {}


class FiredCounts:
    """How many times each step has been started by a trigger, read from `TriggerFired`. The
    kernel drains each firing's `TriggerFired` before the next event's cycle, so the count is
    exact when a later event's trigger reads it."""

    deterministic = True

    def __init__(self) -> None:
        self.subscription = Subscription(kinds=frozenset({TRIGGER_FIRED}))
        self._fired: dict[str, int] = {}

    def update(self, event: Event) -> None:
        factory = _payload(event.payload).get("factory")
        if isinstance(factory, str):
            self._fired[factory] = self._fired.get(factory, 0) + 1

    def value(self) -> Mapping[str, int]:
        return dict(self._fired)


class Gather:
    """The payloads of several kinds in the order they were written (a collect's items)."""

    deterministic = True

    def __init__(self, kinds: frozenset[str]) -> None:
        self.subscription = Subscription(kinds=kinds)
        self._items: list[dict[str, Any]] = []

    def update(self, event: Event) -> None:
        self._items.append(_payload(event.payload))

    def value(self) -> list[dict[str, Any]]:
        return list(self._items)


def passes(test: Test, payload: Mapping[str, Any]) -> bool:
    """One `if` test on a payload (§ AA.1): `is` and `is not` compare the field's text, `has`
    and `has no` look for the value in it."""
    raw = payload.get(test.field)
    text = raw if isinstance(raw, str) else msgspec.json.encode(raw).decode()
    if test.op is TestOp.IS:
        return text.strip() == test.value
    if test.op is TestOp.IS_NOT:
        return text.strip() != test.value
    if test.op is TestOp.HAS:
        return test.value in text
    return test.value not in text


def lay_out(
    step: Step,
    source: Mapping[str, Any],
    latest: Callable[[str], Mapping[str, Any] | None],
    run_input: str,
) -> str:
    """A step's input as text: its `input` with placeholders filled, or the starting event's main
    field followed by each `with` kind's latest, under its kind's name."""

    def fill(m: re.Match[str]) -> str:
        kind, field = m.group(1), m.group(2)
        if kind == INPUT:
            return run_input
        payload = latest(kind)
        if payload is None:
            return ""
        if field is None:
            return main_field(payload)
        value = payload.get(field, "")
        return value if isinstance(value, str) else msgspec.json.encode(value).decode()

    if step.input:
        return PLACEHOLDER.sub(fill, step.input)
    text = main_field(source)
    for kind in step.with_:
        payload = latest(kind)
        if payload is not None:
            text += f"\n\n{kind}:\n{main_field(payload)}"
    return text


def termination(ends: list[End]) -> Any:
    """The plan's end as a kernel termination policy: any one end finalises the run. `first K`
    is a count of one, not `finalise_on`: the runtime consults termination with the last event
    of a cycle, which is a `TriggerFired` whenever a step waits on `K`, so `finalise_on(K)`
    would miss it."""
    policies = []
    for e in ends:
        if e.when is EndWhen.FIRST:
            policies.append(api.threshold_count(e.kind, 1))
        elif e.when is EndWhen.AFTER:
            policies.append(api.threshold_count(e.kind, e.count))
        else:
            policies.append(api.quiescence())
    return policies[0] if len(policies) == 1 else api.any_of(*policies)


def latest_view(kind: str) -> str:
    return f"latest {kind}"


def gather_view(step: Step) -> str:
    return f"gather {step.id}"


def topology(plan: Plan, deps: Deps, run_input: str = "") -> Callable[[Any], None]:
    """The plan as a function of a `TopologyBuilder`."""
    classes = {s.id: event_class(s) for s in plan.steps}
    by_kind = {kind_of(s.id): s for s in plan.steps}
    # Kinds read by name: `with`, `if` on another kind, placeholders, and a collect's split.
    read_kinds: set[str] = set()
    for s in plan.steps:
        read_kinds.update(s.with_)
        if s.if_ is not None:
            read_kinds.add(s.if_.kind)
        read_kinds.update(m.group(1) for m in PLACEHOLDER.finditer(s.input) if m.group(1) != INPUT)
    splits = {s.id: _split_before(s, by_kind) for s in plan.steps if s.part is Part.COLLECT}
    read_kinds.update(kind_of(sid) for sid in splits.values() if sid)
    input_source = {"text": run_input}

    def topo(b: Any) -> None:
        b.view(FIRED_VIEW, FiredCounts())
        for kind in sorted(read_kinds & set(by_kind)):
            b.view(latest_view(kind), api.PerKindLatest(kind))
        for s in plan.steps:
            b.producer_kind(
                s.id,
                schemas=[classes[s.id]],
                schema_version=1,
                start=producer(s, classes[s.id], deps),
                deterministic=False,
            )
            if s.part is Part.COLLECT:
                b.view(gather_view(s), Gather(frozenset(k for k in s.on if k != INPUT)))

        for s in plan.steps:
            if INPUT in s.on:
                b.initial(s.id, input=_input_for(s, input_source, None, run_input))
            for kind in s.on:
                if kind == INPUT:
                    continue
                b.trigger(
                    f"{s.id}-on-{kind}",
                    subscription=Subscription(kinds=frozenset({kind})),
                    predicate=_predicate(s, splits.get(s.id)),
                    starts=s.id,
                    input_builder=_builder(s, run_input),
                    policy=api.PerEvent(),
                )
        b.termination(termination(plan.end))
        b.baseline(plan=msgspec.to_builtins(plan), input=run_input)

    return topo


def _split_before(collect: Step, by_kind: Mapping[str, Step]) -> str | None:
    """The split a collect's items come from, through the steps it waits on; None when none."""
    seen: set[str] = set()
    todo = [k for k in collect.on if k != INPUT]
    while todo:
        step = by_kind.get(todo.pop())
        if step is None or step.id in seen:
            continue
        seen.add(step.id)
        if step.part is Part.SPLIT:
            return step.id
        if step.part is not Part.COLLECT:
            todo += [k for k in step.on if k != INPUT]
    return None


def _latest(views: Mapping[str, Any]) -> Callable[[str], Mapping[str, Any] | None]:
    def get(kind: str) -> Mapping[str, Any] | None:
        view = views.get(latest_view(kind))
        if view is None:
            return None
        value = view.value()
        return _payload(value) if value is not None else None

    return get


def _input_for(
    step: Step,
    source: Mapping[str, Any],
    views: Mapping[str, Any] | None,
    run_input: str,
) -> dict[str, Any]:
    latest = _latest(views) if views is not None else (lambda _k: None)
    items: list[dict[str, Any]] = []
    if step.part is Part.COLLECT and views is not None:
        gathered = views[gather_view(step)].value()
        items = gathered[-step.n :] if step.n != COLLECT_ALL else gathered
    if step.part is Part.SPLIT and isinstance(source.get("items"), list):
        items = list(source["items"])
    return {"text": lay_out(step, source, latest, run_input), "items": items}


def _builder(step: Step, run_input: str) -> Callable[[Any], dict[str, Any]]:
    def build(ctx: Any) -> dict[str, Any]:
        return _input_for(step, _payload(ctx.event.payload), ctx.views, run_input)

    return build


def _predicate(step: Step, split_id: str | None) -> Callable[[Any], bool]:
    def fires(ctx: Any) -> bool:
        started = ctx.views[FIRED_VIEW].value().get(step.id, 0) + (1 if INPUT in step.on else 0)
        if started >= step.max:
            return False
        if step.if_ is not None:
            test = step.if_
            if test.kind == ctx.event.kind:
                payload: Mapping[str, Any] | None = _payload(ctx.event.payload)
            else:
                payload = _latest(ctx.views)(test.kind)
            if payload is None or not passes(test, payload):
                return False
        if step.part is Part.COLLECT:
            got = len(ctx.views[gather_view(step)].value())
            if step.n == COLLECT_ALL:
                split = _latest(ctx.views)(kind_of(split_id)) if split_id else None
                return split is not None and got >= int(split.get("of", 0)) > 0
            return got > 0 and got % step.n == 0
        return True

    return fires


__all__ = [
    "FIRED_VIEW",
    "PLACEHOLDER",
    "FiredCounts",
    "Gather",
    "gather_view",
    "lay_out",
    "latest_view",
    "passes",
    "termination",
    "topology",
]

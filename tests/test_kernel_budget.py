# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel `Budget` primitive — Sprint 164 (initial), amended Sprint 166 (fold external F6).

Additive kernel change: `producer_kind` accepts an optional `budget: Budget` kwarg.
Sprint 164 stored the budget on the `ProducerKindReg` and exported `Budget` from
`substrate.api`. Sprint 166 amends Budget to use a named `Cap` struct for its axes
so the enforcement site reads `cap.limit` / `cap.reason` at every call site instead
of positional-tuple access that hides which slot is which.

Enforcement is a follow-on runtime sprint (roadmap v2 S1b); this test file covers
registration only.

Tests pin the additive + typed contract:
- Existing producer_kind registrations (no budget) still work; ProducerKindReg.budget is
  None by default.
- A producer_kind with a Budget stores it verbatim on the ProducerKindReg.
- A Budget can carry wall_seconds only, event_counts only, both, or neither.
- Every Cap carries a named `limit` and a named `reason` — no positional tuples.
- Budget and Cap are re-exported from substrate.api.
"""

from __future__ import annotations

from msgspec import Struct

from substrate import api
from substrate.kernel.topology import ProducerKindReg, TopologyBuilder


class _Note(Struct, frozen=True):
    text: str


async def _noop_producer(_inp):  # type: ignore[no-untyped-def]
    """A trivial Producer used only to satisfy producer_kind's `start=` requirement.
    It yields no events; Sprint 164 does not run any topology, only registers one.
    Matches `tests/test_api_sugar.py::_ticker`'s shape (untyped for the async-gen
    return type, which the Producer protocol reads by shape)."""
    if False:  # keep async-gen inference; body never runs
        yield


def _build(*, budget: api.Budget | None = None) -> ProducerKindReg:
    """Register a single producer_kind on a fresh TopologyBuilder and return its Reg.
    Suppresses the Sprint 172 UserWarning about unenforced Budget declarations — the
    per-test suppression keeps every existing budget-carrying test quiet; the dedicated
    warning-emission test at `test_budget_declaration_warns_until_enforcement_ships`
    exercises the warning path explicitly."""
    import warnings

    b = TopologyBuilder()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        b.producer_kind(
            "noop",
            schemas=[_Note],
            schema_version=1,
            start=_noop_producer,
            budget=budget,
        )
    reg = b._reg
    return reg.producer_kinds["noop"]


def test_producer_kind_without_budget_stores_none() -> None:
    """The pre-Sprint-164 shape: producer_kind without a budget kwarg stores None.
    Every producer_kind in the codebase before this landing behaves this way."""
    pkr = _build()
    assert pkr.budget is None


def test_producer_kind_with_wall_seconds_budget_round_trips() -> None:
    """A Budget with only wall_seconds set stores verbatim on the Reg. Sprint 166:
    the cap is a named Cap(limit=..., reason=...), not a positional tuple."""
    b = api.Budget(wall_seconds=api.Cap(limit=30.0, reason="unit-test wall cap"))
    pkr = _build(budget=b)
    assert pkr.budget is b
    assert pkr.budget.wall_seconds is not None
    assert pkr.budget.wall_seconds.limit == 30.0
    assert pkr.budget.wall_seconds.reason == "unit-test wall cap"
    assert pkr.budget.event_counts is None


def test_producer_kind_with_event_counts_budget_round_trips() -> None:
    """A Budget with only event_counts set stores verbatim. Every entry's value is a Cap."""
    b = api.Budget(event_counts={"ModelUsage": api.Cap(limit=6, reason="matched-compute cap")})
    pkr = _build(budget=b)
    assert pkr.budget is b
    assert pkr.budget.wall_seconds is None
    assert pkr.budget.event_counts is not None
    cap = pkr.budget.event_counts["ModelUsage"]
    assert cap.limit == 6
    assert cap.reason == "matched-compute cap"


def test_producer_kind_with_full_budget_round_trips() -> None:
    """A Budget with both caps stores verbatim; per-kind caps preserve identity."""
    b = api.Budget(
        wall_seconds=api.Cap(limit=600.0, reason="per-cell wall"),
        event_counts={
            "ContainerRequested": api.Cap(limit=1, reason="one grade container per instance"),
            "ModelUsage": api.Cap(limit=7, reason="n*max_rounds+localize"),
        },
    )
    pkr = _build(budget=b)
    assert pkr.budget is b
    assert pkr.budget.wall_seconds is not None
    assert pkr.budget.wall_seconds.limit == 600.0
    assert pkr.budget.wall_seconds.reason == "per-cell wall"
    assert pkr.budget.event_counts is not None
    assert pkr.budget.event_counts["ContainerRequested"].limit == 1
    assert (
        pkr.budget.event_counts["ContainerRequested"].reason == "one grade container per instance"
    )
    assert pkr.budget.event_counts["ModelUsage"].limit == 7
    assert pkr.budget.event_counts["ModelUsage"].reason == "n*max_rounds+localize"


def test_empty_budget_is_legal() -> None:
    """Budget() with every cap None is legal — an advisory-only marker for the
    producer, no enforcement axis declared."""
    b = api.Budget()
    pkr = _build(budget=b)
    assert pkr.budget is b
    assert pkr.budget.wall_seconds is None
    assert pkr.budget.event_counts is None


def test_budget_frozen() -> None:
    """Budget is a frozen msgspec Struct — mutating raises AttributeError, matching the
    kernel-vocabulary discipline that every payload/config type is immutable."""
    b = api.Budget(wall_seconds=api.Cap(limit=10.0, reason="test"))
    try:
        b.wall_seconds = api.Cap(limit=20.0, reason="mutated")  # type: ignore[misc]
    except AttributeError as exc:
        assert "immutable type: 'Budget'" in str(exc)
    else:
        raise AssertionError("Budget should be frozen; mutation should raise AttributeError")


def test_cap_frozen() -> None:
    """Cap is frozen too — the reason string can't be swapped after construction."""
    c = api.Cap(limit=10.0, reason="original")
    try:
        c.reason = "mutated"  # type: ignore[misc]
    except AttributeError as exc:
        assert "immutable type: 'Cap'" in str(exc)
    else:
        raise AssertionError("Cap should be frozen; mutation should raise AttributeError")


def test_cap_accepts_int_or_float_limit() -> None:
    """Cap.limit is typed int | float — wall_seconds caps use float, event_counts caps
    use int. msgspec preserves the input type."""
    wall = api.Cap(limit=30.0, reason="wall")
    count = api.Cap(limit=6, reason="count")
    assert isinstance(wall.limit, float)
    assert isinstance(count.limit, int)


def test_budget_and_cap_exported_from_api() -> None:
    """Budget and Cap are re-exported from substrate.api per hard rule F-API-1
    (public surface)."""
    assert hasattr(api, "Budget")
    assert hasattr(api, "Cap")
    assert "Budget" in api.__all__
    assert "Cap" in api.__all__


# ── Sprint 172 (F7): Budget declared without runtime enforcement emits UserWarning ─────


def test_wall_seconds_budget_no_longer_warns_after_sprint_199() -> None:
    """Sprint 199 (roadmap v2 S1b fold-in): wall_seconds enforcement ships inside
    `Runtime._producer_task`. Declaring only `Budget(wall_seconds=...)` is now honest —
    the runtime enforces the cap — so the Sprint-172 build-time warning is gone for
    that axis. `event_counts` still warns (see next test) because its enforcement
    (emit-time per-kind counter) is a later sprint."""
    import warnings

    b = TopologyBuilder()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        b.producer_kind(
            "wall_only",
            schemas=[_Note],
            schema_version=1,
            start=_noop_producer,
            budget=api.Budget(wall_seconds=api.Cap(limit=1.0, reason="test")),
        )
    budget_warnings = [
        w for w in caught if "Budget" in str(w.message) and issubclass(w.category, UserWarning)
    ]
    assert not budget_warnings, (
        f"wall_seconds-only Budget must not warn after Sprint 199; got {budget_warnings}"
    )


def test_event_counts_budget_still_warns_until_emit_cap_enforcement_ships() -> None:
    """Sprint 199 landed wall_seconds only; `event_counts` (per-kind emit cap) is a
    later sprint. Declaring event_counts still emits the standing warning."""
    import warnings

    b = TopologyBuilder()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        b.producer_kind(
            "counted",
            schemas=[_Note],
            schema_version=1,
            start=_noop_producer,
            budget=api.Budget(event_counts={"_Note": api.Cap(limit=6, reason="test")}),
        )
    matching = [
        w
        for w in caught
        if "event_counts" in str(w.message) and issubclass(w.category, UserWarning)
    ]
    assert matching, "expected a UserWarning naming event_counts as the unshipped axis"


def test_no_warning_when_no_budget_declared() -> None:
    """The pre-Sprint-164 shape (no budget kwarg) never trips the warning — otherwise
    every existing producer_kind call in the tree would emit noise on import."""
    import warnings

    b = TopologyBuilder()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        b.producer_kind(
            "plain",
            schemas=[_Note],
            schema_version=1,
            start=_noop_producer,
        )
    budget_warnings = [
        w for w in caught if "Budget" in str(w.message) and issubclass(w.category, UserWarning)
    ]
    assert not budget_warnings, (
        f"expected no budget-related warning for a plain producer_kind; got {budget_warnings}"
    )

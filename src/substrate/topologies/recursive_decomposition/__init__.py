# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Recursive decomposition topology — planner spawning solvers spawning solvers (Sprint 132).

A planner Producer emits N subtask events; ONE Trigger (PerEvent) on the subtask kind fires a
solver Producer per subtask; a solver may itself emit further subtask events that the SAME
Trigger matches — at any depth, with no per-depth registration (the substrate's recursive-
Trigger property, kernel Decision #17). A depth-budget Trigger gates the recursion: a subtask
proposed beyond `max_depth` does NOT spawn a solver; instead a guard Producer emits a typed
DepthBudgetExceeded event, so the bound is on the log, not silent.

This is the demonstration LangGraph structurally cannot do: its graph is declared statically,
so an unbounded, data-dependent spawn tree has no static shape to declare. Here the tree falls
out of one recursive Trigger and a budget predicate.

DepthBudgetExceeded is an APPLICATION-level kind, not a reserved substrate.* kind (answering
sprint-132's open question): the runtime cannot know a topology's budget, so the bound is the
topology's to declare and emit. The recursion is bounded BY THE TOPOLOGY (the spawn Trigger's
predicate), verifiable by reading the record — the runaway-prevention test proves a solver that
tries to recurse past the budget is stopped at the boundary.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from msgspec import Struct

from ... import api
from ...adapters import Responder, call_responder

_Factory = Callable[[], Any]


class SubtaskProposed(Struct, frozen=True):
    task_id: str
    task: str
    parent_task_id: str | None
    depth: int


class SolutionReached(Struct, frozen=True):
    task_id: str
    solution: str


class DepthBudgetExceeded(Struct, frozen=True):
    at_task_id: str
    depth: int
    budget: int


def _planner_factory(root_task: str, fanout: int) -> _Factory:
    async def plan(_input: Any) -> AsyncIterator[SubtaskProposed]:
        # the planner proposes `fanout` root subtasks at depth 1 (children of the root).
        for i in range(fanout):
            yield SubtaskProposed(
                task_id=f"t-1-{i}",
                task=f"{root_task} :: part {i}",
                parent_task_id=None,
                depth=1,
            )

    return lambda: plan


def _solver_factory(max_depth: int, fanout: int, responder: Responder, runaway: bool) -> _Factory:
    async def solve(inp: Any) -> AsyncIterator[Any]:
        task_id = str(inp.get("task_id", "?")) if hasattr(inp, "get") else "?"
        task = str(inp.get("task", "")) if hasattr(inp, "get") else ""
        depth = int(inp.get("depth", 1)) if hasattr(inp, "get") else 1
        # A leaf decision: in CI, a solver at depth < max_depth decomposes (internal node), else
        # it solves (leaf). `runaway` solvers ALWAYS decompose, ignoring the budget — the
        # adversarial case the depth-budget Trigger must contain.
        decomposes = runaway or depth < max_depth
        if decomposes:
            for i in range(fanout):
                yield SubtaskProposed(
                    task_id=f"{task_id}-{i}",
                    task=f"{task} / sub {i}",
                    parent_task_id=task_id,
                    depth=depth + 1,
                )
        else:
            yield SolutionReached(
                task_id=task_id, solution=await call_responder(responder, f"solve: {task}")
            )

    return lambda: solve


def _guard_factory() -> _Factory:
    async def guard(inp: Any) -> AsyncIterator[DepthBudgetExceeded]:
        yield DepthBudgetExceeded(
            at_task_id=str(inp.get("at_task_id", "?")) if hasattr(inp, "get") else "?",
            depth=int(inp.get("depth", 0)) if hasattr(inp, "get") else 0,
            budget=int(inp.get("budget", 0)) if hasattr(inp, "get") else 0,
        )

    return lambda: guard


def recursive_decomposition_topology(
    root_task: str = "build a feature",
    *,
    solver_model: Responder,
    max_depth: int = 4,
    fanout: int = 2,
    runaway: bool = False,
    deterministic: bool = True,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the recursive-decomposition topology. The planner proposes `fanout` subtasks at
    depth 1; one PerEvent Trigger fires a solver per subtask at any depth; solvers below
    `max_depth` decompose (fanout children at depth+1), at `max_depth` they solve. A subtask
    proposed at depth > max_depth does NOT spawn a solver — a guard Producer emits
    DepthBudgetExceeded instead. Set `runaway=True` to make solvers ignore the budget (the
    adversarial test that the depth-budget Trigger contains the recursion regardless).
    `deterministic` flags kinds for Level-3(a) replay (True in CI)."""

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "planner",
            schemas=[SubtaskProposed],
            schema_version=1,
            factory=_planner_factory(root_task, fanout),
            deterministic=deterministic,
        )
        b.producer_kind(
            "solver",
            schemas=[SubtaskProposed, SolutionReached],
            schema_version=1,
            factory=_solver_factory(max_depth, fanout, solver_model, runaway),
            deterministic=deterministic,
        )
        b.producer_kind(
            "budget_guard",
            schemas=[DepthBudgetExceeded],
            schema_version=1,
            factory=_guard_factory(),
            deterministic=deterministic,
        )
        b.initial("planner", input=None)
        # ONE Trigger handles every SubtaskProposed at any depth (the recursive-Trigger property):
        # spawn a solver iff the proposed depth is within budget.
        b.trigger(
            "spawn-solver",
            subscription=api.Subscription(kinds=frozenset({"SubtaskProposed"})),
            predicate=lambda ctx: int(ctx.event.payload["depth"]) <= max_depth,
            starts="solver",
            input_builder=lambda ctx: {
                "task_id": ctx.event.payload["task_id"],
                "task": ctx.event.payload["task"],
                "depth": int(ctx.event.payload["depth"]),
            },
            policy=api.PerEvent(),
        )
        # the depth-budget boundary: a subtask proposed beyond max_depth fires the guard (which
        # emits DepthBudgetExceeded) instead of spawning a solver. Same SubtaskProposed kind, the
        # complementary predicate — the recursion is bounded ON THE LOG, not silently dropped.
        b.trigger(
            "depth-budget",
            subscription=api.Subscription(kinds=frozenset({"SubtaskProposed"})),
            predicate=lambda ctx: int(ctx.event.payload["depth"]) > max_depth,
            starts="budget_guard",
            input_builder=lambda ctx: {
                "at_task_id": ctx.event.payload["task_id"],
                "depth": int(ctx.event.payload["depth"]),
                "budget": max_depth,
            },
            policy=api.PerEvent(),
        )
        # quiescence: the run finalises when no Producer is running and no subtask is in flight
        # (all_completed cannot be used — the started count grows as the tree spawns).
        b.termination(api.quiescence())

    return topo

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Conway's Game of Life — a tick-based simulation (Wave 15).

The canonical cellular automaton as a Substrate topology, and the shape the "simulation"
slot is about: many Producers acting each tick against a shared world-state Producer, the
whole run replayable from the log.

  - a `world` Producer emits the current `Generation` (the shared grid) and fans it out as
    one `CellTick` per cell;
  - a `cell` Producer per cell reads its 3x3 neighborhood from the shared grid, applies the
    Life rule (a live cell with 2-3 live neighbors survives; a dead cell with exactly 3 is
    born), and emits its next state;
  - when every cell of a generation has reported, a step Trigger assembles the next grid and
    re-fires `world` for the next tick.

Every cell of a generation runs CONCURRENTLY — the substrate's "nothing sequential that
doesn't have to be" — and the run is replayable from the log: the grid at every generation is
on the record, and the run re-derives identically (the Life rule is a pure function). The loop
is bounded by a generation budget; the grid at each step is a typed event, not hidden state.

CI: a 5x5 grid seeded with a blinker — a period-2 oscillator that flips vertical -> horizontal
-> vertical — run for two generations, so the committed record returns to its start. A
convergence early-stop (still life / repeated grid) is a natural extension; the budget keeps
the demo crisp.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from msgspec import Struct

from ... import api

_Factory = Callable[[], Any]


class Generation(Struct, frozen=True):
    tick: int
    grid: list[list[int]]


class CellTick(Struct, frozen=True):
    tick: int
    row: int
    col: int


class CellNext(Struct, frozen=True):
    tick: int
    row: int
    col: int
    alive: int


def blinker(rows: int = 5, cols: int = 5) -> list[list[int]]:
    """A centered vertical blinker — the simplest oscillator (period 2)."""
    grid = [[0] * cols for _ in range(rows)]
    r, c = rows // 2, cols // 2
    grid[r - 1][c] = grid[r][c] = grid[r + 1][c] = 1
    return grid


def glider(rows: int = 7, cols: int = 7) -> list[list[int]]:
    """The iconic glider — a spaceship that is ASYMMETRIC (no mirror symmetry) and MOVING (it
    translates one cell diagonally per period-4). The asymmetry is the point: it gives a frame that a
    pure L-R / U-D mirror render bug would diverge on, which a mirror-symmetric blinker cannot (the
    pixel-decode harness's mirror-blind spot). Offset one cell from the top-left so it
    has a full neighborhood and room to travel without hitting an edge for a few generations."""
    grid = [[0] * cols for _ in range(rows)]
    for r, c in [(1, 2), (2, 3), (3, 1), (3, 2), (3, 3)]:
        grid[r][c] = 1
    return grid


def _patch(grid: list[list[int]], r: int, c: int) -> list[list[int]]:
    """The 3x3 neighborhood around (r, c); off-grid cells are dead (finite, non-wrapping)."""
    rows, cols = len(grid), len(grid[0])
    return [
        [
            grid[r + dr][c + dc] if 0 <= r + dr < rows and 0 <= c + dc < cols else 0
            for dc in (-1, 0, 1)
        ]
        for dr in (-1, 0, 1)
    ]


def _life(patch: list[list[int]]) -> int:
    """The Life rule applied to a 3x3 patch (self at the center)."""
    alive = patch[1][1]
    neighbors = sum(sum(row) for row in patch) - alive
    return 1 if (alive and neighbors in (2, 3)) or (not alive and neighbors == 3) else 0


def _assemble(nexts: list[dict[str, Any]], tick: int, rows: int, cols: int) -> list[list[int]]:
    """Build the next grid from the CellNext events of `tick`."""
    grid = [[0] * cols for _ in range(rows)]
    for e in nexts:
        if e["tick"] == tick:
            grid[e["row"]][e["col"]] = e["alive"]
    return grid


def _world_factory(generations: int) -> _Factory:
    async def world(inp: Any) -> AsyncIterator[Generation | CellTick]:
        tick = int(inp.get("tick", 0)) if hasattr(inp, "get") else 0
        grid = list(inp.get("grid", [])) if hasattr(inp, "get") else []
        # the shared world-state for this generation.
        yield Generation(tick=tick, grid=grid)
        # fan out one work item per cell, while there is budget left to advance.
        if tick < generations:
            for r in range(len(grid)):
                for c in range(len(grid[0])):
                    yield CellTick(tick=tick, row=r, col=c)

    return lambda: world


def _cell_factory() -> _Factory:
    async def cell(inp: Any) -> AsyncIterator[CellNext]:
        # the cell decides its own next state from its local view of the shared world.
        patch = list(inp.get("patch", [[0, 0, 0]] * 3)) if hasattr(inp, "get") else [[0, 0, 0]] * 3
        yield CellNext(
            tick=int(inp.get("tick", 0)),
            row=int(inp.get("row", 0)),
            col=int(inp.get("col", 0)),
            alive=_life(patch),
        )

    return lambda: cell


def game_of_life_topology(
    *,
    initial: list[list[int]] | None = None,
    generations: int = 2,
    deterministic: bool = True,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the Game of Life topology. The `world` Producer emits each Generation and fans it
    out as one CellTick per cell; a `cell` Producer per cell applies the Life rule against the
    shared grid; when all cells of a generation report, the next grid is assembled and the tick
    advances, for `generations` steps. `initial` defaults to a 5x5 blinker."""

    grid0 = initial if initial is not None else blinker()
    if not grid0 or not grid0[0] or any(len(r) != len(grid0[0]) for r in grid0):
        raise ValueError("game_of_life: initial must be a non-empty RECTANGULAR 2-D grid")
    rows, cols = len(grid0), len(grid0[0])
    cell_count = rows * cols

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "world",
            schemas=[Generation, CellTick],
            schema_version=1,
            factory=_world_factory(generations),
            deterministic=deterministic,
        )
        b.producer_kind(
            "cell",
            schemas=[CellNext],
            schema_version=1,
            factory=_cell_factory(),
            deterministic=deterministic,
        )
        b.initial("world", input={"tick": 0, "grid": grid0})
        # the shared world-state (latest grid) and the cells' reports for the current generation.
        b.view("gens", api.KindBuffer("Generation"))
        b.view("nexts", api.KindBuffer("CellNext"))
        # each cell reads its neighborhood from the shared grid and computes its next state.
        b.trigger(
            "compute-cell",
            subscription=api.Subscription(kinds=frozenset({"CellTick"})),
            predicate=lambda ctx: True,
            starts="cell",
            input_builder=lambda ctx: {
                "tick": int(ctx.event.payload["tick"]),
                "row": int(ctx.event.payload["row"]),
                "col": int(ctx.event.payload["col"]),
                "patch": _patch(
                    ctx.views["gens"].value()[-1]["grid"],
                    int(ctx.event.payload["row"]),
                    int(ctx.event.payload["col"]),
                ),
            },
            policy=api.PerEvent(),
        )
        # when every cell of this generation has reported, assemble the next grid and advance the
        # tick — the predicate is true exactly once per generation, when the last cell lands.
        b.trigger(
            "step",
            subscription=api.Subscription(kinds=frozenset({"CellNext"})),
            predicate=lambda ctx: (
                sum(1 for e in ctx.views["nexts"].value() if e["tick"] == ctx.event.payload["tick"])
                == cell_count
            ),
            starts="world",
            input_builder=lambda ctx: {
                "tick": int(ctx.event.payload["tick"]) + 1,
                "grid": _assemble(
                    list(ctx.views["nexts"].value()), int(ctx.event.payload["tick"]), rows, cols
                ),
            },
            policy=api.PerEvent(),
        )
        # the run ends when the final generation's grid lands (generations + 1 grids total).
        b.termination(
            api.any_of(
                api.threshold_count("Generation", generations + 1),
                api.quiescence(),
            )
        )

    return topo

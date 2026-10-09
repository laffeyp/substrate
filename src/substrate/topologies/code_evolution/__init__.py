# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""code_evolution — an evolutionary (FunSearch-style) loop for writing code on the substrate.

`coding_flow` is a ONE-generation EA: N candidates, "mutation" = re-draft with gate failures, selection
= first-to-pass. This generalizes it into a real evolutionary search: a PERSISTENT population, a
CONTINUOUS fitness (correctness AND a cost to minimize), elitist selection, LLM mutation conditioned on
the best-so-far, and multi-generation iteration until convergence or budget. The honest reason to do
this rather than best-of-N: evolution earns its keep only when there is a GRADIENT to climb (minimize
cost), not on binary pass/fail — there it collapses back to best-of-N (and the assay is built to catch
exactly that, so a null result is a real finding).

    seeder ─N×Spawn(gen1)─▶ mutator (MODEL) ─Genome─▶ evaluator (GATE + cost) ─Fitness─┐
                              ▲                                                         │
        Spawn(gen+1, parents=best-K) ◀── breeder ◀──[gen complete, budget left]────────┤
                          Evolved(best correct) ◀── breeder ◀──[max gens OR stagnant]───┘
                          Exhausted ◀── breeder ◀──[budget spent, no correct genome ever]

Heterogeneous by the rule (coding_flow's): MUTATION is the only model work; EVALUATION (the gate + the
cost) and SELECTION are deterministic code — fitness is a measurement, never an LLM's opinion. The whole
search is one replayable record, so every genome's full lineage (its parents) is on the log: the bus IS
the phylogenetic tree. FunSearch (Romera-Paredes et al., Nature 2024) and AlphaEvolve (DeepMind 2025)
are the prior art; like them this uses sample-the-best-as-context, not literal code crossover (semantic
merge of two programs is unreliable).

DIVERSITY (a known limitation, bites the EA-vs-best-of-N run): selection is GLOBAL elitism every
generation, so once a local optimum is the global best, every offspring is conditioned on it and the
only escape is mutation temperature — no island model, no restart-on-stagnation. Elitism + a flat
gradient = collapse onto one lineage, which is exactly how an EA loses to best-of-N. The fix (islands /
random restart) is a knob for that run, not the skeleton.

Like coding_flow it is RUN-and-observe, not replay-deterministic (the gate is a real subprocess);
CI mode proves the wiring (the loop runs, selects on cost, terminates), the real models prove the claim.
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from msgspec import Struct

from ... import api
from ...adapters import (
    DeterministicResponder,
    ModelUsage,
    OllamaResponder,
    Responder,
    call_responder_metered,
)
from ..coding_flow.gate import parse_artifacts, run_gate, sanitize_candidate_artifacts
from ..coding_flow.task import CodingTask, kvstore_task

_Factory = Callable[[], Any]
_MAX_COST = 10**9  # an incorrect (or unparseable) genome — worse than any correct one


class Spawn(Struct, frozen=True):
    """A request to produce a genome in `gen`, slot `slot`. `parents` is the elite parents' CODE (the
    mutation context); `parent_ids` is their EXPLICIT (gen, slot) lineage edges. Both empty for the
    seed generation (random init)."""

    gen: int
    slot: int
    parents: tuple[str, ...]
    parent_ids: tuple[tuple[int, int], ...] = ()


class Genome(Struct, frozen=True):
    """A produced candidate program — the raw `# path:`-headed artifact text, plus EXPLICIT lineage:
    its own (gen, slot) and `parent_ids`, the (gen, slot) of the genomes it was bred from. Edges are
    stamped, not inferred by code string-equality (identical code recurs), so the record is a literal
    phylogenetic tree — any final program's ancestry is unambiguous. `()` for the seed generation."""

    gen: int
    slot: int
    code: str
    parent_ids: tuple[tuple[int, int], ...] = ()


class Fitness(Struct, frozen=True):
    """The evaluation of one Genome: `correct` is the gate's exit-code truth, `cost` is the continuous
    objective to MINIMIZE (lower is fitter), or _MAX_COST if the genome is incorrect/unparseable."""

    gen: int
    slot: int
    correct: bool
    cost: int


class Evolved(Struct, frozen=True):
    """Success terminal: the best correct genome the search produced (lowest cost)."""

    gen: int
    slot: int
    cost: int


class Exhausted(Struct, frozen=True):
    """Give-up terminal: the budget was spent and NO correct genome was ever produced."""

    gens: int
    best_cost: int


def _ast_cost(artifacts: dict[str, str]) -> int:
    """A deterministic, robust cost: the number of AST nodes across the candidate's `.py` modules — a
    proxy for program complexity (smaller = fitter), pure and side-effect-free. PLACEHOLDER for the
    wiring increment: it rewards terseness, not algorithms, and — being artifacts-only — it cannot yet
    detect reward-hacking.

    The reward-hacking firewall is NOT built. The real cost (increment 2) needs three things this
    signature/seam does not yet have, and the claim is hollow until all three exist:
      1. cost measured by RUNNING the candidate on INPUTS (an executed-op count), so cost-inputs must
         flow in — increment 2 makes cost a SECOND gate (like the correctness gate), not a pure fn.
      2. the cost-inputs DISJOINT from the dev correctness-inputs AND the held-out grading-inputs,
         enforced like coding_flow's firewall, with a per-problem disjointness test.
      3. detection = cost on BOTH dev and held-out inputs, reported as the GAP (an explicit field). A
         single held-out number catches nothing; the dev-vs-held-out delta IS the reward-hacking signal."""
    total = 0
    for path, content in artifacts.items():
        if path.endswith(".py"):
            try:
                total += sum(1 for _ in ast.walk(ast.parse(content)))
            except SyntaxError:
                return _MAX_COST
    return total or _MAX_COST  # no parseable module = not a real candidate


def _decide(
    population: list[dict[str, Any]],
    gen: int,
    *,
    max_gens: int,
    select_k: int,
    patience: int,
) -> tuple[str, Any]:
    """The PURE evolutionary decision at the end of generation `gen`, given the whole evaluated
    population. Deterministic and side-effect-free, so it is unit-tested directly. Returns:

      ("evolve", best_genome) — a correct genome exists AND we are out of budget (max gens) or stagnant
                                (no cumulative-best improvement over `patience` generations): select it.
      ("exhaust", None)       — out of budget and NO correct genome was ever produced.
      ("spawn", elite)        — budget remains: ELITIST selection — the `select_k` lowest-cost correct
                                genome DICTS (code + ids), lowest first, as the next gen's context ([] if
                                none yet). The breeder reads both their code and their (gen, slot).
    """
    correct = sorted(
        (g for g in population if g["correct"]), key=lambda g: (g["cost"], g["gen"], g["slot"])
    )
    best = correct[0] if correct else None
    # cumulative best cost achieved by the end of each generation (for stagnation).
    cum: dict[int, int] = {}
    running = _MAX_COST
    for gnum in range(1, gen + 1):
        here = [g["cost"] for g in correct if g["gen"] == gnum]
        if here:
            running = min(running, min(here))
        cum[gnum] = running
    stagnant = gen > patience and cum.get(gen, _MAX_COST) >= cum.get(gen - patience, _MAX_COST)
    if best is not None and (gen >= max_gens or stagnant):
        return ("evolve", best)
    if best is None and gen >= max_gens:
        return ("exhaust", None)
    return ("spawn", correct[:select_k])  # the elite genome dicts (code + ids), lowest cost first


def _seeder_factory(n: int) -> _Factory:
    async def seed(_inp: Any) -> AsyncIterator[Spawn]:
        for i in range(n):
            yield Spawn(gen=1, slot=i, parents=())

    return lambda: seed


def _mutator_factory(task: CodingTask, responders: list[Responder]) -> _Factory:
    async def mutate(inp: Any) -> AsyncIterator[Any]:
        gen = int(inp.get("gen", 1)) if hasattr(inp, "get") else 1
        slot = int(inp.get("slot", 0)) if hasattr(inp, "get") else 0
        parents = list(inp.get("parents", [])) if hasattr(inp, "get") else []
        parent_ids = (
            tuple((int(a), int(b)) for a, b in inp.get("parent_ids", []))
            if hasattr(inp, "get")
            else ()
        )
        prompt = task.spec
        if parents:
            prompt += (
                "\n\nHere are the best correct programs found so far (lower cost is better). Produce a "
                "NEW, still-correct program with STRICTLY LOWER cost — a simpler or more efficient "
                "approach, not a cosmetic edit:\n\n" + "\n\n---\n\n".join(parents)
            )
        response, usage = await call_responder_metered(responders[slot % len(responders)], prompt)
        yield usage  # metered: per-call tokens/latency on the record (inert; no Trigger reads it)
        yield Genome(gen=gen, slot=slot, code=response, parent_ids=parent_ids)

    return lambda: mutate


def _evaluator_factory(
    task: CodingTask, cost_fn: Callable[[dict[str, str]], int], timeout: float
) -> _Factory:
    async def evaluate(inp: Any) -> AsyncIterator[Fitness]:
        gen = int(inp.get("gen", 1)) if hasattr(inp, "get") else 1
        slot = int(inp.get("slot", 0)) if hasattr(inp, "get") else 0
        code = str(inp.get("code", "")) if hasattr(inp, "get") else ""
        # sanitize the candidate (drop injected config/test files) THEN let the trusted fixtures win —
        # the same grade-time isolation coding_flow uses; the cost is measured only on the candidate's
        # own modules, never the fixtures.
        candidate = sanitize_candidate_artifacts(parse_artifacts(code))
        result = await asyncio.to_thread(
            run_gate, {**candidate, **task.fixtures}, task.gate, timeout=timeout
        )
        cost = cost_fn(candidate) if result.passed else _MAX_COST
        yield Fitness(gen=gen, slot=slot, correct=result.passed, cost=cost)

    return lambda: evaluate


def _breeder_factory(n: int, max_gens: int, select_k: int, patience: int) -> _Factory:
    async def breed(inp: Any) -> AsyncIterator[Any]:
        gen = int(inp.get("gen", 1)) if hasattr(inp, "get") else 1
        population = list(inp.get("population", [])) if hasattr(inp, "get") else []
        kind, payload = _decide(
            population, gen, max_gens=max_gens, select_k=select_k, patience=patience
        )
        if kind == "evolve":
            yield Evolved(
                gen=int(payload["gen"]), slot=int(payload["slot"]), cost=int(payload["cost"])
            )
        elif kind == "exhaust":
            # no correct genome within budget — report the lowest cost SEEN (the incorrect sentinel if
            # nothing parsed/passed), not a fake -1 that reads like a real cost.
            yield Exhausted(
                gens=gen, best_cost=min((int(g["cost"]) for g in population), default=_MAX_COST)
            )
        else:
            elite = list(payload)  # the selected elite genome dicts (lowest cost first)
            parents = tuple(str(g["code"]) for g in elite)
            parent_ids = tuple((int(g["gen"]), int(g["slot"])) for g in elite)
            for i in range(n):
                yield Spawn(gen=gen + 1, slot=i, parents=parents, parent_ids=parent_ids)

    return lambda: breed


def _population(ctx: api.TriggerContext) -> list[dict[str, Any]]:
    """Join the Genome view (code + lineage) with the Fitness view (correct + cost) on (gen, slot) —
    the evaluated population the breeder selects from."""
    code_by_key = {(int(g["gen"]), int(g["slot"])): g["code"] for g in ctx.views["genomes"].value()}
    pop: list[dict[str, Any]] = []
    for f in ctx.views["fitness"].value():
        key = (int(f["gen"]), int(f["slot"]))
        if key in code_by_key:
            pop.append(
                {
                    "gen": int(f["gen"]),
                    "slot": int(f["slot"]),
                    "code": code_by_key[key],
                    "correct": bool(f["correct"]),
                    "cost": int(f["cost"]),
                }
            )
    return pop


def _gen_fitness(ctx: api.TriggerContext, gen: int) -> list[dict[str, Any]]:
    return [f for f in ctx.views["fitness"].value() if int(f["gen"]) == gen]


def code_evolution_topology(
    task: CodingTask | None = None,
    *,
    responders: list[Responder],
    n: int = 4,
    max_gens: int = 4,
    select_k: int = 2,
    patience: int = 3,
    timeout: float = 60.0,
    cost_fn: Callable[[dict[str, str]], int] | None = None,
    deterministic: bool = False,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the evolutionary code-writing topology. A seeder fans out N Spawns; each is mutated into a
    Genome (model), gate-evaluated into a Fitness (correctness + cost); when a generation's N fitnesses
    are in, the breeder selects the elite and either spawns the next generation (conditioned on them),
    declares Evolved (the best correct genome, at max gens or on stagnation), or Exhausted (no correct
    genome within budget). `cost_fn` is the continuous objective (default: AST-node count)."""
    job = task or kvstore_task()
    cost = cost_fn or _ast_cost

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "seeder",
            schemas=[Spawn],
            schema_version=1,
            factory=_seeder_factory(n),
            deterministic=deterministic,
        )
        b.producer_kind(
            "mutator",
            schemas=[Genome, ModelUsage],
            schema_version=1,
            factory=_mutator_factory(job, responders),
            deterministic=deterministic,
        )
        b.producer_kind(
            "evaluator",
            schemas=[Fitness],
            schema_version=1,
            factory=_evaluator_factory(job, cost, timeout),
            deterministic=deterministic,
        )
        b.producer_kind(
            "breeder",
            schemas=[Spawn, Evolved, Exhausted],
            schema_version=1,
            factory=_breeder_factory(n, max_gens, select_k, patience),
            deterministic=deterministic,
        )
        b.view("genomes", api.KindBuffer("Genome"))
        b.view("fitness", api.KindBuffer("Fitness"))
        b.initial("seeder", input=None)
        b.trigger(
            "mutate",
            subscription=api.Subscription(kinds=frozenset({"Spawn"})),
            predicate=lambda ctx: True,
            starts="mutator",
            input_builder=lambda ctx: {
                "gen": int(ctx.event.payload["gen"]),
                "slot": int(ctx.event.payload["slot"]),
                "parents": list(ctx.event.payload["parents"]),
                "parent_ids": list(ctx.event.payload.get("parent_ids", [])),
            },
            policy=api.PerEvent(),
        )
        b.trigger(
            "evaluate",
            subscription=api.Subscription(kinds=frozenset({"Genome"})),
            predicate=lambda ctx: True,
            starts="evaluator",
            input_builder=lambda ctx: {
                "gen": int(ctx.event.payload["gen"]),
                "slot": int(ctx.event.payload["slot"]),
                "code": ctx.event.payload["code"],
            },
            policy=api.PerEvent(),
        )
        # a generation is done when all N of its fitnesses are in; the breeder fires ONCE per generation
        # (at that generation's Nth fitness) — the full population is on the record before it selects.
        b.trigger(
            "breed",
            subscription=api.Subscription(kinds=frozenset({"Fitness"})),
            predicate=lambda ctx: len(_gen_fitness(ctx, int(ctx.event.payload["gen"]))) >= n,
            starts="breeder",
            input_builder=lambda ctx: {
                "gen": int(ctx.event.payload["gen"]),
                "population": _population(ctx),
            },
            policy=api.PerEvent(),
        )
        b.termination(
            api.any_of(
                api.threshold_count("Evolved", 1),
                api.threshold_count("Exhausted", 1),
                api.quiescence(),
            )
        )

    return topo


def ci_responders(genome: str, n: int = 4) -> list[Responder]:
    """CI stand-ins: every slot drafts the same fixed genome `genome`, so the loop's WIRING (mutate →
    evaluate → select → terminate) is exercised deterministically in OUTCOME without a model."""
    return [DeterministicResponder(seed=i, menu=[genome]) for i in range(n)]


def walkthrough_responders(
    models: list[str] | str, *, temperature: float = 0.8, max_tokens: int = 4096
) -> list[Responder]:
    """Best-of-N mutation over an ENSEMBLE — one mutation operator per model (heterogeneous variation:
    different families explore the search space differently). Higher temperature than coding_flow: an
    EA wants exploratory variance, not the single most-likely completion."""
    names = [models] if isinstance(models, str) else list(models)
    return [OllamaResponder(m, temperature=temperature, max_tokens=max_tokens) for m in names]

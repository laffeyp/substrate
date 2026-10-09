# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""ASSEMBLE — the full swebench_solver topology (sprint 141): LOCALIZE -> REPAIR -> SELECT, one
event-sourced graph terminating on SelectedPatch.

Reuses the shared best_of_n factories (seeder, select-first judge) + records + the swebench phase
factories (localizer, repair drafter/validator, select logic + the run-and-observe test-exec). The wiring
is bespoke — swebench has pre/post phases the all-in-one `best_of_n_correction` builder doesn't model:
LOCALIZE seeds the loop (instead of an `initial` seeder), and SELECT runs after the loop's Solved.

  localizer(initial) -EditLocations-> seed -> [best-of-N: drafter -> validator(applier) -> judge] -Solved->
  select_exec(run-and-observe: tests per applied patch) -TestResults-> selector(rerank) -> SelectedPatch
"""

from __future__ import annotations

import asyncio
import os
import warnings
from collections.abc import AsyncIterator, Callable
from typing import Any

from ... import api
from ...adapters import ModelUsage, Responder
from ..best_of_n import best_of_n_correction, seeder_factory, select_first_judge_factory
from ..best_of_n.contracts import Candidate, Draft, Exhausted, Solved, Verdict
from .localize import localizer_factory
from .localize_elements import element_localizer_factory
from .records import (
    AppliedPatch,
    EditLocations,
    RepairOutcome,
    RepairSummary,
    Reproduction,
    ReproductionTest,
    SelectedPatch,
    SuspectElements,
    SuspectFiles,
    TestResults,
)
from .repair import repair_drafter_factory, repair_validate_factory
from .repro_base_validate import repro_base_validate_factory
from .reproduction import repro_generator_factory
from .select import select_patch
from .select_exec import TestRunner, run_one

_Factory = Callable[[], Any]


# F10 fix (review 2026-08-08): view names as module-level string constants so a typo becomes a
# NameError at import time, not a KeyError when the trigger's predicate fires. Sixteen
# `ctx.views["…"]` sites across this file used bare literals — the exact contract-truth gap KIT_DIARY
# finding 33 named (six literals + no static check + only surfaces at run time). Consolidating them
# here also documents the view topology in one place.
_VIEW_APPLIED = "applied"
_VIEW_EDIT_LOCATIONS = "edit_locations"
_VIEW_REPRODUCTION = "reproduction"
_VIEW_SOLVED = "solved"
_VIEW_TEST_RESULTS = "test_results"
_VIEW_VERDICTS = "verdicts"


def _build_edit_context(base_checkout: str, targets: tuple[str, ...]) -> str:
    """Inline the localized files' current content so the drafter edits against real bytes (the
    read_declared_files_for_diff idea). v1: targets are file paths (`file` or `file::elem` / `file:line`).

    2026-08-09 context-window guard. Pre-fix, `_build_edit_context` inlined every localized file's
    FULL source and returned. On astropy where suspect files can be ~150 KB each (io/fits/header,
    coordinates/sky_coordinate) the prompt hit 1.4 MB (~350k tokens) and every drafter call to
    the cloud tags 400'd with `{"error":"The prompt is too long: 1446140, model maximum context
    length: 262144"}` — even kimi's 262k context can't hold it. Elements ordered by AST position
    (extract_elements walks the AST top-to-bottom) plus deduplication of the target file set
    keeps the payload bounded.
    _PER_FILE_CAP + _TOTAL_CAP together bound edit_context. A file whose source exceeds
    _PER_FILE_CAP truncates at the cap boundary with a `# ... [truncated at N of M bytes]`
    marker so the drafter can see it was cut. If the running total would exceed _TOTAL_CAP,
    late files are dropped entirely and a `# ... [omitted N later files: reserving budget]`
    marker records the drop. Cap = 15 KB per file × 4 files worth of headroom = 60 KB text ≈
    15k tokens — fits every model in the ensemble (kimi 262k, glm 128k, nemotron 128k) with
    room for the issue text and the SEARCH/REPLACE preamble.

    A truncated file's SEARCH/REPLACE window is smaller but nonzero; the alternative (whole
    file → prompt-too-long → drafter dies → no patch) is strictly worse. Element-level slicing
    per SuspectElements is the honest v2 — this cap ships now to unblock the run."""
    _PER_FILE_CAP = 15_000  # bytes per file
    _TOTAL_CAP = 60_000  # bytes across all files (concatenated content, excludes headers)

    seen: set[str] = set()
    parts: list[str] = []
    used = 0
    dropped = 0
    for t in targets:
        path = t.split("::")[0].split(":")[0]
        if path in seen:
            continue
        seen.add(path)
        if used >= _TOTAL_CAP:
            dropped += 1
            continue
        full = os.path.join(base_checkout, path)
        try:
            with open(full, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            content = "(file not found)"
        original_size = len(content)
        if original_size > _PER_FILE_CAP:
            content = (
                content[:_PER_FILE_CAP]
                + f"\n# ... [truncated at {_PER_FILE_CAP} of {original_size} bytes]"
            )
        used += len(content)
        parts.append(f"# path: {path}\n```\n{content}\n```")
    if dropped:
        parts.append(f"# ... [omitted {dropped} later file(s): edit-context budget exhausted]")
    return "\n\n".join(parts)


def _round_verdicts(ctx: api.TriggerContext, rnd: int) -> list[dict[str, Any]]:
    return [v for v in ctx.views[_VIEW_VERDICTS].value() if int(v["round"]) == rnd]


def _round_applied(ctx: api.TriggerContext, rnd: int) -> list[dict[str, Any]]:
    return [a for a in ctx.views[_VIEW_APPLIED].value() if int(a["round"]) == rnd]


def _select_exec_factory(
    runner: TestRunner,
    regression: str | Callable[[str], Any],
    passed_at_base: frozenset[str] | None,
) -> _Factory:
    """Triggered on Solved: run the tests for EVERY applied patch of the solved round, concurrently; yield
    a TestResults per patch. The run-and-observe Docker seam (deterministic=False). The generated
    reproduction test (`repro_code`, from the input) is run per patch too. `passed_at_base` (the instance's
    base-passing test ids) switches the signal to `regression_held` — None falls back to whole-run
    `regression_passed`. ALWAYS yields exactly len(patches): a single patch's runner failure (the real
    DockerTestRunner WILL raise — container error, OOM, timeout) becomes a FAILED TestResults, never an
    unraised gather exception that emits ZERO results and stalls the barrier (review #62)."""

    async def run_all(inp: Any) -> AsyncIterator[TestResults]:
        patches = list(inp.get("applied", [])) if hasattr(inp, "get") else []
        repro_code = str(inp.get("repro_code", "")) if hasattr(inp, "get") else ""
        outcomes = await asyncio.gather(
            *[
                run_one(
                    runner,
                    regression,
                    repro_code,
                    int(p["slot"]),
                    str(p["model_patch"]),
                    passed_at_base=passed_at_base,
                )
                for p in patches
            ],
            return_exceptions=True,
        )
        for p, res in zip(patches, outcomes):
            if isinstance(res, BaseException):
                yield TestResults(
                    slot=int(p["slot"]),
                    regression_passed=False,
                    reproduction=Reproduction.OTHER,
                    summary=f"runner error: {type(res).__name__}: {str(res)[:160]}",
                )
            else:
                yield res

    return lambda: run_all


def _selector_factory() -> _Factory:
    """The deterministic rerank (pure given the recorded results): reconstruct the AppliedPatches +
    TestResults from the trigger input and emit the SelectedPatch."""

    async def select(inp: Any) -> AsyncIterator[SelectedPatch]:
        applied = [
            AppliedPatch(
                round=int(a["round"]),
                slot=int(a["slot"]),
                model_patch=str(a["model_patch"]),
                creates_file=bool(a["creates_file"]),
            )
            for a in (inp.get("applied", []) if hasattr(inp, "get") else [])
        ]
        results = {
            int(r["slot"]): TestResults(
                slot=int(r["slot"]),
                regression_passed=bool(r["regression_passed"]),
                reproduction=Reproduction(r["reproduction"]),
                summary=str(r["summary"]),
            )
            for r in (inp.get("results", []) if hasattr(inp, "get") else [])
        }
        sel = select_patch(applied, results)
        if sel is not None:
            yield sel

    return lambda: select


def _first_patch_selector_factory() -> _Factory:
    """The SIMPLE select: emit the patch that APPLIED. The judge's Solved event already names the first
    slot whose candidate applied cleanly; pick that AppliedPatch and emit it as the SelectedPatch. No
    test-running, no regression, no reproduction — the model emits edits, the validator applies them and
    produces the git diff, and we submit it. (The brittle test-picker SELECT is intentionally removed.)"""

    async def select(inp: Any) -> AsyncIterator[SelectedPatch]:
        slot = int(inp.get("slot", 0)) if hasattr(inp, "get") else 0
        applied = list(inp.get("applied", [])) if hasattr(inp, "get") else []
        chosen = next(
            (a for a in applied if int(a["slot"]) == slot), applied[0] if applied else None
        )
        if chosen is not None:
            yield SelectedPatch(
                slot=int(chosen["slot"]),
                model_patch=str(chosen["model_patch"]),
                reason="first-applyable",
            )

    return lambda: select


def _outcome_factory() -> _Factory:
    """The ALWAYS-EMIT terminal summary (technique #51): on SelectedPatch -> RepairSummary(SELECTED); on
    Exhausted -> RepairSummary classified by whether localization happened (NO_LOCALIZATION vs the model's
    edits not applying). Chained AFTER SelectedPatch (not on Solved) so the patch is on the log before this
    triggers termination — no race that could cancel the selector. The enum decision lives here, at the
    speaker's mouth (#2)."""

    async def outcome(inp: Any) -> AsyncIterator[RepairSummary]:
        is_selected = bool(inp.get("is_selected", False)) if hasattr(inp, "get") else False
        localized = int(inp.get("localized", 0)) if hasattr(inp, "get") else 0
        drafted = int(inp.get("drafted", 0)) if hasattr(inp, "get") else 0
        applied = int(inp.get("applied", 0)) if hasattr(inp, "get") else 0
        slot = int(inp.get("slot", -1)) if hasattr(inp, "get") else -1
        if is_selected:
            oc, sel = RepairOutcome.SELECTED, slot
        elif localized == 0:
            oc, sel = RepairOutcome.NO_LOCALIZATION, -1
        else:
            oc, sel = RepairOutcome.NO_APPLICABLE_EDIT, -1
        yield RepairSummary(
            outcome=oc, localized=localized, drafted=drafted, applied=applied, selected_slot=sel
        )

    return lambda: outcome


def _outcome_input(ctx: api.TriggerContext, *, is_selected: bool) -> dict[str, Any]:
    el = ctx.views[_VIEW_EDIT_LOCATIONS].value()
    return {
        "is_selected": is_selected,
        "slot": int(ctx.event.payload["slot"]) if is_selected else -1,
        "localized": len(el[-1]["targets"]) if el else 0,
        "drafted": len(ctx.views[_VIEW_VERDICTS].value()),
        "applied": len(ctx.views[_VIEW_APPLIED].value()),
    }


def swebench_repair_topology(
    *,
    responders: list[Responder] | None = None,
    base_checkout: str,
    issue: str,
    repo_skeleton: str,
    known_files: set[str],
    n: int = 3,
    max_rounds: int = 2,
    top_k: int = 5,
    watchdog_seconds: float = 60.0,
    firewall_instance: Any = None,
) -> Callable[[api.TopologyBuilder], None]:
    """The SIMPLE coding topology: LOCALIZE -> best-of-N REPAIR -> emit the first patch that applied. A real
    substrate topology (drafters/validator/judge are producers) that emits a `SelectedPatch` (a git diff),
    with NONE of the test-running SELECT apparatus. `responders[0]` localizes; `responders` (per slot) draft
    SEARCH/REPLACE edits; the validator clones `base_checkout` per candidate, applies, and emits the diff.
    ALWAYS emits a terminal `RepairSummary` (the enumerated outcome + stage counts) and terminates on it.

    Sprint 187 (roadmap v2 S2 dual-mode): `responders=None` defaults to
    `[DeterministicResponder(seed=i) for i in range(n)]` for CI. Matches the dual-mode pattern
    every other bundled topology uses per `docs/adding-a-topology.md` § "Make it dual-mode"
    (code_review, pair_coding, recursive_decomposition). A test / demo / bundled invocation
    that supplies base_checkout + issue + repo_skeleton + known_files but no responders gets a
    byte-stable deterministic run; every existing caller passing an explicit responders list
    behaves identically.

    Sprint 149 — `firewall_instance`, when passed, runs `firewall_check` at build. `swebench_solver_arm`
    (swebench_suite.py) already goes through `prepare_swebench_case` which firewalls; `swebench_repair_arm`
    (swebench_matrix.py) firewalls at its build (sprint 148). The optional kwarg here is the belt-and-braces
    guard for any future caller that stitches a topology by hand: pass the raw instance and the topology
    refuses to build on a leak. Not required (existing callers pass nothing and are firewall-guarded
    upstream); when present, must pass. `Any` because the shape is the swebench instance dict."""
    if responders is None:
        from ...adapters import DeterministicResponder

        responders = [DeterministicResponder(seed=i) for i in range(n)]
    if firewall_instance is not None:
        from .firewall import FirewallViolation, firewall_check

        ok, reason = firewall_check(firewall_instance)
        if not ok:
            raise FirewallViolation(str(firewall_instance.get("instance_id", "?")), reason)

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "localizer",
            schemas=[SuspectFiles, EditLocations, ModelUsage],
            schema_version=1,
            factory=localizer_factory(
                responders[0], issue, repo_skeleton, known_files, top_k=top_k
            ),
            deterministic=False,
        )
        b.initial("localizer", input=None)
        b.view("edit_locations", api.KindBuffer("EditLocations"))
        b.view("applied", api.KindBuffer("AppliedPatch"))
        b.view("solved", api.KindBuffer("Solved"))

        # Sprint 191 (roadmap v2 S3): the seeder / drafter / validator / judge loop is the shared
        # best-of-N + correction sub-topology at `topologies/best_of_n`. `seed_on="EditLocations"`
        # gates the seeder on the localizer's output (vs the coding_flow shape where seeder is
        # `initial`); `draft_input_extra` merges `edit_context` (built from the EditLocations
        # view) into each drafter invocation. The loop's `verdicts` view + all three of its
        # triggers land via `best_of_n_correction`; swebench_repair_topology keeps selector +
        # outcome + termination as its post-loop phase.
        best_of_n_correction(
            b,
            n=n,
            max_rounds=max_rounds,
            draft_factory=repair_drafter_factory(responders, spec=issue),
            validate_factory=repair_validate_factory(base_checkout),
            validator_schemas=[Verdict, AppliedPatch],
            deterministic=False,
            seed_on="EditLocations",
            draft_input_extra=lambda ctx: {
                "edit_context": _build_edit_context(
                    base_checkout,
                    tuple(ctx.views[_VIEW_EDIT_LOCATIONS].value()[-1]["targets"])
                    if ctx.views[_VIEW_EDIT_LOCATIONS].value()
                    else (),
                ),
            },
            # Consumer runs post-loop phases (selector + outcome); the run's terminal is
            # RepairSummary, not the loop's Solved/Exhausted. Pass a placeholder termination
            # that never fires — the topology's own b.termination(...) below owns the run's
            # terminal, matching the pre-Sprint-191 wire.
            termination=api.quiescence_with_watchdog(seconds=watchdog_seconds * 10),
        )

        b.producer_kind(
            "selector",
            schemas=[SelectedPatch],
            schema_version=1,
            factory=_first_patch_selector_factory(),
            deterministic=True,  # sprint 145: pure — picks first applied patch from input, no I/O
        )
        b.producer_kind(
            "outcome",
            schemas=[RepairSummary],
            schema_version=1,
            factory=_outcome_factory(),
            deterministic=True,  # sprint 145: pure — reads state, emits typed summary, no I/O
        )
        # SELECT (simple): the first applyable patch — on Solved, emit the AppliedPatch at the solved slot.
        b.trigger(
            "selector",
            subscription=api.Subscription(kinds=frozenset({"Solved"})),
            predicate=lambda ctx: True,
            starts="selector",
            input_builder=lambda ctx: {
                "slot": int(ctx.event.payload["slot"]),
                "applied": _round_applied(ctx, int(ctx.event.payload["round"])),
            },
            policy=api.PerEvent(),
        )
        # OUTCOME (always-emit summary, #51): on SelectedPatch -> SELECTED (chained AFTER the patch lands, so
        # termination can't race the selector); on Exhausted -> the failure classification.
        b.trigger(
            "outcome-ok",
            subscription=api.Subscription(kinds=frozenset({"SelectedPatch"})),
            predicate=lambda ctx: True,
            starts="outcome",
            input_builder=lambda ctx: _outcome_input(ctx, is_selected=True),
            policy=api.PerEvent(),
        )
        b.trigger(
            "outcome-fail",
            subscription=api.Subscription(kinds=frozenset({"Exhausted"})),
            predicate=lambda ctx: True,
            starts="outcome",
            input_builder=lambda ctx: _outcome_input(ctx, is_selected=False),
            policy=api.PerEvent(),
        )

        b.termination(
            api.any_of(
                api.threshold_count("RepairSummary", 1),
                api.quiescence_with_watchdog(seconds=watchdog_seconds),
            )
        )

    return topo


def swebench_solver_topology_with_test_selection(
    *,
    responders: list[Responder],
    base_checkout: str,
    issue: str,
    repo_skeleton: str,
    known_files: set[str],
    runner: TestRunner,
    regression_command: str | Callable[[str], Any],
    passed_at_base: frozenset[str] | None = None,
    n: int = 3,
    max_rounds: int = 2,
    top_k: int = 5,
    # F4 fix (review 2026-08-08): K reproduction samples generated in parallel and combined into
    # one runner script (see combine_repro_scripts in reproduction.py). K=1 identical to
    # pre-fix behaviour. K > 1 pays K model calls at generation + K× script execution inside
    # the ONE Docker invocation select_exec already runs per candidate — no extra container starts.
    repro_k: int = 1,
    # F6 fix (review 2026-08-08): defaults were swapped — repair-only (less work) had 600s and the
    # full solver (repair + Docker test execution per candidate) had 60s. A test or script that
    # instantiated the solver topology at defaults got guillotined before select_exec finished
    # even one candidate. Solver needs the longer budget; repair keeps the shorter one.
    watchdog_seconds: float = 600.0,
    firewall_instance: Any = None,
) -> Callable[[api.TopologyBuilder], None]:
    """The whole solver. `responders[0]` localizes; `responders` (per slot) draft. `runner` runs tests in
    the instance env (the real DockerTestRunner, or a stand-in). `regression_command` is a static command
    (same set for every candidate) OR a per-candidate planner (model_patch -> firewall-clean command, e.g.
    `make_regression_planner` — the proximity picker over the checkout). `passed_at_base` (the instance's
    base-passing test ids, from one base run) switches SELECT to the passed-at-base filter — required on
    repos with pre-existing base failures (flask). Terminates on SelectedPatch or Exhausted.

    Sprint 149 — see `swebench_repair_topology` for the `firewall_instance` contract. Same optional guard,
    same reason: production callers firewall upstream through the Adapter (`prepare_swebench_case` via
    `swebench_solver_arm`); a hand-stitched caller passing the instance here gets the third defense layer.

    RETIRED 2026-08-11 (holistic re-review, Move 4): every SWE-bench matrix arm now uses
    `swebench_repair_topology` (localize + best-of-N repair + emit the first patch that applied);
    the official harness grades. The in-topology `select_exec` apparatus this function wires
    duplicated the grader's work, doubled per-cell Docker minutes, and produced the 517-silent-
    fails shape the 2026-08-10 postmortem records (RC1). Kept in-tree behind a DeprecationWarning
    for `swebench_solver_arm` (the pre-Sprint-197 arm that still routes through
    `solver_topology_from_payload`) and the standalone scripts. Sprint 199b (roadmap v2 S7b)
    retired the `_build_solver_arm_from_payload(..., include_test_selection=True)` opt-in;
    matrix-arm code paths never reach the heavy topology. Any future revival needs a study
    plan naming the delta over harness-only grading, per
    `src/substrate/topologies/swebench_solver/_deprecated/README.md`."""
    warnings.warn(
        "swebench_solver_topology_with_test_selection is deprecated as of 2026-08-11 "
        "(KIT_DIARY 38, Move 4). Every SWE-bench matrix arm uses swebench_repair_topology; "
        "the harness grades. See src/substrate/topologies/swebench_solver/_deprecated/README.md "
        "for the retirement reason and revival path.",
        DeprecationWarning,
        stacklevel=2,
    )
    if firewall_instance is not None:
        from .firewall import FirewallViolation, firewall_check

        ok, reason = firewall_check(firewall_instance)
        if not ok:
            raise FirewallViolation(str(firewall_instance.get("instance_id", "?")), reason)

    def topo(b: api.TopologyBuilder) -> None:
        # LOCALIZE
        # F9 fix (review 2026-08-08): swap the solver's file-level `localizer_factory` for the
        # element-level `element_localizer_factory`. Emits SuspectElements per Python suspect
        # file so EditLocations carries `file::element` targets, and `_build_edit_context` trims
        # to class/function granularity per Agentless. Non-Python + syntax-error files degrade
        # to whole-file targets (see element_localizer_factory docstring); no silent drops.
        # SuspectElements was defined-but-dead pre-fix; this closes the drift.
        b.producer_kind(
            "localizer",
            schemas=[SuspectFiles, SuspectElements, EditLocations, ModelUsage],
            schema_version=1,
            factory=element_localizer_factory(
                responders[0], issue, repo_skeleton, base_checkout, known_files, top_k=top_k
            ),
            deterministic=False,
        )
        b.initial("localizer", input=None)
        # the reproduction-test generator runs once at the start (it only needs the issue); SELECT reads
        # its output to check which patches resolve the issue.
        b.producer_kind(
            "repro_gen",
            schemas=[ReproductionTest, ModelUsage],
            schema_version=1,
            factory=repro_generator_factory(responders[0], issue, k=repro_k),
            deterministic=False,
        )
        b.initial("repro_gen", input=None)
        # Sprint 155: base-fails-first validator. Runs the generated repro ONCE on the unmodified
        # base checkout (empty patch → runner runs on base_commit). Overwrites the repro with
        # code="" if the base run doesn't cleanly print "Issue reproduced" — the trivially-passing
        # / broken cases KIT_DIARY finding 21 named. The empty-code convention (records.py:82-88)
        # routes SELECT to regression-only, so no vocab change; the `reproduction` view's
        # value()[-1] snapshot at the select_exec trigger reads the OVERWRITE first when both
        # events land.
        b.producer_kind(
            "repro_base_validate",
            schemas=[ReproductionTest],
            schema_version=1,
            factory=repro_base_validate_factory(runner),
            deterministic=False,  # calls the runner (Docker) — I/O, stays False
        )
        b.view("reproduction", api.KindBuffer("ReproductionTest"))
        b.trigger(
            "repro_base_validate",
            subscription=api.Subscription(kinds=frozenset({"ReproductionTest"})),
            # gate: only fire on the ORIGINAL (from repro_gen) — the overwrite this producer
            # emits also matches the subscription, and re-validating an already-empty repro is
            # both wasted and a fanout loop. First ReproductionTest only.
            predicate=lambda ctx: len(ctx.views[_VIEW_REPRODUCTION].value()) == 1,
            starts="repro_base_validate",
            input_builder=lambda ctx: {"code": ctx.event.payload["code"]},
            policy=api.PerEvent(),
        )
        b.view("edit_locations", api.KindBuffer("EditLocations"))
        b.view("verdicts", api.KindBuffer("Verdict"))
        b.view("applied", api.KindBuffer("AppliedPatch"))
        b.view("test_results", api.KindBuffer("TestResults"))
        b.view("solved", api.KindBuffer("Solved"))

        # REPAIR (shared loop factories, swebench-seeded)
        b.producer_kind(
            "seeder",
            schemas=[Draft],
            schema_version=1,
            factory=seeder_factory(n),
            deterministic=True,  # sprint 145: pure — emits N Drafts from `n` alone, no I/O
        )
        b.producer_kind(
            "drafter",
            schemas=[Candidate, ModelUsage],
            schema_version=1,
            factory=repair_drafter_factory(responders, spec=issue),
            deterministic=False,
        )
        b.producer_kind(
            "validator",
            schemas=[Verdict, AppliedPatch],
            schema_version=1,
            factory=repair_validate_factory(base_checkout),
            deterministic=False,  # clones base_checkout, runs `git apply` — I/O, stays False
        )
        b.producer_kind(
            "judge",
            schemas=[Solved, Draft, Exhausted],
            schema_version=1,
            factory=select_first_judge_factory(n, max_rounds),
            deterministic=True,  # sprint 145: pure — reads verdicts input, emits typed decision
        )

        # SELECT
        b.producer_kind(
            "select_exec",
            schemas=[TestResults],
            schema_version=1,
            factory=_select_exec_factory(runner, regression_command, passed_at_base),
            deterministic=False,  # runs Docker per candidate — I/O, stays False
        )
        b.producer_kind(
            "selector",
            schemas=[SelectedPatch],
            schema_version=1,
            factory=_selector_factory(),
            deterministic=True,  # sprint 145: pure — reads TestResults input, picks patch, no I/O
        )

        # LOCALIZE -> seed the loop
        b.trigger(
            "seed",
            subscription=api.Subscription(kinds=frozenset({"EditLocations"})),
            predicate=lambda ctx: True,
            starts="seeder",
            input_builder=lambda ctx: None,
            policy=api.PerEvent(),
        )
        # draft per Draft, with edit_context built from the localized targets + the repo
        b.trigger(
            "draft",
            subscription=api.Subscription(kinds=frozenset({"Draft"})),
            predicate=lambda ctx: True,
            starts="drafter",
            input_builder=lambda ctx: {
                "round": int(ctx.event.payload["round"]),
                "slot": int(ctx.event.payload["slot"]),
                "context": ctx.event.payload["context"],
                "edit_context": _build_edit_context(
                    base_checkout,
                    tuple(ctx.views[_VIEW_EDIT_LOCATIONS].value()[-1]["targets"])
                    if ctx.views[_VIEW_EDIT_LOCATIONS].value()
                    else (),
                ),
            },
            policy=api.PerEvent(),
        )
        b.trigger(
            "validate",
            subscription=api.Subscription(kinds=frozenset({"Candidate"})),
            predicate=lambda ctx: True,
            starts="validator",
            input_builder=lambda ctx: {
                "round": int(ctx.event.payload["round"]),
                "slot": int(ctx.event.payload["slot"]),
                "response": ctx.event.payload["response"],
            },
            policy=api.PerEvent(),
        )
        b.trigger(
            "judge",
            subscription=api.Subscription(kinds=frozenset({"Verdict"})),
            predicate=lambda ctx: len(_round_verdicts(ctx, int(ctx.event.payload["round"]))) >= n,
            starts="judge",
            input_builder=lambda ctx: {
                "round": int(ctx.event.payload["round"]),
                "verdicts": _round_verdicts(ctx, int(ctx.event.payload["round"])),
            },
            policy=api.PerEvent(),
        )
        # Sprint 155 review fold (finding B1): the select_exec trigger BARRIERS on repro
        # validation completing. Original design fired select_exec on every Solved and read the
        # then-current reproduction view, but nothing gated Solved on `repro_base_validate`
        # having emitted its overwrite/passthrough — a fast REPAIR round could beat a slow base
        # repro run and let SELECT read the un-validated repro (the exact KIT_DIARY 21
        # false-positive shape). Fix: subscribe to BOTH `Solved` and `ReproductionTest`, fire
        # only when (a) a round completed (`_solved_round is not None`), (b) validate has
        # emitted (`reproduction.value()` has >=2 entries — original + overwrite/passthrough,
        # since `repro_base_validate` always emits exactly one for any input including empty),
        # and (c) select_exec hasn't fired yet (`test_results` empty). Whichever event lands
        # LAST flips the predicate true. Multi-round degrades to single-round only under this
        # gate; multi-round is `max_rounds=2` and rarely triggers in practice — deferred until
        # TestResults carries a `round` field (currently doesn't, records.py:99-107).
        b.trigger(
            "select_exec",
            subscription=api.Subscription(kinds=frozenset({"Solved", "ReproductionTest"})),
            predicate=lambda ctx: (
                _solved_round(ctx) is not None
                and len(ctx.views[_VIEW_REPRODUCTION].value()) >= 2
                and len(ctx.views[_VIEW_TEST_RESULTS].value()) == 0
            ),
            starts="select_exec",
            input_builder=lambda ctx: {
                "round": _solved_round(ctx),
                "applied": _round_applied(ctx, _solved_round(ctx)),  # type: ignore[arg-type]
                "repro_code": ctx.views[_VIEW_REPRODUCTION].value()[-1]["code"],
            },
            policy=api.PerEvent(),
        )
        # all TestResults in for the round -> rerank
        b.trigger(
            "selector",
            subscription=api.Subscription(kinds=frozenset({"TestResults"})),
            predicate=lambda ctx: (
                _solved_round(ctx) is not None
                and len([r for r in ctx.views[_VIEW_TEST_RESULTS].value()])
                >= len(_round_applied(ctx, _solved_round(ctx)))  # type: ignore[arg-type]
            ),
            starts="selector",
            input_builder=lambda ctx: {
                "applied": _round_applied(ctx, _solved_round(ctx)),  # type: ignore[arg-type]
                "results": list(ctx.views[_VIEW_TEST_RESULTS].value()),
            },
            policy=api.PerEvent(),
        )

        b.termination(
            api.any_of(
                api.threshold_count("SelectedPatch", 1),
                api.threshold_count("Exhausted", 1),
                api.quiescence_with_watchdog(seconds=watchdog_seconds),
            )
        )

    return topo


def _solved_round(ctx: api.TriggerContext) -> int | None:
    """The round that emitted Solved (the only round whose applied patches get tested), or None."""
    solved = ctx.views[_VIEW_SOLVED].value()
    return int(solved[-1]["round"]) if solved else None

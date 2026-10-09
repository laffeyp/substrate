# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""swebench_solver records — the locked vocabulary (sprint 133), as frozen Structs.

Vocabulary doc: `process/signals/swebench-solver-vocabulary.md`. Registered in WORKING_AGREEMENT.

The shared best-of-N + correction records (`Draft`, `Candidate`, `Verdict`, `Solved`, `Exhausted`) are
REUSED from coding_flow as the canonical 3-consumer contract (review #57 / #58 — verified byte-for-byte;
NOT re-rolled). This module re-exports them and adds the swebench-specific LOCALIZE / REPAIR-bridge /
SELECT records that wrap the shared loop. Collections are `tuple[...]` (a frozen record's fields are
immutable — the locked vocab's `list[str]` is realized as `tuple[str, ...]` for hash/encode stability).
"""

from __future__ import annotations

import enum

from msgspec import Struct

# The shared 3-consumer best-of-N + correction contract, from its CANONICAL home (best_of_n.contracts;
# review #61). Re-exported here so the swebench topology reads them from its own namespace.
from ..best_of_n.contracts import Candidate, Draft, Exhausted, Solved, Verdict

__all__ = [
    "Draft",
    "Candidate",
    "Verdict",
    "Solved",
    "Exhausted",
    "SuspectFiles",
    "SuspectElements",
    "EditLocations",
    "AppliedPatch",
    "ReproductionTest",
    "Reproduction",
    "TestResults",
    "SelectedPatch",
    "RepairOutcome",
    "RepairSummary",
    "GradeResult",
]


# --- LOCALIZE (before the loop) ---


class SuspectFiles(Struct, frozen=True):
    """File-level localization output (LLM-on-repo-skeleton). Observable: recall@k vs the gold-patch
    files (==1.0 on the flask-4045 fixture)."""

    files: tuple[str, ...]


class SuspectElements(Struct, frozen=True):
    """Class/function localization within one suspect file."""

    file: str
    elements: tuple[str, ...]


class EditLocations(Struct, frozen=True):
    """Fine-grained edit targets (`file::element` or `file:line-range`) — the REPAIR loop's input. The
    Repairer's input_builder composes these into the shared `Draft.context` (sprint 5)."""

    targets: tuple[str, ...]


# --- REPAIR -> SELECT bridge (the deterministic apply output) ---


class AppliedPatch(Struct, frozen=True):
    """A candidate that applied cleanly, carrying its `git diff` (`model_patch`) and whether it created a
    new file (the empty-SEARCH path, design §4b). `round`+`slot` complete the lineage. The REPAIR->SELECT
    bridge: SELECT reranks over the AppliedPatches."""

    round: int
    slot: int
    model_patch: str
    creates_file: bool


# --- SELECT (after the loop) ---


class ReproductionTest(Struct, frozen=True):
    """The solver's OWN generated test that reproduces the issue (NOT the held-out FAIL_TO_PASS — firewall).
    Generated once per instance from the issue; SELECT runs it against each candidate patch. `code` is the
    test script; "" means generation failed (SELECT falls back to regression-only)."""

    code: str


class Reproduction(enum.StrEnum):
    """The reproduction test's three-state outcome — enforced at the speaker's mouth (#2), not by string
    convention."""

    REPRODUCED = "reproduced"
    RESOLVED = "resolved"
    OTHER = "other"


class TestResults(Struct, frozen=True):
    """The solver's own validation of one applied patch: repo-DERIVED regression result (NOT the
    PASS_TO_PASS grade field — firewall) + reproduction-test status. A run-and-observe Docker seam
    (design §4) — captured once, `replayable=False` at the producer that emits it."""

    slot: int
    regression_passed: bool
    reproduction: Reproduction
    summary: str


class SelectedPatch(Struct, frozen=True):
    """The final submitted patch + why it won (majority vote / regression / reproduction). Deterministic
    GIVEN the recorded TestResults. The topology's output to the swebench oracle."""

    slot: int
    model_patch: str
    reason: str


# --- TERMINAL OUTCOME (the always-emit summary) ---


class RepairOutcome(enum.StrEnum):
    """Why a repair run terminated — the ENUMERATED terminal states (technique #53), so the record SAYS why
    a run produced no patch instead of leaving it implicit in the absence of other events. The judge only
    declares success when a candidate APPLIES, so the no-patch case splits by whether localization
    happened. Enforced at the speaker's mouth (#2), not a string convention."""

    SELECTED = "selected"  # a candidate applied cleanly and was selected (the success path)
    NO_LOCALIZATION = (
        "no_localization"  # localize picked no edit target -> the drafters had no file to edit
    )
    NO_APPLICABLE_EDIT = (
        "no_applicable_edit"  # drafts were produced but none applied (the model's SEARCH
    )
    #                                            text did not match the file) -> nothing to submit


class RepairSummary(Struct, frozen=True):
    """The terminal summary of a repair run (technique #51): the enumerated `outcome` plus the per-stage
    counts, so a reader (or the assay runner) learns WHAT HAPPENED from ONE typed event rather than
    reconstructing it from the presence/absence of others. Emitted exactly ONCE on every Solved/Exhausted
    terminal (the topology terminates on it). The WATCHDOG terminal (a true wedge — neither Solved nor
    Exhausted reached) emits NONE: a producer can only speak when triggered, and synthesizing a summary
    there would assert a classification the topology never computed; that ABSENCE is the runner's
    `timed_out` signal (so `timed_out`/`error` are the RUNNER-level complement to `RepairOutcome` — the
    terminal taxonomy is complete across the two levels). `selected_slot` = the chosen slot, or -1."""

    outcome: RepairOutcome
    localized: int  # number of edit targets localization produced
    drafted: int  # number of candidate drafts the model produced
    applied: int  # number of drafts that applied cleanly
    selected_slot: int


# --- GRADE (post-loop, topology-level terminal) ---


class GradeResult(Struct, frozen=True):
    """Sprint 195 (roadmap v2 S6 part 1 of 2, vocab v0.3 § G.6): the grade of one instance's
    submitted patch. Emitted once by the grade producer after `SelectedPatch` lands. The
    `LogProjectionOracle` at post-S6 `swebench.py:swebench_log_projection_oracle` reads
    exactly this event off the record — the grade becomes a projection of the record instead
    of an external run-and-observe call the ExternalGraderOracle owned.

    `verdict` matches the § E.1 `Verdict` enum's wire strings (`"pass"` / `"fail"` /
    `"no_verdict"`). `reason` is `""` when `verdict ∈ {"pass", "fail"}`; one of the
    `_HARNESS_REASONS` closed-set strings otherwise (`"timed_out"`, `"container_crashed"`,
    `"harness_error"`, `"docker_error"`, `"rate_limited"`, ...). `instance_id` is the
    SWE-bench instance the grade was on."""

    instance_id: str
    verdict: str
    reason: str

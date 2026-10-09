# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The control-ran conformance check — Sprint 3, the anti-cargo-cult enforcement surface.

The round-1 design (§4.1) requires a reported result to be a delta against a control that ACTUALLY
RAN — and that this be an EXECUTABLE check, not a type. The project's own scar tissue is the reason: a
type happily told a lie (the dead `LET_FINISH` enum; the fake-but-named-real R-3 'checker'), both
green under mypy, caught only by reading the claim against the code. So the guard is a function over
the collected CaseResults, three-state, and `build_report` refuses to emit any delta unless it returns
`pass`. There is no way to get a delta number without the control having run on every Case.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .. import api
from .run import CaseResult
from .suite import Suite

PASS = "pass"  # noqa: S105 — a verdict word, not a credential
FAIL = "fail"
NO_CONTROL = "no-control-ran"


def _has_committed_record(root: str) -> bool:
    """A control 'ran' only if a committed record sits at its root — confirm a terminal
    `substrate.RunFinalised` on the log. The guard dereferences the root rather than trusting the
    CaseResult object: a result without a real finalised record on disk is not a run that happened."""
    try:
        return any(e["kind"] == api.RUN_FINALISED for e in api.read_record(Path(root)))
    except Exception:  # noqa: BLE001 - any unreadable/absent record means "did not run"
        return False


@dataclass(frozen=True)
class ControlRanCheck:
    """Three-state, never boolean: `pass` (control ran on every Case), `fail` (control ran on some but
    not all Cases — the paired comparison would be incomplete), `no-control-ran` (the control produced
    no results at all). `detail` names what is missing."""

    state: str
    detail: str


def check_control_ran(results: Sequence[CaseResult], suite: Suite) -> ControlRanCheck:
    if suite.control_arm is None:
        # Sprint 201 (best-practice fold): a Suite may omit `control_arm` (solo-arm run,
        # topology-attachment test-drive). No paired-delta framing applies; return PASS with
        # a note so downstream code treats every arm as its own free-standing measurement.
        return ControlRanCheck(PASS, "no control_arm declared — solo-arm suite")
    control = [r for r in results if r.arm == suite.control_arm]
    if not control:
        return ControlRanCheck(
            NO_CONTROL,
            f"control arm '{suite.control_arm}' produced no results — no delta can be reported",
        )
    ran_cases = {r.case_id for r in control}
    expected = {c.case_id for c in suite.cases}
    missing = expected - ran_cases
    if missing:
        return ControlRanCheck(
            FAIL,
            f"control arm ran {len(ran_cases)}/{len(expected)} cases; missing {sorted(missing)}",
        )
    # the control claims every Case — now confirm each claim against a committed record on disk, not
    # against the CaseResult object alone (the anti-cargo-cult check: a number needs a real run behind it).
    no_record = sorted(r.case_id for r in control if not _has_committed_record(r.root))
    if no_record:
        return ControlRanCheck(
            FAIL,
            f"control arm has no committed record (RunFinalised) for cases {no_record} "
            "— a result without a real run cannot back a delta",
        )
    return ControlRanCheck(
        PASS, f"control arm ran on all {len(expected)} cases (records confirmed)"
    )

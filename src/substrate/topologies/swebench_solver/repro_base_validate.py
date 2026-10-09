# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Base-fails-first reproduction validator — sprint 155 (roadmap Group D).

The model-generated reproduction test is meant to distinguish a buggy state from a fixed state:
per the prompt at `reproduction.py:20-33`, it prints "Issue reproduced" when the bug is present
and "Issue resolved" when it is fixed. But it is a MODEL artifact — it can be wrong. Two
failure modes matter:

  1. **Trivially-passing repro.** A repro that prints "Issue resolved" without any patch applied
     doesn't discriminate — it says the bug isn't there when the bug IS there. Feeds a
     false-positive resolution signal into SELECT that (per KIT_DIARY finding 21) is exactly
     what happened on flask-4045 with the qwen3-coder:480b run: the model's repro said RESOLVED
     even on the unpatched base because it only exercised the half of the bug the model
     understood, so SELECT picked a partial fix that the oracle rejected.
  2. **Broken repro.** A repro that errors ("Other issues") or prints neither marker can never
     say "Issue reproduced" on any patched candidate, so its signal is always OTHER — a lot of
     Docker time for zero information.

This producer runs the repro ONCE on the unmodified base checkout (empty patch → runner runs
on base_commit) and overwrites `ReproductionTest.code = ""` if it doesn't cleanly print "Issue
reproduced". The empty-code convention (records.py:82-88) already routes SELECT to
regression-only, so no vocab change — the "dropped" state is expressible in the locked shape.

Runs concurrently with REPAIR (both fire off the initial ReproductionTest and Solved chain).
The assemble-side select_exec trigger BARRIERS on `reproduction.value()` length >= 2 so SELECT
never reads an un-validated repro (sprint 155 review-fold finding B1). This producer therefore
emits EXACTLY ONE ReproductionTest on every input path — including the empty-code passthrough
at `_run` below — because the barrier's `len >= 2` gate depends on it. Removing the empty-code
emit would deadlock the barrier on empty-repro cases.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from .records import Reproduction, ReproductionTest
from .select_exec import reproduction_status

_Factory = Callable[[], Any]


class _RunnerLike(Protocol):
    """Matches `DockerTestRunner.run(model_patch, command, extra_files=None) -> (rc, output)` —
    the exact signature `run_one` uses at select_exec.py:129, 137-139. Structural typing so a
    test can pass a stub without a full DockerTestRunner instance. Kwarg name matches the real
    runner (review nit B8) so calling by keyword works at every call site."""

    def run(
        self, model_patch: str, command: str, extra_files: dict[str, str] | None = None
    ) -> tuple[int, str]: ...


def repro_base_validate_factory(runner: _RunnerLike) -> _Factory:
    """A producer that runs the incoming `ReproductionTest.code` on the unmodified base checkout
    (empty patch) and OVERWRITES the repro with `code=""` iff the base run does not cleanly
    report `Issue reproduced`. Passes through unchanged when the incoming code is empty (the
    generator already gave up) or when the base run confirms the repro discriminates.

    Input: the ReproductionTest event's payload (dict with `code`). Emits ONE ReproductionTest —
    either a passthrough copy of the original (when the base run says REPRODUCED) OR an
    overwrite with empty code (when the base run says RESOLVED or OTHER — the two demote
    conditions). Deterministic=False on the producer because the underlying runner is Docker; a
    seeded stand-in in tests is fine because this factory itself is pure over its inputs.

    On any runner exception, passes the original code through unchanged — same
    death-resilience posture as `repro_generator_factory` (KIT_DIARY 16): a Docker hiccup must
    never wedge the topology.
    """

    async def validate(inp: Any) -> AsyncIterator[ReproductionTest]:
        code = str(inp.get("code", "")) if hasattr(inp, "get") else ""
        if not code:
            # Empty code already routes SELECT to regression-only. The passthrough emit is
            # LOAD-BEARING for the assemble-side select_exec barrier (finding B1): that trigger
            # gates on `reproduction.value()` length >= 2, so if this producer emits nothing on
            # the empty-code path, the barrier deadlocks on empty-repro instances. Keep the
            # emit; the "noise" is one record frame that select_exec needs to see.
            yield ReproductionTest(code=code)
            return

        # 2026-08-09 halt-on-error rewrite: no runner-exception swallow. A Docker hiccup
        # halts the sweep instead of silently degrading the repro signal.
        _rc, out = await asyncio.to_thread(
            runner.run, "", "python /sol/repro.py", {"repro.py": code}
        )

        status = reproduction_status(out)
        if status == Reproduction.REPRODUCED:
            # the repro correctly detects the bug on base → keep it, so SELECT can use its
            # signal per candidate later.
            yield ReproductionTest(code=code)
        else:
            # RESOLVED (trivially passing — the false-positive case KIT_DIARY 21 named) OR
            # OTHER (errored / didn't print a marker — signal always OTHER downstream, no
            # information for SELECT). The scope on OTHER is a widening beyond the sprint 155
            # card's "trivially-passing" wording (finding B2, intentional): a repro that says
            # neither marker on base cannot say "reproduced" on any patched candidate either,
            # so its signal is guaranteed useless — same demote path as RESOLVED. Overwrites
            # with empty code; the view's `value()[-1]` snapshot at the select_exec input
            # builder in assemble.py then reads empty and routes SELECT to regression-only.
            yield ReproductionTest(code="")

    return lambda: validate


__all__ = ["repro_base_validate_factory"]

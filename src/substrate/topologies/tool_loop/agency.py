# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Agency assay — score the TRAJECTORY of a tool-loop run, not the artifact (RESEARCH R-13/R-16).

SWE-bench and most coding evals grade the final artifact (does the patch pass the held-out tests).
That is structurally blind to AGENCY: did the model actually RUN its code, read the real result, and
FIX what broke — the loop that separates an agent from a code-completer. Substrate can score it
because the run record IS the trajectory: every `ToolCall` / `ToolResult` / `FinalAnswer` is a typed
event on the log. `score_agency` reads those events and returns a structured score that is orthogonal
to whether the output is correct — the fact SWE-bench cannot see (R-13). `deepseek-v4-pro` is the
clean case: artifact-plausible ("proven working") while its trajectory shows `exit 1` twice — the
artifact grade passes it, the agency grade fails it.

The label is the primary signal; the 0-100 score weights the verify loop (ran + saw exit 0 = half of
it) so a write-spin or a no-op can't score like a real verify. NB: the LIVE record view yields a tool
output as a `mappingproxy`, `read_record` as a plain `dict` — hence the `Mapping` check, not `dict`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from msgspec import Struct, field

from .kinds import FINAL_ANSWER, TOOL_CALL, TOOL_RESULT
from .tools import TOOL_NAME_BASH, TOOL_NAME_EDIT_FILE, TOOL_NAME_WRITE_FILE

_CODE_TOOLS = frozenset({TOOL_NAME_WRITE_FILE, TOOL_NAME_EDIT_FILE})


class AgencyTask(Struct, frozen=True):
    """One assay task: a `{workdir}`-substituted prompt plus optional `seed` files written into the
    workspace before the run. A SUITE of these stresses different agentic demands (build-and-verify,
    fix-a-failure, verify-via-tests) so agency is measured across shapes, not one lucky task."""

    name: str
    prompt: str
    seed: dict[str, str] = field(default_factory=dict)


# The agency task suite (RESEARCH R-19). Each task demands the verify loop in a different way:
#   build_hangman   — build something and prove it runs (build → run → check).
#   fix_runtime_bug — a seeded program crashes; run it, read the error, fix it, re-run (the R-18 shape:
#                     a GUARANTEED failure, so the trajectory must recover, not just produce).
#   build_and_test  — write code AND a test, then run the test (verify-via-tests, the SWE-bench shape,
#                     here UN-firewalled so the model can actually iterate-until-green — R-13).
AGENCY_SUITE: list[AgencyTask] = [
    AgencyTask(
        "build_hangman",
        "Build a working command-line Hangman game in Python at {workdir}/hangman.py: a small "
        "built-in word list, ASCII-art gallows, win/lose detection, reads guesses from stdin. Then "
        "PROVE it works by running it via bash with guesses piped in. If it errors, read the file, "
        "fix it, and re-run until it completes cleanly.",
    ),
    AgencyTask(
        "fix_runtime_bug",
        "The Python file calc.py in this directory is BROKEN — it crashes when run. Run it with bash "
        "to see the error, read the file, fix it so it runs without error, and re-run to CONFIRM it "
        "works. Report the final output.",
        seed={
            "calc.py": (
                "def main():\n    x = 6\n    y = 7\n    print('Result:', compute(x, y))\n\n"
                "if __name__ == '__main__':\n    main()\n"
            )
        },
    ),
    AgencyTask(
        "build_and_test",
        "Write a function add(a, b) that returns a+b in math_ops.py, and a test file test_math_ops.py "
        "that asserts add(2, 3) == 5. Then RUN the test with bash (python -m pytest or a direct run) to "
        "confirm it passes, and report the result.",
    ),
]


class AgencyScore(Struct, frozen=True):
    """A tool-loop run's trajectory scored for AGENCY, independent of artifact correctness.

    label: VERIFIED (ran its code and saw exit 0) | ATTEMPTED (ran, never succeeded) |
           NO_VERIFY (engaged but never ran) | NO_ENGAGE (no tool calls at all).
    score: 0-100 composite (engaged 15 + wrote 10 + ran 25 + saw_exit_zero 25 + resilient 15 +
           honest_final 10) — the verify loop (ran + saw_exit_zero) is half the score by design."""

    label: str
    score: int
    tool_calls: int
    wrote_code: bool  # write_file or edit_file
    ran_code: bool  # a bash call (executed something, the verify action)
    saw_exit_zero: bool  # a bash exited 0 — it actually ran clean at least once
    resilient: bool  # no failure occurred, OR a failure was followed by another action (recovered)
    honest_final: bool  # did NOT declare done over a non-zero last run (or marked it [unverified])
    max_same_file_writes: (
        int  # the write-spin detector: longest run of consecutive same-file writes
    )


class AgencyRates(Struct, frozen=True):
    """N runs of one model aggregated into RATES — the honest upgrade from a single trajectory
    (a behaviour class) to a distribution. `verified` / `runs` is the VERIFIED rate; `mean_score` is
    the average agency; `labels` is the full label distribution. A model like deepseek-v4-pro whose
    agency is variable (VERIFIED one run, false-claim the next) only shows up here, at n>1."""

    runs: int
    verified: int
    mean_score: float
    labels: dict[str, int]


def aggregate_agency(scores: list[AgencyScore]) -> AgencyRates:
    """Aggregate N per-run scores into rates. Empty in -> zeros (nothing ran)."""
    n = len(scores)
    labels: dict[str, int] = {}
    for s in scores:
        labels[s.label] = labels.get(s.label, 0) + 1
    return AgencyRates(
        runs=n,
        verified=labels.get("VERIFIED", 0),
        mean_score=(sum(s.score for s in scores) / n) if n else 0.0,
        labels=labels,
    )


def score_agency(events: Iterable[Mapping[str, Any]]) -> AgencyScore:
    """Score a tool-loop run's trajectory from its record events (`read_record` output, or the live
    view payloads). Orthogonal to whether the produced artifact is correct — this measures whether the
    agent behaved like one: ran what it built, reacted to failures, and reported honestly."""
    tool_calls = 0
    wrote = ran = saw_zero = had_fail = acted_after_fail = False
    last_bash_exit: int | None = None
    final_text = ""
    prev_write: str | None = None
    same_run = 0
    max_same = 0

    for e in events:
        kind = e.get("kind")
        p = e.get("payload", {})
        if kind == TOOL_CALL:
            tool_calls += 1
            tool = p.get("tool")
            if had_fail:
                acted_after_fail = True  # a tool call AFTER a failure = the agent reacted to it
            if tool in _CODE_TOOLS:
                wrote = True
            if tool == TOOL_NAME_BASH:
                ran = True
            if tool == TOOL_NAME_WRITE_FILE:
                args = p.get("args") or []
                path = Path(str(args[0])).name if args else None
                same_run = same_run + 1 if path == prev_write else 1
                prev_write = path
                max_same = max(max_same, same_run)
            else:
                prev_write, same_run = None, 0
        elif kind == TOOL_RESULT:
            tool = p.get("tool")
            out = p.get("output")
            exit_ = int(out.get("exit", 0) or 0) if isinstance(out, Mapping) else None
            if not p.get("ok", True) or (tool == TOOL_NAME_BASH and exit_ not in (None, 0)):
                had_fail = True
            if tool == TOOL_NAME_BASH and isinstance(out, Mapping):
                last_bash_exit = exit_
                if exit_ == 0:
                    saw_zero = True
        elif kind == FINAL_ANSWER:
            final_text = str(p.get("text", ""))

    engaged = tool_calls > 0
    resilient = (not had_fail) or acted_after_fail
    honest_final = last_bash_exit in (None, 0) or "unverified" in final_text.lower()

    if not engaged:
        label = "NO_ENGAGE"
    elif not ran:
        label = "NO_VERIFY"
    elif not saw_zero:
        label = "ATTEMPTED"
    else:
        label = "VERIFIED"

    # a run that never engaged earns nothing — resilient/honest are vacuously true (no failure, no
    # bash) and must not hand a no-op free points.
    score = (
        (15 + 10 * wrote + 25 * ran + 25 * saw_zero + 15 * resilient + 10 * honest_final)
        if engaged
        else 0
    )
    return AgencyScore(
        label=label,
        score=score,
        tool_calls=tool_calls,
        wrote_code=wrote,
        ran_code=ran,
        saw_exit_zero=saw_zero,
        resilient=resilient,
        honest_final=honest_final,
        max_same_file_writes=max_same,
    )

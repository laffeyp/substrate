# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 337: the plan's checks (research create-topology § 5)."""

from __future__ import annotations

import pytest

from substrate.topologies.compose.check import check
from substrate.topologies.compose.vocabulary import Finding, Strength

DRAFT_AND_CRITIQUE = """draft: model "Write the function the user asks for."
critic: model on Draft "List the defects in this draft, or say NONE."
fix: model on Critic with Draft if Critic.text has no NONE max 3 "Fix the listed defects."
end: first Fix"""


@pytest.mark.parametrize(
    ("plan", "code", "step", "fix"),
    [
        ('Draft: model "r"', Finding.BAD_ID, "Draft", "lower-case word"),
        ('a: model "r"\na: model "s"', Finding.BAD_ID, "a", "lower-case word"),
        ('user_message: model "r"', Finding.BAD_ID, "user_message", "lower-case word"),
        ('a: modl "r"', Finding.UNKNOWN_PART, "a", "use `model`"),
        ('a: model onn input "r"', Finding.UNKNOWN_FIELD, "a", "use `on`"),
        (
            '{"steps": [{"id": "a", "part": "model", "rol": "r"}]}',
            Finding.UNKNOWN_FIELD,
            "a",
            "use `role`",
        ),
        ("a: model", Finding.MISSING_ROLE, "a", "add a role"),
        ("a: command", Finding.MISSING_ROLE, "a", "give it one"),
        ('a: model "r"\nb: model on Nope "s"', Finding.NEVER_STARTS, "b", "A"),
        ('a: model "r"\nb: model on A, B "s"', Finding.NO_LIMIT, "b", "max 3"),
        ('a: model "r"\nend: first Zed', Finding.NEVER_ENDS, "", "A"),
        ('a: model "r"\nb: model on A "s"\nend: first A', Finding.ENDS_EARLY, "b", "end later"),
        ('a: model "r"\nb: model on input "s"\nend: first B', Finding.UNREAD, "a", "with A"),
    ],
)
def test_each_finding_names_its_step_and_fix(plan: str, code: Finding, step: str, fix: str) -> None:
    hits = [f for f in check(plan).findings if f.code is code]
    assert hits, [f.line() for f in check(plan).findings]
    assert hits[0].step == step and fix in hits[0].fix
    assert hits[0].line().startswith(f"{code.value} · ")


def test_the_dry_run_goes_both_ways_and_the_fix_comes_checked() -> None:
    c = check(DRAFT_AND_CRITIQUE)
    assert c.dry_run == [
        "— as written",
        "1 draft → Draft: draft answer 1",
        "2 critic → Critic: nothing to say",
        "3 fix → Fix: fix answer 1",
        "ended: first Fix",
        "— with every `if` failing",
        "1 draft → Draft: draft answer 1",
        "2 critic → Critic: stand-in: NONE",
        "went idle with its end unmet",
    ]
    (found,) = c.findings
    assert found.code is Finding.NEVER_ENDS and found.strength is Strength.DRY_RUN
    assert "or quiet" in found.fix
    assert c.fixed is not None and c.fixed.findings == []
    assert c.fixed.lines[-2] == "end: first Fix or quiet"
    assert c.fixed.dry_run[-1] == "ended: quiet, after 2 events"
    assert c.wiring == [
        "input ← the run's input; starts draft",
        "Draft ← draft; starts critic; read by fix",
        "Critic ← critic; starts fix",
        "Fix ← fix; starts nothing; ends the run",
    ]


def test_a_loop_gets_its_limit_in_the_fixed_plan() -> None:
    c = check('a: model "r"\nb: model on A, B "s"')
    assert [f.code for f in c.findings] == [Finding.NO_LIMIT]
    assert c.fixed is not None and c.fixed.findings == []
    assert c.fixed.lines[2] == 'b: model on A, B max 3 "s"'
    assert [ln for ln in c.fixed.dry_run if " b → " in ln] == [
        "2 b → B: b answer 1",
        "3 b → B: b answer 2",
        "4 b → B: b answer 3",
    ]


def test_a_finding_without_a_certain_fix_returns_no_fixed_plan() -> None:
    assert check('a: model "r"\nb: model on Nope "s"').fixed is None
    assert check('a: model "r"\nend: first Zed').fixed is None
    assert check("a: model").fixed is None


def test_a_clean_plan_has_no_findings_and_commands_do_not_run() -> None:
    # Had the command run, its output would be "real" and its exit 7.
    c = check('test: command "echo real; exit 7"\nreport: model on Test "Say how it went."')
    assert c.findings == []
    assert c.dry_run[1] == "1 test → Test: test output"
    assert c.dry_run[-1] == "ended: quiet, after 2 events"

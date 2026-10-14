# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Session vocabulary v0.16 § AA: composed topologies (kernel sprint K335).

A plan is a name, steps and an end. Each step is one of five standard parts; `wire` turns a plan
into a kernel topology, so the model that writes a plan names parts and never writes code.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Final

from msgspec import Struct, field

from ..session.vocabulary import RunOutcome

# `on: [input]` starts a step on the run's input (§ AA.1).
INPUT: Final[str] = "input"
DEFAULT_MAX_MINUTES: Final[int] = 30
DEFAULT_COLLECT_N: Final[int] = 2
# `n all`: a collect after a split waits for one event per item (§ AA.1).
COLLECT_ALL: Final[int] = 0
# A step between a split and its collect runs once per item, up to this many (§ AA.1).
FAN_OUT_MAX: Final[int] = 50
STEP_ID: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")


class Part(StrEnum):
    """What a step is (§ AA.2)."""

    MODEL = "model"  # one call to a model
    AGENT = "agent"  # one session turn with tools in a worktree (§ Z)
    COMMAND = "command"  # one shell command
    COLLECT = "collect"  # waits for n events, then writes them together
    SPLIT = "split"  # writes one event per item of its input


class AgentAs(StrEnum):
    """An agent step's kind (§ AA.1)."""

    PLAIN = "plain"
    BUILD = "build"  # on a new branch
    REVIEW = "review"  # read-only tools


class TestOp(StrEnum):
    """How a `Test` compares a field's text with its value (§ AA.1)."""

    IS = "is"
    IS_NOT = "is not"
    HAS = "has"
    HAS_NO = "has no"


class EndWhen(StrEnum):
    """When a run ends (§ AA.1)."""

    FIRST = "first"  # at the first event of a kind
    AFTER = "after"  # at the n-th
    QUIET = "quiet"  # when nothing runs and nothing is left to start


class Finding(StrEnum):
    """What the plan tool finds (§ AA.5), a closed set."""

    BAD_ID = "bad_id"
    UNKNOWN_PART = "unknown_part"
    UNKNOWN_FIELD = "unknown_field"
    MISSING_ROLE = "missing_role"
    NEVER_STARTS = "never_starts"
    NO_LIMIT = "no_limit"
    NEVER_ENDS = "never_ends"
    ENDS_EARLY = "ends_early"
    UNREAD = "unread"


class Strength(StrEnum):
    """How sure a finding is (§ AA.5)."""

    CERTAIN = "certain"  # it follows from the plan's wiring
    DRY_RUN = "dry_run"  # it rests on the run with stand-in answers


class StopSource(StrEnum):
    """Why a composed run was stopped (§ AA.3, v0.16.1)."""

    CALLER_STOP = "caller_stop"  # its caller stopped it
    MAX_MINUTES = "max_minutes"  # its time ran out


class RunStopRequested(Struct, frozen=True):
    """Injected into a composed run's record to stop it; the run finalises at it (§ AA.3)."""

    source: StopSource


RUN_STOP_REQUESTED: Final[str] = "RunStopRequested"


class Test(Struct, frozen=True):
    """One test on a step's starting event (§ AA.1)."""

    kind: str
    field: str
    op: TestOp
    value: str


class Step(Struct, frozen=True, kw_only=True, rename={"with_": "with", "if_": "if", "as_": "as"}):
    """One step of a plan (§ AA.1). Python names `with_`, `if_` and `as_` are `with`, `if` and
    `as` on the wire."""

    id: str
    part: Part
    role: str = ""
    on: list[str] = field(default_factory=list)
    with_: list[str] = field(default_factory=list)
    input: str = ""
    if_: Test | None = None
    max: int = 1
    model: str = ""
    as_: AgentAs = AgentAs.PLAIN
    command: str = ""
    n: int = DEFAULT_COLLECT_N


class End(Struct, frozen=True):
    """One way a run ends (§ AA.1)."""

    when: EndWhen
    kind: str = ""
    count: int = 1


class Plan(Struct, frozen=True):
    """A composed topology (§ AA.1)."""

    name: str
    steps: list[Step]
    end: list[End] = field(default_factory=lambda: [End(when=EndWhen.QUIET)])
    max_minutes: int = DEFAULT_MAX_MINUTES


# The events each part writes (§ AA.2). `wire` makes one class per step, named from its id, with
# the fields of its part's payload.
PART_PAYLOAD: Final[dict[Part, tuple[tuple[str, Any], ...]]] = {
    Part.MODEL: (("text", str),),
    Part.AGENT: (
        ("run_id", str),
        ("outcome", RunOutcome),
        ("reply", str),
        ("files", list[str]),
        ("branch", str | None),
        ("commits", list[str]),
    ),
    Part.COMMAND: (("ok", bool), ("exit", int), ("output", str)),
    Part.COLLECT: (("items", list[dict[str, Any]]),),
    Part.SPLIT: (("item", str), ("index", int), ("of", int)),
}

# The field a step reads when it has no `input` (§ AA.2), in order of preference.
MAIN_FIELDS: Final[tuple[str, ...]] = ("text", "reply", "output", "item")


def kind_of(step_id: str) -> str:
    """A step's event kind: its id in CamelCase (`critic_a` writes `CriticA`)."""
    return "".join(part[:1].upper() + part[1:] for part in step_id.split("_") if part)


__all__ = [
    "RUN_STOP_REQUESTED",
    "RunStopRequested",
    "StopSource",
    "COLLECT_ALL",
    "DEFAULT_COLLECT_N",
    "FAN_OUT_MAX",
    "DEFAULT_MAX_MINUTES",
    "INPUT",
    "MAIN_FIELDS",
    "PART_PAYLOAD",
    "STEP_ID",
    "AgentAs",
    "End",
    "EndWhen",
    "Finding",
    "Part",
    "Plan",
    "Step",
    "Strength",
    "Test",
    "TestOp",
    "kind_of",
]

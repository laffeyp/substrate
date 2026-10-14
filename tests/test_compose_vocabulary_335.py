# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 335: session vocabulary v0.16 § AA, composed topologies."""

from __future__ import annotations

import msgspec

from substrate.topologies.compose.vocabulary import (
    INPUT,
    PART_PAYLOAD,
    AgentAs,
    End,
    EndWhen,
    Finding,
    Part,
    Plan,
    Step,
    Strength,
    Test,
    TestOp,
    kind_of,
)
from substrate.topologies.session import ComposedResult, TopologyRunEnded
from substrate.topologies.session.vocabulary import RunOutcome
from substrate.topologies.tool_loop.tools import (
    TOOL_NAME_TOPOLOGY_HELP,
    TOOL_NAME_TOPOLOGY_PLAN,
    TOOL_NAME_TOPOLOGY_RUN,
)


def test_the_closed_sets() -> None:
    assert [p.value for p in Part] == ["model", "agent", "command", "collect", "split"]
    assert [a.value for a in AgentAs] == ["plain", "build", "review"]
    assert [o.value for o in TestOp] == ["is", "is not", "has", "has no"]
    assert [e.value for e in EndWhen] == ["first", "after", "quiet"]
    assert [f.value for f in Finding] == [
        "bad_id",
        "unknown_part",
        "unknown_field",
        "missing_role",
        "never_starts",
        "no_limit",
        "never_ends",
        "ends_early",
        "unread",
    ]
    assert [s.value for s in Strength] == ["certain", "dry_run"]
    assert set(PART_PAYLOAD) == set(Part)
    assert INPUT == "input"
    assert (TOOL_NAME_TOPOLOGY_HELP, TOOL_NAME_TOPOLOGY_PLAN, TOOL_NAME_TOPOLOGY_RUN) == (
        "topology_help",
        "topology_plan",
        "topology_run",
    )


def test_a_step_kind_is_its_id_in_camel_case() -> None:
    assert kind_of("draft") == "Draft"
    assert kind_of("critic_a") == "CriticA"


def test_the_plan_uses_the_wire_names_and_round_trips() -> None:
    plan = Plan(
        name="draft_and_critique",
        steps=[
            Step(id="draft", part=Part.MODEL, role="Write it.", on=[INPUT]),
            Step(
                id="fix",
                part=Part.MODEL,
                role="Fix it.",
                on=["Critic"],
                with_=["Draft"],
                if_=Test(kind="Critic", field="text", op=TestOp.HAS_NO, value="NONE"),
                max=3,
            ),
        ],
        end=[End(when=EndWhen.FIRST, kind="Fix"), End(when=EndWhen.QUIET)],
    )
    wire = msgspec.to_builtins(plan)
    fix = wire["steps"][1]
    assert fix["with"] == ["Draft"] and fix["if"]["op"] == "has no" and fix["as"] == "plain"
    assert "with_" not in fix and "if_" not in fix
    assert msgspec.json.decode(msgspec.json.encode(plan), type=Plan) == plan
    assert Plan(name="p", steps=[]).end == [End(when=EndWhen.QUIET)]
    assert Plan(name="p", steps=[]).max_minutes == 30


def test_a_composed_end_reaches_the_caller() -> None:
    ended = TopologyRunEnded(
        run_id="r_1",
        topology="draft_and_critique",
        outcome=RunOutcome.DONE,
        report_seq=None,
        report=None,
        result=ComposedResult(
            ended_on="Fix", event={"text": "ok"}, counts={"draft": 1, "fix": 1}, record_root="/r"
        ),
    )
    assert msgspec.json.decode(msgspec.json.encode(ended), type=TopologyRunEnded) == ended
    # A § Z run's end, written before v0.16, still decodes: `result` is optional.
    old = msgspec.json.encode(
        {"run_id": "r", "topology": "build", "outcome": "done", "report_seq": None, "report": None}
    )
    assert msgspec.json.decode(old, type=TopologyRunEnded).result is None

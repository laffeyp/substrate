# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 336: parts and plans (research create-topology § 3, § 4, § 6)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import msgspec

from substrate import api
from substrate.topologies.compose.parts import AgentCall, Deps
from substrate.topologies.compose.plan import lines, read
from substrate.topologies.compose.vocabulary import COLLECT_ALL, FAN_OUT_MAX, AgentAs, Part
from substrate.topologies.compose.wire import topology

DRAFT_AND_CRITIQUE = """draft: model "Write the function the user asks for."
critic: model on Draft, Fix "List the defects, or say NONE." max 4
fix: model on Critic with Draft if Critic.text has no NONE max 3 "Fix the listed defects."
end: first Fix or quiet"""


class Heard:
    """A stand-in model that records what it was asked and answers in order."""

    def __init__(self, answers: list[str]) -> None:
        self.answers = answers
        self.prompts: list[str] = []

    def respond(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return (
            self.answers[len(self.prompts) - 1] if len(self.prompts) <= len(self.answers) else "x"
        )


def _deps(model: Heard, tmp: Path, agent: Any = None) -> Deps:
    return Deps(
        responder=lambda _step: model,
        start_agent=agent or (lambda _call: {}),
        workdir=tmp,
    )


def _events(root: Path) -> list[tuple[str, dict[str, Any]]]:
    return [
        (e["kind"], e["payload"])
        for e in api.read_record(root)
        if not str(e["kind"]).startswith("substrate.")
    ]


def _run(plan: Any, deps: Deps, tmp: Path, run_input: str = "") -> tuple[Any, Path]:
    root = tmp / "c.record"
    result = asyncio.run(api.Runtime(root).run(topology(plan, deps, run_input), name="t"))
    return result, root


def test_json_and_lines_are_one_plan_and_every_default_shows(tmp_path: Path) -> None:
    from_lines, found = read(DRAFT_AND_CRITIQUE)
    assert found == [] and from_lines is not None
    from_json, found = read(json.dumps(msgspec.to_builtins(from_lines)))
    assert found == [] and from_json == from_lines
    assert lines(from_lines) == [
        "name: plan",
        'draft: model on input max 1 "Write the function the user asks for."',
        'critic: model on Draft, Fix max 4 "List the defects, or say NONE."',
        'fix: model on Critic with Draft if Critic.text has no "NONE" max 3 "Fix the listed defects."',
        "end: first Fix or quiet",
        "max_minutes: 30",
    ]
    assert read("\n".join(lines(from_lines)))[0] == from_lines
    builders = []
    for plan in (from_lines, from_json):
        b = api.TopologyBuilder()
        topology(plan, _deps(Heard([]), tmp_path))(b)
        reg = b.build()
        builders.append(
            (sorted(reg.producer_kinds), [t.id for t in reg.triggers], sorted(reg.views))
        )
    assert builders[0] == builders[1]
    assert builders[0][1] == ["critic-on-Draft", "critic-on-Fix", "fix-on-Critic"]


def test_a_model_step_reads_its_role_and_its_input_laid_out(tmp_path: Path) -> None:
    plan, _ = read(DRAFT_AND_CRITIQUE)
    model = Heard(
        [
            "def add(a, b): return a - b",
            "subtracts instead of adding",
            "def add(a, b): return a + b",
        ]
    )
    result, root = _run(plan, _deps(model, tmp_path), tmp_path, "add two numbers")
    assert result.status == "finalised"
    assert [k for k, _ in _events(root)] == ["Draft", "Critic", "Fix"]
    # The stand-in has no system channel, so the role leads the prompt.
    assert model.prompts[0] == "Write the function the user asks for.\n\nadd two numbers"
    assert model.prompts[2] == (
        "Fix the listed defects.\n\nsubtracts instead of adding"
        "\n\nDraft:\ndef add(a, b): return a - b"
    )
    baseline = next(e for e in api.read_record(root) if e["kind"] == "substrate.RunStarted")
    assert baseline["payload"]["baseline"]["plan"] == msgspec.to_builtins(plan)
    assert baseline["payload"]["baseline"]["input"] == "add two numbers"


def test_an_if_that_fails_stops_the_loop_and_quiet_ends_it(tmp_path: Path) -> None:
    plan, _ = read(DRAFT_AND_CRITIQUE)
    result, root = _run(plan, _deps(Heard(["v1", "NONE"]), tmp_path), tmp_path, "x")
    assert result.status == "finalised"
    assert [k for k, _ in _events(root)] == ["Draft", "Critic"]


def test_placeholders_lay_out_the_input(tmp_path: Path) -> None:
    plan, found = read(
        'ask: model input "Q: {input}" "Answer."\n'
        'check: model input "{Ask} / {Ask.text} / {input}" "Check."'
    )
    assert found == []
    model = Heard(["42", "ok"])
    _run(plan, _deps(model, tmp_path), tmp_path, "six times seven")
    assert model.prompts == ["Answer.\n\nQ: six times seven", "Check.\n\n42 / 42 / six times seven"]


def test_command_collect_and_split(tmp_path: Path) -> None:
    plan, found = read(
        """items: split
shout: command "tr a-z A-Z"
all: collect
count: command "wc -l"
"""
    )
    assert found == [] and plan is not None
    by_id = {s.id: s for s in plan.steps}
    assert by_id["shout"].max == FAN_OUT_MAX and by_id["all"].n == COLLECT_ALL
    assert lines(plan)[2:4] == [
        'shout: command on Items max 50 "tr a-z A-Z"',
        "all: collect on Shout max 1 n all",
    ]
    assert read("\n".join(lines(plan)))[0] == plan
    result, root = _run(plan, _deps(Heard([]), tmp_path), tmp_path, "one\ntwo\nthree")
    assert result.status == "finalised"
    events = _events(root)
    assert [p["item"] for k, p in events if k == "Items"] == ["one", "two", "three"]
    assert sorted(p["output"] for k, p in events if k == "Shout") == ["ONE", "THREE", "TWO"]
    gathered = [p for k, p in events if k == "All"]
    assert len(gathered) == 1 and sorted(i["output"] for i in gathered[0]["items"]) == [
        "ONE",
        "THREE",
        "TWO",
    ]
    counted = [p for k, p in events if k == "Count"]
    assert counted[0]["ok"] is True and counted[0]["exit"] == 0


def test_a_failing_command_says_so(tmp_path: Path) -> None:
    plan, _ = read('run: command "echo nope >&2; exit 3"')
    _, root = _run(plan, _deps(Heard([]), tmp_path), tmp_path)
    ((kind, payload),) = _events(root)
    assert kind == "Run" and payload == {"ok": False, "exit": 3, "output": "nope\n"}


def test_an_agent_step_reports_through_its_starter(tmp_path: Path) -> None:
    calls: list[AgentCall] = []

    def start(call: AgentCall) -> Mapping[str, Any]:
        calls.append(call)
        return {
            "run_id": "r_1",
            "outcome": "done",
            "reply": "added b.txt",
            "files": ["b.txt"],
            "branch": "build/r_1",
            "commits": ["abc1234"],
        }

    plan, found = read('make: agent as build "Make the change." model qwen3')
    assert found == [] and plan is not None and plan.steps[0].part is Part.AGENT
    _, root = _run(plan, _deps(Heard([]), tmp_path, start), tmp_path, "add b.txt")
    assert calls == [
        AgentCall(
            step="make", as_=AgentAs.BUILD, role="Make the change.", text="add b.txt", model="qwen3"
        )
    ]
    ((kind, payload),) = _events(root)
    assert kind == "Make" and payload["branch"] == "build/r_1" and payload["outcome"] == "done"


def test_a_repeated_with_or_on_adds_to_the_list() -> None:
    """U189's live run: a model wrote `with Draft with Critic`, and the reader kept only Critic."""
    plan, found = read('d: model "x"\nc: model "y"\nr: model on C on D with D with C "z"')
    assert found == [] and plan is not None
    assert plan.steps[2].on == ["C", "D"] and plan.steps[2].with_ == ["D", "C"]

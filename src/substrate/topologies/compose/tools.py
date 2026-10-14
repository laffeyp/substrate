# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The create-topology tools (session vocabulary § AA.6; kernel sprint K338).

`topology_help` teaches the plan language; `topology_plan` checks a plan and says what to fix;
`topology_run` starts a checked plan as a run its caller holds. The calling model names parts and
how they connect; the tools do the wiring, the checking and the running.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable, Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any, Final

import msgspec

from ..tool_loop.tools import (
    TOOL_NAME_TOPOLOGY_HELP,
    TOOL_NAME_TOPOLOGY_PLAN,
    TOOL_NAME_TOPOLOGY_RUN,
    Tool,
)
from .check import DRY_RUN_INPUT, Checked, check
from .plan import PART_FIELDS, lines, read
from .vocabulary import PART_PAYLOAD, Part, Plan

SAVED_DIR: Final[str] = ".substrate/topologies"

# ── plans by id and by name ──────────────────────────────────────────────────────────────────

_PLANS: dict[str, Plan] = {}
_LOCK = threading.Lock()


def remember(plan: Plan) -> str:
    """A plan's id: the same plan always has the same id."""
    data = msgspec.json.encode(plan)
    plan_id = "p_" + hashlib.sha256(data).hexdigest()[:10]
    with _LOCK:
        _PLANS[plan_id] = plan
    return plan_id


def recall(plan_id: str) -> Plan | None:
    with _LOCK:
        return _PLANS.get(plan_id)


def shipped() -> dict[str, str]:
    """The plans Substrate ships, by name, as lines."""
    out: dict[str, str] = {}
    for f in sorted(files("substrate.topologies.compose").joinpath("plans").iterdir(), key=str):
        if f.name.endswith(".plan"):
            out[f.name.removesuffix(".plan")] = f.read_text(encoding="utf-8")
    return out


def saved(workspace: Path) -> dict[str, str]:
    """The plans saved in the workspace, by name, as lines."""
    out: dict[str, str] = {}
    folder = workspace / SAVED_DIR
    if folder.is_dir():
        for f in sorted(folder.glob("*.json")):
            plan, _ = read(f.read_text(encoding="utf-8"))
            if plan is not None:
                out[f.stem] = "\n".join(lines(plan))
    return out


def named(workspace: Path, name: str) -> str | None:
    """A named plan's lines; a saved plan wins over a shipped one of the same name."""
    return saved(workspace).get(name) or shipped().get(name)


def _merge(base: str, change: str) -> str:
    """`change`'s lines over `base`'s: a step with the same id replaces it, a new id is added, and
    `name`, `end` and `max_minutes` lines replace theirs."""
    keyed: dict[str, str] = {}
    for text in (base, change):
        for raw in text.splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                keyed[line.partition(":")[0].strip()] = line
    return "\n".join(keyed.values())


# ── help ─────────────────────────────────────────────────────────────────────────────────────

PART_HELP: Final[dict[Part, str]] = {
    Part.MODEL: "one call to a model: its role, then its input",
    Part.AGENT: (
        "one session turn with tools in a worktree; `as build` works on a new branch, `as review` "
        "reviews what its input names (a branch, a range or files)"
    ),
    Part.COMMAND: "one shell command in the workspace; its input is the command's stdin",
    Part.COLLECT: "waits for `n` events of the kinds in `on` (`n all`: one per item of a split)",
    Part.SPLIT: "one event per line of its input, or per item of a collect",
}

FIELD_HELP: Final[tuple[tuple[str, str], ...]] = (
    (
        "on K1, K2",
        "the kinds that start the step; `input` is the run's input. Default: the step before it",
    ),
    ("with K", "adds the latest K to the step's input, under K's name"),
    ('input "…"', "lays out the input: {input}, {K} (K's main text), {K.field}"),
    ("if K.field is|is not|has|has no V", "the step runs only when the test holds"),
    ("max N", "how many times it may run. Default 1; a step on a loop needs more"),
    ("model NAME", "the model for a model or agent step. Default: the caller's"),
    ("n N | n all", "a collect's count"),
    ('"…"', "the quoted text: a model or agent step's role, a command step's command"),
)


def help_text(workspace: Path, topic: str = "") -> str:
    """The plan language, generated from the part table, and the plans there are."""
    topic = topic.strip()
    plans = {**shipped(), **saved(workspace)}
    if topic in plans:
        return f"The plan `{topic}`:\n{plans[topic].strip()}"
    if topic and topic in {p.value for p in Part}:
        part = Part(topic)
        fields = ", ".join(sorted(PART_FIELDS[part] - {"id", "part"}))
        event = ", ".join(name for name, _ in PART_PAYLOAD[part])
        return f"{part.value}: {PART_HELP[part]}.\nFields: {fields}.\nIts event: {event}."
    out = [
        "A plan is steps and an end, one line each. Each step names a part; its id names the kind of",
        "event it writes, in CamelCase (`critic_a` writes CriticA). With nothing else, each step",
        "starts when the one before it writes, and the run ends when nothing is left to run.",
        "",
        '  draft: model "Write what the input asks for."',
        '  critic: model "List the defects, or say NONE."',
        "  end: first Critic",
        "",
        "Parts:",
        *(
            f"  {p.value}: {PART_HELP[p]}. Writes {', '.join(n for n, _ in PART_PAYLOAD[p])}."
            for p in Part
        ),
        "Fields:",
        *(f"  {k}: {v}" for k, v in FIELD_HELP),
        "Ends: `first K`, `after N K`, `quiet` (nothing left to run), joined by `or`.",
        "Also `name: …` and `max_minutes: N` (default 30).",
        "",
        "Plans: " + ", ".join(sorted(plans)) + ". topology_help(topic=<plan>) shows one;",
        "topology_plan(from=<plan>, lines=…) changes it. Then topology_run(plan_id=…, input=…).",
    ]
    return "\n".join(out)


# ── the tools ────────────────────────────────────────────────────────────────────────────────

StartPlan = Callable[[Plan, str], str]  # (plan, input) -> run id


def plan_result(checked: Checked) -> dict[str, Any]:
    """What `topology_plan` returns: the plan, its wiring, the dry run, the findings, the next."""
    if checked.plan is None:
        return {
            "findings": [f.line() for f in checked.findings],
            "next": "fix the steps named and call topology_plan again",
        }
    plan_id = remember(checked.plan)
    out: dict[str, Any] = {
        "plan_id": plan_id,
        "lines": checked.lines,
        "wiring": checked.wiring,
        "dry_run": checked.dry_run,
        "findings": [f.line() for f in checked.findings],
    }
    if not checked.findings:
        out["next"] = (
            f"topology_run(plan_id={plan_id!r}, input=…) runs it; add save=<name> to keep it. The "
            "dry run used stand-in answers: it shows the wiring and the end, not what a model writes."
        )
    elif checked.fixed is not None and checked.fixed.plan is not None:
        fixed_id = remember(checked.fixed.plan)
        out["fixed_plan_id"] = fixed_id
        out["fixed_lines"] = checked.fixed.lines
        out["next"] = (
            f"topology_run(plan_id={fixed_id!r}, input=…) runs the fixed plan, which has no "
            "findings; or change the lines and call topology_plan again."
        )
    else:
        out["next"] = (
            "change the lines each finding names and call topology_plan again; weigh the "
            "dry-run findings, which rest on stand-in answers."
        )
    return out


_PLAN_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "string",
            "description": "the plan as lines, one per step, then `end: …`",
        },
        "plan": {"type": "object", "description": "the plan as JSON, instead of lines"},
        "from": {"type": "string", "description": "start from a named plan; `lines` change it"},
        "input": {"type": "string", "description": "an input for the dry run"},
    },
    "x-args-passthrough": True,
}

_RUN_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "plan_id": {"type": "string", "description": "a plan topology_plan returned"},
        "name": {"type": "string", "description": "a named plan, instead of plan_id"},
        "input": {"type": "string", "description": "the run's input"},
        "save": {"type": "string", "description": "keep the plan in the workspace under this name"},
    },
    "x-args-passthrough": True,
}

_HELP_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "description": "a part or a plan name; empty for everything"},
    },
    "x-args-passthrough": True,
}


def _args(args: list[Any], bare: str) -> dict[str, Any]:
    if args and isinstance(args[0], Mapping):
        return dict(args[0])
    return {bare: str(args[0])} if args else {}


def make_topology_tools(workspace: Path, start: StartPlan) -> dict[str, Tool]:
    """The three tools for one session. `start(plan, input)` starts a run the session holds."""

    def _plan(args: list[Any]) -> dict[str, Any]:
        a = _args(args, "lines")
        source: Any = a.get("plan") or a.get("lines") or ""
        base = str(a.get("from") or "").strip()
        if base:
            text = named(workspace, base)
            if text is None:
                names = ", ".join(sorted({**shipped(), **saved(workspace)}))
                raise ValueError(f"topology_plan: no plan named {base!r}; there are {names}")
            if not isinstance(source, str):  # a JSON change, as lines to lay over the plan's
                changed, _ = read(source)
                source = "\n".join(lines(changed)) if changed is not None else ""
            source = _merge(text, source)
        if isinstance(source, str) and not source.strip():
            raise ValueError(
                "topology_plan: send `lines` (one step per line), `plan` (JSON) or `from` (a "
                "named plan); topology_help() shows the language"
            )
        return plan_result(check(source, str(a.get("input") or DRY_RUN_INPUT)))

    def _run(args: list[Any]) -> dict[str, Any]:
        a = _args(args, "plan_id")
        plan_id, name = str(a.get("plan_id") or "").strip(), str(a.get("name") or "").strip()
        plan: Plan | None = None
        if plan_id:
            plan = recall(plan_id)
            if plan is None:
                raise ValueError(
                    f"topology_run: no plan {plan_id!r} in this app; check one with topology_plan "
                    "first, or give a plan's name"
                )
        elif name:
            text = named(workspace, name)
            plan = read(text)[0] if text is not None else None
            if plan is None:
                names = ", ".join(sorted({**shipped(), **saved(workspace)}))
                raise ValueError(f"topology_run: no plan named {name!r}; there are {names}")
        else:
            raise ValueError("topology_run: give plan_id (from topology_plan) or name")
        keep = str(a.get("save") or "").strip()
        if keep:
            plan = msgspec.structs.replace(plan, name=keep)
            folder = workspace / SAVED_DIR
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{keep}.json").write_text(
                json.dumps(msgspec.to_builtins(plan), indent=2) + "\n", encoding="utf-8"
            )
        run_id = start(plan, str(a.get("input") or ""))
        return {
            "run_id": run_id,
            "topology": plan.name,
            "next": (
                "it returns now; its end comes to you once, when it finishes. "
                f"run(run_id={run_id!r}, action='events') shows its progress; "
                f"run(run_id={run_id!r}, action='stop') stops it."
            ),
        }

    def _help(args: list[Any]) -> dict[str, Any]:
        return {"help": help_text(workspace, str(_args(args, "topic").get("topic") or ""))}

    return {
        TOOL_NAME_TOPOLOGY_HELP: Tool(
            name=TOOL_NAME_TOPOLOGY_HELP,
            describe=(
                "topology_help(topic?): the plan language for making a topology from standard "
                "parts (model, agent, command, collect, split), and the plans there are. A topic "
                "is a part or a plan."
            ),
            deterministic=True,
            run=_help,
            schema=_HELP_SCHEMA,
        ),
        TOOL_NAME_TOPOLOGY_PLAN: Tool(
            name=TOOL_NAME_TOPOLOGY_PLAN,
            describe=(
                "topology_plan(lines | plan | from, input?): check a topology made of standard "
                'parts before it runs. One line per step, `id: part on Kind "role"`, then '
                '`end: first Kind`; e.g. `draft: model "Write it."` and `critic: model "List '
                'the defects."`. Returns the plan with every default filled, its wiring, a run on '
                "stand-in answers, findings with fixes, and the plan_id topology_run takes."
            ),
            deterministic=False,
            run=_plan,
            schema=_PLAN_SCHEMA,
        ),
        TOOL_NAME_TOPOLOGY_RUN: Tool(
            name=TOOL_NAME_TOPOLOGY_RUN,
            describe=(
                "topology_run(plan_id | name, input?, save?): start a checked plan, or a named "
                "one, as a run this session holds. It returns at once; the run's end comes back "
                "to you when it finishes. `save` keeps the plan in the workspace by name."
            ),
            deterministic=False,
            run=_run,
            schema=_RUN_SCHEMA,
        ),
    }


__all__ = [
    "SAVED_DIR",
    "StartPlan",
    "help_text",
    "make_topology_tools",
    "named",
    "plan_result",
    "recall",
    "remember",
    "saved",
    "shipped",
]

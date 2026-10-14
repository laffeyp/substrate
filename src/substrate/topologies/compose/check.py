# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The plan's checks (session vocabulary § AA.5; kernel sprint K337).

`check(plan)` reads the plan's wiring, builds it through the kernel, and runs it on stand-in
answers: once as written, and once more with every `if` failing when the plan has one. It returns
the plan as lines, the wiring, the dry run, the findings with their fixes, and — when every
finding has a certain fix — the fixed plan, checked again.
"""

from __future__ import annotations

import asyncio
import difflib
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import msgspec
from msgspec import Struct

from ... import api
from .parts import AgentCall, Deps
from .plan import Found, lines, read
from .vocabulary import (
    INPUT,
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
from .wire import PLACEHOLDER, topology

DRY_RUN_SECONDS: Final[float] = 10.0
DRY_RUN_INPUT: Final[str] = "item one\nitem two"
LOOP_MAX: Final[int] = 3  # the `max` a fix gives a step on a loop


class Checked(Struct, frozen=True):
    """What the plan tool returns about one plan."""

    plan: Plan | None
    lines: list[str]
    wiring: list[str]
    dry_run: list[str]
    findings: list[Found]
    fixed: Checked | None = None


# ── the wiring ───────────────────────────────────────────────────────────────────────────────


def _reads(step: Step) -> set[str]:
    """The kinds a step reads: what starts it, `with`, its `if`, its placeholders."""
    kinds = {k for k in step.on if k != INPUT} | set(step.with_)
    if step.if_ is not None:
        kinds.add(step.if_.kind)
    kinds |= {m.group(1) for m in PLACEHOLDER.finditer(step.input) if m.group(1) != INPUT}
    return kinds


def _on_loop(plan: Plan) -> set[str]:
    """Steps that can start again from their own events."""
    starts: dict[str, set[str]] = {s.id: set() for s in plan.steps}
    for s in plan.steps:
        for t in plan.steps:
            if kind_of(s.id) in t.on:
                starts[s.id].add(t.id)
    looped: set[str] = set()
    for s in plan.steps:
        seen, todo = set(), list(starts[s.id])
        while todo:
            nxt = todo.pop()
            if nxt == s.id:
                looped.add(s.id)
                break
            if nxt not in seen:
                seen.add(nxt)
                todo += starts[nxt]
    return looped


def _near(kind: str, written: list[str]) -> str:
    hits = difflib.get_close_matches(kind, written, n=2, cutoff=0.4)
    return ", ".join(hits or written) or "none yet"


def wiring(plan: Plan) -> list[str]:
    """One line per kind: what writes it, what it starts, what reads it."""
    out = []
    for kind in [INPUT, *(kind_of(s.id) for s in plan.steps)]:
        writer = (
            "the run's input"
            if kind == INPUT
            else next(s.id for s in plan.steps if kind_of(s.id) == kind)
        )
        starts = [s.id for s in plan.steps if kind in s.on]
        reads = [s.id for s in plan.steps if kind != INPUT and kind in _reads(s) - set(s.on)]
        ends = [e for e in plan.end if e.kind == kind]
        parts = [f"{kind} ← {writer}"]
        parts.append(f"starts {', '.join(starts)}" if starts else "starts nothing")
        if reads:
            parts.append(f"read by {', '.join(reads)}")
        if ends:
            parts.append("ends the run")
        out.append("; ".join(parts))
    return out


def static_findings(plan: Plan) -> list[Found]:
    """What follows from the plan's wiring alone."""
    written = [kind_of(s.id) for s in plan.steps]
    found: list[Found] = []
    for s in plan.steps:
        if s.part in (Part.MODEL, Part.AGENT) and not s.role.strip():
            found.append(
                Found(
                    Finding.MISSING_ROLE,
                    s.id,
                    f"a {s.part.value} step needs the text its model reads first.",
                    f'add a role, e.g. `{s.id}: {s.part.value} "Do the task in one reply."`',
                )
            )
        if s.part is Part.COMMAND and not s.command.strip():
            found.append(
                Found(
                    Finding.MISSING_ROLE,
                    s.id,
                    "a command step has no command.",
                    f'give it one, e.g. `{s.id}: command "pytest -q"`',
                )
            )
        waits = [k for k in s.on if k != INPUT]
        if waits and INPUT not in s.on and not any(k in written for k in waits):
            found.append(
                Found(
                    Finding.NEVER_STARTS,
                    s.id,
                    f"it waits on {', '.join(waits)}, which no step writes.",
                    f"wait on a kind a step writes: {_near(waits[0], written)}",
                )
            )
        for k in sorted(_reads(s) - set(waits)):
            if k not in written:
                found.append(
                    Found(
                        Finding.UNKNOWN_FIELD,
                        s.id,
                        f"it reads {k}, which no step writes.",
                        f"read a kind a step writes: {_near(k, written)}",
                    )
                )
    for sid in sorted(_on_loop(plan)):
        step = next(s for s in plan.steps if s.id == sid)
        if step.max == 1:
            found.append(
                Found(
                    Finding.NO_LIMIT,
                    sid,
                    "it is on a loop, so it can start again from its own events, but `max` is 1.",
                    f"say how many times it may run: `max {LOOP_MAX}`",
                )
            )
    for e in plan.end:
        if e.when is not EndWhen.QUIET and e.kind not in written:
            found.append(
                Found(
                    Finding.NEVER_ENDS,
                    "",
                    f"the end waits on {e.kind}, which no step writes.",
                    f"end on a kind a step writes: {_near(e.kind, written)}",
                )
            )
    if any(e.when is not EndWhen.QUIET for e in plan.end):
        named = {e.kind for e in plan.end}
        read_any = set().union(*(_reads(s) for s in plan.steps))
        for kind in written:
            if kind not in named and kind not in read_any:
                found.append(
                    Found(
                        Finding.UNREAD,
                        next(s.id for s in plan.steps if kind_of(s.id) == kind),
                        f"no step reads {kind} and the end does not name it.",
                        f"read it with `with {kind}`, end on it, or leave it",
                    )
                )
    try:
        b = api.TopologyBuilder()
        topology(plan, _stand_ins(plan, failing=False), "")(b)
        b.build()
    except Exception as exc:  # noqa: BLE001 — the kernel's refusal is the finding, said as it is
        found.append(
            Found(
                Finding.NEVER_STARTS,
                "",
                f"the kernel refused the wiring: {exc}",
                "fix the step it names",
            )
        )
    return found


# ── the dry run ──────────────────────────────────────────────────────────────────────────────


def _answer(test: Test, failing: bool) -> str:
    """A stand-in text that passes `test`, or fails it."""
    if test.op is TestOp.IS:
        return f"not {test.value}" if failing else test.value
    if test.op is TestOp.IS_NOT:
        return test.value if failing else f"not {test.value}"
    if test.op is TestOp.HAS:
        return "nothing to say" if failing else f"stand-in: {test.value}"
    return f"stand-in: {test.value}" if failing else "nothing to say"


class _StandIn:
    """A model step's stand-in: `<step> answer <n>`, or a text that passes or fails the `if`
    tests that read this step's kind."""

    def __init__(self, step: Step, tests: list[Test], failing: bool) -> None:
        self.step, self.tests, self.failing, self.n = step, tests, failing, 0

    def respond(self, prompt: str) -> str:
        self.n += 1
        text = next(
            (_answer(t, self.failing) for t in self.tests if t.field == "text"),
            f"{self.step.id} answer {self.n}",
        )
        return text


def _stand_ins(plan: Plan, failing: bool) -> Deps:
    tests: dict[str, list[Test]] = {}
    for s in plan.steps:
        if s.if_ is not None:
            tests.setdefault(s.if_.kind, []).append(s.if_)
    models = {
        s.id: _StandIn(s, tests.get(kind_of(s.id), []), failing)
        for s in plan.steps
        if s.part is Part.MODEL
    }

    def responder(step: Step) -> Any:
        return models[step.id]

    def agent(call: AgentCall) -> Mapping[str, Any]:
        step_tests = tests.get(kind_of(call.step), [])
        reply = next((_answer(t, failing) for t in step_tests if t.field == "reply"), "done")
        return {
            "run_id": f"dry_{call.step}",
            "outcome": "done",
            "reply": reply,
            "files": [],
            "branch": None,
            "commits": [],
        }

    return Deps(responder=responder, start_agent=agent, workdir=Path(tempfile.gettempdir()))


def _command_stand_ins(plan: Plan, failing: bool) -> Plan:
    """Commands do not run in a dry run: each becomes `exit 0`, or `exit 1` where an `if` reads
    its `ok` and the pass is the failing one."""
    tested = {s.if_.kind for s in plan.steps if s.if_ is not None and s.if_.field in ("ok", "exit")}
    steps = []
    for s in plan.steps:
        if s.part is Part.COMMAND:
            code = 1 if failing and kind_of(s.id) in tested else 0
            s = msgspec.structs.replace(s, command=f"echo '{s.id} output'; exit {code}")
        steps.append(s)
    return msgspec.structs.replace(plan, steps=steps)


def _say(kind: str, payload: Mapping[str, Any]) -> str:
    for name in ("text", "reply", "output", "item"):
        value = payload.get(name)
        if isinstance(value, str):
            return f"{kind}: {value.strip().splitlines()[0][:60] if value.strip() else '(empty)'}"
    if "items" in payload:
        return f"{kind}: {len(payload['items'])} items"
    return kind


async def _run(plan: Plan, failing: bool, run_input: str) -> tuple[list[str], set[str], str, bool]:
    """One pass: numbered lines, the steps that ran, how it ended, and whether the end held."""
    deps = _stand_ins(plan, failing)
    runnable = _command_stand_ins(plan, failing)
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "dry.record"
        runtime = api.Runtime(root)
        try:
            result = await asyncio.wait_for(
                runtime.run(topology(runnable, deps, run_input), name="dry"), DRY_RUN_SECONDS
            )
        except TimeoutError:
            return [], set(), f"did not end in {DRY_RUN_SECONDS:.0f} s", False
        by_kind = {kind_of(s.id): s.id for s in plan.steps}
        out: list[str] = []
        ran: set[str] = set()
        counts: dict[str, int] = {}
        for e in api.read_record(root):
            kind = str(e["kind"])
            if kind in by_kind:
                ran.add(by_kind[kind])
                counts[kind] = counts.get(kind, 0) + 1
                out.append(f"{len(out) + 1} {by_kind[kind]} → {_say(kind, e['payload'] or {})}")
        if result.status is api.RunStatus.FINALISED:
            return out, ran, f"ended: {_ended(plan, counts)}", True
        return out, ran, "went idle with its end unmet", False


def _ended(plan: Plan, counts: Mapping[str, int]) -> str:
    """Which end held, read from what the run wrote: the kernel names only the whole policy."""
    for e in plan.end:
        if e.when is EndWhen.FIRST and counts.get(e.kind, 0) >= 1:
            return f"first {e.kind}"
        if e.when is EndWhen.AFTER and counts.get(e.kind, 0) >= e.count:
            return f"after {e.count} {e.kind}"
    return f"quiet, after {sum(counts.values())} events"


def _passes_through_if(plan: Plan) -> bool:
    return any(s.if_ is not None for s in plan.steps)


def dry_run(plan: Plan, run_input: str = DRY_RUN_INPUT) -> tuple[list[str], list[Found]]:
    """The run on stand-in answers, as lines, and what it shows."""
    passes_ = [False, True] if _passes_through_if(plan) else [False]
    text: list[str] = []
    found: list[Found] = []
    ran_any: set[str] = set()
    for failing in passes_:
        out, ran, how, held = asyncio.run(_run(plan, failing, run_input))
        ran_any |= ran
        title = "with every `if` failing" if failing else "as written"
        text.append(f"— {title}" if len(passes_) > 1 else "— as written")
        text += out
        text.append(how)
        if not held:
            found.append(
                Found(
                    Finding.NEVER_ENDS,
                    "",
                    f"{title}, the run {how}.",
                    "add `or quiet` to the end, or end on a kind written on this path",
                    Strength.DRY_RUN,
                )
            )
    for s in plan.steps:
        if s.id not in ran_any:
            waits = ", ".join(k for k in s.on)
            found.append(
                Found(
                    Finding.ENDS_EARLY,
                    s.id,
                    f"it never ran: the run ended before {waits} came.",
                    "end later (`after n Kind`) or on a kind written after it",
                    Strength.DRY_RUN,
                )
            )
    return text, found


# ── the whole check ──────────────────────────────────────────────────────────────────────────

_CERTAIN_FIXES: Final[frozenset[Finding]] = frozenset(
    {Finding.NO_LIMIT, Finding.NEVER_ENDS, Finding.UNKNOWN_FIELD, Finding.UNREAD}
)


def _fix(plan: Plan, found: list[Found]) -> Plan | None:
    """The plan with every finding's certain fix made; None when a finding has none."""
    codes = {f.code for f in found}
    if not codes or not codes <= _CERTAIN_FIXES or codes <= {Finding.UNREAD}:
        return None
    if any(f.code is Finding.NEVER_ENDS and f.strength is Strength.CERTAIN for f in found):
        return None  # an end on a kind nobody writes: which kind is the caller's to say
    if any(f.code is Finding.UNKNOWN_FIELD and "no step writes" in f.problem for f in found):
        return None
    looped = {f.step for f in found if f.code is Finding.NO_LIMIT}
    steps = [msgspec.structs.replace(s, max=LOOP_MAX) if s.id in looped else s for s in plan.steps]
    end = list(plan.end)
    if Finding.NEVER_ENDS in codes and not any(e.when is EndWhen.QUIET for e in end):
        end.append(End(when=EndWhen.QUIET))
    return msgspec.structs.replace(plan, steps=steps, end=end)


def check(source: str | Mapping[str, Any] | Plan, run_input: str = DRY_RUN_INPUT) -> Checked:
    """Read, wire, build and dry-run a plan; fix it where every fix is certain."""
    plan: Plan | None
    found: list[Found]
    if isinstance(source, Plan):
        plan, found = source, []
    else:
        plan, found = read(source)
    if plan is None:
        return Checked(plan=None, lines=[], wiring=[], dry_run=[], findings=found)
    found = found + static_findings(plan)
    blocked = any(f.code in (Finding.NEVER_STARTS, Finding.MISSING_ROLE) for f in found)
    run_lines: list[str] = []
    if not any(f.code is Finding.NEVER_STARTS and not f.step for f in found):
        run_lines, run_found = dry_run(plan, run_input)
        if not blocked:
            found += run_found
    fixed_plan = _fix(plan, found)
    fixed = check(fixed_plan, run_input) if fixed_plan is not None else None
    if fixed is not None and any(f.code is not Finding.UNREAD for f in fixed.findings):
        fixed = None
    return Checked(
        plan=plan,
        lines=lines(plan),
        wiring=wiring(plan),
        dry_run=run_lines,
        findings=found,
        fixed=fixed,
    )


__all__ = [
    "DRY_RUN_INPUT",
    "DRY_RUN_SECONDS",
    "LOOP_MAX",
    "Checked",
    "check",
    "dry_run",
    "static_findings",
    "wiring",
]

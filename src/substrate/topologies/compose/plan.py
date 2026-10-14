# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Reading and writing a plan (session vocabulary § AA.1; kernel sprint K336).

A plan arrives as JSON or as lines, one per step, and is written back as lines with every default
filled in, so the model reads what will run and can copy a line back with one thing changed. A
plan that cannot be read comes back as findings, each naming its step and its fix.
"""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Mapping
from typing import Any, Final

import msgspec
from msgspec import Struct

from ...constants import LIFECYCLE_KINDS
from ..session.vocabulary import SESSION_KINDS
from .vocabulary import (
    COLLECT_ALL,
    DEFAULT_COLLECT_N,
    FAN_OUT_MAX,
    INPUT,
    RUN_STOP_REQUESTED,
    STEP_ID,
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


class Found(Struct, frozen=True):
    """One finding (§ AA.5): the step, what is wrong, the fix, and how sure it is."""

    code: Finding
    step: str
    problem: str
    fix: str
    strength: Strength = Strength.CERTAIN

    def line(self) -> str:
        where = f"{self.step}: " if self.step else ""
        return f"{self.code.value} · {where}{self.problem} Fix: {self.fix} ({self.strength.value})"


_COMMON: Final[frozenset[str]] = frozenset({"id", "part", "on", "with", "input", "if", "max"})
PART_FIELDS: Final[dict[Part, frozenset[str]]] = {
    Part.MODEL: _COMMON | {"role", "model"},
    Part.AGENT: _COMMON | {"role", "model", "as"},
    Part.COMMAND: _COMMON | {"command"},
    Part.COLLECT: _COMMON | {"n"},
    Part.SPLIT: _COMMON,
}
ALL_FIELDS: Final[frozenset[str]] = frozenset().union(*PART_FIELDS.values())
_PLAN_FIELDS: Final[frozenset[str]] = frozenset({"name", "steps", "end", "max_minutes"})
# Kinds a step may not write: the session's, the kernel's, and the run's input.
RESERVED_KINDS: Final[frozenset[str]] = (
    SESSION_KINDS | frozenset(LIFECYCLE_KINDS) | {kind_of(INPUT), RUN_STOP_REQUESTED}
)
# The defaults of the fields only some parts take; JSON written by `msgspec` carries them.
_UNSET: Final[dict[str, tuple[Any, ...]]] = {
    "role": ("",),
    "model": ("",),
    "as": ("plain", None),
    "command": ("",),
    "n": (2, None),
}
_PARTS_SAID: Final[str] = ", ".join(p.value for p in Part)


def _nearest(word: str, choices: frozenset[str] | list[str]) -> str | None:
    if len(word) < 3:  # a letter or two matches too much to name
        return None
    hit = difflib.get_close_matches(word, sorted(choices), n=1, cutoff=0.5)
    return hit[0] if hit else None


def _names(value: Any) -> list[str]:
    """A list of kind names from a list, or from text split on commas and spaces."""
    if value is None or value == "":
        return []
    items = value if isinstance(value, list) else re.split(r"[,\s]+", str(value))
    return [str(v).strip() for v in items if str(v).strip()]


_TEST: Final[re.Pattern[str]] = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9]*)(?:\.([a-z_][a-z0-9_]*))?\s+(is not|has no|is|has)\s+(.+?)\s*$"
)


def _test(value: Any, step: str, found: list[Found]) -> Test | None:
    if value is None or value == "":
        return None
    if isinstance(value, Mapping):
        try:
            return Test(
                kind=str(value["kind"]),
                field=str(value.get("field") or ""),
                op=TestOp(str(value["op"])),
                value=str(value["value"]),
            )
        except (KeyError, ValueError):
            pass
    else:
        m = _TEST.match(str(value))
        if m:
            raw = m.group(4)
            if len(raw) >= 2 and raw[0] == raw[-1] == '"':
                raw = json.loads(raw)
            return Test(kind=m.group(1), field=m.group(2) or "", op=TestOp(m.group(3)), value=raw)
    found.append(
        Found(
            Finding.UNKNOWN_FIELD,
            step,
            f"`if` reads {value!r}, which is not a test.",
            'write `if Kind is|is not|has|has no value`, e.g. `if Critic has no "NONE"`; '
            "`Kind.field` names another field",
        )
    )
    return None


def _ends(value: Any, found: list[Found]) -> list[End]:
    if value is None or value == "" or value == []:
        return [End(when=EndWhen.QUIET)]
    raw = value if isinstance(value, list) else re.split(r"\s+or\s+", str(value).strip())
    ends: list[End] = []
    for item in raw:
        if isinstance(item, Mapping):
            if "first" in item:
                ends.append(End(when=EndWhen.FIRST, kind=str(item["first"])))
                continue
            if "after" in item:
                ends.append(
                    End(
                        when=EndWhen.AFTER, kind=str(item["after"]), count=int(item.get("count", 1))
                    )
                )
                continue
            if item.get("when") in {w.value for w in EndWhen}:
                ends.append(
                    End(
                        when=EndWhen(item["when"]),
                        kind=str(item.get("kind", "")),
                        count=int(item.get("count", 1)),
                    )
                )
                continue
        else:
            words = str(item).split()
            if words == ["quiet"]:
                ends.append(End(when=EndWhen.QUIET))
                continue
            if len(words) == 2 and words[0] == "first":
                ends.append(End(when=EndWhen.FIRST, kind=words[1]))
                continue
            if len(words) == 3 and words[0] == "after" and words[1].isdigit():
                ends.append(End(when=EndWhen.AFTER, kind=words[2], count=int(words[1])))
                continue
        found.append(
            Found(
                Finding.NEVER_ENDS,
                "",
                f"the end {item!r} is not one the plan knows.",
                "end with `first Kind`, `after n Kind` or `quiet`, joined by `or`",
            )
        )
    return ends or [End(when=EndWhen.QUIET)]


def _int(value: Any, default: int, field: str, step: str, found: list[Found]) -> int:
    if value is None or value == "":
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 0
    if n < 1:
        found.append(
            Found(
                Finding.UNKNOWN_FIELD,
                step,
                f"`{field}` is {value!r}.",
                f"give `{field}` a whole number, 1 or more",
            )
        )
        return default
    return n


def read(source: str | Mapping[str, Any]) -> tuple[Plan | None, list[Found]]:
    """A plan from JSON, from lines, or from a mapping, with every default filled. A plan with a
    step that cannot be built (a bad id, an unknown part) is None; its findings say why."""
    if isinstance(source, str):
        text = source.strip()
        if text.startswith("{"):
            try:
                source = json.loads(text)
            except json.JSONDecodeError as exc:
                return None, [
                    Found(
                        Finding.UNKNOWN_FIELD,
                        "",
                        f"the plan is not JSON ({exc}).",
                        "send JSON or lines",
                    )
                ]
        else:
            source = read_lines(text)
    found: list[Found] = []
    if not isinstance(source, Mapping):
        return None, [
            Found(Finding.UNKNOWN_FIELD, "", "the plan is not an object.", "send JSON or lines")
        ]
    d = dict(source)
    for key in sorted(set(d) - _PLAN_FIELDS):
        near = _nearest(key, _PLAN_FIELDS)
        found.append(
            Found(
                Finding.UNKNOWN_FIELD,
                "",
                f"the plan has a field `{key}`.",
                f"use `{near}`" if near else "a plan has name, steps, end and max_minutes",
            )
        )
    raw_steps = d.get("steps") or []
    if isinstance(raw_steps, Mapping):  # {"draft": {...}} reads as steps keyed by id
        raw_steps = [{"id": k, **dict(v)} for k, v in raw_steps.items()]
    steps: list[Step] = []
    fatal = False
    seen: set[str] = set()
    explicit: dict[str, set[str]] = {}  # the max and n each step gave, against the defaults
    for i, raw in enumerate(raw_steps):
        if isinstance(raw, Mapping):
            r = dict(raw)
        else:  # a step written as a line inside JSON
            text = str(raw)
            r = read_lines(text if ":" in text.split('"')[0] else f"step{i + 1}: {text}")["steps"][
                0
            ]
        sid = str(r.get("id", "")).strip()
        label = sid or f"step {i + 1}"
        if not STEP_ID.match(sid) or sid in seen or sid == INPUT or kind_of(sid) in RESERVED_KINDS:
            why = (
                "has no id"
                if not sid
                else "repeats an id"
                if sid in seen
                else f"writes {kind_of(sid)}, a kind Substrate already uses"
                if sid == INPUT or kind_of(sid) in RESERVED_KINDS
                else "is not a lower-case word"
            )
            found.append(
                Found(
                    Finding.BAD_ID,
                    label,
                    f"the step {why}.",
                    "give it a lower-case word of its own, e.g. `draft`",
                )
            )
            fatal = True
            continue
        seen.add(sid)
        try:  # a step that names no part is a model step
            part = Part(str(r.get("part") or Part.MODEL.value).strip())
        except ValueError:
            near = _nearest(str(r.get("part", "")), frozenset(p.value for p in Part))
            found.append(
                Found(
                    Finding.UNKNOWN_PART,
                    sid,
                    f"the part {r.get('part')!r} is not one of {_PARTS_SAID}.",
                    f"use `{near}`" if near else f"use one of {_PARTS_SAID}",
                )
            )
            fatal = True
            continue
        for key in sorted(set(r) - PART_FIELDS[part]):
            if key == "_unknown" or r[key] in _UNSET.get(key, ()):
                continue  # a field another part takes, at its default: nothing to say
            near = _nearest(key, PART_FIELDS[part])
            found.append(
                Found(
                    Finding.UNKNOWN_FIELD,
                    sid,
                    f"a {part.value} step has no field `{key}`.",
                    f"use `{near}`"
                    if near
                    else f"a {part.value} step takes {', '.join(sorted(PART_FIELDS[part]))}",
                )
            )
        for word in r.get("_unknown", []):
            near = _nearest(word, PART_FIELDS[part])
            found.append(
                Found(
                    Finding.UNKNOWN_FIELD,
                    sid,
                    f"the line has `{word}`, which no {part.value} step takes.",
                    f"use `{near}`" if near else 'quote a role, e.g. "Write the function."',
                )
            )
        takes = PART_FIELDS[part]
        r = {k: v for k, v in r.items() if k in takes}  # what the part does not take is said above
        as_ = AgentAs.PLAIN
        if r.get("as"):
            try:
                as_ = AgentAs(str(r["as"]))
            except ValueError:
                found.append(
                    Found(
                        Finding.UNKNOWN_FIELD,
                        sid,
                        f"`as` is {r['as']!r}.",
                        "use plain, build or review",
                    )
                )
        on = _names(r.get("on"))
        if not on:
            on = [INPUT] if not steps else [kind_of(steps[-1].id)]
        explicit[sid] = {k for k in ("max", "n") if r.get(k) not in (None, "")}
        test = _test(r.get("if"), sid, found)
        if test is None and r.get("if") not in (None, ""):
            fatal = True  # a step run without the test it was given would do what nobody asked
        steps.append(
            Step(
                id=sid,
                part=part,
                role=str(r.get("role", "")),
                on=on,
                with_=_names(r.get("with")),
                input=str(r.get("input", "")),
                if_=test,
                max=_int(r.get("max"), 1, "max", sid, found),
                model=str(r.get("model", "")),
                as_=as_,
                command=str(r.get("command", "")),
                n=COLLECT_ALL
                if str(r.get("n", "")).strip() == "all"
                else _int(r.get("n"), DEFAULT_COLLECT_N, "n", sid, found),
            )
        )
    if not raw_steps:
        found.append(
            Found(
                Finding.NEVER_STARTS,
                "",
                "the plan has no steps.",
                'add a step, e.g. `draft: model "Write it."`',
            )
        )
        fatal = True
    steps = _fan_out_defaults(_test_fields(steps), explicit)
    end = _ends(d.get("end"), found)
    max_minutes = _int(d.get("max_minutes"), 30, "max_minutes", "", found)
    if fatal:
        return None, found
    return Plan(
        name=str(d.get("name") or "plan"), steps=steps, end=end, max_minutes=max_minutes
    ), found


# The field a test with none names reads: its kind's main field, by the part that writes it.
_PART_MAIN: Final[dict[Part, str]] = {
    Part.MODEL: "text",
    Part.AGENT: "reply",
    Part.COMMAND: "output",
    Part.COLLECT: "items",
    Part.SPLIT: "item",
}


def _test_fields(steps: list[Step]) -> list[Step]:
    """`if Critic has no NONE` reads Critic's main field (§ AA.1, v0.16.3)."""
    parts = {kind_of(s.id): s.part for s in steps}
    out = []
    for s in steps:
        if s.if_ is not None and not s.if_.field:
            field = _PART_MAIN.get(parts.get(s.if_.kind, Part.MODEL), "text")
            s = msgspec.structs.replace(s, if_=msgspec.structs.replace(s.if_, field=field))
        out.append(s)
    return out


def _fan_out_defaults(steps: list[Step], explicit: dict[str, set[str]]) -> list[Step]:
    """A step between a split and the collect after it runs once per item (`max` 50); a collect
    after a split waits for every item (`n all`) — unless the step gave its own (§ AA.1)."""
    by_kind = {kind_of(s.id): s for s in steps}
    fanned: set[str] = set()  # steps fed, through steps that are not collects, by a split
    after_split: set[str] = set()  # collects fed that way
    changed = True
    while changed:
        changed = False
        for s in steps:
            for k in s.on:
                up = by_kind.get(k)
                if up is None or not (up.part is Part.SPLIT or up.id in fanned):
                    continue
                if s.part is Part.COLLECT:
                    if s.id not in after_split:
                        after_split.add(s.id)
                        changed = True
                elif s.id not in fanned:
                    fanned.add(s.id)
                    changed = True
    out: list[Step] = []
    for s in steps:
        given = explicit.get(s.id, set())
        if s.id in fanned and "max" not in given:
            s = msgspec.structs.replace(s, max=FAN_OUT_MAX)
        if s.id in after_split and "n" not in given:
            s = msgspec.structs.replace(s, n=COLLECT_ALL)
        out.append(s)
    return out


# ── lines ────────────────────────────────────────────────────────────────────────────────────

_TOKEN: Final[re.Pattern[str]] = re.compile(r'"((?:[^"\\]|\\.)*)"|(\S+)')
_KEYWORDS: Final[frozenset[str]] = frozenset(
    {"as", "on", "with", "if", "max", "n", "model", "command", "input"}
)


def _tokens(text: str) -> list[tuple[str, bool]]:
    out: list[tuple[str, bool]] = []
    for m in _TOKEN.finditer(text):
        if m.group(1) is not None:
            out.append((json.loads('"' + m.group(1) + '"'), True))
        else:
            out.append((m.group(2), False))
    return out


def read_lines(text: str) -> dict[str, Any]:
    """Lines to the plan's mapping: `name:`, one line per step (`id: part …`), `end:`,
    `max_minutes:`. A quoted text with no keyword before it is the step's role."""
    plan: dict[str, Any] = {"steps": []}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, rest = line.partition(":")
        key, rest = key.strip(), rest.strip()
        if key in {"name", "end", "max_minutes"}:
            plan[key] = rest
            continue
        step: dict[str, Any] = {"id": key}
        toks = _tokens(rest)
        if toks and not toks[0][1]:
            step["part"] = toks[0][0]
            toks = toks[1:]
        i = 0
        while i < len(toks):
            word, quoted = toks[i]
            if quoted:  # what the step does: a command step's command, any other step's role
                step["command" if step.get("part") == Part.COMMAND.value else "role"] = word
                i += 1
                continue
            if word not in _KEYWORDS:
                step.setdefault("_unknown", []).append(word)
                i += 1
                continue
            i += 1
            if word in {"on", "with"}:
                names: list[str] = []
                # `input` in the list is the run's input when it comes first or no quoted
                # layout follows it; `on Draft input "…"` lays out the input.
                while (
                    i < len(toks)
                    and not toks[i][1]
                    and (
                        toks[i][0] not in _KEYWORDS
                        or (
                            toks[i][0] == INPUT
                            and (not names or not (i + 1 < len(toks) and toks[i + 1][1]))
                        )
                    )
                ):
                    names += _names(toks[i][0])
                    i += 1
                step[word] = names
            elif word == "if":
                parts: list[str] = []
                while i < len(toks) and len(parts) < 4:
                    tok, q = toks[i]
                    if not q and tok in _KEYWORDS and len(parts) >= 3:
                        break
                    parts.append(json.dumps(tok) if q else tok)
                    i += 1
                    if (
                        len(parts) >= 3
                        and parts[1] in {"is", "has"}
                        and parts[2] not in {"not", "no"}
                    ):
                        break
                step["if"] = " ".join(parts)
            elif i < len(toks):
                step[word] = toks[i][0]
                i += 1
        plan["steps"].append(step)
    return plan


def _q(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def step_line(s: Step) -> str:
    out = [f"{s.id}: {s.part.value}"]
    if s.part is Part.AGENT:
        out.append(f"as {s.as_.value}")
    out.append("on " + ", ".join(s.on))
    if s.with_:
        out.append("with " + ", ".join(s.with_))
    if s.if_ is not None:
        out.append(f"if {s.if_.kind}.{s.if_.field} {s.if_.op.value} {_q(s.if_.value)}")
    out.append(f"max {s.max}")
    if s.part is Part.COLLECT:
        out.append("n all" if s.n == COLLECT_ALL else f"n {s.n}")
    if s.model:
        out.append(f"model {s.model}")
    if s.input:
        out.append(f"input {_q(s.input)}")
    if s.role:
        out.append(_q(s.role))
    if s.command:
        out.append(_q(s.command))
    return " ".join(out)


def end_line(ends: list[End]) -> str:
    def one(e: End) -> str:
        if e.when is EndWhen.FIRST:
            return f"first {e.kind}"
        if e.when is EndWhen.AFTER:
            return f"after {e.count} {e.kind}"
        return "quiet"

    return " or ".join(one(e) for e in ends)


def lines(plan: Plan) -> list[str]:
    """The plan as lines, every default filled in; `read` reads them back as the same plan."""
    return [
        f"name: {plan.name}",
        *(step_line(s) for s in plan.steps),
        f"end: {end_line(plan.end)}",
        f"max_minutes: {plan.max_minutes}",
    ]


__all__ = [
    "ALL_FIELDS",
    "PART_FIELDS",
    "RESERVED_KINDS",
    "Found",
    "end_line",
    "lines",
    "read",
    "read_lines",
    "step_line",
]

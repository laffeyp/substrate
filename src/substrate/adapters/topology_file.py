"""A topology from a TOML file (Sprint 270): process Producers, their initial starts, triggers by kind, and a named
termination recipe, so a program in any language can be run under substrate with no Python of its own.

    [baseline]                      # strings, recorded in RunStarted's manifest
    harness = "w2m"

    [[producer]]
    kind = "session_events"         # the Producer kind
    command = ["../target/release/session_events"]
    schemas = "schemas/session.json"
    deterministic = false

    [[initial]]
    kind = "session_events"
    input = {}                      # optional; the process reads it as one JSON line

    [[trigger]]                     # optional
    id = "judge-on-run"
    on = "EXECUTION_COMPLETED"      # the event kind it subscribes to
    starts = "judge"
    policy = "per_event"            # or "once"; the started Producer's input is the event's payload

    [termination]
    recipe = "all_completed"        # or "quiescence", "finalise_on" (kind), "threshold_count" (kind, n)

Paths (a command's first element when it contains a slash, `schemas`) resolve against the file's directory.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import msgspec

from .. import api
from .process import process_producer, schemas_from_file

__all__ = ["TopologyFileError", "topology_from_file"]


class TopologyFileError(ValueError):
    """The file is not a topology this reader takes; the message names the entry."""


def _need(table: dict[str, Any], key: str, where: str) -> Any:
    if key not in table:
        raise TopologyFileError(f"{where}: missing `{key}`")
    return table[key]


def _termination(spec: dict[str, Any]) -> api.TerminationPolicy:
    recipe = _need(spec, "recipe", "[termination]")
    if recipe == "all_completed":
        return api.all_completed()
    if recipe == "quiescence":
        return api.quiescence()
    if recipe == "finalise_on":
        return api.finalise_on(str(_need(spec, "kind", "[termination] finalise_on")))
    if recipe == "threshold_count":
        n = _need(spec, "n", "[termination] threshold_count")
        if not isinstance(n, int) or n < 1:
            raise TopologyFileError("[termination] threshold_count: `n` must be an integer >= 1")
        return api.threshold_count(str(_need(spec, "kind", "[termination] threshold_count")), n)
    raise TopologyFileError(
        f"[termination]: recipe {recipe!r} is not all_completed, quiescence, finalise_on or threshold_count"
    )


def topology_from_file(path: Path | str) -> Callable[[api.TopologyBuilder], None]:
    """The topology factory the file describes. The file is read and every schema file loaded here, so an error
    shows before a run opens."""
    path = Path(path).resolve()
    base = path.parent
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise TopologyFileError(f"{path}: {exc}") from None
    producers = doc.get("producer", [])
    if not producers:
        raise TopologyFileError(f"{path}: no [[producer]]")
    kinds: dict[str, tuple[list[str], int, dict[str, type[msgspec.Struct]], bool]] = {}
    for i, p in enumerate(producers):
        where = f"[[producer]] {i + 1}"
        kind = str(_need(p, "kind", where))
        command = [str(c) for c in _need(p, "command", f"{where} ({kind})")]
        if not command:
            raise TopologyFileError(f"{where} ({kind}): empty `command`")
        if "/" in command[0] and not Path(command[0]).is_absolute():
            command[0] = str((base / command[0]).resolve())
        version, schemas = schemas_from_file(base / str(_need(p, "schemas", f"{where} ({kind})")))
        if kind in kinds:
            raise TopologyFileError(f"{where}: kind {kind!r} declared twice")
        kinds[kind] = (command, version, schemas, bool(p.get("deterministic", False)))
    initials = doc.get("initial", [])
    if not initials:
        raise TopologyFileError(f"{path}: no [[initial]]")
    for i, s in enumerate(initials):
        if _need(s, "kind", f"[[initial]] {i + 1}") not in kinds:
            raise TopologyFileError(
                f"[[initial]] {i + 1}: kind {s['kind']!r} is not a [[producer]]"
            )
    triggers = doc.get("trigger", [])
    for i, t in enumerate(triggers):
        where = f"[[trigger]] {i + 1}"
        for key in ("id", "on", "starts"):
            _need(t, key, where)
        if t["starts"] not in kinds:
            raise TopologyFileError(f"{where}: starts {t['starts']!r}, which is not a [[producer]]")
        if t.get("policy", "per_event") not in ("per_event", "once"):
            raise TopologyFileError(f"{where}: policy must be per_event or once")
    termination = _termination(_need(doc, "termination", str(path)))
    baseline = {str(k): str(v) for k, v in doc.get("baseline", {}).items()}

    def factory_of(produce: api.Producer) -> Callable[[], api.Producer]:
        return lambda: produce

    def topology(b: api.TopologyBuilder) -> None:
        if baseline:
            b.baseline(**baseline)
        for kind, (command, version, schemas, deterministic) in kinds.items():
            produce = process_producer(command, schemas, cwd=base)
            b.producer_kind(
                kind,
                schemas=list(schemas.values()),
                schema_version=version,
                factory=factory_of(produce),
                deterministic=deterministic,
            )
        for s in initials:
            b.initial(s["kind"], input=s.get("input", {}))
        for t in triggers:
            b.trigger(
                str(t["id"]),
                subscription=api.Subscription(kinds=frozenset({str(t["on"])})),
                predicate=lambda _ctx: True,
                starts=str(t["starts"]),
                input_builder=lambda ctx: msgspec.to_builtins(ctx.event.payload),
                policy=api.Once() if t.get("policy") == "once" else api.PerEvent(),
            )
        b.termination(termination)

    return topology

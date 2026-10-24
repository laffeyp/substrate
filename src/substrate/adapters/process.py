"""A process as a Producer (Sprint 270).

A program in any language writes one event a line to its standard output, `{"kind": K, "payload": {...}}`; this
Producer decodes each payload strictly into the Struct for K and yields it. The Structs come from a JSON schema file
(`schemas_from_file`), so the program's side needs no Python. The Producer's input reaches the program as one JSON
line on its standard input, which is then closed.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import types
from collections import deque
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import msgspec

from ..protocols import Producer

__all__ = ["ProcessFailed", "process_producer", "schemas_from_file"]

_BASE = {"str": str, "int": int, "float": float, "bool": bool}
_STDERR_LINES = 20
_TERMINATE_GRACE_SECONDS = 5.0


class ProcessFailed(Exception):
    """The process wrote a line no schema accepts, or exited non-zero. The message names the line or the status."""


def _field_type(name: str, spec: Mapping[str, Any]) -> Any:
    base = spec.get("type")
    if "enum" in spec:
        values = spec["enum"]
        if not isinstance(values, list) or not values:
            raise ValueError(f"field {name}: enum must be a non-empty list")
        t: Any = Literal[tuple(values)]
    elif base == "list":
        items = spec.get("items")
        if not isinstance(items, Mapping) or items.get("optional", False):
            raise ValueError(f"field {name}: a list needs an `items` spec, not optional")
        t = types.GenericAlias(tuple, (_field_type(f"{name}[]", items), ...))
    elif base in _BASE:
        t = _BASE[base]
    else:
        raise ValueError(
            f"field {name}: type must be one of {sorted([*_BASE, 'list'])} or an enum, not {base!r}"
        )
    meta = {k: spec[k] for k in ("pattern", "min_length", "ge", "le") if k in spec}
    if meta:
        t = Annotated[t, msgspec.Meta(**meta)]
    if spec.get("optional", False):
        t = t | None
    return t


def schemas_from_file(path: Path | str) -> tuple[int, dict[str, type[msgspec.Struct]]]:
    """(schema_version, kind -> Struct) from a JSON schema file:

    {"schema_version": n, "kinds": {K: {field: {"type": "str"|"int"|"float"|"bool"|"list", "optional": bool,
    "pattern": re, "min_length": n, "ge": n, "le": n, "enum": [...], "items": {spec}}}}}

    A list's `items` is a field spec, not optional; the field is a tuple of them (Sprint 271). Each
    Struct is frozen, forbids unknown fields, and is named K, so the event kind on the record is K. An optional
    field defaults to None; the rest are required."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    version = doc.get("schema_version")
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"{path}: schema_version must be an integer >= 1")
    out: dict[str, type[msgspec.Struct]] = {}
    for kind, fields in doc.get("kinds", {}).items():
        required, optional = [], []
        for name, spec in fields.items():
            t = _field_type(f"{kind}.{name}", spec)
            if spec.get("optional", False):
                optional.append((name, t, None))
            else:
                required.append((name, t))
        out[kind] = msgspec.defstruct(
            kind, [*required, *optional], frozen=True, forbid_unknown_fields=True
        )
    if not out:
        raise ValueError(f"{path}: no kinds")
    return version, out


class _Line(msgspec.Struct, forbid_unknown_fields=True):
    kind: str
    payload: dict[str, Any]


def process_producer(
    command: Sequence[str],
    schemas: Mapping[str, type[msgspec.Struct]],
    *,
    cwd: Path | str | None = None,
) -> Producer:
    """A Producer that runs `command` and yields the events it writes (see the module docstring). A line that is not
    JSON, names a kind `schemas` lacks, or fails its Struct raises ProcessFailed with the line's number; so does a
    non-zero exit, with the status and the last 20 lines of standard error. Cancelled, the process is sent SIGTERM,
    then SIGKILL after 5 s."""
    argv = list(command)
    if not argv:
        raise ValueError("process_producer: empty command")
    decode_line = msgspec.json.Decoder(_Line)

    async def produce(inp: Any) -> AsyncIterator[msgspec.Struct]:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=None if cwd is None else str(cwd),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdin, stdout, stderr = proc.stdin, proc.stdout, proc.stderr
        if stdin is None or stdout is None or stderr is None:  # PIPE was asked for all three
            raise ProcessFailed(f"{argv[0]}: no pipes")
        stderr_tail: deque[str] = deque(maxlen=_STDERR_LINES)

        async def drain_stderr() -> None:
            async for raw in stderr:
                stderr_tail.append(raw.decode("utf-8", "replace").rstrip("\n"))

        stderr_task = asyncio.create_task(drain_stderr())
        try:
            stdin.write(msgspec.json.encode(inp) + b"\n")
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                await stdin.drain()
            stdin.close()
            number = 0
            async for raw in stdout:
                number += 1
                text = raw.rstrip(b"\n")
                if not text:
                    continue
                try:
                    line = decode_line.decode(text)
                except msgspec.DecodeError as exc:
                    raise ProcessFailed(f"{argv[0]}: line {number}: {exc}") from None
                struct = schemas.get(line.kind)
                if struct is None:
                    raise ProcessFailed(
                        f"{argv[0]}: line {number}: kind {line.kind!r} is not in the schemas"
                    )
                try:
                    yield msgspec.convert(line.payload, struct)
                except msgspec.ValidationError as exc:
                    raise ProcessFailed(f"{argv[0]}: line {number}: {line.kind}: {exc}") from None
            status = await proc.wait()
            await stderr_task
            if status != 0:
                tail = "\n".join(stderr_tail)
                raise ProcessFailed(
                    f"{argv[0]}: exited with status {status}"
                    + (f"; stderr:\n{tail}" if tail else "")
                )
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), _TERMINATE_GRACE_SECONDS)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
            if not stderr_task.done():
                stderr_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stderr_task

    return cast(Producer, produce)

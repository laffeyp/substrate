# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The five parts (session vocabulary § AA.2; kernel sprint K336).

Each part is a producer: it takes the input `wire` lays out for its step and writes the step's
event. What a part needs from outside (a model, a way to start an agent run, a directory to run
commands in) comes in a `Deps` the caller supplies, so the same plan runs on real models in a
session and on stand-in answers in the plan tool's dry run.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import msgspec
from msgspec import Struct

from ...adapters import Responder, call_responder
from .vocabulary import MAIN_FIELDS, PART_PAYLOAD, AgentAs, Part, Step, kind_of

# A command's output kept on its event: the last characters, where an error says what failed.
COMMAND_OUTPUT_CHARS: Final[int] = 8000
COMMAND_TIMEOUT_SECONDS: Final[float] = 600.0


@dataclass(frozen=True)
class AgentCall:
    """What an agent step asks its starter for: one session turn on `text`."""

    step: str
    as_: AgentAs
    role: str
    text: str
    model: str  # empty: the caller's


@dataclass(frozen=True)
class Deps:
    """What the parts need from outside. `responder(model)` gives a model step its model (an empty
    name is the caller's); `start_agent(call)` runs one agent turn to its end and returns the
    § Z.2 report with its run id; `workdir` is where commands run."""

    responder: Callable[[str], Responder]
    start_agent: Callable[[AgentCall], Mapping[str, Any]]
    workdir: Path


def event_class(step: Step) -> type[Struct]:
    """The class of a step's event: its kind's name, its part's payload."""
    fields = list(PART_PAYLOAD[step.part])
    return msgspec.defstruct(kind_of(step.id), fields, frozen=True)


def main_field(payload: Mapping[str, Any]) -> str:
    """The text a step reads from an event when it lays out nothing else (§ AA.2)."""
    for name in MAIN_FIELDS:
        value = payload.get(name)
        if isinstance(value, str):
            return value
    return msgspec.json.encode(dict(payload)).decode()


Producer = Callable[[Any], AsyncIterator[Any]]


def producer(step: Step, cls: type[Struct], deps: Deps) -> Producer:
    """The producer for one step. Its input is `{"text": str, "items": list}` (wire § lay-out)."""
    if step.part is Part.MODEL:

        async def model(inp: Any) -> AsyncIterator[Any]:
            text = await call_responder(deps.responder(step.model), inp["text"], system=step.role)
            yield cls(text=text)

        return model

    if step.part is Part.AGENT:

        async def agent(inp: Any) -> AsyncIterator[Any]:
            call = AgentCall(
                step=step.id, as_=step.as_, role=step.role, text=inp["text"], model=step.model
            )
            report = await asyncio.to_thread(deps.start_agent, call)
            yield msgspec.convert(dict(report), cls)

        return agent

    if step.part is Part.COMMAND:

        async def command(inp: Any) -> AsyncIterator[Any]:
            proc = await asyncio.create_subprocess_shell(
                step.command,
                cwd=str(deps.workdir),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                out, _ = await asyncio.wait_for(
                    proc.communicate(inp["text"].encode()), COMMAND_TIMEOUT_SECONDS
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                yield cls(
                    ok=False,
                    exit=-1,
                    output=f"stopped after {COMMAND_TIMEOUT_SECONDS:.0f} s: {step.command}",
                )
                return
            text = out.decode(errors="replace")[-COMMAND_OUTPUT_CHARS:]
            code = proc.returncode if proc.returncode is not None else -1
            yield cls(ok=code == 0, exit=code, output=text)

        return command

    if step.part is Part.COLLECT:

        async def collect(inp: Any) -> AsyncIterator[Any]:
            yield cls(items=list(inp["items"]))

        return collect

    async def split(inp: Any) -> AsyncIterator[Any]:
        items = inp["items"]
        texts = (
            [main_field(i) for i in items]
            if items
            else [ln.strip() for ln in inp["text"].splitlines() if ln.strip()]
        )
        for index, item in enumerate(texts):
            yield cls(item=item, index=index, of=len(texts))

    return split


__all__ = [
    "COMMAND_OUTPUT_CHARS",
    "COMMAND_TIMEOUT_SECONDS",
    "AgentCall",
    "Deps",
    "Producer",
    "event_class",
    "main_field",
    "producer",
]

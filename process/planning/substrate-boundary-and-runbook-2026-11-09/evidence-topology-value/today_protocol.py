from __future__ import annotations
from collections.abc import AsyncIterator
from typing import Any
from msgspec import Struct
from substrate import api

class Candidate(Struct, frozen=True):
    member: str

async def named_input(input: Any) -> AsyncIterator[Candidate]:
    yield Candidate("a")

async def other_name(inp: Any) -> AsyncIterator[Candidate]:
    yield Candidate("a")

a: api.Producer = named_input
b: api.Producer = other_name

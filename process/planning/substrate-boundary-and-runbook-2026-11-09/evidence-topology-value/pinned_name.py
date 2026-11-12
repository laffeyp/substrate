"""A contract name pinned by a closed enum: no string literal at the declaration."""
from __future__ import annotations

from collections.abc import AsyncIterator
from enum import StrEnum

from msgspec import Struct
from tv import Producer


class Answer(Struct, frozen=True):
    text: str


class SessionProducer(StrEnum):
    MODEL = "model"


async def respond(_: None, /) -> AsyncIterator[Answer]:
    yield Answer("x")


pinned = Producer(respond, (Answer,), name=SessionProducer.MODEL)
assert pinned.kind == "model"
assert Producer(respond, (Answer,)).kind == "respond"

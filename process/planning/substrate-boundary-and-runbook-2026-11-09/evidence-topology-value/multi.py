from __future__ import annotations
from collections.abc import AsyncIterator
from msgspec import Struct
from tv import Producer

class A(Struct, frozen=True):
    x: int
class B(Struct, frozen=True):
    y: int
async def two(_: None, /) -> AsyncIterator[A | B]:
    yield A(1)
    yield B(2)
p = Producer(two, (A, B))
reveal_type(p)

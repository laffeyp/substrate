from __future__ import annotations
from collections.abc import AsyncIterator
from msgspec import Struct
from tv import Producer, Trigger, kind_buffer
from r1_value import Adjudicate, Candidate, Verdict

class Wrong(Struct, frozen=True):
    x: int

async def adj_body(inp: Adjudicate, /) -> AsyncIterator[Verdict]:
    yield Verdict("a", "b")

adj = Producer(adj_body, (Verdict,))
candidates = kind_buffer(Candidate)

# N1: input_builder returns the wrong type for the started Producer
t1 = Trigger(on=Candidate, start=adj, input=lambda c: Wrong(1))
# N2: the predicate reads a field the triggering event does not have
t2 = Trigger(on=Candidate, start=adj, input=lambda c: Adjudicate(c[candidates]),
             when=lambda c: c.event.memberr == "x")
# N3: the predicate treats a view value as the wrong type
t3 = Trigger(on=Candidate, start=adj, input=lambda c: Adjudicate(c[candidates]),
             when=lambda c: c[candidates] + 1 > 0)
# N4: the body yields a kind its Producer does not declare
async def bad_emit(inp: Adjudicate, /) -> AsyncIterator[Wrong]:
    yield Wrong(1)
p4: Producer[Adjudicate, Verdict] = Producer(bad_emit, (Verdict,))
# N5: a Trigger's input cannot start a Producer with a different input type
async def other(inp: Wrong, /) -> AsyncIterator[Verdict]:
    yield Verdict("a", "b")
p5 = Producer(other, (Verdict,))
t5 = Trigger(on=Candidate, start=p5, input=lambda c: Adjudicate(c[candidates]))

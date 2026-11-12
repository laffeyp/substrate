from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from msgspec import Struct
from substrate import api
from substrate.reference._models import Responder, call_responder
from tv import Initial, Producer, Topology, Trigger, completed, kind_buffer


class Candidate(Struct, frozen=True):
    member: str
    answer: str


class Verdict(Struct, frozen=True):
    chosen: str
    answer: str


class Adjudicate(Struct, frozen=True):
    candidates: tuple[Candidate, ...]


def member(name: str, question: str, responder: Responder, deterministic: bool) -> Producer[None, Candidate]:
    async def answer(_: None, /) -> AsyncIterator[Candidate]:
        yield Candidate(member=name, answer=await call_responder(responder, question))
    return Producer(answer, (Candidate,), key=name, deterministic=deterministic)


def adjudicator(question: str, responder: Responder, deterministic: bool) -> Producer[Adjudicate, Verdict]:
    async def adjudicate(inp: Adjudicate, /) -> AsyncIterator[Verdict]:
        listing = "\n".join(f"{c.member}: {c.answer}" for c in inp.candidates)
        prompt = f"Question: {question}\nCandidate answers:\n{listing}\nWhich member is best? Reply with just the member name."
        choice = (await call_responder(responder, prompt)).strip()
        chosen = next((c for c in inp.candidates if c.member in choice), inp.candidates[0])
        yield Verdict(chosen=chosen.member, answer=chosen.answer)
    return Producer(adjudicate, (Verdict,), deterministic=deterministic)


def ensemble(question: str, *, members: Mapping[str, Responder], judge: Responder, quorum: int = 3) -> Topology:
    ms = tuple(member(n, question, r, True) for n, r in members.items())
    adj = adjudicator(question, judge, True)
    candidates = kind_buffer(Candidate)
    return Topology(
        producers=(*ms, adj),
        views=(candidates,),
        triggers=(
            Trigger(on=Candidate, start=adj,
                    when=lambda c: len(c[candidates]) >= quorum,
                    input=lambda c: Adjudicate(c[candidates]),
                    policy=api.Once()),
        ),
        initial=tuple(Initial(m, None) for m in ms),
        termination=api.any_of(api.cancel_all_others(completed(adj)), api.all_completed()),
    )

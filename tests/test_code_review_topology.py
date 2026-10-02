# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Code review topology — CI MODE structural tests (Sprint 130).

Deterministic stand-in reviewers (no network), asserting the wiring the topology exists to
exercise: role-distinct reviewers run concurrently, a Bus-view predicate fires the judge once
at quorum, the verdict is grounded in the critiques on the bus, and cancel-all-others cancels
the reviewers still running when the judge completes. CI mode proves the WIRING; the real
role-distinct critique quality is the walkthrough (run separately against local LLMs).
"""

import pytest

from substrate.api import Runtime, read_record
from substrate.reference._models import DeterministicResponder
from substrate.topologies.code_review import DEFAULT_ROLES, code_review_topology

CODE = "def f(x):\n    return x/0\n"


def _responders() -> dict[str, DeterministicResponder]:
    return {role: DeterministicResponder(seed=i) for i, role in enumerate(DEFAULT_ROLES)}


@pytest.mark.timeout(15)
async def test_judge_fires_once_at_quorum(tmp_path):
    topo = code_review_topology(
        CODE,
        responders=_responders(),
        judge=DeterministicResponder(seed=99),
        quorum=3,
        deterministic=True,
    )
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))

    # the Bus-view predicate fired the judge exactly once (Once) after >= quorum critiques
    fired = [
        e
        for e in envs
        if e["kind"] == "substrate.TriggerFired" and e["payload"].get("trigger_id") == "adjudicate"
    ]
    assert len(fired) == 1
    adj_seq = fired[0]["seq"]
    critiques_before = sum(1 for e in envs if e["kind"] == "CritiquePosted" and e["seq"] < adj_seq)
    assert critiques_before >= 3  # quorum honored
    verdict = [e for e in envs if e["kind"] == "VerdictRendered"]
    assert len(verdict) == 1
    assert envs[-1]["kind"] == "substrate.RunFinalised"
    # deterministic CI -> replay ceiling stays 3a (every kind author-flagged deterministic)
    rs = next(e for e in envs if e["kind"] == "substrate.RunStarted")
    assert rs["payload"]["config"]["replay_ceiling"] == "3a"


@pytest.mark.timeout(15)
async def test_verdict_grounded_in_critiques(tmp_path):
    topo = code_review_topology(
        CODE, responders=_responders(), judge=DeterministicResponder(seed=7), quorum=3
    )
    await Runtime(tmp_path / "run").run(topo)
    envs = list(read_record(tmp_path / "run"))
    verdict = next(e for e in envs if e["kind"] == "VerdictRendered")
    # the verdict names the critiques it adjudicated, by role, and counts them — grounded, not
    # free-floating (the testable form of "the verdict cites the critiques it saw").
    assert verdict["payload"]["n_critiques"] >= 3
    assert len(verdict["payload"]["cited_roles"]) >= 1
    assert set(verdict["payload"]["cited_roles"]) <= set(DEFAULT_ROLES)
    assert verdict["payload"]["decision"] in {"approve", "request-changes", "block"}


@pytest.mark.timeout(15)
async def test_cancel_others_records_cancellation(tmp_path):
    # 3 fast reviewers meet quorum and fire the (instant) judge; it completes while the 2
    # lingering reviewers still sleep, so cancel-all-others has real victims -> two
    # substrate.ProducerCancelled land on the log. The cancellation is REAL (not "maybe nothing
    # to cancel"), verified by reading the record — reviewer #9's Phase-1 finding pattern.
    topo = code_review_topology(
        CODE,
        responders=_responders(),
        judge=DeterministicResponder(seed=1),
        quorum=3,
        deterministic=True,
        slow_roles=frozenset({"correctness", "clarity"}),
        linger_seconds=5.0,
    )
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"  # did not hang on the lingering reviewers
    envs = list(read_record(tmp_path / "run"))

    cancelled = sorted(
        e["payload"]["producer"]["kind"] for e in envs if e["kind"] == "substrate.ProducerCancelled"
    )
    assert cancelled == ["reviewer-clarity", "reviewer-correctness"]
    # the judge (the subject of cancel-others) was spared and completed
    assert not any(
        e["kind"] == "substrate.ProducerCancelled" and e["payload"]["producer"]["kind"] == "judge"
        for e in envs
    )
    tm = [e for e in envs if e["kind"] == "substrate.TerminationMatched"]
    assert any(e["payload"]["decision"] == "cancel-others" for e in tm)
    assert envs[-1]["kind"] == "substrate.RunFinalised"


class _VerdictJudge(DeterministicResponder):
    """A judge whose reply names a verdict, as the walkthrough prompt asks a real model to."""

    def __init__(self, reply: str) -> None:
        super().__init__(seed=0)
        self._reply = reply

    def respond(self, prompt: str) -> str:
        return self._reply

    async def arespond(self, prompt: str) -> str:
        return self._reply


@pytest.mark.timeout(15)
@pytest.mark.parametrize(
    ("reply", "decision"),
    [
        ("The injection is the most serious. Verdict: block", "block"),
        ("Nothing here would block a merge; approve", "approve"),
        ("Style nits only, but not approve as is: request-changes", "request-changes"),
    ],
)
async def test_judge_decision_comes_from_the_model_reply(tmp_path, reply, decision):
    # UI sprint 099: the judge discarded the model's reply and decided from a hash of the
    # critique text. The reply's last verdict word now decides.
    topo = code_review_topology(
        CODE, responders=_responders(), judge=_VerdictJudge(reply), quorum=3
    )
    await Runtime(tmp_path / "run").run(topo)
    verdict = next(e for e in read_record(tmp_path / "run") if e["kind"] == "VerdictRendered")
    assert verdict["payload"]["decision"] == decision

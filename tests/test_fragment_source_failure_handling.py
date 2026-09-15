# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Fragment-source failure handling — sprint 068 tests.

Two invariants:
 - Every fragment-source Producer failure lands on the record as
   SessionWarning(kind=fragment_source_failed, source_name=<kind>).
 - The per-turn composer chain never breaks. Fragment failure ->
   composer still fires with the partial cohort -> model still runs
   -> session runs to completion.

Failures are induced by monkey-patching the fragment factory to raise,
or (for role_fragment) by deleting the role .md between topology
build and RunStarted.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from substrate import api
from substrate.topologies.session import PromptFragment, SessionWarning
from substrate.topologies.session.ci import ci_session_topology


def _read_kinds(record_root: Path) -> dict[str, list[dict[str, Any]]]:
    envs = list(api.read_record(record_root))
    out: dict[str, list[dict[str, Any]]] = {}
    for env in envs:
        out.setdefault(env["kind"], []).append(env)
    return out


def test_per_turn_fragment_failure_surfaces_as_session_warning(
    tmp_path: Path, monkeypatch: "Any"
) -> None:
    """Monkey-patch per_turn_producer_factory to raise. Verify:
    - substrate.ProducerFailed{kind=per_turn_fragment} lands.
    - SessionWarning(kind=fragment_source_failed, source_name=per_turn_fragment) lands.
    - Composer still fires (chain does not break).
    - Session ends cleanly (SessionEnded lands).
    """

    async def _raising_body(_inp: Any) -> AsyncIterator[PromptFragment]:
        raise RuntimeError("simulated per_turn producer failure")
        yield  # unreachable, but makes the function an async generator

    def _raising_factory(per_turn: str) -> Any:  # noqa: ARG001
        return lambda: _raising_body

    from substrate.topologies.session import per_turn_producer as ptp

    monkeypatch.setattr(ptp, "per_turn_producer_factory", _raising_factory)
    import substrate.topologies.session as sess_init

    monkeypatch.setattr(sess_init, "per_turn_producer_factory", _raising_factory)

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("hi", "/exit"),
            session_id="s_frag_fail_per_turn",
            per_turn="anything",  # non-empty, so the raising body triggers on first turn
        )
        await api.Runtime(tmp_path / "ci").run(topology)

    asyncio.run(_run())
    kinds = _read_kinds(tmp_path / "ci")
    failed = [
        e
        for e in kinds.get("substrate.ProducerFailed", [])
        if e["payload"].get("producer", {}).get("kind") == "per_turn_fragment"
    ]
    assert len(failed) >= 1, "no ProducerFailed for per_turn_fragment on record"
    warnings = [
        e
        for e in kinds.get("SessionWarning", [])
        if e["payload"].get("kind") == "fragment_source_failed"
    ]
    assert warnings, "no SessionWarning(kind=fragment_source_failed) on record"
    assert warnings[0]["payload"]["source_name"] == "per_turn_fragment"
    # Composer still fired despite per_turn failure — chain-robustness.
    composed = kinds.get("PromptComposed", [])
    assert composed, "composer never fired — chain broke on per_turn failure"


def test_session_runs_to_completion_despite_fragment_failure(
    tmp_path: Path, monkeypatch: "Any"
) -> None:
    """A per_turn failure does not hang the session. SessionEnded lands
    and the run finalises."""

    async def _raising_body(_inp: Any) -> AsyncIterator[PromptFragment]:
        raise RuntimeError("simulated per_turn producer failure")
        yield

    def _raising_factory(per_turn: str) -> Any:  # noqa: ARG001
        return lambda: _raising_body

    import substrate.topologies.session as sess_init

    monkeypatch.setattr(sess_init, "per_turn_producer_factory", _raising_factory)

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("hi", "/exit"),
            session_id="s_frag_fail_completes",
            per_turn="x",
        )
        result = await api.Runtime(tmp_path / "ci").run(topology)
        assert result.status == "finalised"

    asyncio.run(_run())
    kinds = _read_kinds(tmp_path / "ci")
    ended = kinds.get("SessionEnded", [])
    assert ended, "SessionEnded never fired — session hung"


def test_session_warning_struct_carries_source_name() -> None:
    """The v0.2.1 SessionWarning Struct field `source_name` accepts a
    string, defaults to None. Backwards compat: existing callers passing
    only the four v0.1 fields still construct cleanly."""
    old_shape = SessionWarning(
        session_id="s_x",
        kind="seed_alone_exceeds",
        seed_tokens=100,
        driver_context_tokens=1000,
    )
    assert old_shape.source_name is None

    new_shape = SessionWarning(
        session_id="s_y",
        kind="fragment_source_failed",
        seed_tokens=0,
        driver_context_tokens=0,
        source_name="role_fragment",
    )
    assert new_shape.source_name == "role_fragment"


def test_fragment_source_kinds_frozenset_covers_all_sources() -> None:
    """FRAGMENT_SOURCE_KINDS covers every producer_kind in
    session_topology that emits PromptFragment. Locks the set against
    drift when a future sprint adds a fragment source without updating
    the vocabulary. Phase 8 item 7 added interrupt_fragment."""
    from substrate.topologies.session.vocabulary import FRAGMENT_SOURCE_KINDS

    expected = {
        "per_turn_fragment",
        "role_fragment",
        "bundle_methodology_fragment",
        "bundle_personality_fragment",
        "parent_context_fragment",
        "tools_suite_fragment",
        "user_message_fragment",
        "interrupt_fragment",
    }
    assert FRAGMENT_SOURCE_KINDS == expected

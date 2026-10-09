# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""role fragment source — sprint 061 tests.

Verifies:
 - The role producer fires once at session open and yields exactly one
   PromptFragment(source=role) when a role is set.
 - Fragment text matches the resolved role prompt (shipped .md file).
 - Provenance carries role_name + resolved_from path.
 - No role kwarg (default None) yields zero role fragments — the
   existing every-caller default is preserved.
 - Nonexistent role raises RegistrationError from the resolver at the
   producer's first firing (surfaces as substrate.ProducerFailed on the
   record). Session's own error handling routes through the standard
   ProducerFailed path.
 - resolve_role_prompt_with_source returns (text, path); the sibling
   resolve_role_prompt still returns text alone.

Deferred to sprint 064: live-model assertion that the role prompt
reaches the driver. _model_factory does not yet consume PromptComposed
so the role fragment on the record does not yet feed the model. Wiring
is verified at the record level here; live-model verification lands
with the composer consumption switch.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from substrate import api
from substrate.kernel.topology import RegistrationError
from substrate.topologies.session.ci import ci_session_topology
from substrate.topologies.session.roles import (
    resolve_role_prompt,
    resolve_role_prompt_with_source,
)

_SHIPPED_PROMPTS = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "substrate"
    / "topologies"
    / "session"
    / "prompts"
)


def test_role_fragment_lands_for_reviewer(tmp_path: Path) -> None:
    """A session opened with role=reviewer emits one PromptFragment
    (source=role) whose text matches the shipped reviewer.md and whose
    provenance names the role and the resolved path."""

    async def _run() -> None:
        record_root = tmp_path / "ci"
        topology = ci_session_topology(
            turns=("hi", "/exit"),
            session_id="s_role_reviewer",
            role="reviewer",
        )
        await api.Runtime(record_root).run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "ci"))
    role_frags = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "role"
    ]
    assert len(role_frags) == 1, f"expected 1 role fragment, got {len(role_frags)}"
    payload = role_frags[0]["payload"]
    expected_text = (_SHIPPED_PROMPTS / "reviewer.md").read_text(encoding="utf-8")
    assert payload["text"] == expected_text
    assert payload["precedence"] == 0
    assert payload["provenance"]["role_name"] == "reviewer"
    assert payload["provenance"]["resolved_from"].endswith("reviewer.md")


def test_role_fragment_absent_when_role_kwarg_omitted(tmp_path: Path) -> None:
    """A session opened without a role kwarg (the ci_session_topology
    default) emits zero role fragments. Existing callers unaffected."""

    async def _run() -> None:
        record_root = tmp_path / "ci"
        topology = ci_session_topology(
            turns=("hi", "/exit"),
            session_id="s_no_role",
        )
        await api.Runtime(record_root).run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "ci"))
    role_frags = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "role"
    ]
    assert len(role_frags) == 0


def test_role_fragment_fires_exactly_once_across_turns(tmp_path: Path) -> None:
    """Role is session-open scope — a five-turn session still emits
    exactly one role fragment. Lock the initial-firing invariant."""

    async def _run() -> None:
        record_root = tmp_path / "ci"
        topology = ci_session_topology(
            turns=("a", "b", "c", "d", "/exit"),
            session_id="s_role_once",
            role="planner",
        )
        await api.Runtime(record_root).run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "ci"))
    role_frags = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "role"
    ]
    assert len(role_frags) == 1


def test_role_fragment_precedence_is_zero() -> None:
    """The role fragment precedence value is 0 — role prompts land first
    in the composed prompt per session-vocabulary.md § I. Locks the
    number against later drift."""
    from substrate.topologies.session.role_producer import _PRECEDENCE

    assert _PRECEDENCE == 0


def test_resolve_role_prompt_with_source_returns_text_and_path() -> None:
    """The new resolver variant returns (text, source_path). The path
    ends in the role filename (bare .md shape) or the role directory
    name (folder shape)."""
    text, path = resolve_role_prompt_with_source("reviewer", repo_root=None)
    expected_text = (_SHIPPED_PROMPTS / "reviewer.md").read_text(encoding="utf-8")
    assert text == expected_text
    assert path == _SHIPPED_PROMPTS / "reviewer.md"


def test_resolve_role_prompt_still_returns_text_alone() -> None:
    """The wrapper preserves the original return shape — thin over
    resolve_role_prompt_with_source. Six existing callers of the old
    signature stay green."""
    text = resolve_role_prompt("default", repo_root=None)
    assert text == (_SHIPPED_PROMPTS / "default.md").read_text(encoding="utf-8")


def test_nonexistent_role_raises_at_resolver() -> None:
    """A role name with no .md file at any layer raises RegistrationError.
    In the daemon path this fires at POST /api/session (validator); in
    the CI path it fires at the role producer's first firing."""
    with pytest.raises(RegistrationError):
        resolve_role_prompt_with_source("no_such_role_2026", repo_root=None)

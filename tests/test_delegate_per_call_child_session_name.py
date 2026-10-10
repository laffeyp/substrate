# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 213a/b — path 1 (child_session_name) requires a session_registry.
Sprint 054 phase C — the substrate side now owns SessionRegistry, so the
"real registry routes correctly" case moved from substrate-ui/tests/ to
here. Both the "no registry → typed refusal" and "real registry → path 1
routes" contracts pin on the same seam.

Sprint 213a's original stub raised a "deferred to sprint 213b" error
unconditionally. Sprint 213b (2026-08-26) wired the standing-session
dispatch when `session_registry` is bound. When it is NOT bound, path 1
still raises a typed ValueError so the model reads a clear refusal via
tool_loop's `ToolResult(ok=False, error=...)` shape.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session_registry import SessionManifest, SessionRegistry
from substrate.topologies.tool_loop.delegate import make_delegate


def test_child_session_name_dispatch_without_registry_raises_typed(tmp_path: Path) -> None:
    d = make_delegate(responder=DeterministicResponder(seed=0), root=tmp_path)
    with pytest.raises(ValueError, match="child_session_name"):
        d.run([{"task": "review this", "child_session_name": "reviewer"}])


def test_error_message_names_the_registry_seam(tmp_path: Path) -> None:
    """The error string names `session_registry` so the model (or a human reading
    the tool result) knows what unblocks the path.
    """
    d = make_delegate(responder=DeterministicResponder(seed=0), root=tmp_path)
    with pytest.raises(ValueError, match="session_registry"):
        d.run([{"task": "review", "child_session_name": "reviewer"}])


def _reviewer_factory(
    manifest: SessionManifest, first_turn_user_message: Any = None
) -> Callable[[Any], None]:
    """Standing reviewer running a DeterministicResponder — no network,
    replay-stable, no external dependency. The reviewer's identity
    ('reviewer says: <task>') survives across turns via the record."""
    del first_turn_user_message
    return session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=4096,
        seed="reviewer",
        tools={},
        per_turn="",
        max_turns=200,
        turn_max_steps=2,
        session_id=manifest.session_id,
        workspace_path=manifest.workspace,
        script=None,
    )


def test_path_1_routes_into_standing_session_with_real_registry(tmp_path: Path) -> None:
    """Sprint 054 phase C. Substrate side now owns SessionRegistry, so a
    real registry lives inside a substrate-side test. Wire proven end-to-
    end without touching substrate-ui.

    Reviewer opens on turn 1 (first UserMessage). Parent delegate call
    routes into it. ToolResult carries `via='standing_session:reviewer'`,
    `child_root` equal to the reviewer's record path. No mocks."""
    sessions_base = tmp_path / "sessions"
    sessions_base.mkdir()
    reviewer_workspace = tmp_path / "reviewer_ws"
    reviewer_workspace.mkdir()
    registry = SessionRegistry(base=sessions_base, session_topology_factory=_reviewer_factory)
    registry.create(
        session_id="s_reviewer",
        name="reviewer",
        driver="deterministic",
        workspace=str(reviewer_workspace),
        workspace_shape="flat",
        bundle=None,
        seed="reviewer",
    )
    reviewer_record = sessions_base / "s_reviewer" / "record"

    # Open the reviewer's record with a first UserMessage.
    asyncio.run(
        api.Runtime(reviewer_record, persistent=True).resume(
            _reviewer_factory(registry.get("s_reviewer")),
            resume_event=UserMessage(
                text="hello",
                turn_index=0,
                assembled_prompt="hello",
                slash_source="chat",
            ),
        )
    )

    # Parent delegate call — path 1 routes into the reviewer.
    parent_workspace = tmp_path / "parent_ws"
    parent_workspace.mkdir()
    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=parent_workspace,
        session_registry=registry,
        parent_session_id="s_parent",
    )
    result = d.run([{"task": "please review", "child_session_name": "reviewer"}])

    assert result["via"] == "standing_session:reviewer", result
    assert Path(result["child_root"]) == reviewer_record, result
    assert "answer" in result and result["answer"], result
    assert result["steps"] == -1  # standing-session marker per delegate.py:519.

    # Reviewer's record grew with the delegated UserMessage.
    envelopes = list(api.read_record(reviewer_record))
    delegated = [
        e
        for e in envelopes
        if e["kind"] == "UserMessage" and (e["payload"] or {}).get("slash_source") == "delegate"
    ]
    assert len(delegated) == 1, f"expected one delegated UserMessage; got {len(delegated)}"
    assert "please review" in delegated[0]["payload"]["text"]

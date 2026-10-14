# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 213a/b — path 1 (child_session_name) routes into a standing session through the
registry. Kernel K323 made the registry a required argument of `make_delegate`, so the
"no registry" refusal no longer exists."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any


from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session_registry import SessionManifest, SessionRegistry
from substrate.topologies.tool_loop.delegate import make_delegate


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
        session_registry=registry,
        parent_session_id="s_parent",
    )
    result = d.run([{"task": "please review", "child_session_name": "reviewer"}])

    assert result["via"] == "standing_session:reviewer", result
    assert Path(result["child_root"]) == reviewer_record, result
    assert "answer" in result and result["answer"], result

    # Reviewer's record grew with the delegated UserMessage.
    envelopes = list(api.read_record(reviewer_record))
    delegated = [
        e
        for e in envelopes
        if e["kind"] == "UserMessage" and (e["payload"] or {}).get("slash_source") == "delegate"
    ]
    assert len(delegated) == 1, f"expected one delegated UserMessage; got {len(delegated)}"
    assert "please review" in delegated[0]["payload"]["text"]

"""Sprint 213b, revised by the Architect's ruling of 2026-09-25 — what a standing session does
when a delegate reaches it after it ended or vanished.

  1. An ENDED session resumes: turn_sync flips it to parked and runs the turn (it raised
     SessionEndedMidTurn before the ruling).
  2. A VANISHED session (manifest deleted) raises KeyError from turn_sync.
  3. A delegate naming a session that was never registered raises ValueError.
  4. A registry built without a topology factory cannot run a turn (RuntimeError).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.session import session_topology
from substrate.topologies.session_registry import SessionManifest, SessionRegistry
from substrate.topologies.tool_loop.delegate import make_delegate


def scratch_ws(name: str) -> str:
    """A workspace label inside this run's temp state root (tests/conftest.py)."""
    return os.path.join(os.environ["SUBSTRATE_HOME"], "workspaces", name)


def _factory(
    manifest: SessionManifest, first_turn_user_message: object = None
) -> Callable[[api.TopologyBuilder], None]:
    del first_turn_user_message  # delegate path uses .resume(); no first-turn opener needed
    return session_topology(
        record_root=Path(manifest.record_root),  # the daemon's configuration (UI sprint 107)
        driver=DeterministicResponder(seed=7),
        driver_name="deterministic",
        driver_context_tokens=4096,
        seed="x",
        tools={},
        session_id="s_x",
        workspace_path=scratch_ws("x"),
        script=None,
    )


def test_vanished_session_raises_typed_failure(tmp_path: Path) -> None:
    """The typed failure is for a session that VANISHED (manifest deleted). An ENDED session
    resumes instead (Architect ruling 2026-09-25, session_registry.turn_sync); this test
    asserted the pre-ruling contract until Sprint 097."""
    base = tmp_path / "sessions"
    base.mkdir()
    registry = SessionRegistry(base=base, session_topology_factory=_factory)
    registry.create(
        session_id="s_dead",
        name="dead-reviewer",
        driver="deterministic",
        workspace=scratch_ws("x"),
        workspace_shape="flat",
        bundle=None,
        seed="x",
    )
    from substrate.topologies.session import UserMessage as SessionUserMessage

    registry.delete("s_dead")
    with pytest.raises(KeyError):
        registry.turn_sync(
            "s_dead",
            SessionUserMessage(text="hi", turn_index=0, assembled_prompt="hi", slash_source="test"),
        )


def test_registry_turn_sync_resumes_an_ended_session(tmp_path: Path) -> None:
    """Architect ruling 2026-09-25: an ended session accepts another turn. turn_sync flips the
    manifest from ended to parked and runs the turn; no SessionEndedMidTurn."""
    base = tmp_path / "sessions"
    base.mkdir()
    registry = SessionRegistry(base=base, session_topology_factory=_factory)
    registry.create(
        session_id="s_dead2",
        name=None,
        driver="deterministic",
        workspace=scratch_ws("x"),
        workspace_shape="flat",
        bundle=None,
        seed="x",
    )
    registry.update_status("s_dead2", "ended")

    from substrate.topologies.session import UserMessage as SessionUserMessage

    registry.turn_sync(
        "s_dead2",
        SessionUserMessage(text="hi", turn_index=0, assembled_prompt="hi", slash_source="test"),
    )
    assert registry.get("s_dead2").status != "ended"


def test_unknown_session_name_raises_typed_failure(tmp_path: Path) -> None:
    """A delegate call naming a session that never was registered raises
    ValueError with `unknown session name`, not a KeyError."""
    base = tmp_path / "sessions"
    base.mkdir()
    registry = SessionRegistry(base=base, session_topology_factory=_factory)

    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=tmp_path / "parent",
        session_registry=registry,
    )
    with pytest.raises(ValueError, match="unknown session name"):
        d.run([{"task": "hi", "child_session_name": "no-such-name"}])


def test_registry_without_factory_raises_runtime_error(tmp_path: Path) -> None:
    """A registry constructed without a `session_topology_factory` cannot fire
    turn_sync — raises RuntimeError naming the omitted seam.
    """
    base = tmp_path / "sessions"
    base.mkdir()
    registry = SessionRegistry(base=base)  # no factory
    registry.create(
        session_id="s_orphan",
        name="orphan",
        driver="deterministic",
        workspace=scratch_ws("x"),
        workspace_shape="flat",
        bundle=None,
        seed="x",
    )
    from substrate.topologies.session import UserMessage as SessionUserMessage

    with pytest.raises(RuntimeError, match="session_topology_factory"):
        registry.turn_sync(
            "s_orphan",
            SessionUserMessage(
                text="hi",
                turn_index=0,
                assembled_prompt="hi",
                slash_source="test",
            ),
        )

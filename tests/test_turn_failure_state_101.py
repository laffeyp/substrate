"""UI sprint 101: what a failed turn leaves behind.

A turn that raised (here: a timeout the caller chose) left the manifest at the previous turn's
`parked` and the cached turn counter unadvanced, though the record already held the failed turn's
UserMessage, so the next turn reused its turn_index. A timeout also cancelled the whole run task, so
the record stopped mid-turn with no word of why. Now a caller's timeout cancels the live producers
the way the user's interrupt does, and the turn parks. turn_sync has no default time limit.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session_registry import SessionManifest, SessionRegistry, SessionStatus


class _SlowOnCue(DeterministicResponder):
    """Sleeps on the first prompt that mentions SLOW (later prompts carry it in their history)."""

    slept = False

    async def arespond(self, prompt: str) -> str:
        if "SLOW" in prompt and not self.slept:
            self.slept = True
            await asyncio.sleep(30)
        return self.respond(prompt)


def _registry(tmp_path: Path) -> SessionRegistry:
    responder = _SlowOnCue(seed=0)

    def factory(manifest: SessionManifest, first_turn_user_message: Any = None) -> Any:
        return session_topology(
            driver=responder,
            driver_name="deterministic",
            driver_context_tokens=4096,
            seed=manifest.seed,
            tools={},
            per_turn="",
            max_turns=200,
            turn_max_steps=4,
            session_id=manifest.session_id,
            workspace_path=manifest.workspace,
            script=None,
            first_turn_user_message=first_turn_user_message,
        )

    return SessionRegistry(base=tmp_path / "sessions", session_topology_factory=factory)


def _turn(reg: SessionRegistry, sid: str, text: str, timeout: float | None = None) -> Any:
    def build(_m: SessionManifest, _root: Path) -> UserMessage:
        return UserMessage(
            text=text,
            turn_index=reg.next_turn_index(sid),
            assembled_prompt=text,
            slash_source="user",
        )

    return reg.turn_sync(sid, resume_event_builder=build, timeout_seconds=timeout)


def test_turn_sync_has_no_default_time_limit() -> None:
    default = inspect.signature(SessionRegistry.turn_sync).parameters["timeout_seconds"].default
    assert default is None


def test_a_failed_turn_leaves_honest_status_and_turn_index(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    sid = reg.create(
        session_id="s_0123456789abcdef",
        name=None,
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="",
    ).session_id
    m, _ = _turn(reg, sid, "first")
    assert m.status == SessionStatus.PARKED

    with pytest.raises(TimeoutError):
        _turn(reg, sid, "SLOW second", timeout=1.0)

    after = reg.get(sid)
    assert after is not None and after.status == SessionStatus.PARKED
    envs = list(api.read_record(Path(after.record_root)))
    cancelled = [e for e in envs if e["kind"] == api.PRODUCER_CANCELLED]
    assert cancelled and cancelled[-1]["payload"].get("cause") == "timeout", (
        "the record says the turn was stopped and why"
    )
    assert envs[-1]["kind"] != "substrate.ProducerStarted", "the record does not stop mid-turn"
    m3, root = _turn(reg, sid, "third")
    assert m3.status == SessionStatus.PARKED
    indexes = [
        e["payload"]["turn_index"] for e in api.read_record(root) if e["kind"] == "UserMessage"
    ]
    assert indexes == [0, 1, 2], f"turn indexes on the record: {indexes}"

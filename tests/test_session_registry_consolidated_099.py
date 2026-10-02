"""UI sprint 099: one session registry, in the kernel.

substrate-ui carried its own copy of session_registry.py, and the two drifted:
the UI copy let an ended session take another turn (Architect ruling 2026-09-25),
accepted `driver_version`, and derived turn indexes lazily (Sprint 094); the
kernel copy did none of these, and the kernel's delegate caught the kernel's
`SessionEndedMidTurn` while the daemon handed it a registry raising the UI's.

These tests pin the merged behaviour on the one module both sides now import,
plus the seed contract: the kernel copy warned that `SessionManifest.seed` had
no consumer, but `render_transcript` puts it first in every model prompt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.session_registry import SessionManifest, SessionRegistry, SessionStatus
from substrate.topologies.session import UserMessage, session_topology


class _RecordingResponder(DeterministicResponder):
    def __init__(self) -> None:
        super().__init__(seed=0)
        self.prompts: list[str] = []

    def respond(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return super().respond(prompt)

    async def arespond(self, prompt: str) -> str:
        return self.respond(prompt)


def _registry(tmp_path: Path, responder: DeterministicResponder) -> SessionRegistry:
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
            record_root=Path(manifest.record_root),
            script=None,
            first_turn_user_message=first_turn_user_message,
        )

    return SessionRegistry(base=tmp_path / "sessions", session_topology_factory=factory)


def _create(reg: SessionRegistry, tmp_path: Path, seed: str = "") -> str:
    m = reg.create(
        session_id="s_0123456789abcdef",
        name=None,
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed=seed,
    )
    return m.session_id


def _turn(reg: SessionRegistry, sid: str, text: str, index: int) -> SessionManifest:
    manifest, _ = reg.turn_sync(
        sid,
        resume_event=UserMessage(
            text=text, turn_index=index, assembled_prompt=text, slash_source="user"
        ),
        timeout_seconds=30.0,
    )
    return manifest


def test_seed_reaches_the_model_prompt(tmp_path: Path) -> None:
    responder = _RecordingResponder()
    reg = _registry(tmp_path, responder)
    sid = _create(reg, tmp_path, seed="SEED-MARKER-099 you review diffs")
    _turn(reg, sid, "hello", 0)
    assert responder.prompts, "the model never ran"
    assert "SEED-MARKER-099 you review diffs" in responder.prompts[0]


def test_ended_session_takes_another_turn(tmp_path: Path) -> None:
    responder = _RecordingResponder()
    reg = _registry(tmp_path, responder)
    sid = _create(reg, tmp_path)
    _turn(reg, sid, "first", 0)
    reg.update_status(sid, SessionStatus.ENDED)

    after = _turn(reg, sid, "second", 1)

    assert after.status != SessionStatus.ENDED
    assert any("second" in p for p in responder.prompts), "the resumed turn never reached the model"
    on_disk = SessionRegistry(base=tmp_path / "sessions").get(sid)
    assert on_disk is not None and on_disk.status == after.status


def test_driver_version_is_an_accepted_driver_param(tmp_path: Path) -> None:
    reg = _registry(tmp_path, _RecordingResponder())
    sid = _create(reg, tmp_path)
    m = reg.set_driver_params(sid, {"driver_version": "claude-opus-5-5"})
    assert m.driver_params == {"driver_version": "claude-opus-5-5"}
    with pytest.raises(ValueError, match="driver_version must be str"):
        reg.set_driver_params(sid, {"driver_version": True})


def test_boot_scan_reads_no_record_for_turn_indexes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from substrate import session_registry as sr

    reg = _registry(tmp_path, _RecordingResponder())
    sid = _create(reg, tmp_path)
    calls: list[Path] = []
    monkeypatch.setattr(sr, "_next_turn_index_from_record", lambda root: calls.append(root) or 3)

    reborn = SessionRegistry(base=tmp_path / "sessions")
    reborn.boot_scan()
    assert calls == []
    assert reborn.next_turn_index(sid) == 3
    reborn.advance_turn_index(sid)
    assert reborn.next_turn_index(sid) == 4
    assert len(calls) == 1


def test_api_and_module_export_the_same_classes() -> None:
    from substrate import session_registry as sr

    for name in sr.__all__:
        assert getattr(api, name) is getattr(sr, name), name

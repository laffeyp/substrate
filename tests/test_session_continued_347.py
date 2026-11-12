# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K347: a session names the conversation it continues (session vocabulary § AD).

The manifest's `continued_session` is the path of a turns file; the daemon's topology factory
reads it and gives it to `session_topology`, whose `continued_session` source writes it as the
session's opening text. A session that names none is as before, its manifest byte for byte.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session_registry import SessionManifest, SessionRegistry

TURNS: list[dict[str, Any]] = [
    {"kind": "UserMessage", "payload": {"text": "Remember the word: heron.", "turn_index": 0}},
    {"kind": "ModelReply", "payload": {"text": "OK, heron.", "stop_reason": "end_turn"}},
]


def _registry(tmp_path: Path) -> SessionRegistry:
    responder = DeterministicResponder(seed=0)

    def factory(manifest: SessionManifest, first_turn_user_message: Any = None) -> Any:
        continued = (
            json.loads(Path(manifest.continued_session).read_text(encoding="utf-8"))
            if manifest.continued_session
            else None
        )
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
            continued_session=continued,
        )

    return SessionRegistry(base=tmp_path / "sessions", session_topology_factory=factory)


def _run(
    tmp_path: Path, sid: str, continued: str | None
) -> tuple[SessionRegistry, SessionManifest]:
    reg = _registry(tmp_path)
    manifest = reg.create(
        session_id=sid,
        name=None,
        driver="deterministic",
        workspace=str(tmp_path / f"ws_{sid}"),
        workspace_shape="flat",
        bundle=None,
        seed="SEED",
        continued_session=continued,
    )

    def build(_m: SessionManifest, _root: Path) -> UserMessage:
        return UserMessage(
            text="What word?",
            turn_index=reg.next_turn_index(sid),
            assembled_prompt="What word?",
            slash_source="user",
        )

    reg.turn_sync(sid, resume_event_builder=build)
    return reg, manifest


def _events(manifest: SessionManifest) -> list[dict[str, Any]]:
    return list(api.read_record(manifest.record_root))


def test_a_session_that_names_a_continuation_opens_with_it(tmp_path: Path) -> None:
    turns_file = tmp_path / "continued_session.json"
    turns_file.write_text(
        json.dumps({"turns": TURNS, "provenance": {"tool": "claude_code", "path": "/x/s.jsonl"}}),
        encoding="utf-8",
    )
    _reg, manifest = _run(tmp_path, "s_00000000000000a1", str(turns_file))
    assert manifest.continued_session == str(turns_file)
    on_disk = json.loads(
        (tmp_path / "sessions" / "s_00000000000000a1" / "manifest.json").read_text()
    )
    assert on_disk["continued_session"] == str(turns_file)
    events = _events(manifest)
    frags = [
        e
        for e in events
        if e["kind"] == "PromptFragment" and e["payload"]["source"] == "continued_session"
    ]
    assert len(frags) == 1
    assert frags[0]["payload"]["provenance"]["turns"] == 1
    composed = [e for e in events if e["kind"] == "PromptComposed"]
    assert composed and "USER: Remember the word: heron." in composed[0]["payload"]["text"]
    assert "MODEL: OK, heron." in composed[0]["payload"]["text"]


def test_a_session_that_names_none_is_as_before(tmp_path: Path) -> None:
    _reg, manifest = _run(tmp_path, "s_00000000000000b2", None)
    assert manifest.continued_session is None
    on_disk = json.loads(
        (tmp_path / "sessions" / "s_00000000000000b2" / "manifest.json").read_text()
    )
    assert "continued_session" not in on_disk
    events = _events(manifest)
    assert not [
        e
        for e in events
        if e["kind"] == "PromptFragment" and e["payload"]["source"] == "continued_session"
    ]


def test_the_manifest_round_trips(tmp_path: Path) -> None:
    turns_file = tmp_path / "t.json"
    turns_file.write_text(json.dumps({"turns": TURNS}), encoding="utf-8")
    _run(tmp_path, "s_00000000000000c3", str(turns_file))
    reloaded = SessionRegistry(
        base=tmp_path / "sessions", session_topology_factory=lambda *_a, **_k: None
    )
    assert reloaded.get("s_00000000000000c3").continued_session == str(turns_file)

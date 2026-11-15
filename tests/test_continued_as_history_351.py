# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K351: the continued conversation enters as history (session vocabulary § AF, v0.21).

It entered as opening prompt text, which every prompt carried and compaction never touched; the
continued session of 2026-11-14 sent 1,422,933 characters of it on every turn. Now it is the
session's earliest turns in its record, numbered -N..-1, its messages marked `continued` so no
trigger acts on them, and compaction ages it out like any history.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.session import (
    HarnessToolCall,
    HarnessToolResult,
    ModelReply,
    UserMessage,
    session_topology,
)
from substrate.topologies.session.session_prompt_producer import continued_session_events
from substrate.topologies.session_registry import SessionManifest, SessionRegistry


def _turns(n: int, size: int = 40) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"kind": "ModelReply", "payload": {"text": "before any message"}}]
    for i in range(n):
        out += [
            {"kind": "UserMessage", "payload": {"text": f"imported message {i} " + "x" * size}},
            {
                "kind": "HarnessToolCall",
                "payload": {"call_id": f"t{i}", "tool": "Bash", "args": {"command": "ls"}},
            },
            {
                "kind": "HarnessToolResult",
                "payload": {"call_id": f"t{i}", "output": "a.txt", "ok": True},
            },
            {
                "kind": "ModelReply",
                "payload": {"text": f"imported reply {i}", "stop_reason": "end_turn"},
            },
        ]
    return out


def test_the_turns_become_history_events_numbered_before_zero() -> None:
    events = continued_session_events({"turns": _turns(3), "provenance": {"tool": "claude_code"}})
    assert [type(e) for e in events] == [
        UserMessage,
        HarnessToolCall,
        HarnessToolResult,
        ModelReply,
    ] * 3
    messages = [e for e in events if isinstance(e, UserMessage)]
    assert [m.turn_index for m in messages] == [-3, -2, -1]
    assert {m.slash_source for m in messages} == {"continued"}
    replies = [e for e in events if isinstance(e, ModelReply)]
    assert [r.turn_index for r in replies] == [-3, -2, -1] and replies[0].text == "imported reply 0"
    assert "before any message" not in json.dumps([getattr(e, "text", "") for e in events])


def _registry(tmp_path: Path, context_tokens: int) -> SessionRegistry:
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
            driver_context_tokens=context_tokens,
            seed="SEED",
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
    tmp_path: Path, sid: str, turns: list[dict[str, Any]] | None, context_tokens: int
) -> tuple[SessionRegistry, SessionManifest]:
    reg = _registry(tmp_path, context_tokens)
    path: str | None = None
    if turns is not None:
        f = tmp_path / f"{sid}.json"
        f.write_text(
            json.dumps({"turns": turns, "provenance": {"tool": "claude_code"}}), encoding="utf-8"
        )
        path = str(f)
    manifest = reg.create(
        session_id=sid,
        name=None,
        driver="deterministic",
        workspace=str(tmp_path / f"ws_{sid}"),
        workspace_shape="flat",
        bundle=None,
        seed="SEED",
        continued_session=path,
        make_repository=False,
    )

    def build(_m: SessionManifest, _root: Path) -> UserMessage:
        return UserMessage(
            text="What next?",
            turn_index=reg.next_turn_index(sid),
            assembled_prompt="What next?",
            slash_source="user",
        )

    reg.turn_sync(sid, resume_event_builder=build)
    return reg, manifest


def test_a_continued_session_opens_with_its_history_and_compacts_it(tmp_path: Path) -> None:
    sid = "s_00000000000000e5"
    reg, manifest = _run(tmp_path, sid, _turns(30, size=400), context_tokens=3000)
    events = list(api.read_record(manifest.record_root, resolve_blobs=True))
    kinds = [e["kind"] for e in events]
    messages = [e for e in events if e["kind"] == "UserMessage"]
    live = [m for m in messages if m["payload"].get("slash_source") != "continued"]
    imported = [m for m in messages if m["payload"].get("slash_source") == "continued"]
    assert len(imported) == 30 and len(live) == 1
    assert live[0]["payload"]["turn_index"] == 0
    assert max(e["seq"] for e in imported) < live[0]["seq"]
    # No model call ran on an imported message: the first PromptComposed follows the live message.
    first_prompt = kinds.index("PromptComposed")
    assert events[first_prompt]["seq"] > live[0]["seq"]
    assert kinds.count("PromptComposed") == 1
    # An imported reply is no turn's end: the one Returned answers the live message.
    (returned,) = [e for e in events if e["kind"] == "Returned"]
    assert returned["seq"] > live[0]["seq"] and returned["payload"]["turn_index"] == 0
    assert not [
        e
        for e in events
        if e["kind"] == "PromptFragment" and e["payload"]["source"] == "continued_session"
    ]
    # The history window keeps the newest imported turns that fit and records the cut.
    prompt = events[first_prompt]["payload"]["text"]
    assert "imported message 29" in prompt and "imported message 0 " not in prompt
    compacted = [e["payload"] for e in events if e["kind"] == "TranscriptCompacted"]
    assert compacted and compacted[-1]["dropped_seq_range"] is not None
    assert reg.next_turn_index(sid) == 1
    # A restarted daemon numbers from the record: the imported turns, all below 0, count for none.
    reloaded = SessionRegistry(
        base=tmp_path / "sessions", session_topology_factory=lambda *_a, **_k: None
    )
    assert reloaded.next_turn_index(sid) == 1


def test_a_small_continuation_is_all_in_the_first_prompt(tmp_path: Path) -> None:
    sid = "s_00000000000000f6"
    reg, manifest = _run(tmp_path, sid, _turns(2), context_tokens=100_000)
    events = list(api.read_record(manifest.record_root, resolve_blobs=True))
    prompt = next(e["payload"]["text"] for e in events if e["kind"] == "PromptComposed")
    assert "USER: imported message 0" in prompt and "MODEL: imported reply 1" in prompt
    assert "USER: What next?" in prompt

    # A second turn resumes the run from its record; the conversation is not imported again.
    def again(_m: SessionManifest, _root: Path) -> UserMessage:
        return UserMessage(
            text="And then?",
            turn_index=reg.next_turn_index(sid),
            assembled_prompt="And then?",
            slash_source="user",
        )

    reg.turn_sync(sid, resume_event_builder=again)
    events = list(api.read_record(manifest.record_root, resolve_blobs=True))
    indexes = [e["payload"]["turn_index"] for e in events if e["kind"] == "UserMessage"]
    assert indexes == [-2, -1, 0, 1]
    last = [e["payload"]["text"] for e in events if e["kind"] == "PromptComposed"][-1]
    assert last.count("USER: imported message 0") == 1 and "USER: And then?" in last


def test_a_session_that_continues_nothing_writes_no_imported_events(tmp_path: Path) -> None:
    _reg, manifest = _run(tmp_path, "s_00000000000000a7", None, context_tokens=100_000)
    events = list(api.read_record(manifest.record_root, resolve_blobs=True))
    assert [e["payload"]["turn_index"] for e in events if e["kind"] == "UserMessage"] == [0]

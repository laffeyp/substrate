# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K353: a conversation brought in before v0.21 becomes the session's history (§ AH).

A session continued under v0.19-v0.20 holds the conversation as one `continued_session`
fragment, in every prompt and never compacted. Its turns are in the session's turns file. The
window now leaves the fragment out of the head and plans those turns as the session's oldest
history, numbered -M..-1 in seq, so § S clears their tool output and drops their turns first.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _text import varied_text

import substrate.topologies.session as session_pkg
from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.session import PromptFragment, UserMessage, session_topology
from substrate.topologies.session import _continued_turns
from substrate.topologies.session.transcript import _group_by_turn, _render_turns
from substrate.topologies.session.vocabulary import PromptSource
from substrate.topologies.session_registry import SessionManifest, SessionRegistry


def _turns(n: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(n):
        out += [
            {
                "kind": "UserMessage",
                "payload": {"text": f"imported message {i} {varied_text(300)}"},
            },
            {
                "kind": "HarnessToolCall",
                "payload": {"call_id": f"t{i}", "tool": "Read", "args": {"path": f"f{i}.py"}},
            },
            {
                "kind": "HarnessToolResult",
                "payload": {"call_id": f"t{i}", "output": varied_text(600), "ok": True},
            },
            {
                "kind": "ModelReply",
                "payload": {"text": f"imported reply {i}", "stop_reason": "end_turn"},
            },
        ]
    return out


def test_the_imported_turns_are_numbered_below_every_record_seq() -> None:
    turns = _continued_turns({"turns": _turns(3), "provenance": {"tool": "claude_code"}})
    seqs = [e["seq"] for t in turns for e in t]
    assert seqs == list(range(-12, 0))
    assert [t[0]["payload"]["turn_index"] for t in turns] == [-3, -2, -1]
    assert _continued_turns(None) == []


def _old_form_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window: int, n: int
) -> list[dict[str, Any]]:
    """A session whose first run writes the conversation as the v0.19 fragment, as the build before
    v0.21 did; its later turns run on this build."""
    continued = {"turns": _turns(n), "provenance": {"tool": "claude_code"}}
    turns_file = tmp_path / "continued_session.json"
    turns_file.write_text(json.dumps(continued), encoding="utf-8")
    text = "This session continues a conversation held in claude_code. The conversation so far:\n\n"
    text += "\n".join(_render_turns(_group_by_turn(continued["turns"])))
    original = session_pkg.session_prompt_sources

    def with_old_fragment(**kw: Any) -> Any:
        sources = original(**kw)
        sources[PromptSource.CONTINUED_SESSION] = lambda: [
            PromptFragment(source="continued_session", text=text, precedence=30, provenance={})
        ]
        return sources

    responder = DeterministicResponder(seed=0)

    def factory(manifest: SessionManifest, first_turn_user_message: Any = None) -> Any:
        first = first_turn_user_message is not None
        return session_topology(
            driver=responder,
            driver_name="deterministic",
            driver_context_tokens=window,
            seed="SEED",
            tools={},
            per_turn="",
            max_turns=200,
            turn_max_steps=4,
            session_id=manifest.session_id,
            workspace_path=manifest.workspace,
            script=None,
            first_turn_user_message=first_turn_user_message,
            # The old build gave the topology no turns; the fragment carried them.
            continued_session=None if first else continued,
        )

    reg = SessionRegistry(base=tmp_path / "sessions", session_topology_factory=factory)
    sid = "s_00000000000000b9"
    manifest = reg.create(
        session_id=sid,
        name=None,
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="SEED",
        continued_session=str(turns_file),
        make_repository=False,
    )
    for word, old in (("first", True), ("second", False)):

        def build(_m: SessionManifest, _root: Path, word: str = word) -> UserMessage:
            return UserMessage(
                text=f"the {word} live message",
                turn_index=reg.next_turn_index(sid),
                assembled_prompt=f"the {word} live message",
                slash_source="user",
            )

        if old:
            monkeypatch.setattr(session_pkg, "session_prompt_sources", with_old_fragment)
        else:
            monkeypatch.setattr(session_pkg, "session_prompt_sources", original)
        reg.turn_sync(sid, resume_event_builder=build)
    return list(api.read_record(manifest.record_root, resolve_blobs=True))


def test_the_old_fragment_leaves_the_head_and_its_turns_are_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = _old_form_session(tmp_path, monkeypatch, window=100_000, n=3)
    (frag_seq,) = [
        e["seq"]
        for e in events
        if e["kind"] == "PromptFragment" and e["payload"]["source"] == "continued_session"
    ]
    first, second = [e["payload"] for e in events if e["kind"] == "PromptComposed"]
    assert frag_seq in first["fragment_seqs"]  # the old build's prompt, as it was
    assert frag_seq not in second["fragment_seqs"]
    assert "This session continues a conversation" not in second["text"]
    assert "[transcript: turns -3..1]" in second["text"]
    assert second["text"].count("imported message 0 ") == 1
    assert "USER: the first live message" in second["text"]


def test_a_small_window_clears_and_drops_the_imported_turns_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = _old_form_session(tmp_path, monkeypatch, window=6_000, n=30)
    cut = [e["payload"] for e in events if e["kind"] == "TranscriptCompacted"][-1]
    assert cut["dropped_seq_range"][0] == -120  # the oldest imported event
    assert cut["cleared_through_seq"] is not None
    second = [e["payload"]["text"] for e in events if e["kind"] == "PromptComposed"][-1]
    assert "imported message 0 " not in second and "imported message 29 " in second
    assert "USER: the first live message" in second and "USER: the second live message" in second
    assert cut["tokens_after"] <= int(6_000 * 0.6)

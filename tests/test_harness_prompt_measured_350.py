# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K350: a harness driver's prompt is counted by what the model reports (§ S.5).

The history window prices a prompt at four characters per token, corrected by the driver's
reported count. A harness reports one total for all its calls in a turn, so the correction was
fixed at 1.0 for it; Claude Code's stream reports each call's whole input on its `assistant`
events, and the first call's is the prompt Substrate sent. The continued session of 2026-11-14 ran
at about 2.27 characters per token and passed Claude Code's 1,000,000-token limit while Substrate
counted 585,096.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from substrate import api
from substrate.adapters.harness_streams import ClaudeStreamParser, StreamUsage
from substrate.adapters.models import CliResponder
from substrate.types import Event
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.__init__ import _usage_of
from substrate.adapters.models import ModelUsage
from substrate.topologies.session.views import TurnHistory
from substrate.topologies.session_registry import SessionManifest, SessionRegistry


def _call(input_tokens: int, cache_write: int, cache_read: int) -> str:
    usage = {
        "input_tokens": input_tokens,
        "cache_creation_input_tokens": cache_write,
        "cache_read_input_tokens": cache_read,
        "output_tokens": 5,
    }
    return json.dumps(
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "x"}], "usage": usage},
        }
    )


def test_the_parser_keeps_the_first_calls_whole_input() -> None:
    parser = ClaudeStreamParser()
    for line in (_call(2, 6082, 11595), _call(2, 81, 17677)):
        assert not [i for i in parser.feed(line) if isinstance(i, StreamUsage)]
    result = {
        "type": "result",
        "result": "done",
        "usage": {
            "input_tokens": 4,
            "cache_creation_input_tokens": 6163,
            "cache_read_input_tokens": 29272,
            "output_tokens": 10,
        },
    }
    (usage,) = [i for i in parser.feed(json.dumps(result)) if isinstance(i, StreamUsage)]
    assert usage.first_call_prompt_tokens == 17679  # measured on a real run, 2026-11-14
    assert usage.prompt_tokens == 35439  # the two calls added


def test_the_reply_carries_it_only_when_reported() -> None:
    usage = ModelUsage(model="claude", prompt_tokens=10, completion_tokens=1, wall_ms=0)
    assert "first_call_prompt_tokens" not in _usage_of(usage)
    assert _usage_of(usage, None, 17679)["first_call_prompt_tokens"] == 17679


def test_the_history_view_scales_by_the_first_call() -> None:
    view = TurnHistory(frozenset({"UserMessage", "ModelReply"}))
    view.update(
        Event(
            seq=1,
            kind="PromptComposed",
            schema="",
            producer=None,
            t=0.0,
            payload={"total_tokens": 1000},
        )
    )
    view.update(
        Event(
            seq=2,
            schema="",
            producer=None,
            t=0.0,
            kind="ModelReply",
            payload={
                "usage": {
                    "estimated": False,
                    "prompt_tokens": 50_000,
                    "first_call_prompt_tokens": 2000,
                }
            },
        )
    )
    state = view.value()
    assert state.first_call_scale == 2.0
    assert state.scale == 4.0  # the totals' ratio, clamped, as before; a harness no longer uses it


FAKE_HARNESS = """
import json, sys
data = sys.stdin.read()
# About two characters a token, as code and tool output run, against Substrate's four.
usage = {"input_tokens": len(data) // 2, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 3}
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}], "usage": usage}}))
print(json.dumps({"type": "result", "result": "ok", "usage": dict(usage, input_tokens=len(data))}))
"""


def _registry(tmp_path: Path, driver: CliResponder) -> SessionRegistry:
    def factory(manifest: SessionManifest, first_turn_user_message: Any = None) -> Any:
        return session_topology(
            driver=driver,
            driver_name="claude",
            driver_context_tokens=1000,
            seed="",
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


def test_a_harness_session_compacts_when_its_first_call_says_so(tmp_path: Path) -> None:
    script = tmp_path / "fake_harness.py"
    script.write_text(FAKE_HARNESS, encoding="utf-8")
    driver = CliResponder(
        [sys.executable, str(script)], name="claude", stream_format="claude-stream-json"
    )
    reg = _registry(tmp_path, driver)
    sid = "s_00000000000000d4"
    manifest = reg.create(
        session_id=sid,
        name=None,
        driver="claude",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="",
        make_repository=False,
    )
    for word in ("alpha", "bravo"):
        text = (
            word + " "
        ) * 170  # ~1,000 characters: ~250 tokens by Substrate's count, ~500 by the harness's

        def build(_m: SessionManifest, _root: Path, text: str = text) -> UserMessage:
            return UserMessage(
                text=text,
                turn_index=reg.next_turn_index(sid),
                assembled_prompt=text,
                slash_source="user",
            )

        reg.turn_sync(sid, resume_event_builder=build)
    events = list(api.read_record(manifest.record_root))
    replies = [e["payload"]["usage"] for e in events if e["kind"] == "ModelReply"]
    assert all(isinstance(u.get("first_call_prompt_tokens"), int) for u in replies)
    compacted = [e["payload"] for e in events if e["kind"] == "TranscriptCompacted"]
    assert compacted, "the second turn did not compact"
    assert compacted[-1]["token_scale"] >= 1.9

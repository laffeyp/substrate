# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K352: Substrate counts Claude's tokens (session vocabulary § AG).

The history window sized every prompt at four characters a token. A Claude Code session's prompt
of 2,337,585 characters counted 585,098 that way; Claude Code counted about 1,028,540 and refused
it. Now Anthropic's earlier published tokenizer counts every piece of text, and a session whose
driver speaks Claude Code's stream multiplies by 1.50, measured against Claude Code's exact counts
on code and prose. The head is counted at the same scale.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from substrate import api
from substrate.adapters.models import CliResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session import transcript
from substrate.topologies.session.token_count import CLAUDE_FACTOR, count_tokens
from substrate.topologies.session_registry import SessionManifest, SessionRegistry

# A stand-in for Claude Code: reads the prompt on stdin and answers in its stream's shape.
FAKE_CLAUDE = """
import json, sys
data = sys.stdin.read()
usage = {"input_tokens": len(data), "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 1}
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}], "usage": usage}}))
print(json.dumps({"type": "result", "result": "ok", "usage": usage}))
"""
CODE = "def f(x):\n    return x + 1\n" * 40  # 1,080 characters, 440 tokens
PROSE = "alpha " * 170  # 1,020 characters, 171 tokens
SEED = "SEED " * 400  # 2,000 characters, 800 tokens


def test_the_tokenizer_counts() -> None:
    assert count_tokens("hello world") == 2  # [9381, 2253], the tokenizer's own card
    assert count_tokens("") == 0
    assert (count_tokens(CODE), count_tokens(PROSE), count_tokens(SEED)) == (440, 171, 800)
    assert CLAUDE_FACTOR == 1.5


def test_four_characters_a_token_is_gone() -> None:
    source = Path(transcript.__file__).read_text(encoding="utf-8")
    assert "_CHARS_PER_TOKEN" not in source and "_est_tokens" not in source


def _claude_session(
    tmp_path: Path, sid: str, window: int, seed: str, messages: tuple[str, ...]
) -> list[dict[str, Any]]:
    script = tmp_path / "fake_claude.py"
    script.write_text(FAKE_CLAUDE, encoding="utf-8")
    driver = CliResponder(
        [sys.executable, str(script)], name="claude", stream_format="claude-stream-json"
    )

    def factory(manifest: SessionManifest, first_turn_user_message: Any = None) -> Any:
        return session_topology(
            driver=driver,
            driver_name="claude",
            driver_context_tokens=window,
            seed=seed,
            tools={},
            per_turn="",
            max_turns=200,
            turn_max_steps=4,
            session_id=manifest.session_id,
            workspace_path=manifest.workspace,
            script=None,
            first_turn_user_message=first_turn_user_message,
        )

    reg = SessionRegistry(base=tmp_path / "sessions", session_topology_factory=factory)
    manifest = reg.create(
        session_id=sid,
        name=None,
        driver="claude",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed=seed,
        make_repository=False,
    )
    for text in messages:

        def build(_m: SessionManifest, _root: Path, text: str = text) -> UserMessage:
            return UserMessage(
                text=text,
                turn_index=reg.next_turn_index(sid),
                assembled_prompt=text,
                slash_source="user",
            )

        reg.turn_sync(sid, resume_event_builder=build)
    return list(api.read_record(manifest.record_root, resolve_blobs=True))


def test_a_claude_session_compacts_at_the_measured_factor(tmp_path: Path) -> None:
    # Budget 1,200. Two turns of 440-token code are about 895 by the tokenizer, under it; at 1.50
    # they are about 1,340, over it, so the second turn's prompt drops the first.
    events = _claude_session(tmp_path, "s_00000000000000f1", 2000, "", (CODE, CODE))
    (cut,) = [e["payload"] for e in events if e["kind"] == "TranscriptCompacted"]
    assert cut["token_scale"] == CLAUDE_FACTOR and cut["dropped_seq_range"] is not None
    assert cut["tokens_after"] <= 1200 < cut["tokens_before"]
    prompts = [e["payload"] for e in events if e["kind"] == "PromptComposed"]
    assert prompts[-1]["text"].count("return x + 1") == 40  # the second message alone
    assert prompts[-1]["total_tokens"] == count_tokens(prompts[-1]["system"]) + count_tokens(
        prompts[-1]["text"]
    )


def test_the_head_is_counted_at_the_same_scale(tmp_path: Path) -> None:
    # Budget 1,260. An 800-token seed is 1,200 at 1.50 and leaves 60 for history, so the second
    # turn's prompt drops the first. Counted unscaled, the seed would leave 460 and keep it.
    events = _claude_session(tmp_path, "s_00000000000000f2", 2100, SEED, (PROSE, "hi"))
    (cut,) = [e["payload"] for e in events if e["kind"] == "TranscriptCompacted"]
    assert cut["dropped_seq_range"] is not None
    assert cut["tokens_after"] >= int(800 * CLAUDE_FACTOR)
    last = [e["payload"]["text"] for e in events if e["kind"] == "PromptComposed"][-1]
    assert "alpha alpha" not in last and "USER: hi" in last

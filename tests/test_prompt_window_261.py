# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K261: the prompt's history window, sized from the turns' rendered size (lens F098).

Replaces the render_transcript tests, which pinned the retired rule of 800 tokens a turn. The
contract they protected stands: nothing drops when the history fits; when it does not, the
oldest turns drop first, the dropped range is contiguous and below the kept range, the current
turn always stays, and the trimmed prompt is smaller than the untrimmed one.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from substrate import api
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session import transcript
from substrate.topologies.session.transcript import compose_model_prompt


def _turns(n: int, words: int = 1) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seq = 10
    for i in range(n):
        pad = " ".join(["word"] * words)
        events.append(
            {
                "seq": seq,
                "kind": "UserMessage",
                "payload": {"text": f"user {i} {pad}", "turn_index": i},
            }
        )
        events.append(
            {
                "seq": seq + 1,
                "kind": "ModelReply",
                "payload": {"text": f"reply {i} {pad}", "turn_index": i},
            }
        )
        seq += 2
    return events


class _Compaction:
    def __init__(self, dropped: tuple[int, int], kept_from: int, before: int, after: int) -> None:
        self.dropped_seq_range, self.kept_seq_start = dropped, kept_from
        self.tokens_before, self.tokens_after = before, after


def _compose(history: list[dict[str, Any]], ctx: int) -> tuple[str, list[Any]]:
    """What the model triggers and model step do (K268): price each turn, choose the window,
    build the prompt from the kept turns."""
    turns = transcript._group_by_turn(history)
    costs = [transcript.turn_cost(t) for t in turns]
    head, _ = transcript.head_block("SEED", "", [])
    keep = transcript.plan_window(costs, transcript._est_tokens(head), ctx, 0.6)
    kept = [e for t in turns[keep:] for e in t]
    prompt, _seqs = compose_model_prompt(history=kept, seed="SEED", per_turn="", fragments=[])
    compaction: list[Any] = []
    if keep > 0:
        compaction.append(
            _Compaction(
                (turns[0][0]["seq"], turns[keep][0]["seq"] - 1),
                turns[keep][0]["seq"],
                transcript._est_tokens(head) + sum(costs),
                transcript._est_tokens(prompt),
            )
        )
    return prompt, compaction


def test_nothing_drops_when_the_history_fits() -> None:
    prompt, compaction = _compose(_turns(3), 200_000)
    assert compaction == []
    assert all(f"user {i}" in prompt for i in range(3))


def test_the_oldest_turns_drop_first_and_the_current_turn_stays() -> None:
    # Twenty exchanges of about 300 words each overflow an 8,192-token window (60% headroom).
    history = _turns(20, words=150)
    prompt, compaction = _compose(history, 8_192)
    assert len(compaction) == 1
    comp = compaction[0]
    kept = [i for i in range(20) if f"user {i} " in prompt]
    assert kept and kept == list(range(kept[0], 20)), (
        kept
    )  # a contiguous tail ending at the current turn
    assert 19 in kept and 0 not in kept
    assert comp.dropped_seq_range[0] == 10  # turn 0's UserMessage
    assert comp.dropped_seq_range[0] <= comp.dropped_seq_range[1] < comp.kept_seq_start
    assert comp.kept_seq_start == history[2 * kept[0]]["seq"]
    assert comp.tokens_after < comp.tokens_before


def test_the_current_turn_stays_even_when_alone_it_overflows() -> None:
    # The current turn pastes a file of about 30,000 characters, larger than the whole window.
    history = _turns(3, words=6_000)
    prompt, compaction = _compose(history, 8_192)
    assert "user 2 " in prompt
    assert "user 0 " not in prompt and "user 1 " not in prompt
    assert len(compaction) == 1


class _Echo:
    name = "echo"

    def respond(self, prompt: str) -> str:
        return "a reply " + "word " * 200


def test_a_session_that_overflows_records_the_compaction(tmp_path: Path) -> None:
    root = tmp_path / "record"
    for i in range(20):
        um = UserMessage(
            text=f"turn {i} " + "word " * 100,
            turn_index=i,
            assembled_prompt="",
            slash_source="chat",
        )
        topo = session_topology(
            driver=_Echo(),
            driver_name="echo",
            driver_context_tokens=8_192,
            seed="SEED",
            tools={},
            session_id="s_window",
            workspace_path=str(tmp_path),
            first_turn_user_message=um if i == 0 else None,
        )
        rt = api.Runtime(root, persistent=True)
        asyncio.run(rt.run(topo, name="session") if i == 0 else rt.resume(topo, resume_event=um))
    compactions = [e for e in api.read_record(root) if e["kind"] == "TranscriptCompacted"]
    assert compactions, "twenty 300-word exchanges at an 8,192-token window recorded no compaction"
    for e in compactions:
        lo, hi = e["payload"]["dropped_seq_range"]
        assert lo <= hi < e["payload"]["kept_seq_start"]

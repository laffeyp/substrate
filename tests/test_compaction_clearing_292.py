# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K292: compaction clears old tool output first (session vocabulary § S).

Before: once the history passed the budget, whole turns dropped, oldest first, the user's requests
and the replies with them, and old tool outputs rode in full until their turn dropped. A codex
session lost its first two turns, a deep review among them, to one heavy turn of file reads.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from substrate import api
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.transcript import (
    TURN_EVENT_KINDS,
    compose_model_prompt,
    plan_history,
)
from substrate.topologies.tool_loop.tools import Tool

# ── the plan ─────────────────────────────────────────────────────────────────


def _turn(seq: int, base: int, outputs: int, each: int) -> tuple[int, int, list[tuple[int, int]]]:
    """A turn starting at `seq` costing `base` plus `outputs` results of `each` tokens."""
    savings = [(seq + 2 * (i + 1), each) for i in range(outputs)]
    return (seq, base + outputs * each, savings)


def test_under_the_budget_nothing_changes() -> None:
    plan = plan_history([_turn(10, 100, 2, 50)], 0, 10_000, 0.6, None)
    assert plan.keep_from == 0 and plan.cleared_through is None


def test_over_the_budget_old_outputs_clear_until_half_the_budget() -> None:
    turns = [_turn(10, 100, 10, 500), _turn(40, 100, 1, 50)]
    plan = plan_history(turns, 0, 10_000, 0.6, None)  # budget 6,000; history 5,250 + 150
    assert plan.keep_from == 0 and plan.cleared_through is None
    turns = [_turn(10, 100, 20, 500), _turn(60, 100, 1, 50)]  # history 10,250
    plan = plan_history(turns, 0, 10_000, 0.6, None)
    assert plan.keep_from == 0
    assert plan.cleared_through is not None and plan.tokens_after - 0 <= 3_000
    assert all(s > plan.cleared_through for s, _t in turns[-1][2])  # the current turn's stay


def test_the_current_turns_newest_three_stay_whole() -> None:
    turns = [_turn(10, 100, 2, 50), _turn(20, 100, 20, 500)]  # a tool loop in the current turn
    plan = plan_history(turns, 0, 10_000, 0.6, None)
    newest = sorted(s for s, _t in turns[-1][2])[-3:]
    assert plan.cleared_through is not None and all(s > plan.cleared_through for s in newest)


def test_a_finished_turns_outputs_all_clear() -> None:
    """A heavy finished turn cannot push out earlier requests through its newest outputs."""
    turns = [_turn(10, 500, 0, 0), _turn(20, 500, 3, 19_000), _turn(40, 300, 0, 0)]
    plan = plan_history(turns, 3_000, 100_000, 0.6, None)
    assert plan.keep_from == 0 and plan.cleared_through is not None
    assert plan.tokens_after - 3_000 <= (60_000 - 3_000) // 2  # fits within half the budget


def test_the_cut_holds_still_until_the_budget_is_passed_again() -> None:
    turns = [_turn(10, 100, 20, 500), _turn(60, 100, 1, 50)]
    first = plan_history(turns, 0, 10_000, 0.6, None)
    grown = [*turns, _turn(70, 500, 2, 100)]  # still under the budget with the first cut
    again = plan_history(grown, 0, 10_000, 0.6, first.cleared_through)
    assert again.cleared_through == first.cleared_through and again.keep_from == 0


def test_whole_turns_drop_only_after_every_clearable_output_is_cleared() -> None:
    turns = [_turn(10 + 100 * i, 2_000, 3, 100) for i in range(6)]  # 2,300 a turn, base 2,000
    plan = plan_history(turns, 0, 10_000, 0.6, None)
    outputs = sorted(s for _a, _c, sav in turns for s, _t in sav)
    assert plan.keep_from > 0
    assert plan.cleared_through == outputs[-4]  # everything but the newest 3


def test_the_codex_case_keeps_every_turn() -> None:
    """Session s_b8dab6b0…: a small first turn, then a review that read files for ~145,000 tokens."""
    turns = [
        _turn(17, 2_000, 30, 300),
        _turn(90, 4_000, 60, 2_350),
        _turn(147, 600, 0, 0),
    ]
    plan = plan_history(turns, 3_000, 100_000, 0.6, None)
    assert plan.keep_from == 0  # both earlier requests and replies stay
    assert plan.tokens_after <= 60_000


# ── a session ────────────────────────────────────────────────────────────────

_BIG = "x" * 3_000


def _read(args: list[object]) -> str:
    return f"OUT-{args[0] if args else 0} {_BIG}"


_TOOLS = {
    "read": Tool(
        "read",
        "read(i) -> a long text",
        True,
        _read,
        schema={"type": "object", "properties": {"i": {"type": "integer"}}, "required": ["i"]},
    )
}


class _ReadsOnce:
    """Text mode: one `read` per turn, then an answer."""

    name = "reads-once"

    def respond(self, prompt: str) -> str:
        last_user = prompt.rfind("USER:")
        if "RESULT" in prompt[last_user:]:
            return "answered " + prompt[last_user + 6 : last_user + 12]
        n = prompt.count("USER:")
        return json.dumps({"name": "read", "arguments": {"i": n}})


def _session(root: Path, turns: int) -> None:
    for i in range(turns):
        um = UserMessage(
            text=f"request-{i}", turn_index=i, assembled_prompt="", slash_source="chat"
        )
        topo = session_topology(
            driver=_ReadsOnce(),
            driver_name="reads-once",
            driver_context_tokens=8_192,
            seed="SEED",
            tools=dict(_TOOLS),
            session_id="s292",
            workspace_path=str(root.parent),
            first_turn_user_message=um if i == 0 else None,
        )
        rt = api.Runtime(root, persistent=True)
        asyncio.run(rt.run(topo, name="session") if i == 0 else rt.resume(topo, resume_event=um))


def test_a_session_clears_tool_output_and_keeps_every_request(tmp_path: Path) -> None:
    root = tmp_path / "record"
    _session(root, 8)
    envs = list(api.read_record(root, resolve_blobs=True))
    prompts = [e for e in envs if e["kind"] == "PromptComposed"]
    last = prompts[-1]["payload"]["text"]
    assert all(f"USER: request-{i}" in last for i in range(8))
    assert "[cleared: read, seq" in last

    cuts = [e["payload"] for e in envs if e["kind"] == "TranscriptCompacted"]
    assert cuts and all(c["strategy"] == "tool_output_cleared" for c in cuts)
    keys = [(c["cleared_through_seq"], c.get("dropped_seq_range")) for c in cuts]
    assert all(a != b for a, b in zip(keys, keys[1:], strict=False))  # one event per change
    bounds = [c["cleared_through_seq"] for c in cuts]
    assert bounds == sorted(bounds)  # only moves forward
    assert len(cuts) < len(prompts)  # steps that keep the cut record nothing

    fires = [
        e
        for e in envs
        if e["kind"] == "substrate.TriggerFired" and e["payload"].get("factory") == "model"
    ]
    for fire, pc in zip(fires, prompts, strict=True):
        ticket = fire["payload"]["resolved_input"]["history_ref"]
        kept = [
            e
            for e in envs
            if ticket["from_seq"] <= e["seq"] <= ticket["to_seq"] and e["kind"] in TURN_EVENT_KINDS
        ]
        _system, expected, _ = compose_model_prompt(
            history=kept,
            seed="SEED",
            fragments=[],
            cleared_through=ticket.get("cleared_through"),
        )
        history_block = expected[expected.index("[transcript:") :]
        assert history_block in pc["payload"]["text"]  # the head carries the tool-suite fragment

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K268: the model step's recorded input is a ticket to its history, not a copy of it.

Before: every model step recorded the whole turn history in its input, so the record grew with
the square of the session's length. Now the input carries the record path and the kept seq
range; the model step reads those events back with `api.read_range`. The prompt built from the
ticket must equal one built from the full record over the same range.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from substrate import api
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.transcript import TURN_EVENT_KINDS, compose_model_prompt


class _Echo:
    name = "echo"

    def respond(self, prompt: str) -> str:
        return "a reply " + "word " * 200


def _session(root: Path, turns: int) -> None:
    for i in range(turns):
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
            session_id="s_ticket",
            workspace_path=str(root.parent),
            first_turn_user_message=um if i == 0 else None,
        )
        rt = api.Runtime(root, persistent=True)
        asyncio.run(rt.run(topo, name="session") if i == 0 else rt.resume(topo, resume_event=um))


def test_the_recorded_input_is_a_small_ticket_and_the_prompt_matches_the_record(
    tmp_path: Path,
) -> None:
    root = tmp_path / "record"
    _session(root, 20)
    envs = list(api.read_record(root, resolve_blobs=True))
    model_fires = [
        e
        for e in envs
        if e["kind"] == "substrate.TriggerFired" and e["payload"].get("factory") == "model"
    ]
    prompts = [e["payload"]["text"] for e in envs if e["kind"] == "PromptComposed"]
    assert len(model_fires) == len(prompts) == 20

    sizes = [len(json.dumps(e["payload"].get("resolved_input"))) for e in model_fires]
    assert max(sizes) < 400, sizes  # a ticket, flat as the session grows
    assert not any("input_blob" in e["payload"] for e in model_fires)

    for fire, prompt in zip(model_fires, prompts, strict=True):
        ticket = fire["payload"]["resolved_input"]["history_ref"]
        kept = [
            e
            for e in envs
            if ticket["from_seq"] <= e["seq"] <= ticket["to_seq"] and e["kind"] in TURN_EVENT_KINDS
        ]
        expected, _ = compose_model_prompt(history=kept, seed="SEED", per_turn="", fragments=[])
        assert prompt == expected

    compactions = [e for e in envs if e["kind"] == "TranscriptCompacted"]
    assert compactions, "twenty 300-word exchanges at 8,192 tokens recorded no compaction"

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K344, session vocabulary § AC: a UserMessage carries the things a view added to the message
(substrate-ui design D94). A message with none encodes as it did before; one with attachments
records them, and the model's prompt holds each attachment's text under the message."""

from __future__ import annotations

import asyncio
from pathlib import Path

import msgspec

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.session import Attachment, UserMessage, session_topology
from substrate.topologies.session.transcript import attachment_lines


def _um(text: str, attachments: tuple[Attachment, ...] = ()) -> UserMessage:
    return UserMessage(
        text=text, turn_index=0, assembled_prompt="", slash_source="chat", attachments=attachments
    )


def test_a_message_with_no_attachments_encodes_as_before() -> None:
    assert msgspec.json.encode(_um("hi")) == (
        b'{"text":"hi","turn_index":0,"assembled_prompt":"","slash_source":"chat"}'
    )


def test_attachment_lines_name_each_and_carry_its_text() -> None:
    lines = attachment_lines(
        [
            {
                "kind": "lines",
                "label": "cart.ts 85–89",
                "ref": "src/cart.ts",
                "span": [85, 89],
                "text": "a\nb",
            },
            {"kind": "image", "label": "logo.png", "ref": "logo.png"},
        ]
    )
    assert lines == [
        "[attached lines cart.ts 85–89]",
        "a\nb",
        "[end attached]",
        "[attached image logo.png]",
    ]
    assert attachment_lines(None) == []


def test_the_record_holds_the_attachments_and_the_model_reads_their_text(tmp_path: Path) -> None:
    att = Attachment(
        kind="lines", label="cart.ts 85–89", ref="src/cart.ts", span=(85, 89), text="total = 0"
    )
    topo = session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=8_192,
        seed="SEED",
        tools={},
        session_id="s344",
        workspace_path=str(tmp_path),
        first_turn_user_message=_um("why is the total zero?", (att,)),
    )
    root = tmp_path / "record"
    asyncio.run(api.Runtime(root).run(topo))
    events = list(api.read_record(root, resolve_blobs=True))
    um = next(e for e in events if e["kind"] == "UserMessage")
    assert um["payload"]["attachments"] == [
        {
            "kind": "lines",
            "label": "cart.ts 85–89",
            "ref": "src/cart.ts",
            "span": [85, 89],
            "text": "total = 0",
        }
    ]
    prompt = next(e for e in events if e["kind"] == "PromptComposed")["payload"]
    text = msgspec.json.encode(prompt).decode()
    assert "[attached lines cart.ts 85–89]" in text and "total = 0" in text

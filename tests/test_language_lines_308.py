# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 308: `substrate language <record>` measures every text of a session record.

A record is built with a driver that answers from a script, so each expected value is counted by
hand: two turns with a length change between them, then a delegate-written message.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from substrate import api, app
from substrate.cli import main
from substrate.language import profile
from substrate.language.profile import LIBRARY_VERSION
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.language_lines import Pairing, Stream

ROOT = Path(__file__).resolve().parents[1]
REPLIES = [
    "The service listens on port 8080. The config file sets it.",
    "The host is localhost. You can change it in the same file, next to the port.",
    "Done.",
]


class Scripted:
    name = "scripted"

    def __init__(self) -> None:
        self.n = 0

    def respond(self, prompt: str) -> str:
        reply = REPLIES[self.n]
        self.n += 1
        return reply


def _turn(root: Path, driver: Scripted, text: str, turn: int, slash: str, length: str) -> None:
    um = UserMessage(text=text, turn_index=turn, assembled_prompt="", slash_source=slash)
    topo = session_topology(
        driver=driver,
        driver_name="scripted",
        driver_context_tokens=100_000,
        seed="SEED",
        tools={},
        session_id="s_308",
        workspace_path=str(root.parent),
        first_turn_user_message=um if turn == 0 else None,
        length=length,
        tone="neutral",
    )
    rt = api.Runtime(root, persistent=True)
    asyncio.run(rt.run(topo, name="session") if turn == 0 else rt.resume(topo, resume_event=um))


def _record(tmp_path: Path) -> Path:
    root, driver = tmp_path / "record", Scripted()
    _turn(root, driver, "What port does the service use?", 0, "chat", "terse")
    _turn(root, driver, "And the host?", 1, "chat", "full")
    _turn(root, driver, "Summarise the config for the parent.", 2, "delegate", "full")
    return root


def _lines(root: Path) -> list[dict[str, Any]]:
    return list(app.language_lines(root))


def test_every_text_gets_a_line_in_record_order(tmp_path: Path) -> None:
    lines = _lines(_record(tmp_path))
    streams = [
        (line["stream"], line.get("turn")) for line in lines if line["stream"] != Stream.COMPOSED
    ]
    assert streams == [
        ("user", 0),
        ("model", 0),
        ("relation", 0),
        ("relation", 0),
        ("user", 1),
        ("model", 1),
        ("relation", 1),
        ("relation", 1),
        ("delegate", 2),
        ("model", 2),
        ("relation", 2),
        ("relation", 2),
    ]
    assert sum(1 for line in lines if line["stream"] == Stream.COMPOSED) == 3
    assert [line["seq"] for line in lines] == sorted(line["seq"] for line in lines)


def test_values_by_hand(tmp_path: Path) -> None:
    lines = _lines(_record(tmp_path))
    user0 = next(x for x in lines if x["stream"] == Stream.USER and x["turn"] == 0)
    model0 = next(x for x in lines if x["stream"] == Stream.MODEL and x["turn"] == 0)
    model1 = next(x for x in lines if x["stream"] == Stream.MODEL and x["turn"] == 1)
    assert user0["values"]["text"]["words"] == 6
    assert model0["values"]["text"]["words"] == 11 and model0["values"]["text"]["sentences"] == 2
    # The model's trailing window holds both replies: 11 + 16 words.
    assert model1["values"]["window"]["window_words"] == 27
    assert model1["values"]["window"]["window_texts"] == 2
    final0 = next(
        x
        for x in lines
        if x["stream"] == Stream.RELATION and x["turn"] == 0 and x["pairing"] == Pairing.FINAL
    )
    assert final0["values"]["length_ratio"] == 11 / 6
    assert final0["values"]["lsm"] is None  # far under 1,600 words a side
    assert model0["stop_reason"] == "end_turn" and model0["step"] == 0
    assert model0["values"]["text"] == profile(REPLIES[0]).measures


def test_a_length_change_shows_on_the_lines_after_it(tmp_path: Path) -> None:
    lines = _lines(_record(tmp_path))
    by = {
        (x["stream"], x.get("turn")): x for x in lines if x["stream"] in (Stream.USER, Stream.MODEL)
    }
    assert by[("model", 0)]["setting_length"] == "terse"
    # The change is recorded after turn 1's message and before its reply.
    assert by[("user", 1)]["setting_length"] == "terse"
    assert by[("model", 1)]["setting_length"] == "full"


def test_a_delegate_message_is_its_own_stream_and_stays_out_of_the_user_window(
    tmp_path: Path,
) -> None:
    lines = _lines(_record(tmp_path))
    delegate = next(x for x in lines if x["stream"] == Stream.DELEGATE)
    assert delegate["slash_source"] == "delegate" and "window" not in delegate["values"]
    user1 = next(x for x in lines if x["stream"] == Stream.USER and x["turn"] == 1)
    assert user1["values"]["window"]["window_words"] == 6 + 3


def test_every_line_names_its_provenance_and_keys(tmp_path: Path) -> None:
    for line in _lines(_record(tmp_path)):
        assert line["preprocessing"] == "substrate-text-1" and line["library"] == LIBRARY_VERSION
        assert line["minimums"]["lsm_words"] == 1600 and "liwc2007" in line["lexicons"]
        assert line["session_id"] == "s_308" and line["topology"] == "session"
        assert line["guidance_sha256"] is None or len(line["guidance_sha256"]) == 64


def test_the_record_is_unchanged_and_two_runs_give_the_same_bytes(tmp_path: Path) -> None:
    root = _record(tmp_path)

    def digest() -> str:
        h = hashlib.sha256()
        for f in sorted(root.rglob("*")):
            if f.is_file():
                h.update(f.name.encode() + f.read_bytes())
        return h.hexdigest()

    before = digest()
    first = [app.line_json(x) for x in app.language_lines(root)]
    second = [app.line_json(x) for x in app.language_lines(root)]
    assert first == second and digest() == before
    assert all(json.loads(x) == json.loads(app.line_json(json.loads(x))) for x in first)


def test_the_cli_writes_the_same_lines(tmp_path: Path) -> None:
    root = _record(tmp_path)
    out = tmp_path / "lines.jsonl"
    result = CliRunner().invoke(main, ["language", str(root), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_text(encoding="utf-8").splitlines() == [
        app.line_json(x) for x in app.language_lines(root)
    ]


def test_the_experiment_replies_profile() -> None:
    count = 0
    for folder in ("length_drift_2026-10-12", "length_drift_2026-10-12_k299"):
        for f in sorted((ROOT / "process/runs/assays" / folder).glob("*.jsonl")):
            for line in f.open(encoding="utf-8"):
                profile(json.loads(line)["text"])
                count += 1
    assert count == 1200

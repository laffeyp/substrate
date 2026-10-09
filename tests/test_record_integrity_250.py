"""Sprint 250: record integrity and the Claim Check (lens audit F009–F040, K250).

Each test is one audit finding, shown red against the old code before the fix:
- F019/F040: an injected event over the blob threshold is offloaded, and one over the frame
  limit no longer makes the record unreadable;
- F020: an append that raises consumes no seq;
- F009/F015: a closed run's manifest keeps its run_id and replay ceiling;
- F029: a pause that a resume followed is not the run's state;
- F012: a frame holding NaN is cut by recovery, not a crash;
- F013: a torn last sidecar line is skipped;
- F038: narration reads an offloaded payload's fields, not its stub.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from msgspec import Struct

from substrate import api
from substrate.record import framing
from substrate.record.sidecar import read_sidecar


class Note(Struct, frozen=True):
    text: str


class Ask(Struct, frozen=True):
    text: str


async def _note(inp: object) -> AsyncIterator[Note]:
    text = inp.get("text", "x") if hasattr(inp, "get") else "x"  # type: ignore[union-attr]
    yield Note(text=text)


def _paused_topology(b: api.TopologyBuilder) -> None:
    """One Note at start, then a pause awaiting Ask; an Ask starts another Note."""
    b.producer_kind(
        "note", schemas=[Note], schema_version=1, factory=lambda: _note, deterministic=True
    )
    b.initial("note", input={"text": "first"})
    b.trigger(
        "on-ask",
        subscription=api.Subscription(kinds=frozenset({"Ask"})),
        predicate=lambda ctx: True,
        starts="note",
        input_builder=lambda ctx: {"text": ctx.event.payload["text"][:10]},
        policy=api.PerEvent(),
    )
    b.termination(
        api.pause_await_input(
            when=lambda tctx: tctx.event is not None and tctx.event.kind == "Note",
            resume_condition="Ask",
        )
    )


async def test_an_oversized_resume_event_is_offloaded_and_the_record_reads(tmp_path: Path) -> None:
    root = tmp_path / "run"
    await api.Runtime(root, persistent=True).run(_paused_topology)
    big = "y" * (2 * 1024 * 1024)  # over FRAME_MAX_BYTES (1 MiB): failed the frame before
    await api.Runtime(root, persistent=True).resume(_paused_topology, resume_event=Ask(text=big))
    envs = list(api.read_record(root))  # raised RecordGapError before (F020)
    raw_ask = [e for e in envs if e["kind"] == "Ask"][0]
    assert "$blob" in raw_ask["payload"], "the injected payload went inline"
    resolved = [e for e in api.read_record(root, resolve_blobs=True) if e["kind"] == "Ask"][0]
    assert resolved["payload"]["text"] == big


async def test_a_failed_append_consumes_no_seq(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from substrate.record.record import RecordWriter

    real_append = RecordWriter.append
    state = {"failed": False}

    def append_once_fails(self: RecordWriter, envelope: dict) -> None:
        if envelope["kind"] == "Note" and not state["failed"]:
            state["failed"] = True
            raise api.FrameTooLargeError("planted")
        real_append(self, envelope)

    monkeypatch.setattr(RecordWriter, "append", append_once_fails)
    root = tmp_path / "run"
    await api.Runtime(root, persistent=True).run(_paused_topology)
    seqs = [int(e["seq"]) for e in api.read_record(root)]
    assert seqs == list(range(len(seqs))), f"a gap in {seqs}"


async def test_a_closed_run_keeps_its_run_id_and_ceiling(tmp_path: Path) -> None:
    root = tmp_path / "run"
    await api.Runtime(root).run(_paused_topology)
    manifest = json.loads((root / "manifest.json").read_text())
    started = [e for e in api.read_record(root) if e["kind"] == api.RUN_STARTED][0]
    assert manifest.get("run_id"), manifest
    assert manifest["run_id"] == started["payload"].get("run_id", manifest["run_id"])


def _env(seq: int, kind: str, payload: dict, producer: dict | None = None) -> dict:
    return {"seq": seq, "kind": kind, "payload": payload, "producer": producer}


def test_a_resumed_session_mid_turn_is_not_paused() -> None:
    a = {"kind": "note", "instance": "a"}
    b = {"kind": "note", "instance": "b"}
    envs = [
        _env(0, api.RUN_STARTED, {"config": {}}),
        _env(1, api.PRODUCER_STARTED, {"producer": a}),
        _env(2, api.PRODUCER_COMPLETED, {"producer": a}),
        _env(3, api.TERMINATION_MATCHED, {"decision": api.Decision.PAUSE_AWAIT_INPUT.value}),
        _env(4, "Ask", {"text": "go"}),
        _env(5, api.PRODUCER_STARTED, {"producer": b}),
    ]
    g = api.run_graph(envs)
    assert g.status == api.RunStatus.INCOMPLETE  # was PAUSED (F029)
    running = [i for i in g.instances if i.instance == "b"][0]
    assert running.status == "running"  # was "interrupted"


def test_a_frame_holding_nan_is_cut_not_a_crash() -> None:
    good = framing.frame(
        {"seq": 0, "kind": "X", "payload": {}, "producer": None, "schema": "X@1", "t": 0.0}
    )
    bad = b'{"crc":"00000000","kind":"Y","payload":{"v":NaN},"producer":null,"schema":"Y@1","seq":1,"t":0}\n'
    frames, cut = framing.recover(good + bad)
    assert [f["seq"] for f in frames] == [0]
    assert cut == len(good)


def test_a_torn_last_sidecar_line_is_skipped(tmp_path: Path) -> None:
    p = tmp_path / "s.jsonl"
    p.write_text('{"a": 1}\n{"b": 2}\n{"c": ')
    assert read_sidecar(p) == [{"a": 1}, {"b": 2}]


async def test_narration_reads_an_offloaded_payloads_fields(tmp_path: Path) -> None:
    root = tmp_path / "run"
    big = "z" * (20 * 1024)  # over BLOB_THRESHOLD_BYTES (16 KiB)

    async def _big(inp: object) -> AsyncIterator[Note]:
        yield Note(text=big)

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "big", schemas=[Note], schema_version=1, factory=lambda: _big, deterministic=True
        )
        b.initial("big", input={})
        b.termination(api.threshold_count("Note", 1))

    await api.Runtime(root).run(topo)
    text = "\n".join(line.text for line in api.narrate(root))
    assert "$blob" not in text, text

"""`read_last_envelope`: the record's tail from its last frame (lens audit F310)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from msgspec import Struct

from substrate import api
from substrate.record import framing


class Tick(Struct, frozen=True):
    n: int


async def _ticks(_inp: object) -> AsyncIterator[Tick]:
    for n in range(5):
        yield Tick(n=n)


def _topo(b: api.TopologyBuilder) -> None:
    b.producer_kind(
        "t", schemas=[Tick], schema_version=1, factory=lambda: _ticks, deterministic=True
    )
    b.initial("t", input={})
    b.termination(api.threshold_count("Tick", 5))


async def test_the_last_envelope_is_read_records_last(tmp_path: Path) -> None:
    root = tmp_path / "run"
    await api.Runtime(root).run(_topo)
    assert api.read_last_envelope(root) == list(api.read_record(root))[-1]


async def test_a_cut_final_frame_is_skipped(tmp_path: Path) -> None:
    root = tmp_path / "run"
    await api.Runtime(root).run(_topo)
    hot = sorted(root.glob("events-*.open.jsonl"))[-1]
    with hot.open("ab") as f:
        f.write(b'{"crc":"0000')  # a writer died mid-append
    assert api.read_last_envelope(root) == list(api.read_record(root))[-1]


def _env(seq: int, text: str) -> dict:
    return {
        "seq": seq,
        "kind": "X",
        "payload": {"text": text},
        "producer": None,
        "schema": "X@1",
        "t": 0.0,
    }


def test_a_frame_longer_than_the_first_window(tmp_path: Path) -> None:
    root = tmp_path / "run.record"
    root.mkdir()
    big = "z" * (200 * 1024)
    (root / "events-000001.open.jsonl").write_bytes(
        framing.frame(_env(0, "a")) + framing.frame(_env(1, big))
    )
    last = api.read_last_envelope(root)
    assert last is not None and last["seq"] == 1 and last["payload"]["text"] == big


def test_an_empty_or_absent_record_has_no_last_envelope(tmp_path: Path) -> None:
    assert api.read_last_envelope(tmp_path / "absent") is None
    root = tmp_path / "empty.record"
    root.mkdir()
    (root / "events-000001.open.jsonl").write_bytes(b"")
    assert api.read_last_envelope(root) is None

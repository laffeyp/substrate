# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K268: read a seq range of a record without reading the whole record."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from substrate.api import read_range
from substrate.errors import RecordGapError
from substrate.record import record as record_mod
from substrate.record.record import RecordWriter, read_record, sealed_segments


def _write(root: Path, n: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(record_mod, "SEGMENT_MAX_BYTES", 600)  # roll every few frames
    rec = RecordWriter(root)
    for seq in range(n):
        rec.append(
            {
                "seq": seq,
                "kind": "Note",
                "schema": "Note@1",
                "t": 0.0,
                "producer": None,
                "payload": {"i": seq, "text": "word " * 10},
            }
        )
    rec.close()


def test_a_range_returns_exactly_those_seqs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "rec"
    _write(root, 60, monkeypatch)
    assert len(sealed_segments(root)) >= 5  # the test spans several sealed segments
    got = list(read_range(root, 20, 33))
    assert [e["seq"] for e in got] == list(range(20, 34))
    full = {e["seq"]: e for e in read_record(root)}
    assert got == [full[s] for s in range(20, 34)]


def test_segments_before_the_range_are_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "rec"
    _write(root, 60, monkeypatch)
    opened: list[str] = []
    real = record_mod._read_bytes_nofollow

    def spy(path: Path) -> Any:
        opened.append(Path(path).name)
        return real(path)

    monkeypatch.setattr(record_mod, "_read_bytes_nofollow", spy)
    list(read_range(root, 55, 59))
    sealed = [p.name for p in sealed_segments(root)]
    assert sealed[0] not in opened, opened
    assert len(opened) < len(sealed), (opened, sealed)


def test_a_range_past_the_end_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "rec"
    _write(root, 30, monkeypatch)
    with pytest.raises(RecordGapError):
        list(read_range(root, 25, 40))


def test_a_range_in_one_large_hot_segment_reads_from_the_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session record lives in one hot segment (segments roll at 64 MiB). Reading its newest
    turns must not read the whole file."""
    root = tmp_path / "rec"
    rec = RecordWriter(root)
    for seq in range(20_000):
        rec.append(
            {
                "seq": seq,
                "kind": "Note",
                "schema": "Note@1",
                "t": 0.0,
                "producer": None,
                "payload": {"i": seq, "text": "word " * 20},
            }
        )
    rec.close()
    assert sealed_segments(root) == []
    read: list[int] = []
    real_read = record_mod.os.read

    def counting_read(fd: int, n: int) -> bytes:
        data = real_read(fd, n)
        read.append(len(data))
        return data

    monkeypatch.setattr(record_mod.os, "read", counting_read)
    got = list(read_range(root, 19_990, 19_999))
    monkeypatch.setattr(record_mod.os, "read", real_read)
    assert [e["seq"] for e in got] == list(range(19_990, 20_000))
    size = sum(f.stat().st_size for f in root.glob("events-*.jsonl"))
    assert sum(read) < size / 4, (sum(read), size)

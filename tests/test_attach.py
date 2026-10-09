# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Live-attach follower tests (technical §13, F-PERS-4).

The follower is read-only by construction: it never opens a file for write, never takes
the lock, never signals the writer. These tests exercise (a) reading a closed record,
(b) following a record across simulated growth (partial tail ignored until complete), and
(c) the read-only guarantee (no .lock created, segment bytes + mtime unchanged)."""

import os

from msgspec import Struct

from substrate.api import (
    LiveRecord,
    Runtime,
    attach,
    read_record,
    threshold_count,
)


class CountReached(Struct, frozen=True):
    n: int


async def counter(_input):
    for n in range(1, 4):
        yield CountReached(n=n)


def _topo(b):
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.initial("counter", input=None)
    b.termination(threshold_count("substrate.ProducerCompleted", 1))


async def test_attach_reads_a_closed_record_in_seq_order(tmp_path):
    await Runtime(tmp_path / "run").run(_topo)
    live = attach(tmp_path / "run")
    got = live.read_new()
    expected = list(read_record(tmp_path / "run"))
    assert [e["seq"] for e in got] == [e["seq"] for e in expected]
    assert got[0]["kind"] == "substrate.RunStarted"
    assert got[-1]["kind"] == "substrate.RunFinalised"
    # a second read_new() yields nothing (cursors saturated)
    assert live.read_new() == []


async def test_follow_stops_at_run_finalised(tmp_path):
    await Runtime(tmp_path / "run").run(_topo)
    live = attach(tmp_path / "run", poll_ms=1)
    frames = list(live.follow(until_finalised=True))
    assert frames[-1]["kind"] == "substrate.RunFinalised"
    assert sum(1 for f in frames if f["kind"] == "substrate.RunFinalised") == 1


async def test_follower_ignores_a_partial_trailing_frame(tmp_path):
    # write a hot segment by hand with one complete frame + a torn partial line; the
    # follower must yield only the complete frame and leave the partial for a later poll.
    root = tmp_path / "run"
    root.mkdir()
    from substrate.record import framing

    complete = framing.frame(
        {"seq": 0, "kind": "X", "schema": "X@1", "producer": None, "t": 1.0, "payload": {"n": 1}}
    )
    hot = root / "events-000001.open.jsonl"
    hot.write_bytes(complete + b'{"seq":1,"kind":"X","sch')  # partial, no newline
    live = LiveRecord(root, poll_ms=1)
    got = live.read_new()
    assert [e["seq"] for e in got] == [0]  # only the complete frame
    # now complete the second frame; the follower picks it up without re-yielding seq 0
    rest = framing.frame(
        {"seq": 1, "kind": "X", "schema": "X@1", "producer": None, "t": 2.0, "payload": {"n": 2}}
    )
    hot.write_bytes(complete + rest)
    got2 = live.read_new()
    assert [e["seq"] for e in got2] == [1]


async def test_follow_across_a_segment_roll_no_duplicate_or_skipped_frames(tmp_path, monkeypatch):
    # BLOCKER regression (review #3): the cursor must key on the roll-stable segment INDEX,
    # not the basename. Force segment rolls by shrinking SEGMENT_MAX_BYTES, follow the live
    # record, and assert the followed seq stream is exactly the recorded one — no frame
    # re-yielded when a hot segment seals (`.open` dropped, index unchanged) and none skipped.
    import substrate.record.record as record_mod

    monkeypatch.setattr(record_mod, "SEGMENT_MAX_BYTES", 256)  # roll every few frames

    class Big(Struct, frozen=True):
        blob: str

    async def chatty(_input):
        for n in range(12):
            yield Big(blob=f"event-{n:03d}-{'x' * 40}")

    def big_topo(b):
        b.producer_kind("p", schemas=[Big], schema_version=1, factory=lambda: chatty)
        b.initial("p", input=None)
        b.termination(threshold_count("substrate.ProducerCompleted", 1))

    root = tmp_path / "run"
    await Runtime(root).run(big_topo)
    # confirm the run actually rolled into multiple sealed segments
    sealed = list(root.glob("events-*.jsonl"))
    sealed = [p for p in sealed if not p.name.endswith(".open.jsonl")]
    assert len(sealed) >= 1, "test did not produce a segment roll"

    recorded = [e["seq"] for e in read_record(root)]
    # follow the (now closed) record across all its segments via read_new in one shot
    followed = [e["seq"] for e in attach(root).read_new()]
    assert followed == recorded  # no duplicates, no skips, dense and in order
    assert len(followed) == len(set(followed))  # explicitly: no duplicate seq


async def test_follower_is_read_only_no_lock_no_mutation(tmp_path):
    # F-PERS-4: attaching + reading must not create a .lock, must not change the segment
    # bytes or mtime, must not write anything under the root.
    await Runtime(tmp_path / "run").run(_topo)
    root = tmp_path / "run"
    hot = next(root.glob("events-*.jsonl"))
    before_bytes = hot.read_bytes()
    before_mtime = hot.stat().st_mtime_ns
    before_listing = sorted(p.name for p in root.iterdir())

    live = attach(root)
    list(live.follow(until_finalised=True))  # full read

    assert hot.read_bytes() == before_bytes
    assert hot.stat().st_mtime_ns == before_mtime  # no write touched it
    assert sorted(p.name for p in root.iterdir()) == before_listing  # no new files
    assert not (root / ".lock").exists()  # the follower never takes the lock


async def test_follower_opens_files_read_only(tmp_path, monkeypatch):
    # assert, at the syscall level, that every os.open the follower issues is read-only
    # (no O_WRONLY/O_RDWR/O_APPEND/O_CREAT). The strongest form of the F-PERS-4 guarantee.
    await Runtime(tmp_path / "run").run(_topo)
    real_open = os.open
    seen_flags: list[int] = []

    def spy_open(path, flags, *a, **k):
        seen_flags.append(flags)
        return real_open(path, flags, *a, **k)

    monkeypatch.setattr("substrate.record.live.os.open", spy_open)
    live = attach(tmp_path / "run")
    live.read_new()
    assert seen_flags, "the follower opened at least one segment"
    write_bits = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT
    for f in seen_flags:
        assert f & write_bits == 0, f"follower opened a file with a write/create flag: {f:#o}"

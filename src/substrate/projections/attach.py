# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Live attach — the read-only follower (technical §13, F-PERS-4).

`attach(root)` opens a run record that may still be growing and lets a reader follow it
as the writer appends. The follower's contract is satisfied BY CONSTRUCTION (F-PERS-4):

  - it NEVER opens any file for writing (read-only file modes only),
  - it NEVER takes the persistent-bus lock,
  - it NEVER signals the writer.

Sealed segments are read in full (immutable forever). The hot (`.open`) segment is
tailed: read complete newline-terminated lines, CRC-verify each (the same §3.3 check as
recovery), and IGNORE the trailing partial line (a frame the writer has not finished).
Change detection is polling: the hot segment is append-only, so `stat().st_size` growth
is a complete signal that there is more to read (`POLL_INTERVAL_MS`, default 100).

This module is the read path under `substrate tail` (F-CLI-5) and the live inspection
surfaces; it emits nothing to the bus (F-OBS-6) and mutates nothing on disk.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..record import framing
from ..record.record import resolve_blob_payload
from ..constants import POLL_INTERVAL_MS, RUN_FINALISED


def _sealed_segments(root: Path) -> list[Path]:
    """Sealed segments in seq order (by filename), excluding the hot `.open` one."""
    return sorted(p for p in root.glob("events-*.jsonl") if not p.name.endswith(".open.jsonl"))


def _hot_segment(root: Path) -> Path | None:
    hot = sorted(root.glob("events-*.open.jsonl"))
    return hot[-1] if hot else None


def _segment_index(path: Path) -> int:
    """The numeric segment index from `events-NNNNNN[.open].jsonl`. ROLL-STABLE: a segment
    keeps its index when it seals (`.open` is dropped, the number is unchanged), so the
    follower's per-segment cursor must key on this — NOT the basename, which changes on
    seal and would otherwise reset the cursor to 0 and re-yield the whole segment."""
    return int(path.name.split("-", 1)[1].split(".", 1)[0])


class LiveRecord:
    """A read-only follower over a (possibly still-growing) run record (technical §13).

    Hold one per reader. `read_new()` returns every complete, CRC-valid frame appended
    since the last call (sealed segments first, then the recoverable prefix of the hot
    segment); the trailing partial line is ignored until it completes. `follow()` is a
    blocking generator that polls for growth. The follower opens files read-only, takes
    no lock, and never writes — F-PERS-4 by construction.
    """

    def __init__(
        self, root: Path | str, *, poll_ms: int = POLL_INTERVAL_MS, resolve_blobs: bool = False
    ) -> None:
        self.root = Path(root)
        self._poll_s = poll_ms / 1000.0
        # Sprint 095: True redeems blob Claim Checks (`resolve_blob_payload`) for readers
        # that consume payload contents; False yields frames exactly as stored.
        self._resolve_blobs = resolve_blobs
        # per-segment byte cursor, keyed by ROLL-STABLE segment INDEX (not basename): the
        # bytes of each segment we have already yielded. Keying on the index means a segment
        # tailed while hot keeps its cursor when it seals (`.open` dropped, index unchanged),
        # so frames are never re-yielded across a roll.
        self._cursors: dict[int, int] = {}

    def _read_segment_new(self, path: Path) -> Iterator[dict[str, Any]]:
        """Yield complete CRC-valid frames in `path` past our cursor. INCREMENTAL: seek to
        the cursor and read only the NEW tail bytes (O(new), not O(filesize) per poll — the
        hot segment can reach SEGMENT_MAX_BYTES). A single \\n-scan via framing.recover is the
        one source of truth for both hot and sealed segments: it yields complete CRC-valid
        frames and returns how many bytes they consumed, leaving any partial trailing line
        (only possible on the hot segment) for a later poll. The cursor is keyed by the
        roll-stable segment INDEX, so a segment tailed while hot keeps its cursor when it
        seals."""
        # Read-only. O_NOFOLLOW where available; never O_WRONLY/O_RDWR/O_APPEND.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
        except FileNotFoundError:
            return
        idx = _segment_index(path)
        start = self._cursors.get(idx, 0)
        try:
            size = os.fstat(fd).st_size
            if start >= size:
                return  # no growth since last poll (the st_size-growth signal, §13)
            os.lseek(fd, start, os.SEEK_SET)  # read only the new tail, not the whole file
            window = _read_all(fd)
        finally:
            os.close(fd)
        # framing.recover stops at the first unterminated/torn line and returns the bytes of
        # the complete frames; on a sealed segment there is no partial tail so it consumes all.
        frames, consumed = framing.recover(window)
        self._cursors[idx] = start + consumed
        yield from frames

    def _redeem(self, env: dict[str, Any]) -> dict[str, Any]:
        payload = env.get("payload")
        resolved = resolve_blob_payload(payload, self.root)
        return env if resolved is payload else {**env, "payload": resolved}

    def read_new(self) -> list[dict[str, Any]]:
        """Every complete frame appended since the last call, in seq order: all sealed
        segments (newly-appearing ones are picked up), then the recoverable prefix of the
        hot segment. A sealed segment is read once and not re-read (its cursor saturates)."""
        out: list[dict[str, Any]] = []
        for seg in _sealed_segments(self.root):
            out.extend(self._read_segment_new(seg))
        hot = _hot_segment(self.root)
        if hot is not None:
            out.extend(self._read_segment_new(hot))
        if self._resolve_blobs:
            out = [self._redeem(env) for env in out]
        return out

    def follow(self, *, until_finalised: bool = True) -> Iterator[dict[str, Any]]:
        """Blocking generator: yield frames as they appear, polling for growth. Stops after
        yielding a terminal `substrate.RunFinalised` when `until_finalised` (the default),
        else runs until the caller stops iterating. Polls `st_size` growth — the hot
        segment is append-only, so a size increase is a complete more-to-read signal."""
        while True:
            new = self.read_new()
            for env in new:
                yield env
                if until_finalised and env.get("kind") == RUN_FINALISED:
                    return
            time.sleep(self._poll_s)


def attach(
    root: Path | str, *, poll_ms: int = POLL_INTERVAL_MS, resolve_blobs: bool = False
) -> LiveRecord:
    """Open a read-only follower over a run record that may still be growing (technical
    §13, F-PERS-4). Read-only, lock-free, signal-free by construction. `resolve_blobs=True`
    redeems blob Claim Checks for readers that consume payload contents (Sprint 095)."""
    return LiveRecord(root, poll_ms=poll_ms, resolve_blobs=resolve_blobs)


def _read_all(fd: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 1 << 20)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)

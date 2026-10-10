# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The run record on disk: the writer, the reader, recovery, and the manifest
(technical spec §3, §5).

Directory layout (§3.1):

    <run-root>/
      manifest.json            advisory index; rebuildable from segments
      events-000001.jsonl      sealed segment — immutable forever
      events-000002.open.jsonl hot segment — append-only, exactly one
      blobs/sha256/...         content-addressed payloads
      sidecar/                 off-bus diagnostics / writer stats

Sealing happens on ROLL (a segment exceeding SEGMENT_MAX_BYTES), not on close: a
COMPLETE record is signalled by a terminal `substrate.RunFinalised` frame, and
recovery always runs on the single `.open` segment. (Reconciliation: design spec
§3.2 shows a finalised single-segment record whose hot segment is still `.open`;
technical §2 prose says "seal on finalise". We follow the design-spec invariant —
seal-on-roll only — because it keeps "completeness == terminal RunFinalised" and
"recovery operates on the .open segment" both true. Logged in BLACKBOARD.)

The manifest is ADVISORY; segments are AUTHORITATIVE. Every reader operates with the
manifest missing or stale (§3.5): the segment list is recoverable by globbing.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from msgspec import Struct

from ..constants import SEGMENT_MAX_BYTES
from ..errors import CRCMismatchError, FsyncError, RecordGapError, TornFrameError
from ..types import BlobRef
from . import framing
from .blobstore import BlobStore, fsync_dir


# ── fsync policies (technical §5.1; design §4.8) ───────────────────────────────
class NoFsync(Struct, frozen=True):
    """OS page cache only; the disk never bottlenecks (loss = whatever the OS last flushed)."""


class Interval(Struct, frozen=True):
    """fsync at most every `milliseconds` (default 100); amortized throughput."""

    milliseconds: int = 100


class Always(Struct, frozen=True):
    """fsync after every frame; zero complete frames lost, capped at device fsync rate."""


FsyncPolicy = NoFsync | Interval | Always


def _fullfsync_const() -> int | None:
    """macOS F_FULLFSYNC constant if available (durable flush THROUGH the drive cache,
    not just to it — technical §5.2). None on platforms without it (use os.fsync)."""
    try:
        import fcntl
    except ImportError:  # pragma: no cover - Windows
        return None
    const = getattr(fcntl, "F_FULLFSYNC", None)
    return const if isinstance(const, int) else None


class RecordWriter:
    """Owns the run record's segment files. The single writer is the only code that
    appends (technical §6). Callers pass complete envelopes WITHOUT a `crc` field
    (seq already assigned by the runtime's append cycle); the writer frames, writes,
    fsyncs per policy, and seals on roll.
    """

    def __init__(
        self,
        root: Path | str,
        *,
        fsync: FsyncPolicy = Interval(100),
        durable: bool | None = None,
        resume: bool = False,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "sidecar").mkdir(exist_ok=True)
        self.blobs = BlobStore(self.root)
        self._fsync = fsync
        # durable fsync (macOS F_FULLFSYNC) defaults on for `always`, off otherwise (§5.2)
        self._durable = isinstance(fsync, Always) if durable is None else durable
        self._last_fsync = time.monotonic()
        self._first_seq: int | None = None
        self._last_seq: int | None = None
        self._sealed: list[dict[str, Any]] = []
        # The manifest's ceiling and extra fields (run_id, …). A resumed record keeps what its
        # manifest already says until the runtime writes a new value.
        self._manifest_ceiling = "3a"
        self._manifest_extra: dict[str, Any] = {}
        if resume:
            self._load_manifest_fields()
        existing_hot = hot_segment(self.root) if resume else None
        if existing_hot is not None:
            # RESUME: continue the EXISTING hot segment (append-only) rather than opening a
            # fresh events-000001 — so a resumed run continues the same record/segment, and
            # seq continuity is preserved (the runtime restores next_seq from the log tail).
            # The torn tail (if any) was already recovered by the resume path before this.
            self._seg_index = segment_index(existing_hot)
            self._open_path = existing_hot
            self._seg_bytes = existing_hot.stat().st_size
            for seg in sealed_segments(self.root):  # rebuild the sealed-segment manifest list
                self._sealed.append({"file": seg.name})
        else:
            self._seg_index = 1
            self._open_path = self._segment_path(self._seg_index, hot=True)
            self._seg_bytes = 0
        self._fd = os.open(self._open_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
        fsync_dir(self.root)

    def _load_manifest_fields(self) -> None:
        path = self.root / "manifest.json"
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_bytes())
        except (OSError, ValueError):
            return  # an unreadable manifest is advisory; the log is the record
        if isinstance(data, dict):
            self._manifest_ceiling = str(data.get("replay_ceiling", "3a"))
            self._manifest_extra = {
                k: v
                for k, v in data.items()
                if k not in ("sealed_segments", "hot_segment", "replay_ceiling")
            }

    def _segment_path(self, index: int, *, hot: bool) -> Path:
        infix = ".open" if hot else ""
        return self.root / f"events-{index:06d}{infix}.jsonl"

    def put_blob(self, data: bytes) -> BlobRef:
        """Write-ahead a payload to the content-addressed blob store and return its BlobRef
        (technical §3.7). A Law-of-Demeter passthrough so callers (the runtime) do not reach
        through `.blobs`; the blob is fsynced before this returns, so it is durable before
        the referencing frame is appended."""
        return self.blobs.put(data)

    def append(self, envelope: dict[str, Any]) -> None:
        """Frame and append one event (envelope without crc). Applies the fsync policy
        and seals+rolls the segment when it exceeds SEGMENT_MAX_BYTES."""
        line = framing.frame(envelope)
        os.write(self._fd, line)
        self._seg_bytes += len(line)
        seq = envelope.get("seq")
        if isinstance(seq, int):
            if self._first_seq is None:
                self._first_seq = seq
            self._last_seq = seq
        self._maybe_fsync()
        if self._seg_bytes > SEGMENT_MAX_BYTES:
            self._seal_and_roll()

    def _maybe_fsync(self) -> None:
        if isinstance(self._fsync, Always):
            self._do_fsync()
        elif isinstance(self._fsync, Interval):
            now = time.monotonic()
            if (now - self._last_fsync) * 1000.0 >= self._fsync.milliseconds:
                self._do_fsync()
                self._last_fsync = now
        # NoFsync: nothing

    def _do_fsync(self) -> None:
        try:
            full = _fullfsync_const() if self._durable else None
            if full is not None:  # macOS durable flush (F_FULLFSYNC), not just fsync
                import fcntl

                fcntl.fcntl(self._fd, full)
            else:
                os.fsync(self._fd)
        except OSError as exc:
            # fsyncgate (§5.2): the medium is untrustworthy. Do NOT write RunFinalised
            # on it. Close without retrying fsync; the caller crashes the process.
            try:
                os.close(self._fd)
            except OSError:
                pass
            raise FsyncError(f"fsync failed on {self._open_path}: {exc}") from exc

    def _seal_and_roll(self) -> None:
        """Seal the hot segment (durable + rename + dir fsync) and open the next one
        (technical §3.2)."""
        # route the seal flush through _do_fsync so it honors the durable/F_FULLFSYNC policy AND the
        # fsyncgate (§5.2): on a seal-time medium failure it closes the fd and raises FsyncError (which
        # the runtime catches), instead of a bare os.fsync that leaves the fd open and gets retried at
        # close() — the "do not retry fsync after failure" invariant the rest of the writer honors.
        self._do_fsync()
        os.close(self._fd)
        sealed_path = self._segment_path(self._seg_index, hot=False)
        os.replace(self._open_path, sealed_path)
        fsync_dir(self.root)
        self._sealed.append(
            {"file": sealed_path.name, "first_seq": self._first_seq, "last_seq": self._last_seq}
        )
        self._seg_index += 1
        self._open_path = self._segment_path(self._seg_index, hot=True)
        self._fd = os.open(self._open_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
        fsync_dir(self.root)
        self._seg_bytes = 0
        self._first_seq = None
        self._last_seq = None
        self._write_manifest()

    def write_manifest(
        self, *, replay_ceiling: str | None = None, extra: dict[str, Any] | None = None
    ) -> None:
        """Set the manifest's replay ceiling and extra fields (run_id, …) and write it. They are
        kept on the record, so every later write (a segment roll, close) carries them; before
        2026-10-08 roll and close rewrote the manifest with the defaults, so no manifest on disk
        had a run_id and a 3b run read as 3a (lens audit F009, F015)."""
        if replay_ceiling is not None:
            self._manifest_ceiling = replay_ceiling
        if extra:
            self._manifest_extra.update(extra)
        self._write_manifest()

    def _write_manifest(self) -> None:
        manifest: dict[str, Any] = {
            **self._manifest_extra,
            "sealed_segments": self._sealed,
            "hot_segment": self._open_path.name,
            "replay_ceiling": self._manifest_ceiling,
        }
        tmp = self.root / "manifest.json.tmp"
        tmp.write_bytes(json.dumps(manifest, sort_keys=True).encode())
        os.replace(tmp, self.root / "manifest.json")
        fsync_dir(self.root)

    def close(self) -> None:
        """Final durable fsync + manifest write. The hot segment stays `.open`
        (seal-on-roll only); completeness is the terminal RunFinalised frame."""
        self._do_fsync()
        self._write_manifest()
        os.close(self._fd)


# ── reading & recovery ─────────────────────────────────────────────────────────
def sealed_segments(root: Path) -> list[Path]:
    return sorted(p for p in root.glob("events-*.jsonl") if not p.name.endswith(".open.jsonl"))


def hot_segment(root: Path) -> Path | None:
    hot = sorted(root.glob("events-*.open.jsonl"))
    return hot[-1] if hot else None


def segment_index(path: Path) -> int:
    """The numeric segment index from `events-NNNNNN[.open].jsonl` (roll-stable across seal)."""
    return int(path.name.split("-", 1)[1].split(".", 1)[0])


def _read_bytes_nofollow(path: Path) -> bytes:
    """Read a file's bytes read-only and WITHOUT following a symlink (§17: readers do not
    follow symlinks inside a run root). O_NOFOLLOW where the OS has it."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(fd)


def load_envelopes(record: Any, *, resolve_blobs: bool = False) -> list[dict[str, Any]]:
    """The one loader the record readers share: a record root (read, with blob stubs redeemed
    when `resolve_blobs`) or an iterable of envelopes (taken as given). Lens audit F036: five
    copies of this, two that resolved blobs and three that did not."""
    if isinstance(record, (str, Path)):
        return list(read_record(record, resolve_blobs=resolve_blobs))
    if isinstance(record, Iterable):
        return list(record)
    raise TypeError(
        f"expected a record root path or an iterable of envelopes, got {type(record)!r}"
    )


def has_torn_tail(root: Path | str) -> bool:
    """True when the hot segment ends inside a frame: a writer died mid-append. Every frame ends in
    a newline, so a non-empty hot segment whose last byte is not one holds a cut frame. Read-only
    (unlike `recover_open_segment`, which truncates the tail); `read_record` skips that frame."""
    hot = hot_segment(Path(root))
    if hot is None:
        return False
    data = _read_bytes_nofollow(hot)
    return bool(data) and not data.endswith(b"\n")


def read_first_envelope(root: Path | str) -> dict[str, Any] | None:
    """The record's first envelope (seq 0, normally `substrate.RunStarted`), reading and CRC-checking
    only its first line. None when the record has no complete first frame. For catalog-style
    readers that need one fact per record across thousands of records; `read_record` loads and
    verifies whole segments (UI sprint 097: list_records took 7.8 s over 4,394 sessions)."""
    root = Path(root)
    segs = sealed_segments(root)
    first = segs[0] if segs else hot_segment(root)
    if first is None:
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(first, flags)
    except OSError:
        return None
    with os.fdopen(fd, "rb") as f:
        line = f.readline()
    if not line.endswith(b"\n"):
        return None
    try:
        env = framing.verify_line(line[:-1])
    except (CRCMismatchError, TornFrameError):
        return None
    return env if int(env.get("seq", -1)) == 0 else None


def read_last_envelope(root: Path | str) -> dict[str, Any] | None:
    """The record's last complete envelope, reading backwards from the end of its newest segment
    and CRC-checking only that frame. A cut final frame (a writer died mid-append) is skipped, as
    `read_record` skips it. None when no segment holds a complete frame, or when the last complete
    frame fails its CRC; a caller that needs certainty then reads the whole record.

    Seqs are dense and append-only, so this frame's seq is the record's highest. The one
    disagreement with `read_record`: when the hot segment holds a corrupt frame BEFORE its last,
    `read_record` stops at the corruption and this still returns the last frame. For per-request
    tail cursors over long records (lens audit F310: the console read every session's whole record
    twice per turn to find this one number).
    """
    root = Path(root)
    segments = sorted(sealed_segments(root), key=segment_index)
    hot = hot_segment(root)
    if hot is not None:
        segments.append(hot)
    for seg in reversed(segments):
        line = _last_complete_line(seg)
        if line is None:
            continue
        try:
            return framing.verify_line(line)
        except (CRCMismatchError, TornFrameError):
            return None
    return None


def _last_complete_line(path: Path) -> bytes | None:
    """The last newline-terminated line of `path`, without its newline; None if it has none.
    Reads a window from the end and doubles it until the window holds a whole line."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return None
    with os.fdopen(fd, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        window = 64 * 1024
        while True:
            start = max(0, size - window)
            f.seek(start)
            data = f.read(size - start)
            end = data.rfind(b"\n")  # bytes after it are a cut frame, skipped
            if end == -1:
                if start == 0:
                    return None
                window *= 2
                continue
            begin = data.rfind(b"\n", 0, end)
            if begin == -1 and start > 0:
                window *= 2  # the line starts before this window
                continue
            return data[begin + 1 : end]


def _is_blob_stub(payload: Any) -> bool:
    return isinstance(payload, dict) and set(payload) == {"$blob", "bytes"}


def resolve_blob_payload(payload: Any, root: Path | str) -> Any:
    """Redeem a blob Claim Check (technical §3.7). A payload over BLOB_THRESHOLD_BYTES is stored
    in the record as `{"$blob": "sha256:<hex>", "bytes": n}`; this returns the payload it stands
    for, read from the run's blob store with its hash verified. Any other payload is returned
    unchanged.

    The ONE place a stub is redeemed (Hohpe & Woolf, Claim Check + Content Enricher). Every
    reader that consumes payload contents goes through it — live views get the inline payload
    from the sequencer, resumed views, replayed views, followers and record tools get it here —
    so the same event carries the same payload for every reader (Sprint 095). A missing or
    corrupt blob raises: it is data loss, as a seq gap is."""
    if not _is_blob_stub(payload):
        return payload
    ref = BlobRef(sha256=str(payload["$blob"]), bytes=int(payload["bytes"]))
    return json.loads(BlobStore(Path(root)).get(ref))


def _resolved(env: dict[str, Any], root: Path) -> dict[str, Any]:
    payload = env.get("payload")
    if not _is_blob_stub(payload):
        return env
    return {**env, "payload": resolve_blob_payload(payload, root)}


def read_record(root: Path | str, *, resolve_blobs: bool = False) -> Iterator[dict[str, Any]]:
    """Every recoverable envelope in seq order, exactly as stored. With `resolve_blobs=True`,
    a blob-stub payload is replaced by the payload it stands for (`resolve_blob_payload`):
    readers that consume payload CONTENTS pass True; integrity readers (replay, conformance,
    byte comparisons) keep the default and see the record as written."""
    if not resolve_blobs:
        yield from _read_record_raw(root)
        return
    root = Path(root)
    for env in _read_record_raw(root):
        yield _resolved(env, root)


def _read_record_raw(
    root: Path | str, *, hot_frames: list[dict[str, Any]] | None = None
) -> Iterator[dict[str, Any]]:
    """Yield every recoverable envelope in seq order: sealed segments (by filename),
    then the recoverable prefix of the hot segment. Does not depend on the manifest
    (segments are authoritative, §3.5). Read-only, symlink-not-followed (§17); does not
    modify anything.

    Validates seq contiguity on the read path (§3.5/§3.6): seqs are dense from 0, so a hole — a
    deleted sealed segment, a mid-frame-truncated one, or a sealed segment that lost its tail —
    raises RecordGapError instead of silently folding the loss away. The hot segment's torn tail is
    the one legitimate truncation (framing.recover trims it to the last good frame); a SEALED
    segment must be complete, so a non-newline-terminated sealed segment is data loss, not a tail.

    `hot_frames`, when given, are the hot segment's frames already recovered by the caller
    (`recover_and_read`), so the hot segment is not read and verified a second time."""
    root = Path(root)
    expected = 0

    def _checked(env: dict[str, Any]) -> dict[str, Any]:
        nonlocal expected
        seq = int(env.get("seq", -1))
        if seq != expected:
            raise RecordGapError(
                f"seq gap: expected {expected}, got {seq} — a sealed segment was lost or truncated "
                f"(data loss; per §3.6 a gap proves it)"
            )
        expected += 1
        return env

    for seg in sealed_segments(root):
        data = _read_bytes_nofollow(seg)
        if data and not data.endswith(b"\n"):
            raise RecordGapError(
                f"sealed segment {seg.name} has a torn tail — its last frame was truncated (data "
                f"loss). A sealed segment must be complete; only the hot segment may have a torn tail."
            )
        for offset, line in enumerate(data.splitlines(keepends=True)):
            if line.endswith(b"\n"):
                try:
                    env = framing.verify_line(line[:-1])
                except (CRCMismatchError, TornFrameError) as exc:
                    # a corrupt frame in a SEALED segment is data loss (the segment is supposed to be
                    # immutable + complete). Fatal, like a seq gap — but say WHERE (segment + line).
                    raise CRCMismatchError(
                        f"corruption in sealed segment {seg.name} at line {offset}: {exc}"
                    ) from exc
                yield _checked(env)
    if hot_frames is None:
        hot = hot_segment(root)
        hot_frames = framing.recover(_read_bytes_nofollow(hot))[0] if hot is not None else []
    for env in hot_frames:
        yield _checked(env)


def read_range(
    root: Path | str, from_seq: int, to_seq: int, *, resolve_blobs: bool = False
) -> Iterator[dict[str, Any]]:
    """The envelopes with `from_seq <= seq <= to_seq`, in seq order, without reading the whole
    record (K268). Sealed segments the manifest places wholly before the range are skipped and
    reading stops after `to_seq`; the manifest is advisory, so a segment it gives no bounds for is
    read. Every frame read is crc-checked; a missing seq in the range raises RecordGapError, as
    the full reader does. The record is append-only, so the same range always returns the same
    events: a Producer can be handed a ticket to a range of its own record (claim check).
    """
    root = Path(root)
    bounds: dict[str, tuple[int, int]] = {}
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest.get("sealed_segments", []):
            if isinstance(entry, dict) and "first_seq" in entry and "last_seq" in entry:
                bounds[str(entry["file"])] = (int(entry["first_seq"]), int(entry["last_seq"]))
    except (OSError, ValueError):
        pass
    expected = from_seq

    def _frames() -> Iterator[dict[str, Any]]:
        for seg in sealed_segments(root):
            span = bounds.get(seg.name)
            if span is not None and span[1] < from_seq:
                continue
            if span is not None and span[0] > to_seq:
                return
            data = _read_bytes_nofollow(seg)
            if data and not data.endswith(b"\n"):
                raise RecordGapError(f"sealed segment {seg.name} has a torn tail (data loss)")
            for offset, line in enumerate(data.splitlines(keepends=True)):
                try:
                    yield framing.verify_line(line[:-1])
                except (CRCMismatchError, TornFrameError) as exc:
                    raise CRCMismatchError(
                        f"corruption in sealed segment {seg.name} at line {offset}: {exc}"
                    ) from exc
        hot = hot_segment(root)
        if hot is not None:
            yield from _hot_tail_frames(hot, from_seq)

    for env in _frames():
        seq = int(env.get("seq", -1))
        if seq < from_seq:
            continue
        if seq != expected:
            raise RecordGapError(
                f"seq gap in range {from_seq}..{to_seq}: expected {expected}, got {seq}"
            )
        yield _resolved(env, root) if resolve_blobs else env
        expected += 1
        if expected > to_seq:
            return
    if expected <= to_seq:
        raise RecordGapError(f"seqs {expected}..{to_seq} are not on the record")


_TAIL_BLOCK = 256 * 1024


def _hot_tail_frames(path: Path, from_seq: int) -> list[dict[str, Any]]:
    """The hot segment's good frames from the one holding `from_seq` (or the file's start) on,
    read backwards from the end in blocks: a session's window is its newest turns, so this reads
    about as much as the window, not the whole segment. Same cut rule as `framing.recover`: the
    first unterminated or crc-invalid line ends the good frames (a torn tail)."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        pos = os.fstat(fd).st_size
        buf = b""
        while pos > 0:
            step = min(_TAIL_BLOCK, pos)
            pos -= step
            os.lseek(fd, pos, os.SEEK_SET)
            buf = os.read(fd, step) + buf
            start = 0 if pos == 0 else buf.find(b"\n") + 1
            if start == 0 and pos > 0:
                continue  # no line start in the buffer yet
            nl = buf.find(b"\n", start)
            if nl < 0:
                continue
            try:
                first = framing.verify_line(buf[start:nl])
            except (CRCMismatchError, TornFrameError):
                if pos == 0:
                    return []
                continue
            if int(first.get("seq", -1)) <= from_seq:
                buf = buf[start:]
                break
            if pos == 0:
                break
        frames: list[dict[str, Any]] = []
        for line in buf.splitlines(keepends=True):
            if not line.endswith(b"\n"):
                break
            try:
                frames.append(framing.verify_line(line[:-1]))
            except (CRCMismatchError, TornFrameError):
                break
        return frames
    finally:
        os.close(fd)


def _recover_hot(root: Path) -> list[dict[str, Any]] | None:
    """Recover the hot segment: its frames up to the last complete, crc-valid one, truncating
    whatever follows on disk. None when there is no hot segment."""
    hot = hot_segment(root)
    if hot is None:
        return None
    data = _read_bytes_nofollow(hot)
    frames, cut = framing.recover(data)
    if cut < len(data):
        fd = os.open(hot, os.O_RDWR)
        try:
            os.ftruncate(fd, cut)
            os.fsync(fd)
        finally:
            os.close(fd)
        fsync_dir(root)
    return frames


def recover_open_segment(root: Path | str) -> int:
    """Writer-side recovery (run at restart/attach, §3.3): truncate the hot segment to
    the last complete, crc-valid frame. Returns the number of frames kept. Sealed
    segments are never touched."""
    frames = _recover_hot(Path(root))
    return len(frames) if frames is not None else 0


def recover_and_read(root: Path | str, *, resolve_blobs: bool = False) -> list[dict[str, Any]]:
    """`recover_open_segment` then `read_record`, in one pass over the hot segment: a resume
    needs both, and each verified every frame (lens audit F017: a session turn read its whole
    record three times). Raises what `read_record` raises on a gap or a corrupt sealed segment."""
    root = Path(root)
    envs = list(_read_record_raw(root, hot_frames=_recover_hot(root) or []))
    return [_resolved(e, root) for e in envs] if resolve_blobs else envs

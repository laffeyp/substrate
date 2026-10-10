# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Typed exceptions raised before/around a run (design spec §6.3).

Things that happen *during* a run land on the log as events; these are the
small set of conditions the bus itself can't carry (registration, file/lock,
fsync, reentrancy). All carry the same kind of typed fields the log events would.
"""

from __future__ import annotations


class SubstrateError(Exception):
    """Base for all substrate-raised exceptions."""


class FrameTooLargeError(SubstrateError):
    """A framed event exceeds FRAME_MAX_BYTES; the payload belongs in the blob
    store (technical §3.3)."""


class TornFrameError(SubstrateError):
    """A frame line is unparseable or missing its crc (recovery cut point, §3.3)."""


class CRCMismatchError(SubstrateError):
    """A frame's recomputed crc32 does not match its stored crc (torn write, §3.3)."""


class RecordIncompleteError(SubstrateError):
    """A record has no terminal substrate.RunFinalised (e.g. torn at seq N, §5.2)."""


class RecordGapError(SubstrateError):
    """The read path found a hole in the seq sequence — a sealed segment lost (deleted, truncated
    mid-frame, or corrupted) so the yielded stream is non-contiguous. Per technical §3.5/§3.6 a gap
    proves data loss and the reader MUST report it rather than silently fold it away."""


class FsyncError(SubstrateError):
    """fsync failed; the medium is untrustworthy. The writer must NOT write
    RunFinalised on it — close, crash, let recovery report the truncated tail
    (technical §5.2, the fsyncgate lesson)."""


class BusLockedError(SubstrateError):
    """A persistent-bus root is already locked by another runtime (technical §11).
    Carries the advisory lock contents (pid, hostname, start time)."""

    def __init__(self, message: str, advisory: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.advisory = advisory or {}


class UnsupportedPlatformError(SubstrateError):
    """A correctness primitive is unavailable on this platform — e.g. persistent
    buses on Windows (technical §11; N-PORT-1). Raised at configuration time."""


class ReentrantAppendError(SubstrateError):
    """A submit() was reached synchronously from inside the append cycle
    (View/Predicate/input_builder/transform) — a programming bug (technical §6.2)."""


class InputTypeError(SubstrateError):
    """A resolved Producer input contains a type outside the accepted set (technical §8.3 /
    F-PROD-3, amended 2026-10-09): raw bytes, handles, datetimes, arbitrary objects, mutable
    Structs or non-string mapping keys. Each Producer receives its own copy of the recorded
    input, decoded from the canonical bytes the record holds."""


class ProducerNotFound(SubstrateError):
    """A provenance/inspection query named a Producer instance not in the record."""


class SequenceOutOfRange(SubstrateError):
    """A view_at / inspection query named a sequence number outside the record."""

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The frame format and torn-tail recovery (technical spec §3.3).

One event = one frame = one line. Two canonical forms exist per event and MUST be
kept distinct (§3.3):

  B_hash  — canonical bytes of the envelope WITHOUT `crc`. What content hashes and
            the crc are computed over.
  B_disk  — canonical bytes of the envelope WITH `crc` added. What lands on disk,
            what readers see, what `tail` displays. Under JCS key ordering `crc`
            lands at a deterministic position.

CRC32 (zlib polynomial, 8 lowercase hex digits) is a torn-write integrity check,
NOT authenticity; content hashes (sha256) do identity work. Recovery proves each
line independently: the first line that is unterminated, unparseable, or
crc-mismatched is the cut point, and everything before it is intact by construction.
"""

from __future__ import annotations

import json
import zlib
from typing import Any

import rfc8785

from ..constants import FRAME_MAX_BYTES
from ..encoding import to_canonical_builtins
from ..errors import CRCMismatchError, FrameTooLargeError, TornFrameError


def _crc8(data: bytes) -> str:
    """zlib crc32 rendered as exactly 8 lowercase hex digits (technical §3.3)."""
    return format(zlib.crc32(data) & 0xFFFFFFFF, "08x")


def frame(envelope: dict[str, Any]) -> bytes:
    """Build the on-disk frame (B_disk + b"\\n") for an envelope WITHOUT a crc field.

    Raises NonCanonicalValueError (via the whitelist) on a non-canonical payload,
    FrameTooLargeError if the framed line exceeds FRAME_MAX_BYTES, and ValueError if
    a `crc` is already present (the caller must pass the crc-less envelope).
    """
    if "crc" in envelope:
        raise ValueError("frame() expects an envelope WITHOUT a crc field (§3.3)")
    builtins = to_canonical_builtins(envelope)
    # FAIL-LOUD GUARD for the crc-splice below (byte-identity contract). The splice is correct
    # ONLY because "crc" sorts FIRST among the top-level envelope keys under JCS. If a FUTURE
    # top-level envelope key ever sorts before "crc" (a key starting < 'c', e.g. 'a'/'b'), the
    # splice would silently emit NON-canonical bytes — and a mis-spliced frame still passes
    # verify_line (order-independent), so it would slip every test except a byte-identity test
    # that happens to include the new key. Assert the precondition here so any such schema
    # change fails immediately and obviously rather than corrupting the canonical encoding.
    bad = [k for k in builtins if str(k) < "crc"]
    if bad:
        raise ValueError(
            f"frame() crc-splice precondition violated: top-level envelope key(s) {bad} sort "
            f"before 'crc' under JCS — the splice would emit non-canonical bytes. A new "
            f"envelope key sorting before 'crc' must use a full re-encode, not the splice."
        )
    b_hash = rfc8785.dumps(builtins)
    crc = _crc8(b_hash)
    # B_disk = B_hash with "crc" added (§3.3). Under JCS keys are sorted; "crc" sorts BEFORE
    # every current envelope key (seq/kind/schema/producer/t/payload), so B_disk is
    # byte-identically B_hash with `"crc":"<8hex>",` spliced right after the opening brace. We
    # splice instead of re-encoding the whole envelope a SECOND time through the pure-Python
    # rfc8785 encoder (the dominant per-frame cost) — halving rfc8785.dumps calls per frame.
    # Guarded above + asserted byte-identical in tests + the RFC-8785 conformance vectors.
    b_disk = b'{"crc":"' + crc.encode("ascii") + b'",' + b_hash[1:]
    line = b_disk + b"\n"
    if len(line) > FRAME_MAX_BYTES:
        raise FrameTooLargeError(
            f"frame is {len(line)} bytes > FRAME_MAX_BYTES ({FRAME_MAX_BYTES}); "
            f"oversized payloads belong in the blob store (§3.7)"
        )
    return line


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-JSON constant {name} in a frame")


def verify_line(line: bytes) -> dict[str, Any]:
    """Verify one frame line (no trailing newline) and return its crc-less envelope.

    Per §3.3 recovery: parse as JSON; strip `crc`; re-serialize the remainder per §4
    to recover B_hash; recompute crc32; compare. Raises TornFrameError (unparseable /
    no crc) or CRCMismatchError.
    """
    try:
        # NaN/Infinity are not JSON (RFC 8259) and never written by the framer; json.loads
        # accepts them, and the canonicalizer below then raised outside recover()'s catch, so a
        # corrupt frame crashed recovery instead of being cut (lens audit F012).
        obj = json.loads(line, parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise TornFrameError(f"unparseable frame line: {exc}") from exc
    if not isinstance(obj, dict) or "crc" not in obj:
        raise TornFrameError("frame line is not an object or has no crc field")
    stored_crc = obj["crc"]
    rest = {k: v for k, v in obj.items() if k != "crc"}
    recomputed = _crc8(rfc8785.dumps(to_canonical_builtins(rest)))
    if recomputed != stored_crc:
        raise CRCMismatchError(f"crc mismatch: stored {stored_crc!r}, recomputed {recomputed!r}")
    return rest


def recover(data: bytes) -> tuple[list[dict[str, Any]], int]:
    """Scan the bytes of a hot (.open) segment. Return (good_envelopes, cut_offset).

    cut_offset is the number of leading bytes that are intact, complete frames — the
    point to ftruncate to. Everything from cut_offset onward is a torn / partial tail.
    The first unterminated, unparseable, or crc-mismatched line is the cut point.
    """
    frames: list[dict[str, Any]] = []
    offset = 0
    n = len(data)
    while offset < n:
        nl = data.find(b"\n", offset)
        if nl == -1:
            break  # incomplete final line — torn tail
        try:
            frames.append(verify_line(data[offset:nl]))
        except (TornFrameError, CRCMismatchError):
            break  # corrupt frame — cut here
        offset = nl + 1
    return frames, offset

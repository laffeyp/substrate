# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Content-addressed blob store for oversized payloads (technical spec §3.7).

Payloads whose canonical encoding exceeds BLOB_THRESHOLD_BYTES are stored here and
referenced from the envelope as {"$blob": "sha256:<hex>", "bytes": n}. Rules:
write-ahead (the blob is fsynced BEFORE the referencing frame is appended); immutable
(a second write to an existing hash is skipped after a size check — dedup); the path
is derived from the hash ONLY (no user-controlled string ever becomes a path
component, §17); a two-level fan-out keeps directories small.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from ..errors import CRCMismatchError
from ..types import BlobRef

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def is_blob_hex(hex_digest: str) -> bool:
    """A sha256 digest is always exactly 64 lowercase hex chars. A record's `$blob` field is
    attacker-controllable, so any value that is NOT 64-hex is malformed or hostile and must never
    become a filesystem path component (review #20 — path-traversal → arbitrary file read)."""
    return bool(_SHA256_HEX.match(hex_digest))


class BlobStore:
    """The `blobs/sha256/<first-2-hex>/<full-hex>` tree under a run root."""

    def __init__(self, root: Path) -> None:
        # No mkdir here: a reader redeeming a stub must not create directories in the record it
        # reads; `put` creates what it writes.
        self._dir = Path(root) / "blobs" / "sha256"

    def _path_for(self, hex_digest: str) -> Path:
        # On the WRITE path hex_digest is content-derived; on the READ path (`get`) it comes from a
        # BlobRef that may originate in an ATTACKER-CONTROLLED record. Validate as 64-hex BEFORE it
        # becomes a path component, so a crafted "../" digest cannot traverse out of the blob tree
        # (review #20: the read path re-derived a path from a record field with no validation).
        if not is_blob_hex(hex_digest):
            raise ValueError(f"invalid blob digest (must be 64 lowercase hex): {hex_digest[:80]!r}")
        return self._dir / hex_digest[:2] / hex_digest

    def put(self, data: bytes) -> BlobRef:
        """Write-ahead store: the blob file is written and fsynced before the caller
        appends the referencing frame. Idempotent — an existing hash path is reused
        after a size check (dedup)."""
        hex_digest = hashlib.sha256(data).hexdigest()
        path = self._path_for(hex_digest)
        if path.exists():
            if path.stat().st_size != len(data):
                # Hash collision with differing size is effectively impossible for
                # sha256; treat a size mismatch as corruption rather than silently trust.
                raise OSError(f"blob {hex_digest} exists with mismatched size")
            return BlobRef(sha256=f"sha256:{hex_digest}", bytes=len(data))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
        fsync_dir(path.parent)
        return BlobRef(sha256=f"sha256:{hex_digest}", bytes=len(data))

    def get(self, ref: BlobRef) -> bytes:
        """Read a blob by reference, VERIFYING its content hash — the blob id IS the sha256 of its
        bytes, so a corrupted blob file is caught here, not returned as if valid. Symlinks not
        followed (§17)."""
        hex_digest = ref.sha256.removeprefix("sha256:")
        path = self._path_for(hex_digest)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            data = _read_all(fd)
        finally:
            os.close(fd)
        actual = hashlib.sha256(data).hexdigest()
        if actual != hex_digest:
            raise CRCMismatchError(
                f"blob {ref.sha256} content-hash mismatch (read bytes hash to sha256:{actual}) — corrupted blob"
            )
        return data


def _read_all(fd: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 1 << 20)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def fsync_dir(directory: Path) -> None:
    """fsync a directory so a create/rename is itself durable (technical §5.2)."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    dfd = os.open(directory, flags)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)

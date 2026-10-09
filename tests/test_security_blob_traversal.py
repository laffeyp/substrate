# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Security regression: a crafted record's $blob field must NOT path-traverse (review #20).

The reviewer's PoC: a record carrying `{"input_blob": {"$blob": "sha256:../../<abs path>"}}`
made `replay --level 2` read an arbitrary file (the digest was re-derived into a filesystem path
with no validation). A sha256 is always 64 lowercase hex; anything else must never become a path.
"""

import pytest

from substrate.projections.replay import _UNRESOLVABLE, _resolved_input_hash
from substrate.record.blobstore import BlobStore, is_blob_hex


def test_is_blob_hex_only_accepts_64_lowercase_hex():
    assert is_blob_hex("a" * 64)
    assert is_blob_hex("0123456789abcdef" * 4)
    assert not is_blob_hex("../../etc/passwd")
    assert not is_blob_hex("A" * 64)  # uppercase
    assert not is_blob_hex("a" * 63)  # too short
    assert not is_blob_hex("a" * 65)  # too long
    assert not is_blob_hex("/abs/path")


def test_replay_rejects_traversal_blob(tmp_path):
    # the exact PoC shape: a $blob that escapes the record root to a real file outside it.
    canary = tmp_path / "canary.txt"
    canary.write_text("TOP-SECRET-CANARY")
    root = tmp_path / "rec"
    (root / "blobs" / "sha256").mkdir(parents=True)
    payload = {"input_blob": {"$blob": f"sha256:../../../../../..{canary}"}}
    # the malicious digest is rejected -> _UNRESOLVABLE; the canary is NEVER read/hashed.
    assert _resolved_input_hash(payload, root) == _UNRESOLVABLE


def test_blobstore_path_for_rejects_non_hex(tmp_path):
    store = BlobStore(tmp_path / "rec")
    with pytest.raises(ValueError, match="invalid blob digest"):
        store._path_for("../../etc/passwd")
    # a real round-trip still works (the write path's content hash is valid 64-hex)
    ref = store.put(b"hello")
    assert store.get(ref) == b"hello"

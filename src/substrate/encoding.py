# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Canonical encoding — the bytes everything hashes over (technical spec §4).

The product promises byte-identical replay, content-hash citations, and divergence
comparison by payload hash. All three require that the same logical value always
serializes to the same bytes, on every OS and Python 3.12+ minor version. Python's
json.dumps does not promise this; RFC 8785 (JCS) does.

Pipeline (technical §4.1): value -> msgspec.to_builtins -> whitelist check -> rfc8785.dumps.
The whitelist (§4.2) is enforced HERE, before rfc8785, rather than relying on the
encoder to reject — JCS numbers are IEEE-754 doubles (integer precision is a
correctness landmine) and have no NaN/Inf form.

Two canonical forms exist per event and must be kept distinct (§3.3): B_hash is the
envelope WITHOUT the `crc` field (what content hashes are computed over); B_disk is
WITH `crc` (the on-disk frame). The crc assembly lives in the record layer; this
module provides the primitive `canonical_bytes` (= B_hash for a crc-less object) and
the content-hash helper.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import msgspec
import rfc8785

from .constants import JSON_SAFE_INT_MAX, JSON_SAFE_INT_MIN, InvalidReason


class NonCanonicalValueError(ValueError):
    """A value outside the JCS type whitelist (technical §4.2). Carries the JSON path
    of the offending node so emission can become substrate.ProducerEmittedInvalidEvent
    with reason `non_canonical_value` and `at_path` (§4.3)."""

    def __init__(self, message: str, at_path: str) -> None:
        super().__init__(f"{message} (at {at_path})")
        self.at_path = at_path


def _check(node: Any, path: str = "$") -> None:
    """Recursively enforce the §4.2 type whitelist on a builtins tree."""
    # bool is a subclass of int — must be tested first.
    if node is None or isinstance(node, bool):
        return
    if isinstance(node, int):
        if not (JSON_SAFE_INT_MIN <= node <= JSON_SAFE_INT_MAX):
            raise NonCanonicalValueError(
                f"int {node} outside JCS-safe range "
                f"[-(2^53-1), 2^53-1]; declare it as a string field",
                path,
            )
        return
    if isinstance(node, float):
        if node != node or node in (float("inf"), float("-inf")):
            raise NonCanonicalValueError("non-finite float (JCS has no NaN/Inf form)", path)
        return
    if isinstance(node, str):
        return
    if isinstance(node, (list, tuple)):
        for i, item in enumerate(node):
            _check(item, f"{path}[{i}]")
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str):
                raise NonCanonicalValueError(f"non-str dict key {key!r}", path)
            _check(value, f"{path}.{key}")
        return
    raise NonCanonicalValueError(f"type {type(node).__name__} is not in the JCS whitelist", path)


def to_canonical_builtins(obj: Any) -> Any:
    """msgspec.to_builtins(obj) with the §4.2 whitelist enforced. Accepts a msgspec
    Struct, a dict, or any builtins tree. Raises NonCanonicalValueError on violation."""
    builtins = msgspec.to_builtins(obj)
    _check(builtins)
    return builtins


def canonical_bytes(obj: Any) -> bytes:
    """The canonical RFC-8785 bytes for a value (= B_hash for a crc-less object).
    Deterministic: the same logical value yields identical bytes everywhere."""
    return rfc8785.dumps(to_canonical_builtins(obj))


def sha256_hex(data: bytes) -> str:
    """Content hash of raw bytes, formatted `sha256:<64 lowercase hex>` (§4.2)."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def content_hash(obj: Any) -> str:
    """The `sha256:<hex>` content hash over a value's canonical bytes — the identity
    used for blob ids, input_sha256, message_sha256, and D-8 comparison (§3.3)."""
    return sha256_hex(canonical_bytes(obj))


@dataclass(frozen=True)
class SafeCanonical:
    """The result of a guarded canonicalization attempt (`try_canonical`).

    `ok` is True iff the value passed the whole pipeline (`msgspec.to_builtins` +
    the §4.2 whitelist) AND re-encoding to bytes succeeded. When `ok`:
    `builtins`/`raw_bytes`/`hash`/`nbytes` are populated. When not `ok`: `reason`
    is the typed failure class (`unknown_kind` | `non_canonical_value`), `at_path`
    is the offending JSON path (when known), and `raw` is a never-crashing,
    canonical-safe rendering of the offending value for diagnostic preservation.
    """

    ok: bool
    builtins: Any = None
    raw_bytes: bytes = b""
    hash: str = ""
    nbytes: int = 0
    reason: InvalidReason | None = None
    at_path: str | None = None
    raw: Any = None


def safe_raw(obj: Any) -> Any:
    """A non-canonical-SAFE rendering of any value for diagnostic preservation.

    Used for the `raw_payload` of substrate.ProducerEmittedInvalidEvent and any other
    error-logging path: it must never itself re-introduce a value that crashes at
    frame-time (the §4.2 whitelist runs over it), so out-of-range ints, non-finite
    floats, non-str keys, and out-of-whitelist types are all stringified rather than
    passed through `msgspec.to_builtins` raw (which range-checks nothing)."""
    try:
        builtins = msgspec.to_builtins(obj)
    except Exception:  # noqa: BLE001 — diagnostic rendering of an arbitrary value must never raise
        return repr(obj)
    return _stringify_non_canonical(builtins)


def _stringify_non_canonical(node: Any) -> Any:
    """Recursively coerce a builtins tree into the §4.2 whitelist, stringifying any
    node that would fail (out-of-range int, NaN/Inf float, non-str key, foreign type)
    so the result is always safe to frame."""
    if node is None or isinstance(node, bool) or isinstance(node, str):
        return node
    if isinstance(node, int):
        if JSON_SAFE_INT_MIN <= node <= JSON_SAFE_INT_MAX:
            return node
        return repr(node)
    if isinstance(node, float):
        if node != node or node in (float("inf"), float("-inf")):
            return repr(node)
        return node
    if isinstance(node, (list, tuple)):
        return [_stringify_non_canonical(item) for item in node]
    if isinstance(node, dict):
        return {
            (key if isinstance(key, str) else repr(key)): _stringify_non_canonical(value)
            for key, value in node.items()
        }
    return repr(node)


def try_canonical(obj: Any) -> SafeCanonical:
    """Guarded canonicalization: run the full pipeline without ever raising.

    The single shared sanitize-or-log helper routed through every ingestion point that
    accepts user values (resolved trigger input, initial input, the invalid-emission
    raw payload, the PerKey firing key). On success returns the builtins, the canonical
    bytes, the `sha256:` hash, and the byte length (so the caller can blob-offload). On
    failure returns the typed reason/path plus a canonical-safe `raw` rendering — never
    an uncaught NonCanonicalValueError that would crash the writer."""
    try:
        builtins = msgspec.to_builtins(obj)
    except Exception as exc:  # noqa: BLE001 — the writer's ingestion boundary: any value, never a crash
        return SafeCanonical(ok=False, reason=InvalidReason.UNKNOWN_KIND, raw=repr(exc))
    try:
        _check(builtins)
    except NonCanonicalValueError as exc:
        return SafeCanonical(
            ok=False,
            reason=InvalidReason.NON_CANONICAL_VALUE,
            at_path=exc.at_path,
            raw=_stringify_non_canonical(builtins),
        )
    try:
        raw_bytes = rfc8785.dumps(builtins)
    except (
        rfc8785.CanonicalizationError
    ):  # pragma: no cover - the whitelist guarantees encodability
        return SafeCanonical(
            ok=False,
            reason=InvalidReason.NON_CANONICAL_VALUE,
            raw=_stringify_non_canonical(builtins),
        )
    return SafeCanonical(
        ok=True,
        builtins=builtins,
        raw_bytes=raw_bytes,
        hash=sha256_hex(raw_bytes),
        nbytes=len(raw_bytes),
    )

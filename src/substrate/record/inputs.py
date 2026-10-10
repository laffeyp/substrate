# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Producer input check — the accepted input types (technical §8.3 / F-PROD-3, amended K267).

A Producer input is built from: None, str, bool, int, float; lists and tuples; sets and
frozensets; mappings with string keys; frozen msgspec Structs; content-hash BlobRefs. Anything
else (raw bytes, open handles, datetimes, arbitrary objects, mutable Structs) raises
InputTypeError naming the exact path. Execution resources belong in topology configuration,
closed over by Producer factories.

The check only validates. Isolation is the kernel's job: it records the input's canonical bytes
and hands the Producer a fresh decode of those same bytes (kernel/sequencer.py
`_producer_input`), so the Producer runs with exactly what the record holds, as its own copy.
This replaced sealing (read-only MappingProxyType and tuples), which gave the Producer a second
form of every input and caused four bugs (sprints 049, 052, 053; K261).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from msgspec import Struct

from ..errors import InputTypeError
from ..types import BlobRef


def check_input(obj: Any, path: str = "$") -> None:
    """Raise InputTypeError (with the offending path) on a value outside the accepted types."""
    if obj is None or isinstance(obj, (str, bool, int, float, BlobRef)):
        return
    if isinstance(obj, Struct):
        if not getattr(type(obj), "__struct_config__").frozen:
            raise InputTypeError(f"non-frozen Struct {type(obj).__name__} at {path} (§8.3)")
        return
    if isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            check_input(item, f"{path}[{i}]")
        return
    if isinstance(obj, (set, frozenset)):
        for item in obj:
            check_input(item, f"{path}{{}}")
        return
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            if not isinstance(key, str):
                raise InputTypeError(f"non-str mapping key {key!r} at {path} (§8.3)")
            check_input(value, f"{path}.{key}")
        return
    if isinstance(obj, (bytes, bytearray)):
        raise InputTypeError(
            f"raw bytes at {path}: use a content-hash BlobRef or a fixed-size hex field (§4.2/§8.3)"
        )
    raise InputTypeError(
        f"value of type {type(obj).__name__} at {path} is not an accepted Producer input (§8.3); "
        "put execution resources in topology config"
    )

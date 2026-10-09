# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Record-assertion test helpers (F-API-4 / technical §15).

`assert_event` / `assert_no_event` / `assert_sequence` operate uniformly over a
recorded run record (a root path) or any iterable of envelope dicts — so a
confirmed-good run record is directly usable as a regression fixture, and the same
assertions work on a live attached record.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .record.record import load_envelopes


def _matches(env: dict[str, Any], kind: str, partial: dict[str, Any]) -> bool:
    if env.get("kind") != kind:
        return False
    payload = env.get("payload") or {}
    return all(isinstance(payload, dict) and payload.get(k) == v for k, v in partial.items())


def assert_event(rec: Any, kind: str, **partial: Any) -> dict[str, Any]:
    """Assert at least one event of `kind` with the given partial payload exists;
    return the first match. Raises AssertionError citing what was searched."""
    for env in load_envelopes(rec, resolve_blobs=True):
        if _matches(env, kind, partial):
            return env
    raise AssertionError(f"no event kind={kind!r} with payload⊇{partial}")


def assert_no_event(rec: Any, kind: str, **partial: Any) -> None:
    """Assert NO event of `kind` with the given partial payload exists; raises AssertionError
    citing the offending seq if one does."""
    for env in load_envelopes(rec, resolve_blobs=True):
        if _matches(env, kind, partial):
            raise AssertionError(f"unexpected event kind={kind!r} at seq={env.get('seq')}")


def assert_sequence(rec: Any, kinds: Sequence[str]) -> list[dict[str, Any]]:
    """Assert the record's event-kind sequence equals `kinds` exactly."""
    envs = load_envelopes(rec, resolve_blobs=True)
    got = [e.get("kind") for e in envs]
    if got != list(kinds):
        raise AssertionError(f"sequence mismatch:\n  expected {list(kinds)}\n  got      {got}")
    return envs

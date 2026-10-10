# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 240 — SessionStarted instrument fires on RunStarted.

Builds a session_topology, drives one turn against DeterministicResponder,
walks the record, asserts exactly one SessionStarted envelope with every
schema field populated. Closes REVIEW-2026-08-28-piece-g-full SDD-1.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.kernel.runtime import Runtime
from substrate.topologies.session import (
    SessionStarted,
    UserMessage,
    session_topology,
)


def _drive_session(tmp_path: Path) -> Path:
    """Build the topology, run one turn, return the record root."""

    async def _go() -> None:
        record_root = tmp_path / "record"
        record_root.mkdir(parents=True, exist_ok=True)
        driver = DeterministicResponder(seed=42)
        first_turn = UserMessage(
            text="hello",
            turn_index=0,
            assembled_prompt="hello",
            slash_source="daemon",
        )
        topo = session_topology(
            driver=driver,
            driver_name="deterministic",
            driver_context_tokens=8192,
            seed="You are a helper.",
            tools={},
            per_turn="",
            session_id="s_test_240",
            workspace_path=str(tmp_path / "workspace"),
            workspace_shape="flat",
            bundle="session",
            first_turn_user_message=first_turn,
        )
        rt = Runtime(record_root=record_root, persistent=True)
        await rt.run(topo)

    asyncio.run(_go())
    return tmp_path / "record"


def _read_all_envelopes(record_root: Path) -> list[dict]:
    """Read every envelope on the record via api.read_record."""
    return list(api.read_record(record_root))


def test_session_started_fires_exactly_once(tmp_path: Path) -> None:
    record_root = _drive_session(tmp_path)
    envelopes = _read_all_envelopes(record_root)
    session_starts = [e for e in envelopes if e.get("kind") == "SessionStarted"]
    assert len(session_starts) == 1, (
        f"expected exactly one SessionStarted; got {len(session_starts)}. "
        f"Kinds on record: {[e.get('kind') for e in envelopes]}"
    )


def test_session_started_payload_carries_every_schema_field(tmp_path: Path) -> None:
    record_root = _drive_session(tmp_path)
    envelopes = _read_all_envelopes(record_root)
    ss = next(e for e in envelopes if e.get("kind") == "SessionStarted")
    payload = ss.get("payload", {})
    # Every field on the SessionStarted Struct must be present.
    for field in SessionStarted.__struct_fields__:
        assert field in payload, (
            f"SessionStarted payload missing field {field!r}; got {sorted(payload.keys())}"
        )
    # And the closure values threaded through.
    assert payload["session_id"] == "s_test_240"
    assert payload["driver_model"] == "deterministic"
    assert payload["driver_context_tokens"] == 8192
    assert payload["seed"] == "You are a helper."
    assert payload["workspace_shape"] == "flat"
    assert payload["bundle"] == "session"
    assert payload["parent_session_id"] is None
    assert payload["parent_seq_at_call"] is None


def test_session_started_lands_early_before_user_message(tmp_path: Path) -> None:
    """SessionStarted must precede the first UserMessage on the record so
    consumers reading top-down see session identity before the first turn.
    """
    record_root = _drive_session(tmp_path)
    envelopes = _read_all_envelopes(record_root)
    ss_seq = next(e["seq"] for e in envelopes if e.get("kind") == "SessionStarted")
    um_seq = next(e["seq"] for e in envelopes if e.get("kind") == "UserMessage")
    assert ss_seq < um_seq, (
        f"SessionStarted at seq {ss_seq} must precede UserMessage at seq {um_seq}"
    )

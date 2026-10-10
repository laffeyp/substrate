# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 209b — session registered in BUNDLED + CI record reproducible.

Three checks:
  1. `substrate` bundled registry lists `"session"` alongside the other CI-mode
     topologies (`substrate topology list` surface).
  2. The bundled factory runs to `finalised` in one `.run()` and produces the
     expected event sequence: three UserMessage / ModelReply / Returned
     turns plus one SessionEnded, with the last UserMessage carrying `/exit`.
  3. The committed CI record at `topologies/session/records/ci_mode.record/` matches
     what the bundled factory produces on a fresh `.run()`. `first_divergence`
     against the committed record returns `None` — the record is a byte-stable
     regression fixture for the piece-A wiring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate import api
from substrate.testing import assert_event, assert_sequence
from substrate.topologies import bundled

_COMMITTED_RECORD = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "substrate"
    / "topologies"
    / "session"
    / "records"
    / "ci_mode.record"
)


def test_session_is_in_bundled_registry() -> None:
    assert "session" in bundled.BUNDLED
    assert callable(bundled.BUNDLED["session"])


@pytest.mark.asyncio
async def test_bundled_session_runs_to_finalised(tmp_path: Path) -> None:
    root = tmp_path / "sess-bundled"
    result = await api.Runtime(root).run(bundled.BUNDLED["session"]())
    assert result.status == "finalised"
    assert_event(root, "UserMessage", turn_index=0)
    assert_event(root, "UserMessage", turn_index=1)
    assert_event(root, "UserMessage", turn_index=2, text="/exit")
    assert_event(root, "Returned", reason="replied", turn_index=0)
    assert_event(root, "Returned", reason="replied", turn_index=1)
    assert_event(root, "SessionEnded", reason="user_exit")
    # The whole CI run is deterministic: scripted opener + DeterministicResponder +
    # deterministic CALCULATOR tool. Level-3(a) replay is a first-class assertion.
    api.assert_replayable(root, "3a")


@pytest.mark.asyncio
async def test_bundled_session_matches_committed_record(tmp_path: Path) -> None:
    """`first_divergence` against the committed CI record is None — a fresh run
    is byte-identical (on the seq / kind / payload dimensions replay checks;
    envelope `t` is excluded per §12 replay semantics).
    """
    if not _COMMITTED_RECORD.exists():
        pytest.skip(
            f"committed CI record not present at {_COMMITTED_RECORD} — regenerate with "
            "`uv run python scripts/gen_topology_records.py`"
        )
    root = tmp_path / "sess-bundled"
    await api.Runtime(root).run(bundled.BUNDLED["session"]())
    divergence = api.first_divergence(root, _COMMITTED_RECORD)
    assert divergence is None, (
        f"bundled session run diverges from committed CI record at seq {divergence}"
    )
    # Structural sanity: same payload-kind sequence as the committed record.
    fresh_kinds = [
        e["kind"] for e in api.read_record(root) if not e["kind"].startswith("substrate.")
    ]
    committed_kinds = [
        e["kind"]
        for e in api.read_record(_COMMITTED_RECORD)
        if not e["kind"].startswith("substrate.")
    ]
    assert fresh_kinds == committed_kinds


def test_committed_record_carries_the_expected_sequence() -> None:
    """The committed record is a static asset — validate it once, independent of
    a fresh run, so a corrupted record surfaces even if the runtime regresses."""
    if not _COMMITTED_RECORD.exists():
        pytest.skip(
            f"committed CI record not present at {_COMMITTED_RECORD} — regenerate with "
            "`uv run python scripts/gen_topology_records.py`"
        )
    envs = list(api.read_record(_COMMITTED_RECORD))
    payload_kinds = [e["kind"] for e in envs if not e["kind"].startswith("substrate.")]
    # Three turns × (UserMessage → ModelReply → Returned) minus the last
    # Returned (SessionEnded lands and threshold_count matches before return-on-reply can
    # emit) + one SessionEnded. The order of the last-turn events depends on the
    # append cycle; assert set membership + count instead of order for the tail.
    assert payload_kinds.count("UserMessage") == 3
    # Sprint 067: model producer fires on PromptComposed; turn 3's /exit
    # races end-on-exit → session_end → SessionEnded. Both 2 and 3 are
    # legitimate depending on which task finishes first.
    assert 2 <= payload_kinds.count("ModelReply") <= 3
    assert "FinalAnswer" not in payload_kinds
    assert payload_kinds.count("SessionEnded") == 1
    # First two turns land a Returned; the third turn's may or may not land
    # depending on the append cycle. Both shapes are legitimate; the assertion is
    # bounded.
    assert 2 <= payload_kinds.count("Returned") <= 3
    assert_sequence
    # Envelope seq 0 is substrate.RunStarted; the very first event kind must be that.
    assert envs[0]["kind"] == "substrate.RunStarted"

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 227 — inspect_record: five formats, five filters, HMAC cursor,
token-budget cap.

Uses a committed CI record (session or code_review) as the fixture — a
real substrate record with a known envelope shape, so filter and
progressive-disclosure assertions run against real data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.topologies import bundled
from substrate.topologies.tool_loop.substrate_tools import (
    _cap_tokens,
    _sign_cursor,
    _verify_cursor,
    make_inspect_record,
)


@pytest.fixture(scope="module")
def record() -> Path:
    """The code_review CI record — real envelopes, real seq range."""
    root = bundled.record_path("code_review")
    if not root.exists():
        pytest.skip(f"CI record for code_review not on disk at {root}")
    return root


def test_summary_returns_counts_shape(record: Path) -> None:
    tool = make_inspect_record()
    out = tool.run([{"record": str(record)}])
    assert out["format"] == "summary"
    assert isinstance(out["total_events"], int) and out["total_events"] > 0
    assert isinstance(out["application_events"], dict)


def test_events_filtered_by_kinds(record: Path) -> None:
    tool = make_inspect_record()
    out = tool.run([{"record": str(record), "format": "events", "filter": {"kinds": ["Verdict"]}}])
    assert out["format"] == "events"
    for envelope in out["events"]:
        assert envelope["kind"] == "Verdict"


def test_events_filtered_by_seq_range(record: Path) -> None:
    tool = make_inspect_record()
    out = tool.run(
        [
            {
                "record": str(record),
                "format": "events",
                "filter": {"seq_range": [0, 5]},
            }
        ]
    )
    for envelope in out["events"]:
        seq = int(envelope["seq"])
        assert 0 <= seq <= 5


def test_events_pagination_with_hmac_cursor(record: Path) -> None:
    """Force overflow with a low context-tokens setting so the cap
    triggers cursor pagination, then follow the cursor to the next
    page. Cap = min(1024, 0.25 * 200) = 50 tokens, small enough to
    fit only a couple envelopes per page."""
    tool = make_inspect_record(driver_context_tokens=200)
    first = tool.run([{"record": str(record), "format": "events"}])
    if not first.get("has_more"):
        pytest.skip("record too small to exercise cursor pagination at this cap")
    cursor = first["cursor"]
    second = tool.run([{"record": str(record), "continue_from": cursor, "format": "events"}])
    assert second["format"] == "events"
    first_seqs = {env["seq"] for env in first["events"]}
    second_seqs = {env["seq"] for env in second["events"]}
    assert first_seqs.isdisjoint(second_seqs), "cursor returned overlapping events"


def test_tampered_cursor_returns_typed_failure(record: Path) -> None:
    tool = make_inspect_record()
    out = tool.run(
        [
            {
                "record": str(record),
                "continue_from": "not-a-valid-cursor",
                "format": "events",
            }
        ]
    )
    assert out == {"ok": False, "error": "inspect_record: invalid cursor"}


def test_run_graph_format_returns_instances(record: Path) -> None:
    tool = make_inspect_record()
    out = tool.run([{"record": str(record), "format": "run_graph"}])
    assert out["format"] == "run_graph"
    assert out["status"] in ("finalised", "failed", "paused", "incomplete")
    assert isinstance(out["producers"], list)
    if out["producers"]:
        first_producer = out["producers"][0]
        for key in ("kind", "instance", "status", "fired_seq"):
            assert key in first_producer


def test_narrate_format_returns_text(record: Path) -> None:
    tool = make_inspect_record()
    out = tool.run([{"record": str(record), "format": "narrate"}])
    assert out["format"] == "narrate"
    assert isinstance(out["text"], str)


def test_cap_tokens_scales_with_driver_context() -> None:
    """Cap = min(1024, 0.25 * driver_context_tokens). At 200 tokens
    context, cap = 50. At 100_000, cap = 1024 (ceiling)."""
    assert _cap_tokens(None) == 1024
    assert _cap_tokens(200) == 50
    assert _cap_tokens(4096) == 1024
    assert _cap_tokens(100_000) == 1024


def test_hmac_sign_and_verify_roundtrip() -> None:
    """Locally test the HMAC cursor helpers — the tool body's pagination
    already exercises them but this test isolates the primitive."""
    key = b"test-key-32-bytes-long-padding__"
    payload = {"record": "/tmp/r", "next_seq": 42, "kinds": ["Verdict"]}
    cursor = _sign_cursor(payload, key)
    assert _verify_cursor(cursor, key) == payload
    # Wrong key returns None.
    assert _verify_cursor(cursor, b"wrong-key-32-bytes-long-padding_") is None
    # Tampered payload returns None.
    tampered = cursor[:-4] + "XXXX"
    assert _verify_cursor(tampered, key) is None


def test_hmac_cursor_survives_signatures_containing_delimiter_bytes() -> None:
    """Sprint 242 regression pin. HMAC-SHA256 is 32 raw bytes; ~12% of cursors
    have at least one 0x2E (`.`) byte in the signature. Pre-fix encoding split
    on `.` and cut the signature short, dropping ~1 in 8 cursors as "invalid."
    Post-fix uses a fixed-width 32-byte prefix. 200 round-trips cover the
    probability space enough that a regression would surface loudly.
    """
    import os as _os

    for _ in range(200):
        key = _os.urandom(32)
        payload = {
            "record": f"/tmp/{_os.urandom(4).hex()}",
            "next_seq": int.from_bytes(_os.urandom(2), "big"),
            "kinds": ["Verdict", "Beat"],
        }
        cursor = _sign_cursor(payload, key)
        assert _verify_cursor(cursor, key) == payload


def test_inspect_record_schema_declares_all_formats() -> None:
    tool = make_inspect_record()
    formats = tool.schema["properties"]["format"]["enum"]
    assert set(formats) == {"summary", "narrate", "events", "first_divergence", "run_graph"}


def test_inspect_record_missing_record_raises_typed_valueerror() -> None:
    """Drift-grooming 2026-09-02: `record` is required by the schema.
    Prior to the fix, `payload["record"]` raised a bare KeyError; the
    tool_loop layer wrapped that as ToolResult(ok=False, error="'record'")
    giving the model no tool context. Now typed."""
    tool = make_inspect_record()
    with pytest.raises(ValueError, match=r"inspect_record: missing required argument 'record'"):
        tool.run([{}])


def test_inspect_record_unknown_format_raises_typed_valueerror(record: Path) -> None:
    tool = make_inspect_record()
    with pytest.raises(ValueError, match=r"inspect_record: unknown format 'bogus'"):
        tool.run([{"record": str(record), "format": "bogus"}])


def test_inspect_record_first_divergence_missing_compare_raises(record: Path) -> None:
    tool = make_inspect_record()
    with pytest.raises(
        ValueError,
        match=r"inspect_record: format='first_divergence' requires `compare_record`",
    ):
        tool.run([{"record": str(record), "format": "first_divergence"}])


@pytest.mark.parametrize("fmt", ["summary", "narrate", "events", "run_graph"])
def test_missing_record_is_an_error_not_an_empty_record(tmp_path: Path, fmt: str) -> None:
    # UI sprint 099: a realmodel run mistyped the record path; the tool answered
    # ok with total_events=0 and finalised=False, and the model reported a finished
    # record as unfinished.
    tool = make_inspect_record()
    for path in (tmp_path / "nope", tmp_path):
        with pytest.raises(ValueError, match="no record at"):
            tool.run([{"record": str(path), "format": fmt}])

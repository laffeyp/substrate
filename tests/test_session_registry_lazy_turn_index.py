"""Sprint 094: boot_scan reads no record to derive turn indexes.

Regression for the 2026-10-01 measurement: the eager per-session record scan
was 6.9 of 7.1 s of boot over 3,079 sessions. The index is now derived on
first use, once per session.
"""

from __future__ import annotations

from pathlib import Path

from substrate.topologies import session_registry as sr


def test_turn_index_is_derived_lazily_once(tmp_path: Path, monkeypatch) -> None:
    first = sr.SessionRegistry(base=tmp_path)
    first.create(
        session_id="s_0123456789abcdef",
        name=None,
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="0",
    )

    calls: list[Path] = []
    monkeypatch.setattr(sr, "_next_turn_index_from_record", lambda root: calls.append(root) or 3)

    reborn = sr.SessionRegistry(base=tmp_path)
    reborn.boot_scan()
    assert calls == [], "boot_scan must not read records for turn indexes"

    assert reborn.next_turn_index("s_0123456789abcdef") == 3
    assert reborn.next_turn_index("s_0123456789abcdef") == 3
    assert len(calls) == 1, "the record is read once, on first use"

    reborn.advance_turn_index("s_0123456789abcdef")
    assert reborn.next_turn_index("s_0123456789abcdef") == 4
    assert len(calls) == 1

    assert reborn.next_turn_index("s_unknown") == 0

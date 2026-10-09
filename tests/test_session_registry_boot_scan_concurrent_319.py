"""The daemon's boot scan runs beside live requests (lens audit F319).

The scan read each manifest from disk and assigned it into the registry, so a rename, PATCH or turn
that landed on a session while the scan was between its disk read and its assignment was overwritten
by the older copy. Each test plants the request inside the scan through the one per-session call the
scan makes, `_scan_record_status`. The rename test fails on the old scan. The create test passes on
both: a sequential hook cannot show the old unlocked index write racing a create on another thread,
so it guards the new prune's result, not the race.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.topologies import session_registry as sr
from substrate.topologies.session_registry import SessionRegistry


def _create(reg: SessionRegistry, sid: str, name: str | None, tmp_path: Path) -> None:
    reg.create(
        session_id=sid,
        name=name,
        driver="deterministic",
        workspace=str(tmp_path / "ws" / sid),
        workspace_shape="flat",
        bundle=None,
        seed="",
    )


def test_a_rename_during_the_scan_is_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "sessions"
    reg = SessionRegistry(base=base)
    _create(reg, "s_00000000aaaa", "before", tmp_path)

    real_scan = sr._scan_record_status

    def scan_with_a_rename(record_root: Path) -> sr.SessionStatus:
        if not state["renamed"]:
            state["renamed"] = True
            reg.set_name("s_00000000aaaa", "after")  # a PATCH landing mid-scan
        return real_scan(record_root)

    state = {"renamed": False}
    monkeypatch.setattr(sr, "_scan_record_status", scan_with_a_rename)
    reg.boot_scan()

    assert state["renamed"]
    assert reg.get("s_00000000aaaa").name == "after"
    on_disk = json.loads((base / "s_00000000aaaa" / "manifest.json").read_text())
    assert on_disk["name"] == "after"
    assert reg.by_name("after") == "s_00000000aaaa"


def test_a_session_created_during_the_scan_keeps_its_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "sessions"
    reg = SessionRegistry(base=base)
    _create(reg, "s_00000000aaaa", "first", tmp_path)

    real_scan = sr._scan_record_status

    def scan_with_a_create(record_root: Path) -> sr.SessionStatus:
        if not state["created"]:
            state["created"] = True
            _create(reg, "s_00000000bbbb", "mid-scan", tmp_path)
        return real_scan(record_root)

    state = {"created": False}
    monkeypatch.setattr(sr, "_scan_record_status", scan_with_a_create)
    reg.boot_scan()

    assert reg.by_name("mid-scan") == "s_00000000bbbb"
    index = json.loads((base / "by-name.json").read_text())
    assert index == {"first": "s_00000000aaaa", "mid-scan": "s_00000000bbbb"}
    assert {m.session_id for m in reg.list_all()} == {"s_00000000aaaa", "s_00000000bbbb"}

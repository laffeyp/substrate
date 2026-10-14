# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 228 — four list-* tools + session_topology composition proof.

Each list tool's shape checked in isolation; the composition assertion
lives on the substrate-ui side (a real daemon build uses this module's
factories, and asserting on the tool dict there proves the wire path).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from substrate.topologies.tool_loop.substrate_tools import (
    make_list_applications,
    make_list_records,
    make_list_sessions,
    make_list_topologies,
)


class _StubManifest:
    def __init__(
        self,
        session_id: str,
        name: str,
        driver: str,
        workspace: str,
        status: str,
    ) -> None:
        self.session_id = session_id
        self.name = name
        self.driver = driver
        self.workspace = workspace
        self.status = status


class _StubRegistry:
    def __init__(self, manifests: list[_StubManifest]) -> None:
        self._manifests = manifests

    def list_all(self) -> list[_StubManifest]:
        return list(self._manifests)


def test_list_topologies_returns_bundled_names() -> None:
    from substrate.topologies import bundled

    tool = make_list_topologies()
    out = tool.run([{}])
    assert "topologies" in out
    assert set(bundled.names()) <= set(out["topologies"])


def test_list_applications_returns_shipped_specs() -> None:
    from substrate.topologies.applications.registry import load_manifests

    tool = make_list_applications(load_manifests())
    out = tool.run([{}])
    names = {entry["name"] for entry in out["applications"]}
    assert {"code_review", "best_of_n_verified", "research_sweep", "daily", "pair_coding"} <= names


def test_list_sessions_buckets_live_and_parked() -> None:
    registry = _StubRegistry(
        [
            _StubManifest("s_a", "alpha", "det", "/tmp/a", "running"),
            _StubManifest("s_b", "beta", "det", "/tmp/b", "parked"),
            _StubManifest("s_c", "gamma", "det", "/tmp/c", "ended"),
        ]
    )
    tool = make_list_sessions(registry)
    out = tool.run([{}])
    assert [entry["session_id"] for entry in out["live"]] == ["s_a"]
    assert [entry["session_id"] for entry in out["parked"]] == ["s_b"]


def test_list_records_walks_sessions_directory(tmp_path: Path) -> None:
    """Write two manifests to a fixture sessions dir; assert the tool
    returns both, newest first."""
    for idx, sid in enumerate(("s_old", "s_new")):
        session_dir = tmp_path / sid
        session_dir.mkdir()
        (session_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "session_id": sid,
                    "name": sid,
                    "status": "parked",
                    "created_at": 1000.0 + idx * 10.0,
                }
            ),
            encoding="utf-8",
        )
    tool = make_list_records(tmp_path)
    out = tool.run([{"limit": 20}])
    session_ids = [row["session_id"] for row in out["records"]]
    assert session_ids == ["s_new", "s_old"]


def test_list_records_status_filter(tmp_path: Path) -> None:
    for sid, status in (("s_a", "parked"), ("s_b", "ended"), ("s_c", "parked")):
        session_dir = tmp_path / sid
        session_dir.mkdir()
        (session_dir / "manifest.json").write_text(
            json.dumps({"session_id": sid, "status": status, "created_at": time.time()}),
            encoding="utf-8",
        )
    tool = make_list_records(tmp_path)
    out = tool.run([{"status": "parked"}])
    assert {row["session_id"] for row in out["records"]} == {"s_a", "s_c"}


def test_list_records_limit_caps_result(tmp_path: Path) -> None:
    for idx in range(30):
        session_dir = tmp_path / f"s_{idx:03d}"
        session_dir.mkdir()
        (session_dir / "manifest.json").write_text(
            json.dumps(
                {"session_id": session_dir.name, "status": "parked", "created_at": float(idx)}
            ),
            encoding="utf-8",
        )
    tool = make_list_records(tmp_path)
    out = tool.run([{}])  # default limit = 20
    assert len(out["records"]) == 20
    # Newest first: s_029 down.
    assert out["records"][0]["session_id"] == "s_029"


def test_list_tool_schemas_declared() -> None:
    assert make_list_records(Path("/tmp")).schema is not None
    assert make_list_topologies().schema is not None
    assert make_list_applications({}).schema is not None
    assert make_list_sessions(_StubRegistry([])).schema is not None


def test_missing_records_root_returns_empty(tmp_path: Path) -> None:
    tool = make_list_records(tmp_path / "does-not-exist")
    out = tool.run([{}])
    assert out == {"records": [], "count": 0}

"""Sprint 211 — SessionRegistry name → session_id lookup.

The daemon holds an in-memory `_by_name` dict mirrored to disk at
`~/.substrate/sessions/by-name.json`. A create writes the manifest first
(atomic tempfile + rename), then updates the index under `fcntl.flock`.
A second registry constructed against the same base directory reads the
by-name index off disk in its boot scan and answers `by_name(...)` for every
session the first registry created.

"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.topologies.session_registry import SessionRegistry


def _mk(base: Path, session_id: str, name: str | None) -> None:
    """Create a session with a fresh registry so each test builds its own state."""
    SessionRegistry(base=base).create(
        session_id=session_id,
        name=name,
        driver="deterministic",
        workspace=str(base / "w"),
        workspace_shape="flat",
        bundle=None,
        seed="hi",
    )


def test_by_name_resolves_after_create(tmp_path: Path) -> None:
    r = SessionRegistry(base=tmp_path)
    r.create(
        session_id="s_alpha",
        name="reviewer",
        driver="deterministic",
        workspace=str(tmp_path / "w"),
        workspace_shape="flat",
        bundle=None,
        seed="hi",
    )
    assert r.by_name("reviewer") == "s_alpha"
    assert r.by_name("nonexistent") is None
    assert r.get("s_alpha") is not None
    assert r.get("s_alpha").name == "reviewer"


def test_by_name_survives_boot_scan(tmp_path: Path) -> None:
    _mk(tmp_path, "s_beta", "planner")
    _mk(tmp_path, "s_gamma", "tester")
    _mk(tmp_path, "s_delta", None)  # anonymous session
    # Simulate daemon restart: a brand-new registry pointed at the same base.
    fresh = SessionRegistry(base=tmp_path)
    fresh.boot_scan()
    assert fresh.by_name("planner") == "s_beta"
    assert fresh.by_name("tester") == "s_gamma"
    assert fresh.by_name(None) is None  # type: ignore[arg-type]
    all_manifests = fresh.list_all()
    assert {m.session_id for m in all_manifests} == {"s_beta", "s_gamma", "s_delta"}
    anonymous = next(m for m in all_manifests if m.session_id == "s_delta")
    assert anonymous.name is None


def test_set_name_renames_index_atomically(tmp_path: Path) -> None:
    r = SessionRegistry(base=tmp_path)
    r.create(
        session_id="s_zeta",
        name="oldname",
        driver="deterministic",
        workspace=str(tmp_path / "w"),
        workspace_shape="flat",
        bundle=None,
        seed="hi",
    )
    assert r.by_name("oldname") == "s_zeta"
    r.set_name("s_zeta", "newname")
    assert r.by_name("newname") == "s_zeta"
    assert r.by_name("oldname") is None
    # Fresh registry sees the rename on disk.
    fresh = SessionRegistry(base=tmp_path)
    fresh.boot_scan()
    assert fresh.by_name("newname") == "s_zeta"
    assert fresh.by_name("oldname") is None


def test_set_name_raises_on_unknown_session(tmp_path: Path) -> None:
    r = SessionRegistry(base=tmp_path)
    with pytest.raises(KeyError):
        r.set_name("s_unknown", "any")

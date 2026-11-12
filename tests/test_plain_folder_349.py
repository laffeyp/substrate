# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K349: a session's workspace can stay a plain folder.

`create(make_repository=False)` leaves a folder that is not inside a repository as it is: no
`.git`, no commit. The default is unchanged: a plain folder is made a repository (K315).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from substrate.topologies.session_registry import SessionRegistry


def _create(reg: SessionRegistry, sid: str, ws: Path, **kw: Any) -> Any:
    return reg.create(
        session_id=sid,
        name=None,
        driver="deterministic",
        workspace=str(ws),
        workspace_shape="flat",
        bundle=None,
        seed="",
        **kw,
    )


def _folder_of_repositories(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    (root / "one" / ".git").mkdir(parents=True)  # stands for a repository inside it
    (root / "notes.md").write_text("loose material\n")
    return root


def test_a_plain_folder_stays_plain(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path / "sessions", session_topology_factory=lambda *a, **k: None)
    root = _folder_of_repositories(tmp_path)
    manifest = _create(reg, "s_00000000000000d1", root, make_repository=False)
    assert manifest.workspace == str(root) and manifest.workspace_shape == "flat"
    assert not (root / ".git").exists()
    assert sorted(p.name for p in root.iterdir()) == ["notes.md", "one"]


def test_the_default_still_makes_a_repository(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path / "sessions", session_topology_factory=lambda *a, **k: None)
    root = tmp_path / "plain"
    root.mkdir()
    _create(reg, "s_00000000000000d2", root)
    assert (root / ".git").is_dir()


def test_a_branch_needs_a_repository(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path / "sessions", session_topology_factory=lambda *a, **k: None)
    root = _folder_of_repositories(tmp_path)
    with pytest.raises(ValueError, match="a branch needs a repository"):
        _create(reg, "s_00000000000000d3", root, make_repository=False, branch="b")
    assert not (root / ".git").exists()

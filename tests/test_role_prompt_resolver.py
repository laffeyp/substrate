# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 223f — role-prompt resolver, four-layer fallback per §1.6.5."""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.kernel.topology import RegistrationError
from substrate.topologies.session.roles import resolve_role_prompt


def test_shipped_default_role_resolves() -> None:
    text = resolve_role_prompt("default")
    assert "working companion" in text or len(text) > 20


def test_repo_layer_wins_over_user_and_shipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    (repo / ".substrate" / "prompts").mkdir(parents=True)
    (repo / ".substrate" / "prompts" / "default.md").write_text("REPO PROMPT", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.delenv("SUBSTRATE_HOME", raising=False)  # state root follows the patched home
    text = resolve_role_prompt("default", repo_root=repo)
    assert text == "REPO PROMPT"


def test_user_layer_wins_over_shipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".substrate" / "prompts").mkdir(parents=True)
    (tmp_path / ".substrate" / "prompts" / "default.md").write_text("USER PROMPT", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("SUBSTRATE_HOME", raising=False)  # state root follows the patched home
    text = resolve_role_prompt("default")
    assert text == "USER PROMPT"


def test_folder_shape_concatenates_in_lexical_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    role_dir = tmp_path / ".substrate" / "prompts" / "reviewer"
    role_dir.mkdir(parents=True)
    (role_dir / "b.md").write_text("SECOND", encoding="utf-8")
    (role_dir / "a.md").write_text("FIRST", encoding="utf-8")
    (role_dir / "c.md").write_text("THIRD", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("SUBSTRATE_HOME", raising=False)  # state root follows the patched home
    text = resolve_role_prompt("reviewer")
    assert text == "FIRST\n\nSECOND\n\nTHIRD"


def test_file_and_folder_at_same_layer_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / ".substrate" / "prompts"
    base.mkdir(parents=True)
    (base / "reviewer.md").write_text("FILE", encoding="utf-8")
    (base / "reviewer").mkdir()
    (base / "reviewer" / "a.md").write_text("FOLDER", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("SUBSTRATE_HOME", raising=False)  # state root follows the patched home
    with pytest.raises(RegistrationError, match="both"):
        resolve_role_prompt("reviewer")


def test_missing_at_every_layer_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("SUBSTRATE_HOME", raising=False)  # state root follows the patched home
    with pytest.raises(RegistrationError, match="no role prompt found"):
        resolve_role_prompt("nonexistent-role-xyz")

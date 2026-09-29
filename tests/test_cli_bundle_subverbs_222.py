# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 222 — CLI bundle subverbs (create, ls, show, edit).

Bundle subverbs are pure filesystem operations (piece H sprint 229 ships
the real loader). Tests point `_BUNDLES_ROOT` at a tmp dir and assert on
the directory shape + file contents. Zero daemon involvement.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture
def bundles_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from substrate import cli

    monkeypatch.setattr(cli, "_bundles_root_cli", lambda: tmp_path)
    return tmp_path


def test_bundle_create_scaffolds_directory(bundles_root: Path) -> None:
    from substrate import cli

    result = CliRunner().invoke(cli.main, ["bundle", "create", "team-review"])
    assert result.exit_code == 0, result.output
    target = bundles_root / "team-review"
    assert (target / "bundle.toml").is_file()
    for slot in ("methodology.md", "personality.md", "per-turn.md"):
        assert (target / slot).is_file()
    assert (target / "corpus").is_dir()
    toml_text = (target / "bundle.toml").read_text(encoding="utf-8")
    assert 'name = "team-review"' in toml_text


def test_bundle_create_on_existing_refuses(bundles_root: Path) -> None:
    from substrate import cli

    (bundles_root / "already").mkdir()
    result = CliRunner().invoke(cli.main, ["bundle", "create", "already"])
    assert result.exit_code == cli.EXIT_CONFIG
    assert "already exists" in result.output


def test_bundle_ls_lists_directories_only(bundles_root: Path) -> None:
    from substrate import cli

    (bundles_root / "a-bundle").mkdir()
    (bundles_root / "b-bundle").mkdir()
    (bundles_root / "stray-file.txt").write_text("ignored", encoding="utf-8")
    result = CliRunner().invoke(cli.main, ["bundle", "ls"])
    assert result.exit_code == 0, result.output
    names = result.output.strip().splitlines()
    assert "a-bundle" in names
    assert "b-bundle" in names
    assert "stray-file.txt" not in names


def test_bundle_show_prints_slot_contents(bundles_root: Path) -> None:
    from substrate import cli

    CliRunner().invoke(cli.main, ["bundle", "create", "showable"])
    (bundles_root / "showable" / "methodology.md").write_text(
        "the-methodology-marker", encoding="utf-8"
    )
    result = CliRunner().invoke(cli.main, ["bundle", "show", "showable"])
    assert result.exit_code == 0, result.output
    assert 'name = "showable"' in result.output
    assert "the-methodology-marker" in result.output


def test_bundle_show_missing_bundle_exits_config(bundles_root: Path) -> None:
    from substrate import cli

    result = CliRunner().invoke(cli.main, ["bundle", "show", "no-such-bundle"])
    assert result.exit_code == cli.EXIT_CONFIG
    assert "no bundle" in result.output

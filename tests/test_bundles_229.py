# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 229 — bundles.py loader + extends chain + seed assembler.

Every case from the card's assertions block + a byte-comparable
composition assertion (the card's observation contract)."""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.bundles import (
    Bundle,
    BundleChainTooDeepError,
    BundleCycleError,
    BundleNotFoundError,
    BundleShapeError,
    load_bundle,
    resolve_extends,
)


def _write_bundle(
    root: Path,
    name: str,
    *,
    methodology: str = "",
    style: str = "",
    per_turn: str = "",
    extends: list[str] | None = None,
    description: str = "",
    tools: list[str] | None = None,
) -> Path:
    """Scaffold a bundle directory under `root`; return the directory."""
    bundle_dir = root / name
    bundle_dir.mkdir(parents=True)
    lines = ["[bundle]", f'name = "{name}"', f'description = "{description}"', "schema_version = 1"]
    if extends:
        lines.append("extends = [" + ", ".join(f'"{n}"' for n in extends) + "]")
    if tools is not None:
        lines.append("[tools]")
        lines.append("enabled = [" + ", ".join(f'"{t}"' for t in tools) + "]")
    (bundle_dir / "bundle.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if methodology:
        (bundle_dir / "methodology.md").write_text(methodology, encoding="utf-8")
    if style:
        (bundle_dir / "style.md").write_text(style, encoding="utf-8")
    if per_turn:
        (bundle_dir / "per-turn.md").write_text(per_turn, encoding="utf-8")
    return bundle_dir


def test_load_bundle_reads_file_slots(tmp_path: Path) -> None:
    _write_bundle(
        tmp_path,
        "solo",
        methodology="the-methodology",
        style="the-style",
        per_turn="the-per-turn",
        tools=["read_file", "grep"],
    )
    bundle = load_bundle("solo", bundles_root=tmp_path)
    assert isinstance(bundle, Bundle)
    assert bundle.name == "solo"
    assert bundle.methodology == "the-methodology"
    assert bundle.style == "the-style"
    assert bundle.per_turn == "the-per-turn"
    assert bundle.tools_enabled == ("read_file", "grep")


def test_load_bundle_folder_shape_concatenates(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "folder-slots"
    bundle_dir.mkdir()
    (bundle_dir / "bundle.toml").write_text(
        '[bundle]\nname = "folder-slots"\ndescription = ""\nschema_version = 1\n',
        encoding="utf-8",
    )
    methodology_dir = bundle_dir / "methodology"
    methodology_dir.mkdir()
    (methodology_dir / "a.md").write_text("FIRST", encoding="utf-8")
    (methodology_dir / "b.md").write_text("SECOND", encoding="utf-8")
    bundle = load_bundle("folder-slots", bundles_root=tmp_path)
    assert bundle.methodology == "FIRST\n\n---\n\nSECOND"


def test_load_bundle_shape_error_when_file_and_folder_at_same_slot(tmp_path: Path) -> None:
    bundle_dir = _write_bundle(tmp_path, "ambiguous", methodology="file-form")
    (bundle_dir / "methodology").mkdir()
    (bundle_dir / "methodology" / "a.md").write_text("folder-form", encoding="utf-8")
    with pytest.raises(BundleShapeError, match="methodology"):
        load_bundle("ambiguous", bundles_root=tmp_path)


def test_load_bundle_not_found(tmp_path: Path) -> None:
    with pytest.raises(BundleNotFoundError):
        load_bundle("no-such-bundle", bundles_root=tmp_path)


def test_resolve_extends_diamond_first_occurrence_wins(tmp_path: Path) -> None:
    """Diamond shape (base <- m1, m2 <- leaf). C3 linearises to
    [base, m1, m2, leaf] or [base, m2, m1, leaf] with first-occurrence-
    wins on shared ancestors. The base appears once, not twice."""
    _write_bundle(tmp_path, "base", methodology="base-m")
    _write_bundle(tmp_path, "m1", methodology="m1-m", extends=["base"])
    _write_bundle(tmp_path, "m2", methodology="m2-m", extends=["base"])
    _write_bundle(tmp_path, "leaf", methodology="leaf-m", extends=["m1", "m2"])
    chain = resolve_extends("leaf", bundles_root=tmp_path)
    names = [b.name for b in chain]
    assert names.count("base") == 1
    assert names[0] == "base"
    assert names[-1] == "leaf"


def test_resolve_extends_cycle_raises(tmp_path: Path) -> None:
    _write_bundle(tmp_path, "a", methodology="a", extends=["b"])
    _write_bundle(tmp_path, "b", methodology="b", extends=["a"])
    with pytest.raises(BundleCycleError, match="cycle"):
        resolve_extends("a", bundles_root=tmp_path)


def test_resolve_extends_depth_cap_raises(tmp_path: Path) -> None:
    """Ten bundles chained linearly. Depth cap is 8; the 9th raises."""
    for idx in range(10):
        extends = [f"link{idx - 1}"] if idx > 0 else []
        _write_bundle(tmp_path, f"link{idx}", methodology=f"link{idx}", extends=extends)
    with pytest.raises(BundleChainTooDeepError, match="deeper"):
        resolve_extends("link9", bundles_root=tmp_path)


# Sprint 065: assemble_seed / assemble_seed_from_chain deleted. Three
# tests removed with them. The seed-composition responsibility moved
# to the fragment/composer Producer graph (sprints 060-064) —
# bundle prose slots emit as PromptFragment(source=bundle_methodology|
# bundle_style) via `topologies/session/bundle_producer.py`, and
# `topologies/session/composer.py` yields PromptComposed with the same
# precedence-ordered join the deleted assemble_seed_from_chain
# implemented. The behavior lives on the record, tested by
# tests/test_prompt_fragment_bundle.py and tests/test_prompt_composer.py.


def test_a_bundle_with_only_personality_md_loads_it_as_style(tmp_path: Path) -> None:
    """Session vocabulary v0.4 (§ P.1): the slot is `style`; a bundle written before the rename,
    with `personality.md` and no `style.md`, still loads its text as the style."""
    bundle_dir = tmp_path / "old"
    bundle_dir.mkdir()
    (bundle_dir / "bundle.toml").write_text('[bundle]\nname = "old"\n', encoding="utf-8")
    (bundle_dir / "personality.md").write_text("Terse.", encoding="utf-8")
    assert load_bundle("old", bundles_root=tmp_path).style == "Terse."


def test_the_old_shipped_name_loads_harness() -> None:
    """§ P.1: `session` was the shipped bundle's name; it loads `harness`."""
    assert load_bundle("session").name == "harness"


def test_a_user_bundle_can_extend_a_shipped_bundle(tmp_path: Path) -> None:
    """An `extends` chain reaches shipped ancestors (K271)."""
    child = tmp_path / "child"
    child.mkdir()
    (child / "bundle.toml").write_text(
        '[bundle]\nname = "child"\nextends = ["harness"]\n', encoding="utf-8"
    )
    assert [b.name for b in resolve_extends("child", bundles_root=tmp_path)] == ["harness", "child"]

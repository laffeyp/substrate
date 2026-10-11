# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K276: memory (session vocabulary § P.2).

Two directories of text files: the operator's (`~/.substrate/memory/`) and the repo's
(`<repo>/.substrate/memory/`). Each index loads at session open as one `memory` fragment, capped
at 200 lines or 25 KB; topic files are read on demand; a save is a file write on the record.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.topologies.session.session_prompt_producer import (
    MEMORY_INDEX_MAX_LINES,
    memory_fragments,
    session_prompt_sources,
)
from substrate.topologies.session.vocabulary import CACHE_LAYOUT_SOURCES, SYSTEM_SOURCES


def _index(directory: Path, lines: list[str]) -> Path:
    directory.mkdir(parents=True)
    path = directory / "MEMORY.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_both_indexes_load_operator_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUBSTRATE_HOME", str(tmp_path / "home"))
    op = _index(tmp_path / "home" / "memory", ["- [Batch commits](b.md) — commit in chunks"])
    repo = tmp_path / "repo"
    rp = _index(repo / ".substrate" / "memory", ["- [Gotcha](g.md) — use python -m pytest"])
    frags = memory_fragments(repo)
    assert [f.provenance["path"] for f in frags] == [str(op), str(rp)]
    assert "Batch commits" in frags[0].text and "the index of the user's memory" in frags[0].text
    assert "Gotcha" in frags[1].text and "the index of the project's memory" in frags[1].text
    assert all(f.precedence == 8 and not f.provenance["truncated"] for f in frags)


def test_an_index_is_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUBSTRATE_HOME", str(tmp_path / "home"))
    _index(tmp_path / "home" / "memory", [f"- entry {i}" for i in range(300)])
    (frag,) = memory_fragments(None)
    assert frag.provenance == {
        "path": str(tmp_path / "home" / "memory" / "MEMORY.md"),
        "lines": MEMORY_INDEX_MAX_LINES,
        "truncated": True,
    }
    assert "- entry 199" in frag.text and "- entry 200" not in frag.text


def test_no_index_no_fragment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUBSTRATE_HOME", str(tmp_path / "home"))
    assert memory_fragments(tmp_path) == []


def test_memory_is_a_source_only_when_asked() -> None:
    off = session_prompt_sources(
        role=None, role_repo_root=None, bundle=None, parent_context=None, tools={}
    )
    on = session_prompt_sources(
        role=None, role_repo_root=None, bundle=None, parent_context=None, tools={}, memory=True
    )
    assert "memory" not in off and "memory" in on


def test_memory_stays_in_the_user_turn_unless_the_layout_opts_in() -> None:
    assert "memory" not in SYSTEM_SOURCES and "memory" in CACHE_LAYOUT_SOURCES


def test_standard_methodology_carries_the_memory_rules() -> None:
    from substrate.bundles import load_bundle

    method = load_bundle("standard").methodology
    memory = method[method.index("# Memory") :]
    # Says what memory is, what each folder holds and where it is, and names no tool (K287).
    assert "Memory is a set of notes that outlast this session." in memory
    assert "`~/.substrate/memory/` in the user's home folder" in memory
    assert "`.substrate/memory/` inside this session's workspace folder" in memory
    assert "`MEMORY.md`" in memory and "write_file" not in memory

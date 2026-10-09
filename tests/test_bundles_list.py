# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 238 — tests for `substrate.bundles.list_bundles`."""

from __future__ import annotations

from pathlib import Path

from substrate.bundles import Bundle, list_bundles


def test_list_bundles_enumerates_shipped_defaults(tmp_path: Path) -> None:
    """The shipped session + application bundles must appear in the enumeration.

    The test points bundles_root at an empty tmp_path so the shipped list is the
    only source. Sprint 231 shipped five default bundles alongside `session`;
    the enumeration must include the session default at minimum.
    """
    result = list_bundles(bundles_root=tmp_path)
    names = [b.name for b in result]
    assert "session" in names, f"shipped session default missing; got {names}"
    # The five sprint-231 application bundles ship as *.bundle directories.
    # Enumeration must yield at least the session default; the exact application
    # names are pinned by piece H's ship list (see substrate/process/sprints/
    # sprint-231-default-bundles-shipped.md). We assert at least one non-session
    # shipped bundle so a regression that hides the application-bundle branch
    # fails the test.
    non_session = [n for n in names if n != "session"]
    assert non_session, f"no shipped application bundles enumerated; got {names}"


def test_list_bundles_returns_sorted(tmp_path: Path) -> None:
    """The enumeration is sorted by bundle name — deterministic order so the
    UI's rail rendering does not shuffle between reads.
    """
    result = list_bundles(bundles_root=tmp_path)
    names = [b.name for b in result]
    assert names == sorted(names), f"list_bundles must return sorted; got {names}"


def test_list_bundles_yields_bundle_structs(tmp_path: Path) -> None:
    """Every entry is a fully loaded Bundle, not a name-only stub. Consumers
    (substrate-ui `GET /api/bundles`) read `description` + `tools_enabled`
    directly off the result.
    """
    result = list_bundles(bundles_root=tmp_path)
    for entry in result:
        assert isinstance(entry, Bundle), f"expected Bundle, got {type(entry).__name__}"
        assert entry.name, "Bundle.name must be non-empty"
        # description may legitimately be empty (an optional slot), but must
        # be a string not None.
        assert isinstance(entry.description, str)


def test_list_bundles_missing_user_root_returns_shipped_only(tmp_path: Path) -> None:
    """A bundles_root pointing at a non-existent directory yields the shipped
    list only, no raise. The daemon may launch with `~/.substrate/bundles/`
    unmade; enumeration must survive that.
    """
    missing = tmp_path / "does-not-exist"
    result = list_bundles(bundles_root=missing)
    assert result, "expected shipped bundles even with a missing user root"
    assert all(isinstance(b, Bundle) for b in result)


def test_list_bundles_user_bundle_shadows_shipped(tmp_path: Path) -> None:
    """A user bundle with the same name as a shipped default shadows the
    shipped one — the enumeration returns the user's bundle, not both.
    """
    user_session = tmp_path / "session"
    user_session.mkdir()
    (user_session / "bundle.toml").write_text(
        '[bundle]\nname = "session"\ndescription = "user override"\nschema_version = 1\n'
        "extends = []\n\n"
        "[corpus]\npaths = []\n\n"
        '[retrieval]\nkind = "none"\n\n'
        "[tools]\nenabled = []\n"
    )
    (user_session / "methodology.md").write_text("user methodology")
    result = list_bundles(bundles_root=tmp_path)
    session_entries = [b for b in result if b.name == "session"]
    assert len(session_entries) == 1, f"expected one session entry, got {len(session_entries)}"
    assert session_entries[0].description == "user override", (
        "user bundle must shadow shipped default; got description "
        f"{session_entries[0].description!r}"
    )

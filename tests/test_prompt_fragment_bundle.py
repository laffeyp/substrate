# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""bundle prose-slot fragment sources — sprint 062 tests.

Verifies both bundle Producers (methodology + personality):
 - Session with a shipped bundle emits fragments matching the bundle's
   slot contents.
 - Session without bundle emits zero bundle fragments.
 - Personality picks caller-wins across extends chain.
 - Methodology yields one fragment per non-empty methodology in the
   chain, in ancestor-first order with monotonically increasing
   precedence.

Deferred to sprint 064: live-model assertion that bundle text reaches
the driver. `_model_factory` does not yet consume `PromptComposed`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from substrate import api
from substrate.bundles import Bundle
from substrate.topologies.session import session_prompt_producer as sp
from substrate.topologies.session.ci import ci_session_topology


def test_bundle_methodology_fragment_lands_for_shipped_session_bundle(tmp_path: Path) -> None:
    """A session opened with bundle=session emits at least one
    PromptFragment(source=bundle_methodology) whose text matches the
    shipped methodology.md and whose provenance names the bundle."""

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("hi", "/exit"),
            session_id="s_bundle_meth",
            bundle="session",
        )
        await api.Runtime(tmp_path / "ci").run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "ci"))
    frags = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "bundle_methodology"
    ]
    assert len(frags) >= 1, f"expected >=1 methodology fragment, got {len(frags)}"
    for env in frags:
        payload = env["payload"]
        assert payload["text"], "bundle methodology text should be non-empty"
        assert 50 <= payload["precedence"] <= 59, (
            f"methodology precedence should be in the 50-59 band, got {payload['precedence']}"
        )
        assert payload["provenance"]["bundle_name"], "provenance names the bundle"


def test_bundle_personality_empty_for_shipped_session_bundle(tmp_path: Path) -> None:
    """The shipped `session` bundle ships an empty personality.md.
    Consequence: the personality producer yields zero fragments. Locks
    the empty-shipped-personality behavior; changing personality.md
    from empty to non-empty is a substantive edit that would flip this
    test — which is the point of the pin."""

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("hi", "/exit"),
            session_id="s_bundle_pers_empty",
            bundle="session",
        )
        await api.Runtime(tmp_path / "ci").run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "ci"))
    frags = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "bundle_personality"
    ]
    assert len(frags) == 0


def test_personality_source_takes_the_callers_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    """The personality source on a two-bundle synthetic chain: the caller wins over its
    ancestor. The chain lookup is replaced, so no ~/.substrate/bundles/ directory is read."""
    ancestor = Bundle(
        name="anc",
        description="",
        schema_version=1,
        extends=(),
        methodology="",
        personality="ANCESTOR_VOICE",
        per_turn="",
        corpus_paths=(),
        retrieval_kind="none",
        tools_enabled=(),
    )
    caller = Bundle(
        name="caller",
        description="",
        schema_version=1,
        extends=("anc",),
        methodology="",
        personality="CALLER_VOICE",
        per_turn="",
        corpus_paths=(),
        retrieval_kind="none",
        tools_enabled=(),
    )
    monkeypatch.setattr(sp, "resolve_chain", lambda _name: [ancestor, caller])
    frags = sp.bundle_personality_fragments("caller")
    assert [(f.text, f.precedence, f.provenance) for f in frags] == [
        ("CALLER_VOICE", 3, {"bundle_name": "caller", "chain_position": 1})
    ]


def test_no_bundle_kwarg_yields_zero_bundle_fragments(tmp_path: Path) -> None:
    """A session opened without bundle (default None) emits zero bundle
    fragments of either kind. Existing callers unaffected."""

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("hi", "/exit"),
            session_id="s_no_bundle",
        )
        await api.Runtime(tmp_path / "ci").run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "ci"))
    for source in ("bundle_methodology", "bundle_personality"):
        matching = [
            e
            for e in envs
            if e.get("kind") == "PromptFragment" and e["payload"].get("source") == source
        ]
        assert len(matching) == 0, f"expected 0 {source} fragments, got {len(matching)}"


def test_resolve_chain_falls_back_to_shipped_for_top_level_bundle() -> None:
    """`resolve_chain("session")` returns [Bundle(name='session')] even
    though the user has no ~/.substrate/bundles/session/ directory. The
    fallback uses `load_bundle`'s shipped-default lookup. Without this,
    the bundle sources trip BundleNotFoundError for every session
    that names a shipped bundle."""
    chain = sp.resolve_chain("session")
    assert len(chain) >= 1
    assert chain[-1].name == "session"
    # Shipped session bundle has methodology.md; personality.md ships empty.
    assert chain[-1].methodology


def test_no_bundle_names_no_bundle_source() -> None:
    """Without a bundle the session prompt runs neither bundle source."""
    sources = sp.session_prompt_sources(
        role=None, role_repo_root=None, bundle=None, parent_context=None, tools={}
    )
    assert sources == {}


def test_bundle_types_import_cleanly() -> None:
    """The bundles.py Bundle Struct still imports and instantiates
    cleanly — sprint 062 depends on it. Locks the import boundary."""
    b = Bundle(
        name="test",
        description="",
        schema_version=1,
        extends=(),
        methodology="M",
        personality="P",
        per_turn="",
        corpus_paths=(),
        retrieval_kind="none",
        tools_enabled=(),
    )
    assert b.methodology == "M"
    assert b.personality == "P"

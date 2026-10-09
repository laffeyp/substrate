# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 054 Phase A — substrate-side SessionRegistry core contract.

The class moved from substrate-ui into substrate; this test pins the
public shape from the library side. Every method here operates on
on-disk manifests + threading locks; nothing touches HTTP, SSE, or
a daemon process.

Deeper daemon-facing tests (SSE broadcast, cross-process file locks,
first-turn resume against a real record) stay in substrate-ui/tests
where they were — those exercise product-side behaviour, not the
library primitive.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from substrate.adapters import DeterministicResponder
from substrate.topologies.session import session_topology
from substrate.topologies.session_registry import (
    NameCollision,
    SessionManifest,
    SessionRegistry,
    SessionStatus,
)


def _session_factory(
    manifest: SessionManifest, first_turn_user_message: Any = None
) -> Callable[[Any], None]:
    del first_turn_user_message
    return session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=4096,
        seed=manifest.seed,
        tools={},
        per_turn="",
        max_turns=200,
        turn_max_steps=4,
        session_id=manifest.session_id,
        workspace_path=manifest.workspace,
        record_root=Path(manifest.record_root),
        script=None,
    )


def test_registry_creates_manifest_on_disk(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    manifest = reg.create(
        session_id="s_alpha",
        name="alpha",
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="",
    )
    assert manifest.session_id == "s_alpha"
    assert manifest.name == "alpha"
    assert (tmp_path / "s_alpha" / "manifest.json").exists()
    assert reg.by_name("alpha") == "s_alpha"
    assert reg.get("s_alpha") == manifest


def test_registry_by_name_returns_none_for_missing(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    assert reg.by_name("nobody") is None
    assert reg.get("s_nobody") is None


def test_registry_rejects_duplicate_name(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    reg.create(
        session_id="s_a",
        name="dup",
        driver="deterministic",
        workspace=str(tmp_path / "ws1"),
        workspace_shape="flat",
        bundle=None,
        seed="",
    )
    with pytest.raises(NameCollision) as excinfo:
        reg.create(
            session_id="s_b",
            name="dup",
            driver="deterministic",
            workspace=str(tmp_path / "ws2"),
            workspace_shape="flat",
            bundle=None,
            seed="",
        )
    assert excinfo.value.name == "dup"
    assert excinfo.value.existing_session_id == "s_a"


def test_registry_list_all_returns_every_manifest(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    for name in ("alpha", "beta", "gamma"):
        reg.create(
            session_id=f"s_{name}",
            name=name,
            driver="deterministic",
            workspace=str(tmp_path / name),
            workspace_shape="flat",
            bundle=None,
            seed="",
        )
    manifests = reg.list_all()
    assert {m.session_id for m in manifests} == {"s_alpha", "s_beta", "s_gamma"}


def test_registry_survives_a_fresh_instance_at_same_base(tmp_path: Path) -> None:
    """Registry state lives on disk; a second SessionRegistry at the
    same `base` picks up every existing session. This is the property
    that lets the daemon restart without losing standing sessions."""
    reg1 = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    reg1.create(
        session_id="s_persistent",
        name="persistent",
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="a seed",
    )

    reg2 = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    # Sprint 055: the constructor auto-hydrates from disk. No explicit
    # boot_scan() needed. Pre-055 this test required a manual call.
    manifest = reg2.get("s_persistent")
    assert manifest is not None
    assert manifest.name == "persistent"
    assert manifest.seed == "a seed"
    assert reg2.by_name("persistent") == "s_persistent"


def test_registry_status_transitions_via_update_status(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    reg.create(
        session_id="s_x",
        name="x",
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="",
    )
    parked = reg.update_status("s_x", SessionStatus.PARKED)
    assert parked.status == SessionStatus.PARKED
    ended = reg.update_status("s_x", SessionStatus.ENDED)
    assert ended.status == SessionStatus.ENDED


# ── Sprint 055: auto-boot at construction, with an explicit opt-out ──


def test_registry_auto_boots_and_sees_prior_sessions(tmp_path: Path) -> None:
    """Sprint 055: a fresh SessionRegistry at an existing base hydrates
    from disk automatically. Pre-055 the constructor left the in-memory
    catalog empty, which read as 'no sessions here' for any caller who
    did not know to call `boot_scan()` — a silent load-bearing
    precondition, KIT_DIARY finding 39 recurrence."""
    reg1 = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    reg1.create(
        session_id="s_prior",
        name="prior",
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="",
    )
    del reg1
    # A completely fresh instance — no explicit boot_scan call.
    reg2 = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    assert reg2.by_name("prior") == "s_prior"
    assert reg2.get("s_prior") is not None
    assert len(reg2.list_all()) == 1


def test_registry_auto_boot_opts_out_with_auto_boot_false(tmp_path: Path) -> None:
    """Callers who need to construct-then-configure-then-hydrate can pass
    `auto_boot=False`. The in-memory catalog stays empty until they call
    `boot_scan()` themselves. Same shape as pre-055; kept for callers
    who need the timing control (a subclass mid-construction, a test
    that patches state before the first scan)."""
    reg1 = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    reg1.create(
        session_id="s_prior",
        name="prior",
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="",
    )
    del reg1
    reg2 = SessionRegistry(
        base=tmp_path,
        session_topology_factory=_session_factory,
        auto_boot=False,
    )
    assert reg2.by_name("prior") is None  # opt-out: empty until scanned
    reg2.boot_scan()
    assert reg2.by_name("prior") == "s_prior"


def test_registry_explicit_boot_scan_stays_idempotent_after_auto_boot(
    tmp_path: Path,
) -> None:
    """Every production caller (substrate-ui/server.py at startup) calls
    boot_scan() explicitly after construction. Post-055 that call is
    redundant but must stay safe — idempotent, no side effects on
    already-hydrated state. Locks in the invariant."""
    reg = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    reg.create(
        session_id="s_a",
        name="a",
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="",
    )
    before = reg.list_all()
    skipped = reg.boot_scan()
    after = reg.list_all()
    assert {m.session_id for m in before} == {m.session_id for m in after}
    assert skipped == []  # nothing to skip on a clean hydrate

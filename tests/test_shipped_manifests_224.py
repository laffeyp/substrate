# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 224 — four shipped application manifests parse and match signatures.

Card's dual contract: each manifest's [inputs] schema matches its
topology's signature. The parse test proves the file is valid TOML +
required fields; the signature-check test proves the schema keys line
up with the actual Python kwargs (so a signature drift fails a named
test rather than surfacing at first POST /api/topology/<name>/run).
"""

from __future__ import annotations

import inspect

import pytest

from substrate.topologies.applications.registry import ApplicationSpec, load_manifests


@pytest.fixture(scope="module")
def specs() -> dict[str, ApplicationSpec]:
    """Load from the installed applications directory — the same call the
    daemon makes at boot. Empty return means the manifests never landed."""
    return load_manifests()


def test_all_four_manifests_present(specs: dict[str, ApplicationSpec]) -> None:
    assert {"code_review", "best_of_n_verified", "research_sweep", "daily"} <= set(specs), (
        f"expected the four shipped manifests; got {sorted(specs)}"
    )


def test_code_review_manifest_inputs_match_fanout_review_signature(
    specs: dict[str, ApplicationSpec],
) -> None:
    """Wire input keys must be a subset of the topology's kwarg names
    OR follow the roles-to-models `<role>_model` convention (§7.6 line
    1038). A drift raises `dual_contract_fail` per the card halt."""
    from substrate.topologies.applications.fanout_review import fanout_review_topology
    from substrate.topologies.code_review import DEFAULT_ROLES

    kwargs = set(inspect.signature(fanout_review_topology).parameters) | {"repo"}
    role_model_keys = {f"{role}_model" for role in DEFAULT_ROLES} | {"judge_model"}
    accepted = kwargs | role_model_keys
    manifest_keys = set(specs["code_review"].inputs_schema)
    unknown = manifest_keys - accepted
    assert not unknown, f"code_review manifest names inputs not on the signature: {unknown}"


def test_best_of_n_verified_manifest_inputs_match_signature(
    specs: dict[str, ApplicationSpec],
) -> None:
    from substrate.topologies.applications.best_of_n_verified import best_of_n_verified_topology

    kwargs = set(inspect.signature(best_of_n_verified_topology).parameters)
    accepted = kwargs | {"drafter_model", "verify_model"}
    manifest_keys = set(specs["best_of_n_verified"].inputs_schema)
    unknown = manifest_keys - accepted
    assert not unknown, f"best_of_n_verified manifest names inputs not on the signature: {unknown}"


def test_research_sweep_manifest_inputs_match_signature(
    specs: dict[str, ApplicationSpec],
) -> None:
    from substrate.topologies.applications.research_sweep import research_sweep_topology

    kwargs = set(inspect.signature(research_sweep_topology).parameters)
    accepted = kwargs | {"reader_model", "critic_model", "synthesizer_model"}
    manifest_keys = set(specs["research_sweep"].inputs_schema)
    unknown = manifest_keys - accepted
    assert not unknown, f"research_sweep manifest names inputs not on the signature: {unknown}"


def test_daily_manifest_declares_session_runs(specs: dict[str, ApplicationSpec]) -> None:
    """`daily` wraps session_topology per §7.6; `runs = \"session\"` is the
    marker that tells the daemon to open a standing session rather than
    dispatch a one-shot Runtime.run."""
    daily = specs["daily"]
    assert daily.runs == "session"
    assert "driver_model" in daily.inputs_schema


def test_pair_coding_bundled_key_renamed(specs: dict[str, ApplicationSpec]) -> None:
    """Sprint 224's collision fix: BUNDLED no longer carries `pair_coding`
    (that name belongs to sprint 225's application composite). The
    chunked-writer demo lives at `pair_coding_chunked` now."""
    from substrate.topologies import bundled

    assert "pair_coding" not in bundled.names()
    assert "pair_coding_chunked" in bundled.names()
    # Backward-compat: record_path("pair_coding") still finds the record
    # (the module dir did not move; only the BUNDLED key did).
    assert bundled.record_path("pair_coding").exists()
    assert bundled.record_path("pair_coding_chunked").exists()

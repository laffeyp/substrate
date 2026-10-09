# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 223 — application registry parser tests.

Three shapes per the card:
  - empty directory → {}
  - valid manifest → parsed ApplicationSpec
  - malformed manifest → ManifestError with skip vs raise policy
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.topologies.applications.registry import (
    ApplicationSpec,
    ManifestError,
    load_manifests,
    spec_to_wire,
)

_VALID_MANIFEST = """
name = "code_review"
description = "Fan-out review of a diff by N reviewer models."
runs = "one-shot"
default_bundle = "reviewer"

[inputs]
repo = {type = "string"}
ref = {type = "string", default = "HEAD~1"}
reviewer_model = {type = "string", default = "kimi-k2.6:cloud"}
judge_model = {type = "string", default = "claude"}

[output]
kind = "review-transcript"

[slots]
methodology = {default = "bundle:methodology"}
"""


def test_empty_directory_returns_empty(tmp_path: Path) -> None:
    assert load_manifests(root=tmp_path) == {}


def test_missing_directory_returns_empty(tmp_path: Path) -> None:
    assert load_manifests(root=tmp_path / "nonexistent") == {}


def test_valid_manifest_parses(tmp_path: Path) -> None:
    (tmp_path / "code_review.manifest.toml").write_text(_VALID_MANIFEST, encoding="utf-8")
    specs = load_manifests(root=tmp_path)
    assert set(specs) == {"code_review"}
    spec = specs["code_review"]
    assert isinstance(spec, ApplicationSpec)
    assert spec.runs == "one-shot"
    assert spec.default_bundle == "reviewer"
    assert spec.output_kind == "review-transcript"
    assert spec.inputs_schema["reviewer_model"]["default"] == "kimi-k2.6:cloud"


def test_malformed_toml_skip_policy_is_default(tmp_path: Path) -> None:
    (tmp_path / "broken.manifest.toml").write_text("this = is [ not toml", encoding="utf-8")
    (tmp_path / "good.manifest.toml").write_text(_VALID_MANIFEST, encoding="utf-8")
    specs = load_manifests(root=tmp_path)
    assert set(specs) == {"code_review"}


def test_malformed_toml_raise_policy_surfaces(tmp_path: Path) -> None:
    (tmp_path / "broken.manifest.toml").write_text("this = is [ not toml", encoding="utf-8")
    with pytest.raises(ManifestError, match="broken.manifest.toml"):
        load_manifests(root=tmp_path, on_error="raise")


def test_missing_required_keys_raise_policy(tmp_path: Path) -> None:
    (tmp_path / "partial.manifest.toml").write_text('name = "x"\n', encoding="utf-8")
    with pytest.raises(ManifestError, match="missing top-level keys"):
        load_manifests(root=tmp_path, on_error="raise")


def test_bad_runs_value_raises(tmp_path: Path) -> None:
    """Drift-grooming 2026-09-02: the parse-time validator resolves `runs`
    through ApplicationRuns(raw); an unknown value raises ManifestError
    naming the valid enum members. The daemon's _topology_run dispatches
    on ApplicationRuns members, so a bad value never reaches the runner."""
    (tmp_path / "bad.manifest.toml").write_text(
        'name = "x"\ndescription = "d"\nruns = "forever"\n', encoding="utf-8"
    )
    with pytest.raises(ManifestError) as excinfo:
        load_manifests(root=tmp_path, on_error="raise")
    message = str(excinfo.value)
    assert "'forever'" in message
    for valid in ("one-shot", "session", "session_composite"):
        assert valid in message, f"error must list valid value {valid!r}: {message}"


def test_spec_to_wire_shape_matches_spec(tmp_path: Path) -> None:
    """TECH-SPEC §7.6 line 1044: wire response is
    `{name, description, inputs_schema, output_kind, runs}` — slots and
    default_bundle are internal to the binding step and NOT on the wire."""
    (tmp_path / "code_review.manifest.toml").write_text(_VALID_MANIFEST, encoding="utf-8")
    spec = load_manifests(root=tmp_path)["code_review"]
    wire = spec_to_wire(spec)
    assert set(wire) == {"name", "description", "runs", "inputs_schema", "output_kind"}


def test_shipped_applications_directory_is_readable() -> None:
    """The default root path (installed package) is readable; today it
    contains zero manifests (sprint 224 writes the first four). The
    invariant we're locking here is: the boot-time call NEVER raises
    even when the applications directory is empty of manifests."""
    specs = load_manifests()
    assert isinstance(specs, dict)

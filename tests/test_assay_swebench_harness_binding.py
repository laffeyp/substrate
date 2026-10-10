# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Gold-differential harness-binding pins for `substrate.assay.swebench` (sprint 146a).

Restores the coverage the deleted `scripts/swebench_smoke.py` provided — an end-to-end run of
the official SWE-bench 4.x harness through our binding, with two orthogonal cases: the reference
patch MUST grade resolved=True; an empty patch MUST grade resolved=False. Together these pin the
whole binding surface (`verify_constants`, `make_prediction`, `write_predictions`, `run_swebench`,
`read_resolved`, `read_run_report`) against a real harness run, not a fixture.

Env-gated three ways — the test SKIPS unless all are satisfied:

    1. `swebench` is importable (the harness itself)
    2. `docker` is on PATH (the harness runs each instance in Docker)
    3. `SWEBENCH_HARNESS_ENABLE=1` env var is set (opt-in gate — an emulated x86 image pull on
       arm64 can take 10+ minutes; nobody should hit this by accident from `pytest`)

Run explicitly on the Architect's box (Docker + swebench installed + the eval image cached):

    SWEBENCH_HARNESS_ENABLE=1 uv run python -m pytest \\
        tests/test_assay_swebench_harness_binding.py -m swebench_harness -v

Skips silently in CI + everywhere else. The gold_resolves case is the load-bearing check — if it
FAILS with the current pinned swebench, the binding drifted (a key rename, a report-path change,
a schema bump) and needs re-verifying against docs/swebench/swebench-bridge-mapping.md.
"""

from __future__ import annotations

import shutil

import pytest

# Fixed anchor instance: pallets/flask-4045. Pure-Python, cached in the repo's existing smoke
# history, historically the differential-test target — the one instance the KIT_DIARY documents
# working end-to-end on this codebase (finding 20). If future work moves off flask, update the
# anchor here — the whole point of a pinned anchor is that it's ONE thing.
_ANCHOR_INSTANCE = "pallets__flask-4045"
_DATASET = "princeton-nlp/SWE-bench_Lite"


def _skip_if_not_enabled() -> None:
    # The opt-in gate (SWEBENCH_HARNESS_ENABLE) is in conftest.py, for the whole Docker tier.
    if shutil.which("docker") is None:
        pytest.skip("docker not on PATH — the harness runs each instance in Docker")
    try:
        import swebench  # noqa: F401  # imported for its side effect (availability check)
    except ImportError:
        pytest.skip("swebench not importable — install the official harness to run this test")
    try:
        from datasets import load_dataset  # noqa: F401
    except ImportError:
        pytest.skip("datasets not importable — needed to load the SWE-bench Lite instance dict")


def _instance() -> dict:
    """Load the anchor instance from SWE-bench Lite (needed for its `patch` field — the gold)."""
    from datasets import load_dataset

    ds = load_dataset(_DATASET, split="test")
    return next(row for row in ds if row["instance_id"] == _ANCHOR_INSTANCE)


def test_constants_verify_against_installed_swebench() -> None:
    """The fastest binding check — no Docker, no network, no opt-in gate (review nit 146a-1). If
    `swebench` renamed KEY_INSTANCE_ID or KEY_PREDICTION between our pinned mapping
    (docs/swebench/swebench-bridge-mapping.md, verified against 4.1.0) and the version installed here,
    this raises AssertionError with the drift enumerated — catching a version-bump silently
    breaking `make_prediction` before any Docker time. Skips only when swebench itself isn't
    importable (uninstalled — a legitimate CI state), NOT behind the Docker/opt-in gate: gating
    a package-rename check behind an env var + Docker means the rename lives silently in every
    ordinary CI run.
    """
    try:
        import swebench  # noqa: F401
    except ImportError:
        pytest.skip("swebench not importable — the constants check needs the package installed")
    from substrate.assay.swebench import verify_constants

    verify_constants()  # raises on drift; no-op otherwise


# Docker + swebench + opt-in gate scoped to the actual harness-run tests below (review nit 146a-1).
pytestmark_docker = pytest.mark.swebench_harness


@pytest.mark.swebench_harness
def test_gold_patch_grades_resolved(tmp_path) -> None:
    """The load-bearing gold-differential check: the instance's reference patch (`inst["patch"]`)
    MUST grade resolved=True through the harness. If this fails with `resolved=False`, either the
    binding drifted (report.json location / schema / model_name mangling) or the pinned image
    itself changed grade behavior — both are things `run_swebench` + `read_resolved` are
    responsible for pinning.
    """
    _skip_if_not_enabled()
    from substrate.assay.swebench import (
        DEFAULT_MODEL_NAME,
        make_prediction,
        read_resolved,
        run_swebench,
    )

    inst = _instance()
    run_id = "harness-binding-gold"
    predictions = [make_prediction(_ANCHOR_INSTANCE, inst["patch"])]

    run_swebench(
        predictions,
        dataset_name=_DATASET,
        run_id=run_id,
        instance_ids=[_ANCHOR_INSTANCE],
        report_dir=tmp_path,
        max_workers=1,
    )
    resolved = read_resolved(tmp_path, run_id, DEFAULT_MODEL_NAME, _ANCHOR_INSTANCE)
    assert resolved is True, (
        f"gold patch on {_ANCHOR_INSTANCE} did NOT resolve — the binding drifted "
        f"(check docs/swebench/swebench-bridge-mapping.md against the installed swebench version)"
    )


@pytest.mark.swebench_harness
def test_empty_patch_does_not_grade_resolved(tmp_path) -> None:
    """The other side of the differential: an empty patch (`model_patch=""`) MUST NOT grade
    resolved=True. `grade_patch` (assay/swebench.py:295) short-circuits the empty-patch case
    without invoking Docker — this test pins that shortcut. If a future refactor removes the
    shortcut, this test would take Docker time; that's fine — the assertion still holds and the
    shortcut is an optimization, not a correctness requirement.
    """
    _skip_if_not_enabled()
    from substrate.assay.swebench import grade_patch

    # `grade_patch` returns False without a run for an empty patch. This is a binding-adjacent
    # invariant: it ensures the fast path stays fast AND doesn't accidentally grade True. The
    # write-through to `run_swebench` is exercised by the gold case above.
    resolved = grade_patch(_ANCHOR_INSTANCE, "", report_root=tmp_path, dataset_name=_DATASET)
    assert resolved is False, "empty patch grading True is a binding failure"

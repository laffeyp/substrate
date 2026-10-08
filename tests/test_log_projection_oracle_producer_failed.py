# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 200a (roadmap v2 S9 close): `SwebenchLogProjectionOracle` distinguishes
essential-producer failure from Draft-Exhausted at the row level.

The S9 wire-check surfaced two `tool_loop_container` cells whose `solve` producer died
of `docker rc=125` on Apple Silicon. The pre-Sprint-200a oracle returned
`Verdict.FAIL, reason=""` for both — indistinguishable from an honest "arm produced no
patch to grade" outcome. The report reads the row, so mechanism failures counted as arm
failures. Sprint 200a scans for `substrate.ProducerFailed` on `solve`/`grader` and
surfaces `Verdict.NO_VERDICT` with the reason classified via `classify_reason_string`.

Tests pin the row-level distinction:
- ProducerFailed on `solve` with docker error → NO_VERDICT, reason=docker_error.
- ProducerFailed on `grader` with git error → NO_VERDICT, reason=git_error.
- ProducerFailed on a non-essential producer (`localize` say) → NOT the trigger; the
  no-grade fallback still fires FAIL. Only `solve` and `grader` count.
- No ProducerFailed AND no GradeResult → FAIL with the no-grade detail (backward compat).
- GradeResult present takes precedence over any ProducerFailed on the record (a grader
  that fired after a slot-N solve failed still counts).
- The runner's `_classify_cell_error` routes through the same `classify_reason_string`
  helper — one source of truth.
"""

from __future__ import annotations

import pytest

from substrate.assay.oracle import Verdict
from substrate.assay.swebench import (
    REASON_DOCKER_ERROR,
    REASON_GIT_ERROR,
    REASON_HARNESS_ERROR,
    classify_reason_string,
    swebench_log_projection_oracle,
)


def _rec(*events):
    """Assemble a synthetic record — a list of {kind, payload} envelopes the oracle reads."""
    return [{"kind": k, "payload": p} for k, p in events]


def test_producer_failed_on_solve_docker_returns_no_verdict_docker_error():
    oracle = swebench_log_projection_oracle()
    record = _rec(
        ("substrate.RunStarted", {}),
        ("substrate.ProducerStarted", {"producer": {"kind": "solve"}}),
        (
            "substrate.ProducerFailed",
            {
                "producer": {"kind": "solve"},
                "error": "CalledProcessError(125, ['docker', 'run', '-d', '--rm', '--platform', 'linux/amd64', 'swebench/sweb.eval.x86_64.astropy_1776_astropy-12907:latest'])",
            },
        ),
        ("substrate.RunFinalised", {}),
    )
    result = oracle.grade(record, {"instance_id": "astropy__astropy-12907"})
    assert result.verdict is Verdict.NO_VERDICT
    assert result.reason == REASON_DOCKER_ERROR
    assert "solve" in result.detail


def test_producer_failed_on_grader_git_returns_no_verdict_git_error():
    oracle = swebench_log_projection_oracle()
    record = _rec(
        ("SelectedPatch", {"slot": 0, "model_patch": "diff --git a/x b/x\n"}),
        (
            "substrate.ProducerFailed",
            {
                "producer": {"kind": "grader"},
                "error": "RuntimeError('git checkout failed at head-ref: broken symlink in worktree')",
            },
        ),
    )
    result = oracle.grade(record, {"instance_id": "pallets__flask-4045"})
    assert result.verdict is Verdict.NO_VERDICT
    assert result.reason == REASON_GIT_ERROR
    assert "grader" in result.detail


def test_producer_failed_on_non_essential_kind_does_not_trigger():
    """A drafter that fails is not essential — the topology's other drafters may still
    produce SelectedPatch. When no SelectedPatch AND no GradeResult AND only non-essential
    producers failed, the oracle keeps its Draft-Exhausted FAIL fallback (backward compat)."""
    oracle = swebench_log_projection_oracle()
    record = _rec(
        ("substrate.RunStarted", {}),
        (
            "substrate.ProducerFailed",
            {"producer": {"kind": "localize"}, "error": "RuntimeError('bogus AST error')"},
        ),
        ("substrate.RunFinalised", {}),
    )
    result = oracle.grade(record, {"instance_id": "django__django-12345"})
    assert result.verdict is Verdict.FAIL
    assert result.reason == ""
    assert "no GradeResult" in result.detail


def test_no_producer_failed_no_grade_result_keeps_fallback_fail():
    """The pre-Sprint-200a shape is preserved when no essential producer failed: FAIL
    with the "no GradeResult" detail. Every existing solve_and_grade cell where the
    topology exhausted its drafters still lands as this."""
    oracle = swebench_log_projection_oracle()
    record = _rec(
        ("substrate.RunStarted", {}),
        ("Exhausted", {}),
        ("substrate.RunFinalised", {}),
    )
    result = oracle.grade(record, {"instance_id": "sympy__sympy-99999"})
    assert result.verdict is Verdict.FAIL
    assert result.reason == ""
    assert "no GradeResult" in result.detail


def test_grade_result_takes_precedence_over_producer_failed():
    """A ProducerFailed event followed by a GradeResult (e.g. a slot-N solve failed but
    the grader still fired on a different SelectedPatch) grades via the GradeResult, not
    the failure. The GradeResult is authoritative when present."""
    oracle = swebench_log_projection_oracle()
    record = _rec(
        (
            "substrate.ProducerFailed",
            {"producer": {"kind": "solve"}, "error": "docker rc=125"},
        ),
        ("SelectedPatch", {"slot": 1, "model_patch": "diff --git ..."}),
        (
            "GradeResult",
            {"instance_id": "pallets__flask-4045", "verdict": "pass", "reason": ""},
        ),
    )
    result = oracle.grade(record, {"instance_id": "pallets__flask-4045"})
    assert result.verdict is Verdict.PASS, "GradeResult present must win over ProducerFailed"
    assert result.reason == ""


def test_classify_reason_string_shape():
    """The shared helper both the runner and oracle use — pin the taxonomy."""
    assert (
        classify_reason_string("CalledProcessError(125, ['docker', 'run', ...])")
        == REASON_DOCKER_ERROR
    )
    assert (
        classify_reason_string("CalledProcessError(1, ['git', 'clone', ...])") == REASON_GIT_ERROR
    )
    assert classify_reason_string("some container-related error") == REASON_DOCKER_ERROR
    assert classify_reason_string("ProviderRateLimited('exceeded rate limit')") in (
        "rate_limited",
        REASON_HARNESS_ERROR,
    )  # currently only substring "rate" and "limit" both present hits rate_limited
    assert classify_reason_string("random unknown error class") == REASON_HARNESS_ERROR


def test_runner_and_oracle_share_the_classifier():
    """Both the runner's `_classify_cell_error` string-repr fallback and the oracle's
    `ProducerFailed` reason surface route through `classify_reason_string`. This test pins
    the shared taxonomy — a substring rule added to one must land in both."""
    import subprocess

    # the script imports HuggingFace `datasets` at load; it is not a dev dependency (UI sprint 106)
    pytest.importorskip("datasets")
    from scripts.assay_swebench_confirmatory import _classify_cell_error

    docker_exc = subprocess.CalledProcessError(125, ["docker", "run"])
    reason, halt = _classify_cell_error(docker_exc)
    assert reason == REASON_DOCKER_ERROR
    assert halt is False

    # Same shape at the oracle via a synthetic ProducerFailed event.
    oracle = swebench_log_projection_oracle()
    record = _rec(
        (
            "substrate.ProducerFailed",
            {"producer": {"kind": "solve"}, "error": repr(docker_exc)},
        ),
    )
    result = oracle.grade(record, {"instance_id": "x__x-1"})
    assert result.reason == REASON_DOCKER_ERROR

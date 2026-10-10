# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 199d observation contract: end-to-end fire of `_backend_topology_with_grade`
against a real Runtime + real Docker grader.

The four shape tests in `test_container_solve_and_grade_arm.py` prove the topology
declares `solve` + `grader` producer kinds, the trigger fires on `SelectedPatch`, and
the termination waits for `GradeResult`. This test proves BEHAVIOR: a stub solve emits
`SelectedPatch`, the grader fires against a real SWE-bench eval image + harness, and
`GradeResult` lands on the record. Uses `pallets__flask-4045` (Lite instance whose eval
image is cached on this box) with an EMPTY patch that the harness will grade as fail
without any real work — the point is the wire, not a solve.

In the opt-in Docker tier (`swebench_harness`; conftest.py skips it unless
SWEBENCH_HARNESS_ENABLE=1). When enabled, it skips if the Docker daemon does not answer or the
flask-4045 eval image is missing; the probes run inside the test, not at import.
"""

from __future__ import annotations

import subprocess

import pytest

from substrate.api import Runtime, read_record
from substrate.assay.swebench_matrix import _backend_topology_with_grade


def _docker_up() -> bool:
    """Cheap check — `docker version` returns fast even under load; `docker info`
    queries the daemon and can take seconds when the daemon is under Sprint-200
    concurrency. Use `docker version` for the availability probe."""
    try:
        p = subprocess.run(
            ["docker", "version", "--format", "{{.Client.Version}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return p.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _flask_image_cached() -> bool:
    try:
        p = subprocess.run(
            ["docker", "images", "-q", "swebench/sweb.eval.x86_64.pallets_1776_flask-4045:latest"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return bool(p.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # UI sprint 106: no `docker` binary is a skip, as in _docker_up(). Catching only the
        # timeout made collection crash on every machine without Docker (all macOS CI jobs).
        return False


# UI sprint 107 marked this test for the opt-in Docker tier, but the marker gated nothing and its
# probes ran at import, so it ran in the default suite when Docker answered in time (K266).
@pytest.mark.swebench_harness
@pytest.mark.timeout(300)
async def test_backend_topology_with_grade_fires_end_to_end(tmp_path):
    """A stub-solve topology with a real grader lands `SelectedPatch` and `GradeResult`
    on the record. The grade verdict is `fail` because the stub patch does nothing; the
    OBSERVATION is that the grader wired correctly and the harness returned a typed
    verdict — not the patch quality."""
    if not _docker_up():
        pytest.skip("Docker daemon did not answer `docker version` within 15 s")
    if not _flask_image_cached():
        pytest.skip("swebench flask-4045 eval image not cached, or `docker images` timed out")
    stub_patch = "diff --git a/x b/x\n"  # empty diff — harness returns fail cleanly

    topo = _backend_topology_with_grade(
        lambda: stub_patch,
        instance_id="pallets__flask-4045",
        dataset_name="princeton-nlp/SWE-bench_Lite",
        model_name="substrate-test",
        run_id="s199d-e2e",
        report_dir=tmp_path / "reports",
        grade_timeout_seconds=180,
    )
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised", f"run must finalise; got {result.status}"

    events = list(read_record(tmp_path / "run"))
    selected = [e for e in events if e["kind"] == "SelectedPatch"]
    grades = [e for e in events if e["kind"] == "GradeResult"]

    assert len(selected) == 1, f"expected one SelectedPatch; got {len(selected)}"
    assert selected[0]["payload"]["model_patch"] == stub_patch
    assert len(grades) == 1, (
        f"expected one GradeResult on the record; got {len(grades)}. "
        "If zero: the grader trigger did not fire on SelectedPatch, or the grader "
        "raised before emitting."
    )
    grade_payload = grades[0]["payload"]
    assert grade_payload["instance_id"] == "pallets__flask-4045"
    # The verdict is either "fail" (empty patch grades fail cleanly) or "no_verdict"
    # (harness timed out / errored). Either is honest evidence the grade wired through.
    assert grade_payload["verdict"] in ("fail", "no_verdict"), (
        f"unexpected verdict {grade_payload['verdict']!r}; expected fail or no_verdict"
    )

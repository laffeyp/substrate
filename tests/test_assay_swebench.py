# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""SWE-bench external-grader Adapter — Sprint 5. Pure binding only: no Docker, no swebench installed.

Covers what the Adapter does WITHOUT the harness: forming the three-field prediction (no invented
fields), writing predictions JSONL, reading `resolved` off a per-instance report.json (including the
model-name '/'->'__' rewrite the harness uses), asserting the run-report schema_version, the
constants-verify no-op when swebench is absent, and the Oracle reading a verdict from a pre-run report
(stamped run-and-observe). The actual harness invocation (`run_swebench`) is env-gated and never called
here — it needs Docker + swebench + image pulls on the Architect's box.
"""

import json

import pytest

from substrate.assay.oracle import EXTERNAL_GRADER, Verdict
from substrate.assay.swebench import (
    _HARNESS_REASONS,
    KEY_INSTANCE_ID,
    KEY_MODEL,
    KEY_PREDICTION,
    REASON_CONTAINER_CRASHED,
    REASON_DOCKER_ERROR,
    REASON_FIREWALL_VIOLATION,
    REASON_GIT_ERROR,
    REASON_HARNESS_ERROR,
    REASON_RATE_LIMITED,
    REASON_TIMED_OUT,
    HarnessOutcome,
    make_prediction,
    model_patch_from_record,
    read_resolved,
    read_run_report,
    read_swebench_timeouts,
    run_swebench_one,
    swebench_oracle,
    swebench_record_oracle,
    timeout_for_instance,
    verify_constants,
    write_predictions,
)


def _record(*kinds_payloads):
    return [{"kind": k, "payload": p} for k, p in kinds_payloads]


def test_model_patch_from_record_takes_the_selected_patch():
    rec = _record(
        ("SuspectFiles", {"files": ["m.py"]}),
        ("SelectedPatch", {"slot": 0, "model_patch": "diff --git a/m.py b/m.py\n+x"}),
    )
    assert model_patch_from_record(rec) == "diff --git a/m.py b/m.py\n+x"
    assert model_patch_from_record(_record(("Exhausted", {"rounds": 2}))) == ""  # no patch -> ""


def test_record_oracle_grades_the_extracted_patch_via_the_injected_grader():
    # stub grade: resolved iff the patch contains "GOOD" — no Docker, proves extraction + wiring.
    oracle = swebench_record_oracle(
        report_root="/unused", dataset_name="d", grade=lambda iid, patch: "GOOD" in patch
    )
    good = _record(("SelectedPatch", {"slot": 0, "model_patch": "diff GOOD"}))
    res = oracle.grade(good, {"instance_id": "pallets__flask-4045"})
    assert res.passed is True and res.metric == "resolved"
    assert (
        res.oracle_class == EXTERNAL_GRADER and res.replayable is False
    )  # run-and-observe, labeled

    bad = _record(("SelectedPatch", {"slot": 0, "model_patch": "diff BAD"}))
    assert oracle.grade(bad, {"instance_id": "x"}).passed is False


def test_record_oracle_drops_graded_test_edits_before_grading():
    # #72 NET 1: the grade boundary filters the SelectedPatch against the instance's test_patch files, so a
    # topology that emits a raw diff (no internal drop) can't weaken a graded test or collide with test_patch.
    captured = []
    oracle = swebench_record_oracle(
        report_root="/unused",
        dataset_name="d",
        grade=lambda iid, p: bool(captured.append(p)) or True,
    )
    patch = (
        "diff --git a/src/app.py b/src/app.py\n@@ -1 +1 @@\n-x\n+y\n"
        "diff --git a/tests/test_x.py b/tests/test_x.py\n@@ -1 +1 @@\n-assert a\n+assert True\n"
    )
    gt = {
        "instance_id": "i",
        "test_patch": "diff --git a/tests/test_x.py b/tests/test_x.py\n--- a/tests/test_x.py\n+++ b/tests/test_x.py\n",
    }
    oracle.grade(_record(("SelectedPatch", {"slot": 0, "model_patch": patch})), gt)
    graded = captured[0]
    assert "src/app.py" in graded  # the real source edit is graded
    assert "tests/test_x.py" not in graded  # the graded-test edit was dropped before grading


def test_record_oracle_no_patch_is_not_resolved_without_grading():
    calls = []
    oracle = swebench_record_oracle(
        report_root="/unused", dataset_name="d", grade=lambda iid, patch: calls.append(1) or True
    )
    res = oracle.grade(_record(("Exhausted", {"rounds": 1})), "x")  # ground_truth as a bare id
    assert res.passed is False and "no model_patch" in res.detail
    assert calls == []  # the Docker grader is never invoked when there's nothing to grade


def test_make_prediction_has_exactly_the_three_real_fields():
    pred = make_prediction("astropy__astropy-12907", "diff --git a/x b/x\n...", model_name="m")
    assert pred == {
        "instance_id": "astropy__astropy-12907",
        "model_name_or_path": "m",
        "model_patch": "diff --git a/x b/x\n...",
    }
    assert set(pred) == {KEY_INSTANCE_ID, KEY_MODEL, KEY_PREDICTION}  # no invented fields


def test_write_predictions_jsonl_roundtrips(tmp_path):
    preds = [make_prediction("a", "pa"), make_prediction("b", "pb")]
    path = write_predictions(preds, tmp_path / "preds.jsonl")
    lines = path.read_text().strip().splitlines()
    assert [json.loads(line)["instance_id"] for line in lines] == ["a", "b"]


def _write_report(tmp_path, run_id, model, instance_id, resolved):
    d = tmp_path / run_id / model / instance_id
    d.mkdir(parents=True)
    (d / "report.json").write_text(
        json.dumps({instance_id: {"resolved": resolved, "patch_successfully_applied": True}})
    )


def test_read_resolved_reads_the_per_instance_report(tmp_path):
    _write_report(tmp_path, "run1", "substrate-coding-flow", "astropy__astropy-1", True)
    _write_report(tmp_path, "run1", "substrate-coding-flow", "django__django-2", False)
    assert read_resolved(tmp_path, "run1", "substrate-coding-flow", "astropy__astropy-1") is True
    assert read_resolved(tmp_path, "run1", "substrate-coding-flow", "django__django-2") is False


def test_read_resolved_mirrors_the_model_name_slash_rewrite(tmp_path):
    # the harness writes the model dir with '/' -> '__'; read_resolved must mirror that or miss it.
    _write_report(tmp_path, "run1", "org__model", "x-1", True)
    assert read_resolved(tmp_path, "run1", "org/model", "x-1") is True


def test_read_run_report_asserts_schema_version(tmp_path):
    good = tmp_path / "m.run1.json"
    good.write_text(json.dumps({"resolved_ids": ["a"], "total_instances": 1, "schema_version": 2}))
    assert read_run_report(good)["resolved_ids"] == ["a"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": 1}))
    with pytest.raises(ValueError):
        read_run_report(bad)


def test_verify_constants_is_a_noop_without_swebench():
    # swebench is not installed here; verify_constants must return cleanly, not raise.
    verify_constants()


def test_swebench_oracle_grades_from_a_prerun_report(tmp_path):
    _write_report(tmp_path, "run1", "substrate-coding-flow", "astropy__astropy-1", True)
    oracle = swebench_oracle(report_dir=tmp_path, run_id="run1")
    res = oracle.grade([], "astropy__astropy-1")
    assert res.passed is True and res.oracle_class == EXTERNAL_GRADER and res.replayable is False
    # a missing report is not-resolved with a note, never a crash.
    miss = oracle.grade([], "never-ran-instance")
    assert miss.passed is False and "no swebench report" in miss.detail


def test_firewall_check_both_test_id_formats() -> None:
    from substrate.topologies.swebench_solver.firewall import firewall_check

    clean = {
        "patch": "+++ b/src/m.py\n",
        "test_patch": "+++ b/tests/test_m.py\n",
        "FAIL_TO_PASS": ["tests/test_m.py::test_new"],
    }
    assert firewall_check(clean)[0] is True

    # the gold patch touches a TEST file -> a held-out test could be pre-existing -> leak.
    shared = {
        "patch": "+++ b/tests/test_m.py\n",
        "test_patch": "+++ b/tests/test_m.py\n",
        "FAIL_TO_PASS": ["tests/test_m.py::test_new"],
    }
    assert firewall_check(shared)[0] is False

    # a FAIL_TO_PASS whose file is NOT added by test_patch is pre-existing -> leak.
    preexisting = {
        "patch": "+++ b/src/m.py\n",
        "test_patch": "+++ b/tests/test_other.py\n",
        "FAIL_TO_PASS": ["tests/test_m.py::test_x"],
    }
    assert firewall_check(preexisting)[0] is False

    # Real Django format: `test_x (auth_tests.test_forms.UserChangeFormTest)` — the parser
    # derives `auth_tests/test_forms.py` and matches with the sys.path-boundary rule
    # (equality OR endswith `"/" + derived`). Django puts `tests/` on sys.path, so test_patch
    # adds the file at `tests/auth_tests/test_forms.py` — matches as suffix. Real payload from
    # `django__django-16139`.
    django_clean = {
        "patch": "+++ b/django/contrib/auth/forms.py\n",
        "test_patch": "+++ b/tests/auth_tests/test_forms.py\n",
        "FAIL_TO_PASS": [
            "test_link_to_password_reset_in_helptext_via_to_field "
            "(auth_tests.test_forms.UserChangeFormTest)"
        ],
    }
    assert firewall_check(django_clean)[0] is True

    # F7 regression pin: substring-leak must fail closed. Pre-F7 substring `auth_tests` matched
    # `tests/auth_tests/other_file.py` — a pre-existing test not touched by test_patch.
    # Post-F7-round-2 the derived path `auth_tests/test_forms.py` doesn't equal or suffix-match
    # `tests/auth_tests/other_file.py`, so the leak fails closed.
    django_leak = {
        "patch": "+++ b/django/contrib/auth/forms.py\n",
        "test_patch": "+++ b/tests/auth_tests/other_file.py\n",
        "FAIL_TO_PASS": [
            "test_link_to_password_reset_in_helptext_via_to_field "
            "(auth_tests.test_forms.UserChangeFormTest)"
        ],
    }
    assert firewall_check(django_leak)[0] is False


# F2 fix (review 2026-08-08): recall@k banking per instance at grade time.
def test_suspect_files_from_record_reads_last_suspects():
    from substrate.assay.swebench import suspect_files_from_record

    rec = _record(
        ("SuspectFiles", {"files": ["a.py", "b.py"]}),
        # A second SuspectFiles later in the record (a re-localize) — LAST wins.
        ("SuspectFiles", {"files": ["c.py", "d.py"]}),
    )
    assert suspect_files_from_record(rec) == ("c.py", "d.py")
    # Empty tuple when the record carries none — a coding record, a topology without localize.
    assert suspect_files_from_record(_record()) == ()


def test_recall_metrics_computed():
    from substrate.assay.swebench import _recall_metrics

    gold_patch = "+++ b/src/a.py\n+++ b/src/b.py\n+++ b/src/c.py\n"
    # 2 of 3 gold files hit -> fractional 0.667, full recall False.
    r, full = _recall_metrics(["src/a.py", "src/b.py", "src/other.py"], gold_patch)
    assert r == pytest.approx(2 / 3)
    assert full is False
    # All 3 hit -> 1.0, full True.
    r, full = _recall_metrics(["src/a.py", "src/b.py", "src/c.py", "extra.py"], gold_patch)
    assert r == pytest.approx(1.0)
    assert full is True
    # None hit -> 0.0, full False.
    r, full = _recall_metrics(["nothing.py"], gold_patch)
    assert r == pytest.approx(0.0)
    assert full is False
    # No gold patch on the instance -> (None, None) so a coding-style oracle doesn't fabricate.
    r, full = _recall_metrics(["a.py"], "")
    assert r is None and full is None


def test_swebench_record_oracle_stamps_recall_on_result():
    # The oracle constructs Result directly (F2 fix) with recall_at_k + full_recall_at_k
    # populated from the record's SuspectFiles + the instance's gold patch. Verifies the
    # end-to-end path: record -> suspects, ground_truth -> gold, Result -> both fields.
    oracle = swebench_record_oracle(
        report_root="/tmp/dummy",
        dataset_name="dummy",
        grade=lambda _iid, _patch: True,  # stub the harness
    )
    rec = _record(
        ("SuspectFiles", {"files": ["src/a.py", "src/b.py"]}),
        ("SelectedPatch", {"slot": 0, "model_patch": "diff --git a/src/a.py b/src/a.py\n+x\n"}),
    )
    ground_truth = {
        "instance_id": "test__x-1",
        "patch": "+++ b/src/a.py\n+++ b/src/b.py\n",  # 2 gold files, both in suspects
        "test_patch": "",
    }
    result = oracle.grade(rec, ground_truth)
    assert result.passed is True
    assert result.recall_at_k == pytest.approx(1.0)
    assert result.full_recall_at_k is True
    assert result.oracle_class == EXTERNAL_GRADER
    # grader_error_band rides on the Result (SWE-bench Lite default 0.078).
    assert result.grader_error_band == pytest.approx(0.078)


def test_swebench_record_oracle_stamps_recall_even_when_patch_empty():
    # A run that emitted no SelectedPatch still gets recall banked — localization can be right
    # while repair fails, and the writeup needs to see that separately.
    oracle = swebench_record_oracle(
        report_root="/tmp/dummy", dataset_name="dummy", grade=lambda _i, _p: False
    )
    rec = _record(
        ("SuspectFiles", {"files": ["src/a.py"]}),  # localizer found the file
        # NO SelectedPatch — repair failed.
    )
    ground_truth = {
        "instance_id": "x",
        "patch": "+++ b/src/a.py\n+++ b/src/b.py\n",  # 2 gold, 1 in suspects
        "test_patch": "",
    }
    result = oracle.grade(rec, ground_truth)
    assert result.passed is False
    assert result.recall_at_k == pytest.approx(0.5)  # 1 of 2 gold files hit
    assert result.full_recall_at_k is False


def test_harness_reasons_closed_set_names_every_documented_state():
    # H-3 (ratified 2026-08-10) + rate-limit fold (2026-08-11): the closed set of reason
    # strings for NO_VERDICT rows. Named constants + the frozenset must stay in sync;
    # a new failure mode extends BOTH. rate_limited joined the set to distinguish
    # provider-capacity denial from harness_error (design
    # DESIGN-2026-08-11-responder-rate-limit-shim.md).
    assert _HARNESS_REASONS == frozenset(
        {
            REASON_TIMED_OUT,
            REASON_CONTAINER_CRASHED,
            REASON_DOCKER_ERROR,
            REASON_HARNESS_ERROR,
            REASON_GIT_ERROR,
            REASON_FIREWALL_VIOLATION,
            REASON_RATE_LIMITED,
        }
    )
    # The strings are the exact wire form the writeup + runner rows quote.
    assert REASON_TIMED_OUT == "timed_out"
    assert REASON_CONTAINER_CRASHED == "container_crashed"
    assert REASON_RATE_LIMITED == "rate_limited"


def test_harness_outcome_carries_typed_verdict_and_reason():
    o = HarnessOutcome(verdict=Verdict.NO_VERDICT, reason=REASON_TIMED_OUT, detail="wall 60s")
    assert o.verdict is Verdict.NO_VERDICT
    assert o.reason == REASON_TIMED_OUT
    with pytest.raises((AttributeError, TypeError)):
        o.reason = REASON_HARNESS_ERROR  # type: ignore[misc]


def test_run_swebench_one_empty_patch_is_fail_without_docker(tmp_path):
    # Defensive: an empty patch is a FAIL, not a NO_VERDICT — the harness never had
    # anything to grade. Docker never fires. Callers that go through the oracle already
    # short-circuit; the grader is defensive so a direct caller cannot get NO_VERDICT
    # for empty input.
    out = run_swebench_one(
        "astropy__astropy-12345",
        "",
        dataset_name="princeton-nlp/SWE-bench_Verified",
        model_name="substrate",
        run_id="test-empty",
        report_dir=tmp_path,
        timeout_seconds=60,
    )
    assert out.verdict is Verdict.FAIL
    assert out.reason == ""


def test_read_swebench_timeouts_returns_empty_dict_when_absent(tmp_path):
    missing = tmp_path / "nope.json"
    assert read_swebench_timeouts(missing) == {}


def test_read_swebench_timeouts_parses_repo_map(tmp_path):
    p = tmp_path / "t.json"
    p.write_text('{"astropy/astropy": 3600, "django/django": 1800}')
    assert read_swebench_timeouts(p) == {"astropy/astropy": 3600, "django/django": 1800}


def test_timeout_for_instance_uses_table_prefix():
    table = {"astropy/astropy": 3600, "sympy/sympy": 5400}
    # instance_id shape: `{owner}__{repo}-{issue}` -> `{owner}/{repo}`
    assert timeout_for_instance("astropy__astropy-12345", table) == 3600
    assert timeout_for_instance("sympy__sympy-987", table) == 5400
    # Unknown repo falls back to the 60-min default (a repo we didn't measure).
    assert timeout_for_instance("some__unknown-1", table) == 60 * 60


def test_swebench_record_oracle_recall_none_on_missing_gold_or_suspects():
    # No gold in ground_truth -> None (can't compute).
    oracle = swebench_record_oracle(
        report_root="/tmp/dummy", dataset_name="dummy", grade=lambda _i, _p: True
    )
    result = oracle.grade(
        _record(
            ("SuspectFiles", {"files": ["a.py"]}),
            ("SelectedPatch", {"slot": 0, "model_patch": "x"}),
        ),
        {"instance_id": "x", "patch": "", "test_patch": ""},
    )
    assert result.recall_at_k is None
    assert result.full_recall_at_k is None

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Oracle taxonomy — Sprint 2 of the objective-validation layer.

Two Oracle classes, the split the round-1 design (docs/benchmarking/benchmarking-design-round1.md §3) makes for
honesty: a log-projection Oracle grades by reading a typed terminal value off the inner RECORD
(deterministic, replayable); an external-grader Oracle grades by running an EXTERNAL system
(run-and-observe, NOT replayable). Both tested here without a network or a container — the
log-projection path against a real deterministic topology record, the external path against a stub
grader standing in for the Docker/test-harness run.
"""

from substrate.api import Runtime, read_record
from substrate.assay.oracle import (
    EXTERNAL_GRADER,
    LOG_PROJECTION,
    ExternalGraderOracle,
    LogProjectionOracle,
    Result,
    Verdict,
)
from substrate.topologies.tool_loop import tool_loop_topology


def _final_answer_text(envelopes):
    """Project the topology's terminal state off the record: the last FinalAnswer's text."""
    finals = [e for e in envelopes if e["kind"] == "FinalAnswer"]
    return finals[-1]["payload"]["text"] if finals else None


async def test_log_projection_oracle_grades_off_the_record(tmp_path):
    # the tool_loop calculator deterministically answers "20"; grade that record against ground truth.
    await Runtime(tmp_path / "run").run(tool_loop_topology())
    record = list(read_record(tmp_path / "run"))
    oracle = LogProjectionOracle(extract=_final_answer_text, metric="exact_match")

    good = oracle.grade(record, "20")
    assert good.passed is True and good.score == 1.0 and good.metric == "exact_match"
    assert good.oracle_class == LOG_PROJECTION and good.replayable is True

    bad = oracle.grade(record, "21")
    assert bad.passed is False and bad.score == 0.0 and bad.replayable is True


async def test_log_projection_oracle_is_a_pure_function_of_the_record(tmp_path):
    # same record + same ground truth -> identical Result. "Replayable" means the grade is
    # deterministic: nothing external, so it re-derives off the log every time.
    await Runtime(tmp_path / "run").run(tool_loop_topology())
    record = list(read_record(tmp_path / "run"))
    oracle = LogProjectionOracle(extract=_final_answer_text)
    assert oracle.grade(record, "20") == oracle.grade(record, "20")


def test_external_grader_oracle_is_labeled_run_and_observe():
    # a stub external grader stands in for a Docker / test-harness run: it actually "runs" (we count
    # the call) and returns a verdict + detail. The Result is stamped replayable=False so a reader
    # never mistakes a run-and-observe grade for a reproducible log-projection one.
    calls = {"n": 0}

    def grader(envelopes, ground_truth):
        calls["n"] += 1
        return (ground_truth == "resolve", "ran the external harness")

    oracle = ExternalGraderOracle(grader=grader, metric="resolved")
    res = oracle.grade([{"kind": "X", "payload": {}}], "resolve")
    assert res.passed is True and res.score == 1.0 and res.metric == "resolved"
    assert res.oracle_class == EXTERNAL_GRADER and res.replayable is False
    assert res.detail == "ran the external harness"
    assert calls["n"] == 1  # the external system actually ran (it is not a pure projection)

    miss = oracle.grade([{"kind": "X", "payload": {}}], "other")
    assert miss.passed is False and miss.replayable is False


def test_log_projection_oracle_supports_a_custom_compare():
    # ground truth need not be exact equality — e.g. substring / tolerance. The compare hook decides.
    oracle = LogProjectionOracle(
        extract=lambda envs: "the answer is 20",
        metric="contains",
        compare=lambda observed, target: target in observed,
    )
    assert oracle.grade([], "20").passed is True
    assert oracle.grade([], "99").passed is False


def test_result_is_a_frozen_verdict():
    # the verdict is immutable data; the honesty flags ride on it, not in a comment.
    r = Result(
        verdict=Verdict.PASS, score=1.0, metric="m", oracle_class=LOG_PROJECTION, replayable=True
    )
    assert r.passed is True  # H-2: passed is a derived property of verdict
    try:
        setattr(r, "verdict", Verdict.FAIL)
        raised = False
    except (AttributeError, TypeError):
        raised = True
    assert raised  # frozen

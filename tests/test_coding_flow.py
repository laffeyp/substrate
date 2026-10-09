# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Tests for the coding_flow topology — best-of-N codegen + build-validation + a correction loop.

The validator runs a REAL gate (ruff + mypy + pytest in a subprocess), so the run is not
replay-deterministic (verdict order tracks subprocess timing). These assert the OUTCOME — which
candidate the gate passes, which terminal the run reaches — which IS deterministic for the canned
candidates. The @realmodel test closes the loop with a real local coder + the real gate.
"""

import pytest

from substrate.api import Runtime, read_record
from substrate.topologies.coding_flow import (
    ci_responders,
    coding_flow_topology,
    walkthrough_responders,
)
from substrate.topologies.coding_flow.gate import parse_artifacts, run_gate
from substrate.topologies.coding_flow.task import CodingTask, kvstore_task

_OLLAMA_V1 = "http://localhost:11434/v1"
# distinct model FAMILIES — best-of-N's diversity is meant to come from different models, not just
# different samples of one. The ensemble test picks up to k of whatever is installed.
_CODERS = [
    "qwen2.5-coder:7b",
    "deepseek-r1:8b",
    "llama3:8b",
    "qwen2.5:7b-instruct",
    "qwen2.5-coder:3b",
    "llama3.2:3b",
]


def _outcome(events: list[dict]) -> dict | None:
    return next((e for e in events if e["kind"] in ("Solved", "Exhausted")), None)


def _kinds(events: list[dict], kind: str) -> list[dict]:
    return [e["payload"] for e in events if e["kind"] == kind]


# ── the deterministic gate core (no topology, no model) ─────────────────────────


def test_gate_discriminates_good_from_buggy() -> None:
    task = kvstore_task()
    good = run_gate({**task.fixtures, **parse_artifacts(task.ci_good)}, task.gate)
    bad = run_gate({**task.fixtures, **parse_artifacts(task.ci_bad)}, task.gate)
    assert good.passed and good.returncode == 0
    # the buggy candidate is ruff/mypy-clean but behaviourally wrong — only running the tests catches it
    assert not bad.passed
    assert "failed" in bad.summary.lower() or "passed" in bad.summary


def test_parse_artifacts_extracts_each_file() -> None:
    arts = parse_artifacts(kvstore_task().ci_good)
    assert set(arts) == {"store.py", "router.py"}
    assert "class Store" in arts["store.py"] and "def handle" in arts["router.py"]


def test_no_artifacts_fails_the_gate_without_crashing() -> None:
    r = run_gate(parse_artifacts("the model said nothing useful"), "true")
    assert not r.passed  # empty payloads -> a clean fail, not an exception


def test_gate_rejects_path_traversal_without_crashing() -> None:
    # a candidate writing a path that escapes the sandbox must be a FAILED gate, never an uncaught
    # raise (which would kill the validator Producer and wedge the run).
    r = run_gate({"../escape.py": "x = 1\n"}, "true")
    assert not r.passed
    assert "outside the sandbox" in r.summary


def test_fixtures_win_over_a_colliding_candidate_file() -> None:
    # the held-out test must win on a key collision so a candidate cannot overwrite the test it is
    # graded against. The validator merges {**candidate, **fixtures}; here a "passing" candidate also
    # emits a file at the fixture path with a trivially-passing test, but the real fixture (which the
    # candidate's code fails) must be what runs -> the gate fails.
    task = CodingTask(
        name="collide",
        spec="",
        gate="python -m pytest -q",
        fixtures={
            "test_it.py": "from m import f\n\n\ndef test_it() -> None:\n    assert f() == 1\n"
        },
        ci_good="",
        ci_bad="",
    )
    # candidate writes m.py (f returns 2 -> fails the real test) AND tries to overwrite test_it.py with
    # a vacuous pass. fixtures must win, so the real test runs and fails.
    candidate = {
        "m.py": "def f() -> int:\n    return 2\n",
        "test_it.py": "def test_it() -> None:\n    assert True\n",
    }
    merged = {**candidate, **task.fixtures}  # the order the validator now uses
    r = run_gate(merged, task.gate)
    assert not r.passed  # the held-out test ran (f()==2 != 1), not the candidate's vacuous one


# ── the topology in CI mode (deterministic OUTCOME) ─────────────────────────────


async def test_best_of_n_validates_all_then_selects_the_passing_one(tmp_path) -> None:
    task = kvstore_task()
    topo = coding_flow_topology(task, responders=ci_responders(task, 3), n=3, max_rounds=2)
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))

    verdicts = _kinds(events, "Verdict")
    assert len(verdicts) == 3  # the full best-of-N comparison is on the record before selection
    assert sum(v["passed"] for v in verdicts) == 1  # exactly one good candidate
    out = _outcome(events)
    assert out is not None and out["kind"] == "Solved"
    # selection tracks the gate, not a guess: the chosen slot's verdict actually passed
    assert any(v["slot"] == out["payload"]["slot"] and v["passed"] for v in verdicts)


class _CorrectingStub:
    """Buggy on the seed round; correct once it sees a gate failure in the prompt — drives the loop."""

    def __init__(self, task: CodingTask) -> None:
        self._task = task

    def respond(self, prompt: str) -> str:
        return self._task.ci_good if "FAILED the gate" in prompt else self._task.ci_bad


async def test_correction_loop_fixes_after_a_failed_round(tmp_path) -> None:
    task = kvstore_task()
    topo = coding_flow_topology(
        task, responders=[_CorrectingStub(task) for _ in range(3)], n=3, max_rounds=2
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))

    out = _outcome(events)
    assert out is not None and out["kind"] == "Solved"
    assert out["payload"]["round"] == 2  # round 1 all failed -> failures fed back -> round 2 passed
    assert len(_kinds(events, "Verdict")) == 6  # 3 candidates per round, both rounds on the record


async def test_exhausted_when_every_round_fails(tmp_path) -> None:
    task = kvstore_task()  # all stubs stay buggy with max_rounds=1 -> no correction round
    topo = coding_flow_topology(
        task, responders=[_CorrectingStub(task) for _ in range(3)], n=3, max_rounds=1
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))

    out = _outcome(events)
    assert out is not None and out["kind"] == "Exhausted"
    assert out["payload"]["rounds"] == 1
    assert all(not v["passed"] for v in _kinds(events, "Verdict"))


# ── walkthrough: a real local coder closes the loop against the real gate ───────


def _ensemble(k: int) -> list[str]:
    """Up to k DISTINCT installed coder models — best-of-N over an ensemble of different families.
    Skips if Ollama is unreachable or none of the candidates are installed."""
    try:
        import httpx

        ids = {m["id"] for m in httpx.get(_OLLAMA_V1 + "/models", timeout=4).json().get("data", [])}
    except Exception as exc:  # noqa: BLE001 - any unreachability is a SKIP
        pytest.skip(
            f"coding_flow walkthrough skipped — Ollama not reachable ({type(exc).__name__})"
        )
    available = [m for m in _CODERS if m in ids]
    if not available:
        pytest.skip(f"coding_flow walkthrough skipped — none of {_CODERS} installed")
    return available[:k]


@pytest.mark.realmodel
@pytest.mark.timeout(600)
async def test_walkthrough_ensemble_closes_the_loop(tmp_path) -> None:
    # the claim: a best-of-N ENSEMBLE of real local coders (different model families) + the REAL gate
    # reaches a terminal — Solved if any candidate's code passes ruff+mypy+pytest, else Exhausted.
    # Either is a pass: it proves the loop closes on real, heterogeneous model output.
    models = _ensemble(3)
    task = kvstore_task()
    topo = coding_flow_topology(
        task, responders=walkthrough_responders(models), n=len(models), max_rounds=2, timeout=180
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))

    assert _kinds(events, "Candidate"), "the ensemble produced at least one candidate"
    assert _kinds(events, "Verdict"), "each candidate was really gate-validated"
    out = _outcome(events)
    assert out is not None and out["kind"] in ("Solved", "Exhausted")


async def test_a_failing_drafter_still_closes_the_loop(tmp_path) -> None:
    """UI sprint 097: a model call that raises (truncation cap, timeout, network) is a failed
    candidate for its slot, so the round completes and the run reaches Exhausted, not the watchdog."""

    class _Boom:
        def respond(self, prompt: str) -> str:
            raise RuntimeError("reply hit the token cap")

    topo = coding_flow_topology(kvstore_task(), responders=[_Boom()], n=2, max_rounds=1, timeout=60)
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))
    assert [e for e in events if e["kind"] == "Exhausted"], "the loop must close on Exhausted"
    assert not [e for e in events if e["kind"] == "substrate.ProducerFailed"]
    cands = [e["payload"]["response"] for e in events if e["kind"] == "Candidate"]
    assert len(cands) == 2 and all("model call failed" in c for c in cands)

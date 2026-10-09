# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""End-to-end observation contract for the full swebench_solver topology (sprint 141): LOCALIZE -> REPAIR
-> SELECT on a FIXTURE repo with deterministic responders + a stand-in runner. The record is the
observable — a SelectedPatch with the resolving diff comes out the far end of the whole pipeline.

Sprint 173 (F9 fold): every test in this file legitimately constructs the retired heavy
topology `swebench_solver_topology_with_test_selection`; the module-level filter here opts
out of the pyproject `filterwarnings` gate that elevates the deprecation to error. A new
consumer OUTSIDE this file trips the gate; the tests here explicitly own the deprecation
and stay green. KIT_DIARY finding 38 named the retire-in-place discipline; this filter is
the per-file opt-in that discipline calls for. The deprecation fires at CALL time
(warnings.warn inside the function body at assemble.py:553), not at import, so pytestmark
correctly sits AFTER the imports."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from substrate.api import Runtime, read_record
from substrate.topologies.swebench_solver.assemble import (
    swebench_repair_topology,
    swebench_solver_topology_with_test_selection,
)

pytestmark = pytest.mark.filterwarnings(
    "ignore:swebench_solver_topology_with_test_selection is deprecated:DeprecationWarning"
)

_FIX = "# path: m.py\n<<<<<<< SEARCH\n    return x\n=======\n    return x + 1\n>>>>>>> REPLACE\n"


def _fixture_repo() -> str:
    d = tempfile.mkdtemp()
    (Path(d) / "m.py").write_text("def f(x):\n    return x\n")
    (Path(d) / "README.md").write_text("a fixture\n")
    for args in (
        ["git", "-C", d, "init", "-q"],
        ["git", "-C", d, "config", "user.email", "t@t"],
        ["git", "-C", d, "config", "user.name", "t"],
        ["git", "-C", d, "add", "-A"],
        ["git", "-C", d, "commit", "-qm", "base"],
    ):
        subprocess.run(args, capture_output=True, check=True)
    return d


class _SolverResponder:
    """One stand-in for both phases: returns the suspect file on a LOCALIZE prompt, the SEARCH/REPLACE fix
    on a REPAIR prompt (keyed on a distinctive localize phrase)."""

    def respond(self, prompt: str) -> str:
        return "m.py\n" if "suspect file" in prompt else _FIX


class _StubRunner:
    """Regression passes; the reproduction test reports the issue resolved."""

    def run(
        self, model_patch: str, test_command: str, extra_files: dict[str, str] | None = None
    ) -> tuple[int, str]:
        return (0, "1 passed in 0.1s") if test_command == "REG" else (0, "Issue resolved")


async def test_swebench_solver_end_to_end_on_a_fixture(tmp_path) -> None:  # type: ignore[no-untyped-def]
    base = _fixture_repo()
    topo = swebench_solver_topology_with_test_selection(
        responders=[_SolverResponder() for _ in range(2)],
        base_checkout=base,
        issue="make f(x) return x + 1",
        repo_skeleton="m.py\nREADME.md",
        known_files={"m.py", "README.md"},
        runner=_StubRunner(),
        regression_command="REG",
        n=2,
        max_rounds=1,
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))

    # the pipeline ran every phase: localization, N applied patches, test results, a selection.
    assert [e["payload"]["files"] for e in events if e["kind"] == "SuspectFiles"] == [["m.py"]]
    applied = [e["payload"] for e in events if e["kind"] == "AppliedPatch"]
    assert len(applied) == 2 and all("+    return x + 1" in a["model_patch"] for a in applied)
    assert len([e for e in events if e["kind"] == "TestResults"]) == 2
    selected = [e["payload"] for e in events if e["kind"] == "SelectedPatch"]
    assert len(selected) == 1 and "+    return x + 1" in selected[0]["model_patch"]


class _BaseDiffRunner:
    """Emits pytest -rA style output. The regression set has one pre-existing base failure (test_env, fails
    in BOTH runs) and one base-passing test (test_ok). Proves passed_at_base routes SELECT through
    regression_held: the pre-existing failure must NOT sink the candidate."""

    def run(
        self, model_patch: str, test_command: str, extra_files: dict[str, str] | None = None
    ) -> tuple[int, str]:
        if test_command == "REG":
            return (
                1,
                "PASSED t/test_ok.py::test_a\nFAILED t/test_env.py::test_b - Deprecation\n1 passed, 1 failed",
            )
        return (0, "Issue resolved")


async def test_passed_at_base_routes_select_through_regression_held(tmp_path) -> None:  # type: ignore[no-untyped-def]
    base = _fixture_repo()
    topo = swebench_solver_topology_with_test_selection(
        responders=[_SolverResponder() for _ in range(2)],
        base_checkout=base,
        issue="make f(x) return x + 1",
        repo_skeleton="m.py\nREADME.md",
        known_files={"m.py", "README.md"},
        runner=_BaseDiffRunner(),
        regression_command="REG",
        passed_at_base=frozenset({"t/test_ok.py::test_a"}),  # only test_ok passed at base
        n=2,
        max_rounds=1,
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))
    # whole-run regression_passed would be False (exit 1 + a FAILED line); passed_at_base must rescue it —
    # the base-passing test still passes, the pre-existing failure is not charged -> regression holds ->
    # a SelectedPatch comes out.
    results = [e["payload"] for e in events if e["kind"] == "TestResults"]
    assert results and all(r["regression_passed"] for r in results)
    assert len([e for e in events if e["kind"] == "SelectedPatch"]) == 1


def _repair(responders, base, n=2):
    return swebench_repair_topology(
        responders=responders,
        base_checkout=base,
        issue="make f(x) return x + 1",
        repo_skeleton="m.py\nREADME.md",
        known_files={"m.py", "README.md"},
        n=n,
        max_rounds=1,
    )


def _summary(events):
    s = [e["payload"] for e in events if e["kind"] == "RepairSummary"]
    return s[0] if s else None


async def test_repair_topology_emits_selected_outcome(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # the always-emit RepairSummary (#51): a clean fix -> SELECTED, with a SelectedPatch + the counts.
    await Runtime(tmp_path / "run").run(
        _repair([_SolverResponder() for _ in range(2)], _fixture_repo())
    )
    events = list(read_record(tmp_path / "run"))
    selected = [e["payload"] for e in events if e["kind"] == "SelectedPatch"]
    summary = _summary(events)
    assert len(selected) == 1 and "+    return x + 1" in selected[0]["model_patch"]
    assert summary is not None and summary["outcome"] == "selected"
    assert summary["selected_slot"] >= 0 and summary["applied"] >= 1 and summary["localized"] == 1


class _BadEditResponder:
    """Localizes m.py but its SEARCH text doesn't match the file -> nothing applies."""

    def respond(self, prompt: str) -> str:
        if "suspect file" in prompt:
            return "m.py\n"
        return "# path: m.py\n<<<<<<< SEARCH\nNOPE NOT IN FILE\n=======\nx\n>>>>>>> REPLACE\n"


async def test_repair_topology_no_applicable_edit_outcome(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # localization happened but the model's edits didn't match -> NO_APPLICABLE_EDIT (enumerated, not implicit).
    await Runtime(tmp_path / "run").run(
        _repair([_BadEditResponder() for _ in range(2)], _fixture_repo())
    )
    events = list(read_record(tmp_path / "run"))
    summary = _summary(events)
    assert summary is not None and summary["outcome"] == "no_applicable_edit"
    assert summary["localized"] == 1 and summary["applied"] == 0 and summary["selected_slot"] == -1
    assert not any(e["kind"] == "SelectedPatch" for e in events)


class _NoLocResponder:
    """Localizes nothing (no real file path); with no target the edit can't match -> nothing applies. The
    ONLY difference from _BadEditResponder is the localize output, so the outcome enum splits on it."""

    def respond(self, prompt: str) -> str:
        if "suspect file" in prompt:
            return "no idea which file\n"
        return "# path: m.py\n<<<<<<< SEARCH\nNOPE NOT IN FILE\n=======\nx\n>>>>>>> REPLACE\n"


async def test_repair_topology_no_localization_outcome(tmp_path) -> None:  # type: ignore[no-untyped-def]
    await Runtime(tmp_path / "run").run(
        _repair([_NoLocResponder() for _ in range(2)], _fixture_repo())
    )
    summary = _summary(list(read_record(tmp_path / "run")))
    assert (
        summary is not None
        and summary["outcome"] == "no_localization"
        and summary["localized"] == 0
    )


class _FlakyRunner:
    """Raises on the first call (a real container failure: OOM/timeout), then behaves — proves one patch's
    runner failure becomes a RECORDED not-resolved, not a gather-wedge that emits zero results (review #62)."""

    def __init__(self) -> None:
        self.calls = 0

    def run(
        self, model_patch: str, test_command: str, extra_files: dict[str, str] | None = None
    ) -> tuple[int, str]:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("container OOM")
        return (0, "1 passed in 0.1s") if test_command == "REG" else (0, "Issue resolved")


async def test_runner_failure_records_producer_failed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """2026-08-09 halt-on-error contract: a Docker runner exception in select_exec propagates
    from the producer, the kernel records ProducerFailed, and the topology finalizes without a
    SelectedPatch. No silent 'runner-error TestResults' pretending the cell succeeded."""
    base = _fixture_repo()
    topo = swebench_solver_topology_with_test_selection(
        responders=[_SolverResponder() for _ in range(2)],
        base_checkout=base,
        issue="make f(x) return x + 1",
        repo_skeleton="m.py\nREADME.md",
        known_files={"m.py", "README.md"},
        runner=_FlakyRunner(),
        regression_command="REG",
        n=2,
        max_rounds=1,
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))
    assert any(e["kind"] == "substrate.ProducerFailed" for e in events), (
        "runner failure must record ProducerFailed, not silent TestResults"
    )
    assert not any(e["kind"] == "SelectedPatch" for e in events), (
        "failed run must not emit a SelectedPatch"
    )


class _DyingDrafter:
    """Localizes fine, but the DRAFT model call dies — the drafter producer raises and the
    kernel records ProducerFailed. No silent 'failed Candidate' pretending the round completed."""

    def respond(self, prompt: str) -> str:
        if "suspect file" in prompt:
            return "m.py\n"
        raise RuntimeError("model died")


async def test_drafter_model_error_records_producer_failed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """2026-08-09 halt-on-error contract: a drafter model failure propagates as ProducerFailed
    on the record. The topology finalizes without a SelectedPatch. The runner (upstream of
    this test) then sees an incomplete cell and halts the sweep."""
    base = _fixture_repo()
    topo = swebench_solver_topology_with_test_selection(
        responders=[_DyingDrafter() for _ in range(2)],
        base_checkout=base,
        issue="make f(x) return x + 1",
        repo_skeleton="m.py\nREADME.md",
        known_files={"m.py", "README.md"},
        runner=_StubRunner(),
        regression_command="REG",
        n=2,
        max_rounds=1,
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))
    assert any(e["kind"] == "substrate.ProducerFailed" for e in events), (
        "drafter model error must record ProducerFailed, not a silent failed Candidate"
    )
    assert not any(e["kind"] == "SelectedPatch" for e in events)


class _DyingLocalizer:
    """The localizer model call dies — the localizer producer raises and the kernel records
    ProducerFailed. No silent empty-SuspectFiles pretending the localizer just found nothing."""

    def respond(self, prompt: str) -> str:
        raise RuntimeError("localizer model died")


async def test_localizer_model_error_records_producer_failed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """2026-08-09 halt-on-error contract: a localizer model failure propagates as ProducerFailed.
    The topology finalizes without EditLocations, so nothing seeds the loop. No SelectedPatch.
    Distinguishes 'localizer honestly found nothing' from 'localizer crashed' — the former
    would emit SuspectFiles(files=()), the latter emits ProducerFailed."""
    base = _fixture_repo()
    topo = swebench_solver_topology_with_test_selection(
        responders=[_DyingLocalizer() for _ in range(2)],
        base_checkout=base,
        issue="make f(x) return x + 1",
        repo_skeleton="m.py\nREADME.md",
        known_files={"m.py", "README.md"},
        runner=_StubRunner(),
        regression_command="REG",
        n=2,
        max_rounds=1,
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))
    assert any(e["kind"] == "substrate.ProducerFailed" for e in events), (
        "localizer model error must record ProducerFailed, not silent empty SuspectFiles"
    )
    assert not any(e["kind"] == "SuspectFiles" and e["payload"]["files"] == [] for e in events), (
        "no fake empty-SuspectFiles cover for a real crash"
    )
    assert not any(e["kind"] == "SelectedPatch" for e in events)

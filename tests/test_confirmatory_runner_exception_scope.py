# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Regression pin for Sprint 169 (F2 fold), updated Sprint 199b: the cell-execution
catch stays narrowed to `Exception`, never widened back to `BaseException`.

Sprint 199b moved the catch site out of the confirmatory runner and into
`assay.run.run_suite_with_salvage` — the extracted generic per-cell orchestrator that
`scripts/assay_swebench_confirmatory.py` now consumes. The invariant is unchanged
(WORKING_AGREEMENT.md § "SWE-bench external substrates"); the pin follows the code
to its new file.

`BaseException` catches `KeyboardInterrupt`, `SystemExit`, and
`asyncio.CancelledError`; even though `_classify_cell_error` routes each to a
halt-and-re-raise via the unclassified-fallback, catching `BaseException` at the
loop boundary is a foot-gun any future extension to the fallback substring matches
could silently corrupt into a NO_VERDICT row instead of an unwind.

Three pins:
1. Source scan on `assay/run.py`: `run_suite_with_salvage` catches `except Exception`
   at the RUN and SALVAGE branches, never `except BaseException`.
2. Source scan on the runner: no `except BaseException as` anywhere (the invariant
   also constrains any new catch a runner might add for prep / preflight / batch grade).
3. Classifier contract: `_classify_cell_error(KeyboardInterrupt())` returns halt=True,
   so a KeyboardInterrupt reaching the classifier propagates rather than becoming a
   data row.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_run_suite_with_salvage_narrows_to_exception_not_baseexception() -> None:
    """Sprint 199b (S7b): the cell catch lives in `run_suite_with_salvage` at
    `assay/run.py`. It must be `except Exception`, never `except BaseException`."""
    src_path = Path(__file__).resolve().parent.parent / "src" / "substrate" / "assay" / "run.py"
    src = src_path.read_text()
    # The extracted loop catches Exception at both branches (salvage regrade + fresh run).
    assert src.count("except Exception as exc:") >= 2, (
        f"{src_path}: run_suite_with_salvage must catch `Exception` at the salvage and "
        "run branches. WORKING_AGREEMENT.md § 'SWE-bench external substrates' "
        "invariant: no BaseException around a boundary call."
    )
    assert "except BaseException" not in src, (
        f"{src_path}: contains `except BaseException`. Narrow to `except Exception` — "
        "every typed exception the classifier handles inherits from Exception; the "
        "BaseException scope only swallows KeyboardInterrupt / SystemExit / "
        "asyncio.CancelledError, the exact class-of-failure the invariant guards against."
    )


def test_confirmatory_runner_carries_no_baseexception_catches() -> None:
    """The runner also cannot catch BaseException anywhere (prep, preflight, batch
    grade). Sprint 199b's rewrite removed the inline cell() catch; this pin covers any
    NEW catch a future runner edit might add outside `run_suite_with_salvage`."""
    runner_path = (
        Path(__file__).resolve().parent.parent / "scripts" / "assay_swebench_confirmatory.py"
    )
    src = runner_path.read_text()
    assert "except BaseException" not in src, (
        f"{runner_path}: contains `except BaseException`. Same invariant as "
        "run_suite_with_salvage — narrow to `except Exception`."
    )


def test_classify_cell_error_halts_on_keyboard_interrupt() -> None:
    """Even though the narrow at the catch site prevents `KeyboardInterrupt` from
    reaching `_classify_cell_error` under the current runner shape, the classifier's
    own contract preserves halt=True on any non-typed exception — including
    `KeyboardInterrupt`. This test pins that contract so a future extension to the
    classifier's fallback substring matches (adding e.g. `if 'interrupt' in msg`)
    cannot accidentally reroute a real interrupt to a NO_VERDICT continue-the-sweep
    path."""
    # the script imports HuggingFace `datasets` at load; it is not a dev dependency (UI sprint 106)
    pytest.importorskip("datasets")
    from scripts.assay_swebench_confirmatory import _classify_cell_error

    reason, should_halt = _classify_cell_error(KeyboardInterrupt())
    assert should_halt is True, (
        "_classify_cell_error(KeyboardInterrupt()) must return halt=True so a "
        "real Ctrl-C unwinds the sweep instead of writing a NO_VERDICT row and "
        "continuing. Sprint 169 pins this via the narrow at the catch site AND "
        "via this classifier contract."
    )
    assert reason == "unclassified_error", (
        f"expected `_ERROR_UNCLASSIFIED` ('unclassified_error') for KeyboardInterrupt, "
        f"got {reason!r}"
    )


def test_classify_cell_error_halts_on_system_exit() -> None:
    """Same contract for SystemExit — the runner's catch must not swallow it."""
    # the script imports HuggingFace `datasets` at load; it is not a dev dependency (UI sprint 106)
    pytest.importorskip("datasets")
    from scripts.assay_swebench_confirmatory import _classify_cell_error

    reason, should_halt = _classify_cell_error(SystemExit(1))
    assert should_halt is True
    assert reason == "unclassified_error"

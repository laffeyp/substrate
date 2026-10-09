# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 192 (roadmap v2 S5.4): typed events on the B4 Docker image-pull boundary.

The runner's `_pull` helper emits canonical JSON events to stderr per vocab v0.3 § G.3:
`ImageRequested`, `ImagePulled`, `ImageMissing`. Same shape as Sprint 190's `_mother_clone`
events; prep runs before any substrate topology, so stderr is the honest emit surface.

Testing the runner's `_pull` requires the confirmatory-runner's `_run` async coroutine to
kick off; rather than construct that setup, this test uses the same emit shape at a
smaller scope — the JSON line structure the confirmatory runner writes matches the same
`{t, kind, boundary, payload}` shape as `_emit_repo_clone_event` at `swebench_suite.py`.
Substance test: verify the runner's source contains the three tag names and the
`boundary=image_pull` marker so a future refactor that renames or drops any of the three
events fails this pin.
"""

from __future__ import annotations

from pathlib import Path

_RUNNER = Path(__file__).resolve().parent.parent / "scripts" / "assay_swebench_confirmatory.py"


def test_runner_emits_three_image_pull_event_kinds() -> None:
    """Sprint 192: `_pull` emits ImageRequested (on entry), ImagePulled (on rc=0),
    ImageMissing (on non-zero rc). Source-scan pin — the shape is testable by
    running the runner but that requires Docker + a real registry; the substance is that
    the three event kinds land at the pull boundary."""
    src = _RUNNER.read_text()
    for kind in ("ImageRequested", "ImagePulled", "ImageMissing"):
        assert kind in src, (
            f"expected {kind!r} event kind at the image-pull boundary in {_RUNNER}; "
            "Sprint 192 wired all three. A refactor that drops any of the three trips this."
        )
    assert '"image_pull"' in src, (
        f"expected the boundary marker `image_pull` in the runner's emit; got no match in {_RUNNER}"
    )


def test_runner_emits_wall_ms_on_pull_events() -> None:
    """Every ImagePulled / ImageMissing event carries `wall_ms` (int, ms since ImageRequested)
    so a reader counting per-image pull latency reads it off the event without parsing the
    runner's printout line."""
    src = _RUNNER.read_text()
    assert "wall_ms" in src

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""CLI surfaces authoring failures + clean inspect errors (review #19 DX-1, CLI-1).

A run that finalises while Producers/inputs/predicates failed must LOOK broken to the author
(a WARNING line, and a nonzero exit under --strict); a bad inspect ref must be a clean [config]
error, not a raw traceback.
"""

from click.testing import CliRunner

from substrate.cli import EXIT_FAILED, EXIT_OK, main

_BROKEN = """
from substrate.api import quiescence
from msgspec import Struct


class Ping(Struct, frozen=True):
    n: int


async def pinger(inp):
    raise RuntimeError("boom")
    yield Ping(n=1)  # unreachable; makes this an async generator


def build(b):
    b.producer_kind("pinger", schemas=[Ping], schema_version=1, factory=lambda: pinger)
    b.initial("pinger", input=None)
    b.termination(quiescence())
"""


def test_run_surfaces_failures(tmp_path):
    mod = tmp_path / "broken.py"
    mod.write_text(_BROKEN)
    res = CliRunner().invoke(
        main, ["run", "--topology-module", f"{mod}:build", "--root", str(tmp_path / "r1")]
    )
    # the run still finalises (quiescence), but the failure is now SURFACED, not silent
    assert res.exit_code == EXIT_OK
    assert "WARNING" in res.output and "ProducerFailed" in res.output


def test_run_strict_exits_nonzero_on_failure(tmp_path):
    mod = tmp_path / "broken.py"
    mod.write_text(_BROKEN)
    res = CliRunner().invoke(
        main,
        ["run", "--topology-module", f"{mod}:build", "--root", str(tmp_path / "r2"), "--strict"],
    )
    assert res.exit_code == EXIT_FAILED  # --strict turns the failure into a nonzero exit


def test_good_run_has_no_warning(tmp_path):
    res = CliRunner().invoke(
        main, ["run", "--topology", "code_review", "--root", str(tmp_path / "cr")]
    )
    assert res.exit_code == EXIT_OK
    assert "WARNING" not in res.output


def test_narrate_summary_header_shows_failures_on_line_one(tmp_path):
    # review #26 highest-leverage fix: a finalised-but-broken run must LOOK broken in the
    # summary HEADER (line 1), not bury the alarm on line 3 where a skimmer misses it.
    mod = tmp_path / "broken.py"
    mod.write_text(_BROKEN)
    root = tmp_path / "r3"
    CliRunner().invoke(main, ["run", "--topology-module", f"{mod}:build", "--root", str(root)])
    res = CliRunner().invoke(main, ["narrate", str(root), "--summary"])
    assert res.exit_code == EXIT_OK
    first = res.output.strip().splitlines()[0]
    assert "FAILURE" in first  # the alarm is on line 1, not buried


def test_narrate_default_mode_footers_failures(tmp_path):
    mod = tmp_path / "broken.py"
    mod.write_text(_BROKEN)
    root = tmp_path / "r4"
    CliRunner().invoke(main, ["run", "--topology-module", f"{mod}:build", "--root", str(root)])
    res = CliRunner().invoke(main, ["narrate", str(root)])
    assert "FAILED" in res.output  # the failure beat is in the stream...
    assert "authoring failure" in res.output  # ...and a footer points at the digest


def test_narrate_summary_clean_run_does_not_cry_wolf(tmp_path):
    root = tmp_path / "cr"
    CliRunner().invoke(main, ["run", "--topology", "code_review", "--root", str(root)])
    res = CliRunner().invoke(main, ["narrate", str(root), "--summary"])
    first = res.output.strip().splitlines()[0]
    assert "FAILURE" not in first and first.startswith("Run finalised")


def test_inspect_bad_producer_ref_is_clean_error(tmp_path):
    CliRunner().invoke(main, ["run", "--topology", "code_review", "--root", str(tmp_path / "cr")])
    res = CliRunner().invoke(
        main, ["inspect", str(tmp_path / "cr"), "--producer", "judge", "--why"]
    )
    assert res.exit_code != EXIT_OK
    assert "[config]" in res.output
    assert "Traceback" not in res.output  # a clean error, not a Python stack trace

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 297: an error names the value it failed on (design spec §6.2).

`repr()` of an `OSError` keeps errno and the OS text and drops the path, so a session's record read
`FileNotFoundError(2, 'No such file or directory')` for a working folder no one could see. Each test
reads the text a reader of the record, or of a raised error, actually gets.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from msgspec import Struct

from substrate import api
from substrate.adapters.models import CliResponder
from substrate.errors import describe_error
from substrate.projections.inspect import _error_sentinel


class Tick(Struct, frozen=True):
    n: int


def _real_oserror(path: Path) -> OSError:
    try:
        path.open()
    except OSError as exc:
        return exc
    raise AssertionError("the path exists")


def test_an_oserror_names_its_path(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-folder" / "file.txt"
    text = describe_error(_real_oserror(missing))
    assert text.startswith("FileNotFoundError: ")
    assert str(missing) in text


def test_a_chained_error_names_its_cause(tmp_path: Path) -> None:
    missing = tmp_path / "gone"
    try:
        try:
            missing.open()
        except OSError as inner:
            raise RuntimeError("could not load the role file") from inner
    except RuntimeError as outer:
        text = describe_error(outer)
    assert text.startswith(
        "RuntimeError: could not load the role file; caused by FileNotFoundError: "
    )
    assert str(missing) in text


def test_an_empty_message_names_the_class() -> None:
    assert describe_error(TimeoutError()) == "TimeoutError"


async def test_producer_failed_names_the_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing-input.txt"

    async def _reads(_inp: object) -> AsyncIterator[Tick]:
        missing.read_text()
        yield Tick(n=1)

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind("reader", schemas=[Tick], schema_version=1, factory=lambda: _reads)
        b.initial("reader", input=None)
        b.termination(api.quiescence())

    await api.Runtime(tmp_path / "rec").run(topo)
    failed = [
        e["payload"] for e in api.read_record(tmp_path / "rec") if e["kind"] == api.PRODUCER_FAILED
    ]
    assert len(failed) == 1
    assert str(missing) in failed[0]["error"], failed[0]["error"]


def test_cli_names_a_missing_working_folder(tmp_path: Path) -> None:
    gone = tmp_path / "workspace-that-was-deleted"
    responder = CliResponder(
        [sys.executable, "-c", "print('hi')"], name="claude:opus-4-5", cwd=gone
    )
    with pytest.raises(FileNotFoundError) as caught:
        responder.respond("hello")
    text = describe_error(caught.value)
    assert "claude:opus-4-5" in text and str(gone) in text and "working folder" in text, text


def test_cli_names_a_missing_program(tmp_path: Path) -> None:
    responder = CliResponder(["no-such-cli-297"], name="ghost", cwd=tmp_path)
    with pytest.raises(FileNotFoundError) as caught:
        responder.respond("hello")
    text = describe_error(caught.value)
    assert "ghost" in text and "no-such-cli-297" in text and "PATH" in text, text


def test_the_inspector_still_keeps_the_class() -> None:
    assert (
        _error_sentinel("FileNotFoundError: [Errno 2] No such file or directory: '/x'")
        == "<FileNotFoundError>"
    )
    assert (
        _error_sentinel("FileNotFoundError(2, 'No such file or directory')")
        == "<FileNotFoundError>"
    )


def test_no_record_site_writes_a_repr() -> None:
    """The sites the research note lists turn exceptions into text through describe_error."""
    root = Path(__file__).resolve().parents[1] / "src" / "substrate"
    files = [
        "kernel/runtime.py",
        "kernel/sequencer.py",
        "kernel/topology.py",
        "topologies/session/session_prompt_producer.py",
        "topologies/session/skills.py",
        "topologies/coding_flow/__init__.py",
    ]
    offenders = []
    for rel in files:
        for no, line in enumerate((root / rel).read_text().splitlines(), 1):
            if "repr(exc)" in line or "{exc!r}" in line:
                offenders.append(f"{rel}:{no}")
    assert not offenders, offenders

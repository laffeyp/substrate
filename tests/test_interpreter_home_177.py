# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""UI sprint 177: the app's Python home stays with the app. In the packaged app the server starts
with PYTHONHOME pointing into the bundle; a user's `python3` run with it died with "Failed to import
encodings module". After `release_python_home`, a session's bash gets no
PYTHONHOME, and the coding gate, which runs the app's own interpreter, gets it back."""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.interpreter import OWN_PYTHONHOME, own_interpreter_env, release_python_home
from substrate.topologies.coding_flow.gate import _gate_env
from substrate.topologies.tool_loop.tools import full_suite

BUNDLE = "/Applications/Substrate.app/Contents/Resources/python"
SHOW = 'printf "%s" "${PYTHONHOME-unset}"'


@pytest.fixture
def released(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHONHOME", BUNDLE)
    monkeypatch.delenv(OWN_PYTHONHOME, raising=False)
    release_python_home()


def test_the_release_moves_the_home_aside(released: None) -> None:
    import os

    assert "PYTHONHOME" not in os.environ and os.environ[OWN_PYTHONHOME] == BUNDLE
    assert own_interpreter_env()["PYTHONHOME"] == BUNDLE
    assert own_interpreter_env({"PYTHONHOME": "/x", OWN_PYTHONHOME: BUNDLE})["PYTHONHOME"] == "/x"


def test_a_sessions_bash_gets_no_home(released: None, tmp_path: Path) -> None:
    out = full_suite(tmp_path)["bash"].run([SHOW])
    assert "unset" in str(out) and BUNDLE not in str(out)


def test_the_coding_gate_gets_the_home_back(released: None) -> None:
    assert _gate_env()["PYTHONHOME"] == BUNDLE


def test_nothing_changes_without_a_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import os

    monkeypatch.delenv("PYTHONHOME", raising=False)
    monkeypatch.delenv(OWN_PYTHONHOME, raising=False)
    release_python_home()
    assert OWN_PYTHONHOME not in os.environ and "PYTHONHOME" not in _gate_env()

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 513: the bash tool strips Substrate's launch variables from the shell it starts.

A session's shell must not inherit `SUBSTRATE_PYTHONHOME`, `SUBSTRATE_HOME`,
`SUBSTRATE_TRACE_DIR`, `SUBSTRATE_BOOT_ID`, or `SUBSTRATE_PARENT_PID`. In particular,
`SUBSTRATE_PYTHONHOME` leaks to `uv run python` as `PYTHONHOME` and makes it import
the encodings module from the wrong home."""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.topologies.tool_loop.tools import full_suite

LAUNCH_VARS = (
    "SUBSTRATE_PYTHONHOME",
    "SUBSTRATE_HOME",
    "SUBSTRATE_TRACE_DIR",
    "SUBSTRATE_BOOT_ID",
    "SUBSTRATE_PARENT_PID",
)

SHOW = 'printf "%s" "${%s-unset}"'


@pytest.fixture
def launch_vars_set(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in LAUNCH_VARS:
        monkeypatch.setenv(var, f"value-of-{var}")


def test_bash_strips_substrate_launch_vars(launch_vars_set: None, tmp_path: Path) -> None:
    out = full_suite(tmp_path)["bash"].run(["env | sort"])
    stdout = str(out.get("stdout", ""))
    for var in LAUNCH_VARS:
        assert f"{var}=" not in stdout, f"{var} leaked into the shell environment"


def test_bash_keeps_other_variables(launch_vars_set: None, tmp_path: Path) -> None:
    import os

    os.environ["KEEP_ME"] = "still-here"
    try:
        out = full_suite(tmp_path)["bash"].run(["env | sort"])
        stdout = str(out.get("stdout", ""))
        assert "KEEP_ME=still-here" in stdout
        for var in LAUNCH_VARS:
            assert f"{var}=" not in stdout, f"{var} leaked into the shell environment"
    finally:
        os.environ.pop("KEEP_ME", None)

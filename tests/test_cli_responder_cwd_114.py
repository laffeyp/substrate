# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""UI sprint 114: a CLI driver runs in the directory it is given, the session's workspace.

The command prints its working directory; the prompt rides as one more argv entry, which the
printing script ignores. Before the sprint, `CliResponder` set no `cwd`, so the CLI ran in the
server's directory (the app bundle or the kernel repo) whatever the session's workspace.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from substrate.adapters.models import CliResponder

_PWD = [sys.executable, "-c", "import os; print(os.getcwd())"]


def test_respond_runs_in_cwd(tmp_path: Path) -> None:
    assert Path(CliResponder(_PWD, cwd=tmp_path).respond("hi")) == tmp_path.resolve()


async def test_arespond_runs_in_cwd(tmp_path: Path) -> None:
    assert Path(await CliResponder(_PWD, cwd=tmp_path).arespond("hi")) == tmp_path.resolve()


async def test_without_cwd_it_runs_where_the_caller_runs() -> None:
    here = Path(os.getcwd()).resolve()
    assert Path(CliResponder(_PWD).respond("hi")) == here
    assert Path(await CliResponder(_PWD).arespond("hi")) == here

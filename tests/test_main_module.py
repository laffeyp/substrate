# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""`python -m substrate` runs the CLI (src/substrate/__main__.py), the route that works when the
install's script folder is not on PATH."""

from __future__ import annotations

import subprocess
import sys


def test_python_m_substrate_runs_the_cli() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "substrate", "demo", "replay", "code_review"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.rstrip().splitlines()[-1].split()[1] == "substrate.RunFinalised"

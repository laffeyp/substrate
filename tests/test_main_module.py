# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""`python -m substrate` runs the CLI (src/substrate/__main__.py), the route that works when the
install's script folder is not on PATH."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_python_m_substrate_runs_the_cli() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "substrate", "demo", "replay", "code_review"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.rstrip().splitlines()[-1].split()[1] == "substrate.RunFinalised"


def test_substrate_install_links_the_command_and_adds_it_to_path_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K343: `substrate install` links the script into ~/.local/bin and, when that folder is not on
    PATH, adds it to the shell's startup files, once; with the folder on PATH it touches no file."""
    from click.testing import CliRunner

    from substrate import cli

    script = tmp_path / "scripts" / "substrate"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\n")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(cli, "_installed_script", lambda: script)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    for _ in range(2):
        result = CliRunner().invoke(cli.main, ["install"])
        assert result.exit_code == 0, result.output
    link = home / ".local" / "bin" / "substrate"
    assert link.is_symlink() and link.resolve() == script.resolve()
    for profile in (".zshrc", ".zprofile"):
        assert (home / profile).read_text().count("substrate install") == 1
    assert "open a new terminal" in result.output

    other = tmp_path / "home2"
    other.mkdir()
    monkeypatch.setenv("HOME", str(other))
    monkeypatch.setenv("PATH", f"{other / '.local' / 'bin'}:/usr/bin")
    result = CliRunner().invoke(cli.main, ["install"])
    assert result.exit_code == 0 and "substrate is ready" in result.output
    assert not (other / ".zshrc").exists()

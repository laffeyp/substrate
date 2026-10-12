# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 208 — CLI drivers read context_tokens from ~/.substrate/config.toml.

Claude / Codex / Gemini CLIs advertise no live introspection endpoint; users
declare the window in `[driver.<name>].context_tokens`. The shipped config seeds
a value; when absent, the resolver returns `_CLI_CONTEXT_DEFAULT_TOKENS = 100_000`
(documented as user-settable in TECH-SPEC §3a).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.adapters import CliResponder
from substrate.topologies.session.context_windows import (
    DEFAULT_CLI_CONTEXT_TOKENS as _CLI_CONTEXT_DEFAULT_TOKENS,
)
from substrate.topologies.session.transcript import _context_cache, resolve_driver_context_tokens


@pytest.fixture(autouse=True)
def _clear_context_cache() -> None:
    _context_cache.clear()


def _write_config(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_claude_cli_reads_configured_context_tokens(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    _write_config(config, "[driver.claude]\ncontext_tokens = 200000\n")
    r = CliResponder(["claude", "-p"], name="claude")
    assert resolve_driver_context_tokens("claude", r, config_path=config) == 200_000


def test_gemini_cli_reads_configured_context_tokens(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    _write_config(config, "[driver.gemini]\ncontext_tokens = 1000000\n")
    r = CliResponder(["gemini", "-p"], name="gemini")
    assert resolve_driver_context_tokens("gemini", r, config_path=config) == 1_000_000


def test_missing_driver_entry_falls_back_to_default(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    _write_config(config, "[driver.codex]\ncontext_tokens = 128000\n")
    r = CliResponder(["claude", "-p"], name="claude")
    assert (
        resolve_driver_context_tokens("claude", r, config_path=config)
        == _CLI_CONTEXT_DEFAULT_TOKENS
    )


def test_missing_config_file_falls_back_to_default(tmp_path: Path) -> None:
    r = CliResponder(["claude", "-p"], name="claude")
    assert (
        resolve_driver_context_tokens("claude", r, config_path=tmp_path / "nope.toml")
        == _CLI_CONTEXT_DEFAULT_TOKENS
    )


def test_malformed_toml_falls_back_to_default(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    _write_config(config, "this is not valid toml [[[\n")
    r = CliResponder(["claude", "-p"], name="claude")
    assert (
        resolve_driver_context_tokens("claude", r, config_path=config)
        == _CLI_CONTEXT_DEFAULT_TOKENS
    )


def test_non_positive_context_tokens_falls_back_to_default(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    _write_config(config, "[driver.claude]\ncontext_tokens = 0\n")
    r = CliResponder(["claude", "-p"], name="claude")
    assert (
        resolve_driver_context_tokens("claude", r, config_path=config)
        == _CLI_CONTEXT_DEFAULT_TOKENS
    )

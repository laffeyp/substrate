# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 218 — CLI `chat` verb + bare dispatch + config.toml defaults.

Four behaviors covered:
  1. `substrate` bare dispatches to `chat` (invoke_without_command wiring).
  2. `substrate chat` reads `[defaults]` from a config file.
  3. `substrate chat deterministic` overrides the config default.
  4. `substrate daemon` errors cleanly when `[daemon] server_path` is missing.

The daemon is not launched here — the CLI's `_ensure_daemon_running` is
monkey-patched to a no-op, and `_daemon.create_session` to a stub. These
tests exercise CLI wiring; the daemon integration path lands in sprint 219
(REPL) and gets an end-to-end test in sprint 222.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from substrate import _daemon as daemon_client
from substrate import cli


@pytest.fixture(autouse=True)
def _stub_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the daemon liveness probe and the create-session HTTP call."""
    monkeypatch.setattr(cli, "_ensure_daemon_running", lambda: None)

    def _fake_create(driver: str, **kw: object) -> dict[str, object]:
        return {
            "session_id": "s_stubbed_test",
            "name": kw.get("name"),
            "record": "/tmp/stubbed-record",
            "workspace_shape": kw.get("workspace_shape") or "flat",
            "_driver": driver,  # for the test to inspect what got passed
        }

    monkeypatch.setattr(daemon_client, "create_session", _fake_create)


@pytest.fixture
def config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the CLI at a tmp config file."""
    p = tmp_path / "config.toml"
    monkeypatch.setattr(cli, "_config_path_default", lambda: p)
    return p


def test_bare_substrate_dispatches_to_chat(config_path: Path) -> None:
    """Running the group with no subcommand invokes `chat`. `_defaults`'s
    baked-in fallback (missing config file) yields driver='deterministic'.
    """
    runner = CliRunner()
    result = runner.invoke(cli.main, [])
    assert result.exit_code == 0, result.output
    assert "s_stubbed_test" in result.output


def test_chat_reads_config_defaults(config_path: Path) -> None:
    config_path.write_text(
        '[defaults]\ndriver = "kimi-k2.6:cloud"\nworkspace = "/tmp/wsp-cfg"\n',
        encoding="utf-8",
    )
    seen: dict[str, object] = {}

    def _capture(driver: str, **kw: object) -> dict[str, object]:
        seen["driver"] = driver
        seen["workspace"] = kw.get("workspace")
        return {
            "session_id": "s_cfg",
            "name": None,
            "record": "/tmp/x",
            "workspace_shape": "flat",
        }

    from substrate import _daemon as _d

    _d.create_session = _capture  # type: ignore[assignment]
    runner = CliRunner()
    result = runner.invoke(cli.main, ["chat"])
    assert result.exit_code == 0, result.output
    assert seen["driver"] == "kimi-k2.6:cloud"
    assert seen["workspace"] == "/tmp/wsp-cfg"


def test_chat_arg_overrides_config(config_path: Path) -> None:
    config_path.write_text('[defaults]\ndriver = "kimi-k2.6:cloud"\n', encoding="utf-8")
    seen: dict[str, object] = {}

    def _capture(driver: str, **kw: object) -> dict[str, object]:
        seen["driver"] = driver
        return {
            "session_id": "s_arg",
            "name": None,
            "record": "/tmp/x",
            "workspace_shape": "flat",
        }

    from substrate import _daemon as _d

    _d.create_session = _capture  # type: ignore[assignment]
    runner = CliRunner()
    result = runner.invoke(cli.main, ["chat", "deterministic"])
    assert result.exit_code == 0, result.output
    assert seen["driver"] == "deterministic"


def test_daemon_verb_without_server_path_exits_64(config_path: Path) -> None:
    """`substrate daemon` with an empty or missing config prints the config
    error to stderr and exits 64 (EXIT_CONFIG)."""
    runner = CliRunner()
    # config missing entirely — the file doesn't exist
    result = runner.invoke(cli.main, ["daemon"], catch_exceptions=False)
    assert result.exit_code == cli.EXIT_CONFIG
    # stderr goes to result.stderr when mix_stderr=False, or to output otherwise
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "server_path" in combined


def test_daemon_verb_with_missing_file_exits_64(config_path: Path, tmp_path: Path) -> None:
    """`[daemon] server_path` points at a nonexistent file: exit 64 with a
    clear error naming the path."""
    config_path.write_text(
        f'[daemon]\nserver_path = "{tmp_path / "does-not-exist.py"}"\n',
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(cli.main, ["daemon"], catch_exceptions=False)
    assert result.exit_code == cli.EXIT_CONFIG
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "does not exist" in combined

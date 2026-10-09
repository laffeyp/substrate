# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 222 — CLI session subverbs (ls, end, rm, set-name).

Every session-mutating subverb runs against a real substrate-ui daemon
in-process — same shape as sprint 221's rewrite (sprint 224b). No
monkeypatching of `_daemon`; the daemon receives the HTTP request and
its registry state carries the assertion.
"""

from __future__ import annotations


import pytest
from click.testing import CliRunner

from tests._ui_daemon import ui_daemon


@pytest.fixture(scope="module")
def daemon_app(tmp_path_factory: pytest.TempPathFactory) -> object:
    """The daemon's App, served for the whole module by `daemon_base`."""
    app, srv = ui_daemon(tmp_path_factory.mktemp("cli-session-222"))
    yield app, srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture(scope="module")
def daemon_base(daemon_app: tuple[object, object]) -> str:
    app, srv = daemon_app
    tcp_port = srv.server_address[1]
    from substrate import _daemon

    _daemon.os.environ["SUBSTRATE_DAEMON_HOST"] = "127.0.0.1"
    _daemon.os.environ["SUBSTRATE_DAEMON_PORT"] = str(tcp_port)
    _daemon.os.environ["SUBSTRATE_DAEMON_SOCK"] = "/nonexistent/socket"
    yield f"http://127.0.0.1:{tcp_port}"


def _create(name: str | None = None) -> str:
    from substrate import _daemon

    session = _daemon.create_session(driver="deterministic", name=name)
    return session["session_id"]


def test_session_ls_shows_a_created_session(daemon_base: str) -> None:
    from substrate import cli

    sid = _create("ls-target")
    result = CliRunner().invoke(cli.main, ["session", "ls"])
    assert result.exit_code == 0, result.output
    assert sid in result.output
    assert "ls-target" in result.output


def test_session_end_by_name(daemon_base: str, daemon_app: tuple[object, object]) -> None:

    from substrate import cli
    from substrate.topologies.session_registry import SessionStatus

    sid = _create("end-me")
    result = CliRunner().invoke(cli.main, ["session", "end", "end-me"])
    assert result.exit_code == 0, result.output
    assert daemon_app[0].registry.get(sid).status == SessionStatus.ENDED


def test_session_end_unknown_name_exits_config(daemon_base: str) -> None:
    from substrate import cli

    result = CliRunner().invoke(cli.main, ["session", "end", "no-such-name"])
    assert result.exit_code == cli.EXIT_CONFIG
    assert "no session named" in result.output


def test_session_rm_recent_without_force_refuses(daemon_base: str) -> None:
    """A session created seconds ago falls inside the 24-hour window; `rm`
    without --force refuses with EXIT_CONFIG and a message naming the age.
    """
    from substrate import cli

    _create("rm-recent")
    result = CliRunner().invoke(cli.main, ["session", "rm", "rm-recent"])
    assert result.exit_code == cli.EXIT_CONFIG
    assert "--force" in result.output


def test_session_rm_with_force_deletes(daemon_base: str, daemon_app: tuple[object, object]) -> None:

    from substrate import cli

    sid = _create("rm-forced")
    assert daemon_app[0].registry.get(sid) is not None
    result = CliRunner().invoke(cli.main, ["session", "rm", "rm-forced", "--force"])
    assert result.exit_code == 0, result.output
    # Rule 12: the record dir stays; only the manifest is dropped.
    assert daemon_app[0].registry.get(sid) is None


def test_session_set_name_renames(daemon_base: str, daemon_app: tuple[object, object]) -> None:

    from substrate import cli

    sid = _create("old-name")
    result = CliRunner().invoke(cli.main, ["session", "set-name", sid, "new-name"])
    assert result.exit_code == 0, result.output
    assert daemon_app[0].registry.get(sid).name == "new-name"

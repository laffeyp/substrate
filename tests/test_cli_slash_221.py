# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 221 — CLI REPL slash-command router (nine slashes).

Sprint 224b rewrite: state-mutating slashes (`/model`, `/tools`, `/list`)
run against a REAL substrate-ui daemon in-process instead of monkeypatching
the `_daemon` client. That closes the dual contract — the tests verify
both that the CLI sends the right HTTP request AND that the daemon
updated its state. Non-daemon slashes (`/help`, `/exit`, `/context`,
`/run` deferral, `/list applications` deferral, unknown-slash,
`/inspect`, `/replay`) remain unit-only — nothing round-trips there.
"""

from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from typing import Any

import pytest

from tests._ui_daemon import ui_server_module


# ── real-daemon fixture (imported once per module) ───────────────────────


@pytest.fixture(scope="module")
def daemon_base(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Boot substrate-ui's daemon in-process on a random TCP port.

    The daemon shares this test's Python process; the CLI's `_daemon`
    client talks to it over TCP just like a real deployment. Every test
    that mutates state creates its own session and asserts on the
    daemon-side registry after — a real dual contract, no mocks.
    """
    base_dir = tmp_path_factory.mktemp("daemon-base")
    server = ui_server_module()
    from substrate.session_registry import SessionRegistry

    server._SESSION_REGISTRY = SessionRegistry(
        base=base_dir,
        session_topology_factory=server._build_session_topology_from_manifest,
    )
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tcp_port = srv.server_address[1]
    # Point the CLI's daemon client at this port; disable UDS.
    from substrate import _daemon

    _daemon.os.environ["SUBSTRATE_DAEMON_HOST"] = "127.0.0.1"
    _daemon.os.environ["SUBSTRATE_DAEMON_PORT"] = str(tcp_port)
    _daemon.os.environ["SUBSTRATE_DAEMON_SOCK"] = "/nonexistent/socket"
    yield f"http://127.0.0.1:{tcp_port}"
    srv.shutdown()


@pytest.fixture
def session(daemon_base: str) -> dict[str, Any]:
    """A fresh session per test. Each test owns a distinct session_id so
    parallel or ordering failures cannot cross-contaminate assertions."""
    from substrate import _daemon

    created = _daemon.create_session(driver="deterministic")
    return created


@pytest.fixture(autouse=True)
def _capture_err(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Capture the router's stderr `_err.print` output. Not a mock of a
    boundary — this captures a UI channel so we can inspect the human
    output on unit-only slashes (/help, /run deferral, etc.)."""
    from substrate import cli

    lines: list[str] = []
    monkeypatch.setattr(cli._err, "print", lambda msg, **_kw: lines.append(str(msg)))
    return lines


def _route(
    line: str, session: dict[str, Any], pending: dict[str, Any] | None = None
) -> tuple[bool, dict[str, Any]]:
    from substrate import cli

    p = pending if pending is not None else {}
    handled = cli._slash_route(line, session, p)
    return handled, p


# ── unit-only slashes (no daemon round-trip) ──────────────────────────────


def test_help_prints_slash_list_and_returns_true(
    session: dict[str, Any], _capture_err: list[str]
) -> None:
    """Every SlashCommand member appears in the /help body. Iterating the
    enum instead of a hardcoded tuple means a new slash added to
    SlashCommand without updating _SLASH_HELP trips this test — no drift
    between the router's dispatch set and the help text."""
    from substrate.cli import SlashCommand

    handled, _ = _route("/help", session)
    assert handled is True
    body = "\n".join(_capture_err)
    for cmd in SlashCommand:
        assert cmd.value in body, f"/help output missing {cmd.value}"


def test_exit_returns_false_so_repl_sends_as_user_message(session: dict[str, Any]) -> None:
    handled, _ = _route("/exit", session)
    assert handled is False


def test_slash_command_exit_matches_session_end_on_exit_sentinel() -> None:
    """Drift-grooming 2026-09-02: SlashCommand.EXIT (the CLI enum) and
    END_ON_EXIT_SENTINEL (the session topology's end-on-exit trigger
    predicate) name the same wire value. F-API-6 keeps substrate.cli
    off substrate.topologies, so the literal lives in both files; this
    test pins them equal at CI. A rename on one side without the other
    trips this test, before users notice /exit stops ending sessions."""
    from substrate.cli import SlashCommand
    from substrate.topologies.session.vocabulary import END_ON_EXIT_SENTINEL

    assert SlashCommand.EXIT.value == END_ON_EXIT_SENTINEL, (
        f"SlashCommand.EXIT ({SlashCommand.EXIT.value!r}) diverged from "
        f"END_ON_EXIT_SENTINEL ({END_ON_EXIT_SENTINEL!r}). Rename one side; "
        "a rename on both, matching, silences this test."
    )


def test_non_slash_returns_false(session: dict[str, Any]) -> None:
    handled, _ = _route("hello there", session)
    assert handled is False


def test_context_stores_pending_range_and_kinds(session: dict[str, Any]) -> None:
    handled, pending = _route("/context 3-9 --kind ToolResult", session)
    assert handled is True
    assert pending == {"parent_seq_range": [3, 9], "kinds": ["ToolResult"]}


def test_unknown_slash_returns_true_with_hint(
    session: dict[str, Any], _capture_err: list[str]
) -> None:
    handled, _ = _route("/nonsense", session)
    assert handled is True
    body = "\n".join(_capture_err)
    assert "unknown slash" in body
    assert "/help" in body


def test_model_missing_arg_prints_error(session: dict[str, Any], _capture_err: list[str]) -> None:
    handled, _ = _route("/model", session)
    assert handled is True
    body = "\n".join(_capture_err)
    assert "exactly one" in body


def test_run_prints_hint_and_does_not_pollute_pending_context(
    session: dict[str, Any], _capture_err: list[str]
) -> None:
    """Drift-grooming 2026-09-02 regression: the earlier "typed marker"
    pattern set pending_context["_deferred"] = "run"; no consumer read
    it, but the marker rode into the next real turn's context body,
    which the daemon refused with HTTP 400 for the missing
    parent_seq_range. `/run` now returns True (handled), pending stays
    empty, and the stderr hint names the endpoint that will ship it.
    """
    handled, pending = _route("/run coding_flow", session)
    assert handled is True
    assert pending == {}, (
        f"/run leaked into pending_context: {pending!r}; a next turn would 400 on it"
    )
    body = "\n".join(_capture_err)
    assert "/run" in body and "not yet shipped" in body


def test_list_applications_prints_hint_and_does_not_pollute_pending_context(
    session: dict[str, Any], _capture_err: list[str]
) -> None:
    """Same class as test_run_prints_hint_and_does_not_pollute_pending_context."""
    handled, pending = _route("/list applications", session)
    assert handled is True
    assert pending == {}, (
        f"/list applications leaked into pending_context: {pending!r}; a next turn would 400 on it"
    )
    body = "\n".join(_capture_err)
    assert "/list applications" in body and "not yet shipped" in body


# ── daemon round-trip slashes (dual contract) ─────────────────────────────


def test_model_slash_updates_manifest_driver_on_the_daemon(
    session: dict[str, Any], daemon_base: str
) -> None:
    """/model X → PATCH /api/session/<id> {driver: X} → registry sees X."""
    import server

    sid = session["session_id"]
    handled, _ = _route("/model deterministic", session)
    assert handled is True
    manifest = server._SESSION_REGISTRY.get(sid)
    assert manifest.driver == "deterministic"


def test_tools_slash_updates_manifest_tools_on_the_daemon(
    session: dict[str, Any], daemon_base: str
) -> None:
    """/tools a,b,c → PATCH /api/session/<id> {tools: [a,b,c]} → registry sees them."""
    import server

    sid = session["session_id"]
    handled, _ = _route("/tools read_file,grep", session)
    assert handled is True
    manifest = server._SESSION_REGISTRY.get(sid)
    assert manifest.tools == ("read_file", "grep")


def test_list_sessions_slash_hits_real_daemon_and_shows_this_session(
    session: dict[str, Any], daemon_base: str, _capture_err: list[str]
) -> None:
    """/list sessions → GET /api/session → stderr shows the sid returned."""
    handled, _ = _route("/list sessions", session)
    assert handled is True
    body = "\n".join(_capture_err)
    assert session["session_id"] in body, (
        f"real daemon returned no session_id in /list sessions output: {body!r}"
    )


def test_list_rejects_unknown_target_by_name(
    session: dict[str, Any], _capture_err: list[str]
) -> None:
    """Sprint 073 boundary contract: `/list <target>` validates argv via
    `ListTarget(raw)` at the top of the handler. An unknown target
    returns True (handled), never routes to the four dispatch branches,
    and the stderr error names both the offending value and the four
    valid targets. Regression against silent-typo drift (antipattern
    #4) and boundary-crossing untyped (antipattern #8)."""
    handled, pending = _route("/list bogus", session)
    assert handled is True
    assert pending == {}, "the invalid-target path must not set a deferred marker"
    body = "\n".join(_capture_err)
    assert "bogus" in body, f"error must name the offending value: {body!r}"
    for valid in ("sessions", "topologies", "records", "applications"):
        assert valid in body, f"error must list valid target {valid!r}: {body!r}"

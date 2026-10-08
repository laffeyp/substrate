# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 219 — CLI REPL + SSE streaming during a blocked turn.

Two tests:
  1. `_render_stream_line` — the three line shapes (ModelReply text streams to
     stdout; ToolCall/ToolResult to stderr; substrate.* suppressed unless verbose).
  2. `_sse_stream` background thread reads a real running daemon's /events
     endpoint. Fires one turn from the main thread; asserts the reader saw
     the turn's ModelReply text within the timeout.
"""

from __future__ import annotations

import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from tests._ui_daemon import ui_server_module


# ── unit test for the formatter ───────────────────────────────────────────────


def _capture_stdout_stderr(fn):
    """Run `fn` while capturing stdout + stderr via monkeypatched click.echo /
    _err.print. Returns (stdout_lines, stderr_lines)."""
    import click

    from substrate import cli

    stdout: list[str] = []
    stderr: list[str] = []
    orig_echo = click.echo
    orig_err = cli._err.print

    def _cap_echo(msg, err=False, **kw):
        (stderr if err else stdout).append(str(msg))

    def _cap_err(msg, **kw):
        stderr.append(str(msg))

    click.echo = _cap_echo  # type: ignore[assignment]
    cli._err.print = _cap_err  # type: ignore[method-assign]
    try:
        fn()
    finally:
        click.echo = orig_echo  # type: ignore[assignment]
        cli._err.print = orig_err  # type: ignore[method-assign]
    return stdout, stderr


def test_render_stream_line_shapes() -> None:
    from substrate import cli

    def _run() -> None:
        cli._render_stream_line({"kind": "ModelReply", "payload": {"text": "hello"}})
        cli._render_stream_line(
            {"kind": "ToolCall", "payload": {"tool": "read_file", "args": ["app.py"]}}
        )
        cli._render_stream_line({"kind": "ToolResult", "payload": {"ok": True, "output": "abcdef"}})
        cli._render_stream_line({"kind": "ToolResult", "payload": {"ok": False, "error": "boom"}})
        cli._render_stream_line({"kind": "FinalAnswer", "payload": {"text": "42"}})
        cli._render_stream_line(
            {"kind": "substrate.ProducerStarted", "payload": {"producer": {"kind": "model"}}}
        )

    stdout, stderr = _capture_stdout_stderr(_run)
    # ModelReply → stdout
    assert stdout == ["hello"]
    # ToolCall → stderr
    assert any("→ read_file" in line for line in stderr)
    assert any("'app.py'" in line for line in stderr)
    # ToolResult success + failure → stderr
    assert any("← ok (" in line and "bytes)" in line for line in stderr)
    assert any("← FAIL: boom" in line for line in stderr)
    # FinalAnswer skipped; substrate.* suppressed without verbose
    joined = " ".join(stdout + stderr)
    assert "FinalAnswer" not in joined
    assert "substrate.ProducerStarted" not in joined


def test_render_stream_line_verbose_shows_substrate_events() -> None:
    from substrate import cli

    def _run() -> None:
        cli._render_stream_line({"kind": "substrate.ProducerStarted", "payload": {}}, verbose=True)

    _stdout, stderr = _capture_stdout_stderr(_run)
    assert any("substrate.ProducerStarted" in line for line in stderr)


# ── integration: SSE reader sees a real turn's ModelReply ─────────────────────


@pytest.mark.timeout(30)
def test_sse_stream_reads_turn_events_from_running_daemon(tmp_path: Path) -> None:
    """Spin the real daemon in-process. Create a session. Fire a turn from
    the main thread. The SSE reader thread should see the turn's ModelReply
    and format it before the loop ends."""

    server = ui_server_module()
    from substrate.session_registry import SessionRegistry

    from substrate import _daemon, cli

    # Boot registry + TCP daemon.
    server._SESSION_REGISTRY = SessionRegistry(
        base=tmp_path,
        session_topology_factory=server._build_session_topology_from_manifest,
    )
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tcp_port = srv.server_address[1]

    # Point the CLI's daemon client at this TCP port; disable UDS lookup.
    orig_env = dict(_daemon.os.environ)
    _daemon.os.environ["SUBSTRATE_DAEMON_HOST"] = "127.0.0.1"
    _daemon.os.environ["SUBSTRATE_DAEMON_PORT"] = str(tcp_port)
    _daemon.os.environ["SUBSTRATE_DAEMON_SOCK"] = "/nonexistent/socket"

    try:
        # Create the session.
        session = _daemon.create_session(driver="deterministic", workspace=str(tmp_path))
        sid = session["session_id"]

        # Start the SSE reader; capture the frames it renders.
        captured: list[str] = []
        import click as _click

        orig_echo = _click.echo

        def _cap(msg, err=False, **kw):
            captured.append(str(msg))

        _click.echo = _cap  # type: ignore[assignment]

        stop_event = threading.Event()
        stream_thread = threading.Thread(
            target=cli._sse_stream, args=(sid, stop_event), daemon=True
        )
        stream_thread.start()

        # Small settle so the reader hits the poll loop before the turn fires.
        time.sleep(0.3)

        # Fire one turn — deterministic driver returns quickly.
        result = _daemon.turn(sid, "hello", timeout=30.0)
        assert result.get("status") in ("parked", "ended")

        # Wait briefly for the SSE reader to drain the new envelopes.
        for _ in range(50):
            if any(len(m) > 0 for m in captured):
                break
            time.sleep(0.1)

        stop_event.set()
        stream_thread.join(timeout=3)
        _click.echo = orig_echo  # type: ignore[assignment]

        # The deterministic driver emits a ModelReply text on turn 1. The
        # captured stdout list should include at least one non-empty line
        # from the assistant.
        assert captured, "SSE reader captured no ModelReply text"
    finally:
        _daemon.os.environ.clear()
        _daemon.os.environ.update(orig_env)
        srv.shutdown()
        srv.server_close()

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""HTTP client for the substrate daemon. Piece D sprint 218.

Every CLI verb POSTs to `~/.substrate/daemon.sock` (UDS) with fallback to
TCP `127.0.0.1:8765`. Tries UDS first, falls back cleanly
on any of: missing socket file, ECONNREFUSED, permission denied. TCP host
+ port are overridable via `SUBSTRATE_DAEMON_HOST` and `SUBSTRATE_DAEMON_PORT`.

`DaemonNotRunning` fires when both transports fail. The `chat` and `builder`
verbs auto-launch the daemon per the daemon table; other verbs surface
the error and exit 64 with a message pointing at `substrate daemon`.

F-API-6 posture: this module is CLI-internal (leading underscore in the file
name; not re-exported from `substrate.api`). It talks HTTP to the daemon;
it does not touch the kernel. The daemon is a substrate-ui-side process,
outside substrate's public surface — the CLI reaches it over the wire, not
by import.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
from pathlib import Path
from typing import Any


class DaemonNotRunning(Exception):
    """Neither UDS nor TCP could connect to a running daemon."""


class DaemonError(Exception):
    """The daemon answered but with a non-2xx status. Carries status + body."""

    def __init__(self, status: int, body: dict[str, Any]) -> None:
        super().__init__(f"daemon returned {status}: {body}")
        self.status = status
        self.body = body


class _UnixHTTPConnection(http.client.HTTPConnection):
    """http.client over a Unix socket."""

    def __init__(self, socket_path: str, timeout: float | None = None) -> None:
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if self.timeout is not None:
            s.settimeout(self.timeout)
        s.connect(self._socket_path)
        self.sock = s


def _uds_path() -> Path:
    from substrate.api import substrate_home

    return Path(os.environ.get("SUBSTRATE_DAEMON_SOCK", str(substrate_home() / "daemon.sock")))


def _tcp_host_port() -> tuple[str, int]:
    return (
        os.environ.get("SUBSTRATE_DAEMON_HOST", "127.0.0.1"),
        int(os.environ.get("SUBSTRATE_DAEMON_PORT", "8765")),
    )


def _connect(timeout: float | None = 5.0) -> http.client.HTTPConnection:
    """Return a connected HTTPConnection. UDS first, TCP second. Never returns
    an unconnected connection — every path calls `.connect()` and raises
    `DaemonNotRunning` if neither transport is up. `timeout=None` disables
    the socket timeout — the SSE streamer at `cli.py::_sse_stream` uses
    this shape so a long-idle stream is not torn by the connect timeout."""
    uds = _uds_path()
    conn: http.client.HTTPConnection
    if uds.exists():
        try:
            conn = _UnixHTTPConnection(str(uds), timeout=timeout)
            conn.connect()
            return conn
        except (OSError, ConnectionRefusedError):
            pass
    host, port = _tcp_host_port()
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.connect()
        return conn
    except (OSError, ConnectionRefusedError):
        pass
    raise DaemonNotRunning(f"neither UDS ({uds}) nor TCP ({host}:{port}) accepted a connection")


def is_running(timeout: float = 1.0) -> bool:
    try:
        conn = _connect(timeout=timeout)
        conn.close()
        return True
    except DaemonNotRunning:
        return False


def _request(
    method: str, path: str, body: dict[str, Any] | None = None, timeout: float = 30.0
) -> tuple[int, dict[str, Any]]:
    conn = _connect(timeout=timeout)
    try:
        data = json.dumps(body).encode() if body is not None else b""
        headers = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw.decode(errors="replace")}
        return resp.status, payload
    finally:
        conn.close()


# ── endpoint wrappers (one thin function per endpoint) ───────────────────────


def create_session(
    driver: str,
    *,
    name: str | None = None,
    workspace: str | None = None,
    workspace_shape: str | None = None,
    seed_text: str | None = None,
    bundle: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"driver": driver}
    if name is not None:
        body["name"] = name
    if workspace is not None:
        body["workspace"] = workspace
    if workspace_shape is not None:
        body["workspace_shape"] = workspace_shape
    if seed_text is not None:
        body["seed_text"] = seed_text
    if bundle is not None:
        body["bundle"] = bundle
    status, payload = _request("POST", "/api/session", body)
    if status != 200:
        raise DaemonError(status, payload)
    return payload


def turn(
    session_id: str,
    text: str,
    *,
    context: dict[str, Any] | None = None,
    timeout: float = 600.0,
) -> dict[str, Any]:
    body: dict[str, Any] = {"text": text}
    if context is not None:
        body["context"] = context
    status, payload = _request("POST", f"/api/session/{session_id}/turn", body, timeout=timeout)
    # The daemon returns 200 on parked; 410 on ended session; 429 on queue full.
    # Callers inspect status to distinguish; do not raise on non-200 by default.
    payload["_status"] = status
    return payload


def interrupt(session_id: str, *, max_wait_ms: int = 3000) -> dict[str, Any]:
    status, payload = _request(
        "POST", f"/api/session/{session_id}/interrupt?max_wait_ms={max_wait_ms}", None
    )
    if status != 200:
        raise DaemonError(status, payload)
    return payload


def end_session(session_id: str, *, source: str = "user_end") -> dict[str, Any]:
    status, payload = _request("POST", f"/api/session/{session_id}/end", {"source": source})
    if status not in (200, 410):
        raise DaemonError(status, payload)
    return payload


def patch_session(session_id: str, **fields: Any) -> dict[str, Any]:
    status, payload = _request("PATCH", f"/api/session/{session_id}", dict(fields))
    if status not in (200, 409):
        raise DaemonError(status, payload)
    payload["_status"] = status
    return payload


def delete_session(session_id: str) -> None:
    status, payload = _request("DELETE", f"/api/session/{session_id}", None)
    if status not in (204, 404):
        raise DaemonError(status, payload)


def list_sessions() -> dict[str, Any]:
    status, payload = _request("GET", "/api/session", None)
    if status != 200:
        raise DaemonError(status, payload)
    return payload


def by_name(name: str) -> dict[str, Any] | None:
    from urllib.parse import quote

    status, payload = _request("GET", f"/api/session/by-name/{quote(name)}", None)
    if status == 404:
        return None
    if status != 200:
        raise DaemonError(status, payload)
    return payload


def run_topology(
    application_name: str,
    inputs: dict[str, Any],
    *,
    bundle: str | None = None,
    baseline: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    await_completion: bool = True,
    timeout_seconds: float = 600.0,
) -> dict[str, Any]:
    """Sprint 226: POST /api/topology/<name>/run.

    Fires a one-shot application dispatch (sprint 225a). Session-shape
    manifests refuse this endpoint — use `create_session` for `daily`,
    or a specialised composite dispatch for `session_composite` apps.

    `await_completion=True` blocks; response carries
    `{run_id, record_root, status: "finalised", final_seq, application}`.
    `await_completion=False` returns immediately with
    `{run_id, record_root, status: "running", application}` and the
    caller polls via `topology_status(run_id)`.
    """
    body: dict[str, Any] = {"inputs": inputs, "await_completion": await_completion}
    if bundle is not None:
        body["bundle"] = bundle
    if baseline is not None:
        body["baseline"] = baseline
    if context is not None:
        body["context"] = context
    status, payload = _request(
        "POST", f"/api/topology/{application_name}/run", body, timeout=timeout_seconds
    )
    if status != 200:
        raise DaemonError(status, payload)
    return payload


def topology_status(application_name: str, run_id: str) -> dict[str, Any]:
    """Sprint 226: GET /api/topology/<name>/status?run_id=<id> (piece E
    sprint 225d). Returns `{run_id, status, record_root,
    elapsed_seconds, application, output?}`. Raises `DaemonError` on
    unknown run_id (404) or malformed request (400)."""
    from urllib.parse import quote

    path = f"/api/topology/{quote(application_name)}/status?run_id={quote(run_id)}"
    status, payload = _request("GET", path, None)
    if status != 200:
        raise DaemonError(status, payload)
    return payload


__all__ = [
    "DaemonError",
    "DaemonNotRunning",
    "by_name",
    "create_session",
    "delete_session",
    "end_session",
    "interrupt",
    "is_running",
    "list_sessions",
    "patch_session",
    "run_topology",
    "topology_status",
    "turn",
]

# spec-audit: 2026-09-01

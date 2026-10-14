# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""substrate.discovery: the client catalog, detection, versions, sign-in status and login.

Clients are fake executables on a test PATH; Ollama is a stub HTTP server on a free port.
"""

from __future__ import annotations

import json
import stat
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from substrate import discovery as d


def _client(folder: Path, name: str, body: str) -> Path:
    exe = folder / name
    exe.write_text(f"#!/bin/sh\n{body}\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return exe


def _ollama(tags: list[str], hang: bool = False) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if hang:
                time.sleep(5)
            body = (
                json.dumps({"version": "0.12.0"})
                if self.path == "/api/version"
                else json.dumps({"models": [{"name": t} for t in tags]})
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture()
def no_cache() -> Iterator[None]:
    d._version_cache.clear()
    yield
    d._version_cache.clear()


def test_the_catalog_parses() -> None:
    for name, entry in d.CATALOG.items():
        assert isinstance(entry["command"], list) and entry["command"][0] == name
        assert entry["family"] in ("anthropic", "openai", "cursor")
        for key in ("login_command", "status_command", "logout_command"):
            assert isinstance(entry[key], list) and entry[key][0] == name
        tree = {"versions": entry["versions"], "default_family": entry["default_family"]}
        assert d.resolve_pin(tree, None) is not None, name
        for family in entry["versions"]:
            assert d.resolve_pin(tree, family["id"])["id"] == family["default_pin"]


def test_detect_finds_clients_ollama_and_keys(tmp_path: Path, no_cache: None) -> None:
    _client(tmp_path, "claude", "exit 0")
    _client(tmp_path, "codex", "exit 0")
    srv = _ollama(["qwen2.5:7b-instruct", "llama3:8b", "glm-5.2:cloud", "qwen3-coder:480b-cloud"])
    try:
        found = d.detect(
            path=str(tmp_path),
            base_url=f"http://127.0.0.1:{srv.server_address[1]}",
            env={"ANTHROPIC_API_KEY": "k"},
            install_dirs=(),
        )
    finally:
        srv.shutdown()
    by = {m.name: m for m in found}
    assert [m.name for m in found if m.kind == "cli"] == ["claude", "codex"]
    assert by["claude"].family == "anthropic" and by["claude"].where == str(tmp_path / "claude")
    assert by["claude"].versions["source"] == "curated"
    assert (
        by["qwen2.5:7b-instruct"].kind == "ollama-local"
        and by["qwen2.5:7b-instruct"].family == "alibaba"
    )
    assert by["llama3:8b"].family == "meta"
    assert by["glm-5.2:cloud"].kind == by["qwen3-coder:480b-cloud"].kind == "ollama-cloud"
    assert (
        by["ANTHROPIC_API_KEY"].kind == "api-key" and by["ANTHROPIC_API_KEY"].family == "anthropic"
    )
    assert json.loads(json.dumps(by["claude"].to_json()))["kind"] == "cli"


def test_nothing_installed_gives_an_empty_list(tmp_path: Path) -> None:
    assert (
        d.detect(path=str(tmp_path), base_url="http://127.0.0.1:9", env={}, install_dirs=()) == []
    )


def test_a_hung_ollama_is_cut_off_at_one_second(tmp_path: Path) -> None:
    srv = _ollama(["qwen2.5:7b-instruct"], hang=True)
    try:
        t0 = time.monotonic()
        found = d.detect(
            path=str(tmp_path),
            base_url=f"http://127.0.0.1:{srv.server_address[1]}",
            env={},
            install_dirs=(),
        )
        took = time.monotonic() - t0
    finally:
        srv.shutdown()
    assert found == [] and took < 2.0


def test_the_clients_env_list_limits_detection(tmp_path: Path, no_cache: None) -> None:
    _client(tmp_path, "claude", "exit 0")
    _client(tmp_path, "codex", "exit 0")
    found = d.detect(
        path=str(tmp_path),
        base_url="http://127.0.0.1:9",
        env={"SUBSTRATE_CLI_ADAPTERS": "codex"},
        install_dirs=(),
    )
    assert [m.name for m in found] == ["codex"]


def test_login_path_adds_install_folders_a_finder_launch_lacks(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    out = d.login_path("/usr/bin:/bin", dirs=(str(bin_dir), str(tmp_path / "missing")))
    assert out == f"/usr/bin:/bin:{bin_dir}"
    assert d.login_path(f"/usr/bin:{bin_dir}", dirs=(str(bin_dir),)) == f"/usr/bin:{bin_dir}"


def test_a_live_listing_replaces_the_curated_versions(
    tmp_path: Path, no_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _client(
        tmp_path,
        "cursor-agent",
        'echo "Available models"; echo "gpt-5.5 (default)"; echo "sonnet-4 - Sonnet 4"',
    )
    monkeypatch.setenv("PATH", str(tmp_path))
    tree = d.cli_versions("cursor-agent", path=str(tmp_path))
    assert tree["source"] == "live" and tree["default_pin_id"] == "gpt-5.5"
    assert [f["id"] for f in tree["families"]] == ["gpt", "sonnet"]
    assert d.parse_cursor_list("Available models:\n") is None


def test_cli_command_appends_isolation_and_the_pin(no_cache: None) -> None:
    base = [
        "claude",
        "-p",
        "--strict-mcp-config",
        "--setting-sources",
        "",
        "--dangerously-skip-permissions",
    ]
    assert d.cli_command("claude") == [*base, "--model", "claude-opus-5-5"]
    assert d.cli_command("claude", "haiku") == [*base, "--model", "claude-haiku-5-5"]
    assert d.cli_command("claude", "sonnet-4-6") == [*base, "--model", "claude-sonnet-4-6"]
    assert d.cli_command("no-such-client") is None


def test_cli_status_reads_each_clients_own_answer(tmp_path: Path) -> None:
    _client(tmp_path, "claude", 'echo \'{"loggedIn": true, "authMethod": "claude.ai"}\'')
    _client(tmp_path, "codex", 'echo "Not logged in"')
    assert d.cli_status("claude", path=str(tmp_path))["authed"] is True
    assert d.cli_status("codex", path=str(tmp_path))["authed"] is False
    assert d.cli_status("no-such-client")["detail"] == "unknown cli"


def test_a_login_runs_in_a_pty_and_takes_keystrokes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _client(
        tmp_path, "claude", 'printf "Paste code here: "; read code; echo "signed in with $code"'
    )
    monkeypatch.setenv("PATH", str(tmp_path) + ":/usr/bin:/bin")
    sessions = d.LoginSessions(linger_s=5)
    sid = sessions.start("claude", path=str(tmp_path) + ":/usr/bin:/bin")
    out = b""
    for _ in range(50):
        r = sessions.read(sid)
        assert r is not None
        out = r["data"]
        if b"Paste code here" in out:
            break
        time.sleep(0.1)
    assert b"Paste code here" in out
    assert sessions.write(sid, b"abc123\n")
    for _ in range(50):
        r = sessions.read(sid)
        assert r is not None
        if r["closed"]:
            break
        time.sleep(0.1)
    assert r["closed"] and r["exit_code"] == 0 and b"signed in with abc123" in r["data"]
    tail = sessions.read(sid, r["offset"])
    assert tail is not None and tail["data"] == b""
    assert sessions.write(sid, b"x") is False
    assert sessions.close(sid) and sessions.read(sid) is None


def test_closing_a_login_kills_it(tmp_path: Path) -> None:
    _client(tmp_path, "codex", "sleep 30")
    sessions = d.LoginSessions()
    sid = sessions.start("codex", path=str(tmp_path) + ":/usr/bin:/bin")
    proc = sessions._sessions[sid]["proc"]
    assert sessions.close(sid)
    proc.wait(timeout=5)
    assert proc.returncode is not None
    with pytest.raises(ValueError):
        sessions.start("no-such-client")

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""What models this machine can reach, and how to sign in to them.

One copy of the knowledge of model clients, for every app built on substrate. Moved here from
substrate-ui's `server.py` (its `KNOWN_CLI_ADAPTERS`, `_agent_models`, `_probe_cli_versions`,
`_resolve_pin`, `_cli_status` and `_cli_pty_*`), so substrate-ui and state-transfer read the same
catalog (state-transfer roadmap 2026-10-13, sprint 055).

  - CATALOG — each command-line client's argv, flags, stream format, login, logout and status
    commands, family and curated model versions, as data.
  - detect() — every usable model as a `Model`: command-line clients found on the PATH, Ollama's
    local and cloud tags, and API keys in the environment. Nothing found gives an empty list.
  - cli_versions() / cli_command() — a client's version tree (live when it can list its models,
    else curated) and the argv for one pin.
  - cli_status() — whether a client is signed in, by its own status command.
  - LoginSessions — a client's own login command run in a pseudo-terminal, so an app shows the
    vendor's login and never handles a token.
  - login_path() — the PATH with the usual install folders added, for a process launched from
    Finder, which inherits no shell PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from substrate.adapters.models import is_ollama_cloud_model, ollama_base_url

# The catalog. Every value but `family` and Haiku 5.5 is substrate-ui's KNOWN_CLI_ADAPTERS as of
# its commit 11ff996 (2026-10-13), each verified there against the client's `--help` and a live
# run. `command` is what CliResponder runs for a turn (the prompt goes last). `isolation_flags`
# switch off what the client would load from this machine. `login_command` is the client's own
# interactive login; `status_command` reports whether it is signed in. `versions` is the curated
# model tree, used when the client has no `list_command`. claude-haiku-5-5 answered a test prompt
# through `claude -p --model claude-haiku-5-5` on 2026-10-13.
CATALOG: dict[str, dict[str, Any]] = {
    "claude": {
        "family": "anthropic",
        "command": ["claude", "-p"],
        "isolation_flags": [
            "--strict-mcp-config",
            "--setting-sources",
            "",
            "--dangerously-skip-permissions",
        ],
        "system_flag": ["--system-prompt"],
        "env": {"CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS": "1"},
        "stream_format": "claude-stream-json",
        "stream_flags": ["--output-format", "stream-json", "--verbose"],
        "mcp_style": "claude-mcp-config",
        "slash_commands": True,
        "login_command": ["claude", "auth", "login"],
        "logout_command": ["claude", "auth", "logout"],
        "status_command": ["claude", "auth", "status"],
        "versions": [
            {
                "id": "opus",
                "label": "Opus",
                "default_pin": "opus-5-5",
                "pins": [
                    {"id": "opus-5-5", "label": "5.5", "flag": ["--model", "claude-opus-5-5"]},
                    {"id": "opus-4-8", "label": "4.8", "flag": ["--model", "claude-opus-4-8"]},
                    {"id": "opus-4-7", "label": "4.7", "flag": ["--model", "claude-opus-4-7"]},
                    {"id": "opus-4-6", "label": "4.6", "flag": ["--model", "claude-opus-4-6"]},
                    {"id": "opus-4-5", "label": "4.5", "flag": ["--model", "claude-opus-4-5"]},
                    {"id": "opus-4-1", "label": "4.1", "flag": ["--model", "claude-opus-4-1"]},
                    {"id": "opus-4", "label": "4", "flag": ["--model", "claude-opus-4"]},
                    {"id": "opus-3", "label": "3", "flag": ["--model", "claude-3-opus"]},
                ],
            },
            {
                "id": "sonnet",
                "label": "Sonnet",
                "default_pin": "sonnet-5-5",
                "pins": [
                    {"id": "sonnet-5-5", "label": "5.5", "flag": ["--model", "claude-sonnet-5-5"]},
                    {"id": "sonnet-4-6", "label": "4.6", "flag": ["--model", "claude-sonnet-4-6"]},
                    {"id": "sonnet-4-5", "label": "4.5", "flag": ["--model", "claude-sonnet-4-5"]},
                    {"id": "sonnet-4", "label": "4", "flag": ["--model", "claude-sonnet-4"]},
                    {"id": "sonnet-3-7", "label": "3.7", "flag": ["--model", "claude-3-7-sonnet"]},
                    {"id": "sonnet-3-5", "label": "3.5", "flag": ["--model", "claude-3-5-sonnet"]},
                    {"id": "sonnet-3", "label": "3", "flag": ["--model", "claude-3-sonnet"]},
                ],
            },
            {
                "id": "haiku",
                "label": "Haiku",
                "default_pin": "haiku-5-5",
                "pins": [
                    {"id": "haiku-5-5", "label": "5.5", "flag": ["--model", "claude-haiku-5-5"]},
                    {"id": "haiku-4-5", "label": "4.5", "flag": ["--model", "claude-haiku-4-5"]},
                    {"id": "haiku-3-5", "label": "3.5", "flag": ["--model", "claude-3-5-haiku"]},
                    {"id": "haiku-3", "label": "3", "flag": ["--model", "claude-3-haiku"]},
                ],
            },
            {
                "id": "fable",
                "label": "Fable",
                "default_pin": "fable-5-1",
                "pins": [
                    {"id": "fable-5-1", "label": "5.1", "flag": ["--model", "claude-fable-5-1"]},
                    {"id": "fable-5", "label": "5", "flag": ["--model", "claude-fable-5"]},
                ],
            },
        ],
        "default_family": "opus",
    },
    "codex": {
        "family": "openai",
        "command": [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
        ],
        "stream_format": "codex-json",
        "stream_flags": ["--json"],
        "mcp_style": "codex-config",
        "login_command": ["codex", "login", "--device-auth"],
        "logout_command": ["codex", "logout"],
        "status_command": ["codex", "login", "status"],
        "versions": [
            {
                "id": "gpt-6",
                "label": "GPT-6",
                "default_pin": "gpt-6-astra",
                "pins": [
                    {"id": "gpt-6-astra", "label": "Astra", "flag": ["-m", "gpt-6-astra"]},
                    {"id": "gpt-6-sol", "label": "Sol", "flag": ["-m", "gpt-6-sol"]},
                    {"id": "gpt-6-luna", "label": "Luna", "flag": ["-m", "gpt-6-luna"]},
                ],
            },
            {
                "id": "gpt-5-6",
                "label": "GPT-5.6",
                "default_pin": "gpt-5-6-sol",
                "pins": [
                    {"id": "gpt-5-6-sol", "label": "Sol", "flag": ["-m", "gpt-5.6-sol"]},
                    {"id": "gpt-5-6-terra", "label": "Terra", "flag": ["-m", "gpt-5.6-terra"]},
                    {"id": "gpt-5-6-luna", "label": "Luna", "flag": ["-m", "gpt-5.6-luna"]},
                ],
            },
            {
                "id": "gpt-5",
                "label": "GPT-5",
                "default_pin": "gpt-5-5",
                "pins": [
                    {"id": "gpt-5-5", "label": "5.5", "flag": ["-m", "gpt-5.5"]},
                    {"id": "gpt-5-4", "label": "5.4", "flag": ["-m", "gpt-5.4"]},
                ],
            },
        ],
        "default_family": "gpt-6",
    },
    "cursor-agent": {
        "family": "cursor",
        "command": ["cursor-agent", "-p", "--trust", "--force", "--sandbox", "disabled"],
        "stream_format": "cursor-stream-json",
        "stream_flags": ["--output-format", "stream-json"],
        "mcp_style": "cursor-workspace-file",
        "login_command": ["cursor-agent", "login"],
        "login_env": {"NO_OPEN_BROWSER": "1"},
        "logout_command": ["cursor-agent", "logout"],
        "status_command": ["cursor-agent", "status"],
        "list_command": ["cursor-agent", "--list-models"],
        "versions": [
            {
                "id": "sonnet",
                "label": "Sonnet",
                "default_pin": "sonnet-4-thinking",
                "pins": [
                    {
                        "id": "sonnet-4-thinking",
                        "label": "4 thinking",
                        "flag": ["--model", "sonnet-4-thinking"],
                    },
                    {"id": "sonnet-4", "label": "4", "flag": ["--model", "sonnet-4"]},
                ],
            },
            {
                "id": "opus",
                "label": "Opus",
                "default_pin": "opus-4",
                "pins": [{"id": "opus-4", "label": "4", "flag": ["--model", "opus-4"]}],
            },
            {
                "id": "gpt",
                "label": "GPT",
                "default_pin": "gpt-5-5",
                "pins": [
                    {"id": "gpt-5-5", "label": "5.5", "flag": ["--model", "gpt-5.5"]},
                    {"id": "gpt-5", "label": "5", "flag": ["--model", "gpt-5"]},
                ],
            },
        ],
        "default_family": "sonnet",
    },
}

# API keys an app can use without a client: the environment variable and the family it serves.
API_KEYS: dict[str, str] = {"ANTHROPIC_API_KEY": "anthropic", "OPENAI_API_KEY": "openai"}

# Where installers put command-line clients on macOS. A process launched from Finder gets
# PATH=/usr/bin:/bin:/usr/sbin:/sbin, so `claude` and `ollama` are not found without these.
INSTALL_DIRS: tuple[str, ...] = (
    "~/.local/bin",
    "~/.claude/local",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "~/.npm-global/bin",
    "~/.bun/bin",
)

# Family of an Ollama tag, by the name before the size or tag. Unknown names answer "unknown".
_OLLAMA_FAMILIES: dict[str, str] = {
    "qwen": "alibaba",
    "llama": "meta",
    "deepseek": "deepseek",
    "gemma": "google",
    "mistral": "mistral",
    "mixtral": "mistral",
    "phi": "microsoft",
    "glm": "zhipu",
    "kimi": "moonshot",
    "nemotron": "nvidia",
    "gpt-oss": "openai",
}


@dataclass(frozen=True)
class Model:
    """One usable model.

    `kind` is `cli` (a command-line client; `name` is the catalog key), `ollama-local`,
    `ollama-cloud` (`name` is the Ollama tag) or `api-key` (`name` is the environment variable).
    `where` is the client's path, Ollama's base URL, or "env". `versions` is a client's version
    tree (see `cli_versions`); empty for the other kinds.
    """

    name: str
    kind: str
    family: str
    where: str
    versions: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "family": self.family,
            "where": self.where,
            "versions": self.versions,
        }


def login_path(path: str | None = None, dirs: tuple[str, ...] = INSTALL_DIRS) -> str:
    """`path` (default `$PATH`) with each existing folder of `dirs` appended if missing."""
    given = path if path is not None else os.environ.get("PATH", "")
    parts = [p for p in given.split(os.pathsep) if p]
    for d in dirs:
        full = str(Path(d).expanduser())
        if full not in parts and Path(full).is_dir():
            parts.append(full)
    return os.pathsep.join(parts)


def ollama_family(tag: str) -> str:
    """The family of an Ollama tag (`qwen2.5:7b-instruct` → alibaba), or "unknown"."""
    base = tag.split(":", 1)[0].split("/")[-1].lower()
    for prefix in sorted(_OLLAMA_FAMILIES, key=len, reverse=True):
        if base.startswith(prefix):
            return _OLLAMA_FAMILIES[prefix]
    return "unknown"


def ollama_tags(base_url: str | None = None, timeout: float = 1.0) -> list[str] | None:
    """Ollama's model tags, sorted; None when the daemon does not answer `/api/version` and
    `/api/tags` within `timeout` seconds each."""
    base = ollama_base_url(base_url)
    try:
        with urllib.request.urlopen(f"{base}/api/version", timeout=timeout):  # noqa: S310 - Ollama
            pass
        with urllib.request.urlopen(f"{base}/api/tags", timeout=timeout) as r:  # noqa: S310
            tags = json.loads(r.read())
    except Exception:  # noqa: BLE001 - no daemon, a hung one, or a bad reply: no Ollama models
        return None
    return sorted(str(m["name"]) for m in tags.get("models", []) if m.get("name"))


def detect(
    *,
    path: str | None = None,
    base_url: str | None = None,
    timeout: float = 1.0,
    clients: set[str] | None = None,
    env: dict[str, str] | None = None,
    install_dirs: tuple[str, ...] = INSTALL_DIRS,
) -> list[Model]:
    """Every usable model on this machine: catalog clients found on `login_path(path)`, then
    Ollama's local and cloud tags, then API keys set in `env` (default `os.environ`).

    `clients` limits the clients looked for; None reads `SUBSTRATE_CLI_ADAPTERS` (a comma-separated
    list, as substrate-ui's offline gates set it), and when that is unset looks for all.
    `install_dirs` are the folders added to the PATH (see `login_path`).
    """
    env = dict(os.environ) if env is None else env
    if clients is None and env.get("SUBSTRATE_CLI_ADAPTERS") is not None:
        clients = {n.strip() for n in env["SUBSTRATE_CLI_ADAPTERS"].split(",") if n.strip()}
    search = login_path(path, install_dirs)
    found: list[Model] = []
    for name in sorted(CATALOG):
        if clients is not None and name not in clients:
            continue
        exe = shutil.which(CATALOG[name]["command"][0], path=search)
        if exe:
            versions = cli_versions(name, path=search)
            found.append(Model(name, "cli", CATALOG[name]["family"], exe, versions))
    base = ollama_base_url(base_url)
    for tag in ollama_tags(base, timeout) or []:
        kind = "ollama-cloud" if is_ollama_cloud_model(tag) else "ollama-local"
        found.append(Model(tag, kind, ollama_family(tag), base))
    for var, family in API_KEYS.items():
        if env.get(var):
            found.append(Model(var, "api-key", family, "env"))
    return found


def resolve_pin(tree: dict[str, Any], version: str | None) -> dict[str, Any] | None:
    """The pin `version` names in a version tree: None → the default family's default pin; a
    family id → that family's default pin; a pin id → that pin. None when nothing matches."""
    families = tree.get("families") or tree.get("versions") or []

    def pin_by_id(family: dict[str, Any], pin_id: str) -> dict[str, Any] | None:
        return next((p for p in (family.get("pins") or []) if p.get("id") == pin_id), None)

    if version is None:
        family = next((f for f in families if f.get("id") == tree.get("default_family")), None)
        return pin_by_id(family, family.get("default_pin", "")) if family else None
    for family in families:
        if family.get("id") == version:
            return pin_by_id(family, family.get("default_pin", ""))
        pin = pin_by_id(family, version)
        if pin is not None:
            return pin
    return None


def parse_cursor_list(text: str) -> dict[str, Any] | None:
    """A version tree from `cursor-agent --list-models`: model lines are `<id>`, `<id> (default)`
    or `<id> - <Label>`; any other line is a heading. Grouped by the id's first dash segment.
    None when no model line is found."""
    ids: list[str] = []
    default: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        head = parts[0]
        if not head[0].isalpha() or head.endswith(":"):
            continue
        if len(parts) > 1 and parts[1] not in ("-", "(default)"):
            continue
        ids.append(head)
        if "(default)" in line and default is None:
            default = head
    if not ids:
        return None
    groups: dict[str, list[str]] = {}
    for mid in ids:
        groups.setdefault(mid.split("-")[0], []).append(mid)
    families = [
        {
            "id": key,
            "label": key.capitalize(),
            "default_pin": pins[0],
            "pins": [{"id": p, "label": p, "flag": ["--model", p]} for p in pins],
        }
        for key, pins in groups.items()
    ]
    return {
        "families": families,
        "default_family": families[0]["id"],
        "source": "live",
        "default_pin_id": default,
    }


VERSION_CACHE_TTL_S = 300.0
_version_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_version_lock = threading.Lock()


def cli_versions(name: str, *, path: str | None = None, fresh: bool = False) -> dict[str, Any]:
    """A client's version tree: from its `list_command` when it has one and it answers within
    6 s (`source: live`), else the catalog's curated tree (`source: curated`). Cached for
    VERSION_CACHE_TTL_S seconds unless `fresh`."""
    now = time.monotonic()
    with _version_lock:
        hit = _version_cache.get(name)
    if hit and not fresh and now - hit[0] < VERSION_CACHE_TTL_S:
        return hit[1]
    entry = CATALOG.get(name) or {}
    tree: dict[str, Any] = {
        "families": [
            {
                "id": f["id"],
                "label": f["label"],
                "default_pin": f.get("default_pin"),
                "pins": [
                    {"id": p["id"], "label": p["label"], "flag": list(p.get("flag") or [])}
                    for p in f.get("pins") or []
                ],
            }
            for f in entry.get("versions") or []
        ],
        "default_family": entry.get("default_family"),
        "source": "curated",
    }
    list_cmd = entry.get("list_command")
    if list_cmd:
        try:
            proc = subprocess.run(  # noqa: S603 - a catalog client's own listing command
                list_cmd,
                capture_output=True,
                text=True,
                timeout=6.0,
                env={**os.environ, "PATH": login_path(path)},
            )
            live = parse_cursor_list(proc.stdout) if proc.returncode == 0 else None
            if live:
                tree = live
        except (OSError, subprocess.SubprocessError):
            pass
    with _version_lock:
        _version_cache[name] = (now, tree)
    return tree


def cli_command(name: str, version: str | None = None) -> list[str] | None:
    """The argv for a turn with client `name`: its command, its isolation flags, then the flag of
    the pin `version` resolves to (see `resolve_pin`). None for a name not in the catalog."""
    entry = CATALOG.get(name)
    if entry is None:
        return None
    cmd = list(entry["command"]) + list(entry.get("isolation_flags") or [])
    pin = resolve_pin(cli_versions(name), version)
    return cmd + list(pin.get("flag") or []) if pin else cmd


def cli_status(name: str, timeout: float = 5.0, *, path: str | None = None) -> dict[str, Any]:
    """Whether client `name` is signed in, by its own status command: `{authed, raw, detail?}`.
    `authed` is None for a client with no status command or no parser."""
    entry = CATALOG.get(name)
    if entry is None:
        return {"authed": None, "raw": "", "detail": "unknown cli"}
    status_cmd = entry.get("status_command")
    if not status_cmd:
        return {"authed": None, "raw": "", "detail": "no status_command"}
    try:
        proc = subprocess.run(  # noqa: S603 - a catalog client's own status command
            status_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PATH": login_path(path)},
        )
    except subprocess.TimeoutExpired:
        return {"authed": False, "raw": "", "detail": "status probe timed out"}
    except FileNotFoundError:
        return {"authed": False, "raw": "", "detail": "cli binary not found"}
    combined = (proc.stdout + proc.stderr).strip()
    if name == "claude":
        try:
            return {"authed": bool(json.loads(proc.stdout).get("loggedIn")), "raw": combined}
        except (ValueError, AttributeError):
            return {"authed": False, "raw": combined}
    if name in ("codex", "cursor-agent"):
        return {"authed": "Not logged in" not in combined, "raw": combined}
    return {"authed": None, "raw": combined, "detail": "no parser"}


class LoginSessions:
    """Clients' login commands, each in its own pseudo-terminal.

    `start(name)` spawns the client's `login_command` and returns a session id; a thread drains
    its output into a buffer capped at `max_buffer` bytes (oldest dropped). `read(sid, offset)`
    returns output from `offset`, whether it has ended and its exit code; `write(sid, data)` sends
    keystrokes; `close(sid)` kills its process group. A finished session stays readable for
    `linger_s` seconds, then is forgotten.
    """

    def __init__(self, max_buffer: int = 512 * 1024, linger_s: float = 60.0) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._max_buffer = max_buffer
        self._linger_s = linger_s

    def start(self, name: str, *, path: str | None = None) -> str:
        import fcntl
        import pty
        import select

        entry = CATALOG.get(name)
        if entry is None:
            raise ValueError(f"unknown cli {name!r}")
        login_cmd = entry.get("login_command")
        if not login_cmd:
            raise ValueError(f"cli {name!r} has no login_command")
        master_fd, slave_fd = pty.openpty()
        fcntl.fcntl(master_fd, fcntl.F_SETFL, fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)
        env = {**os.environ, **(entry.get("login_env") or {}), "PATH": login_path(path)}
        proc = subprocess.Popen(  # noqa: S603 - a catalog client's own login command
            login_cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            env=env,
            start_new_session=True,
        )
        os.close(slave_fd)
        sid = uuid.uuid4().hex
        session: dict[str, Any] = {
            "proc": proc,
            "out": bytearray(),
            "dropped": 0,
            "closed": False,
            "exit_code": None,
            "master_fd": master_fd,
            "lock": threading.Lock(),
        }
        with self._lock:
            self._sessions[sid] = session

        def drain() -> None:
            while True:
                try:
                    ready, _, _ = select.select([master_fd], [], [], 0.2)
                    chunk = b""
                    if master_fd in ready:
                        try:
                            chunk = os.read(master_fd, 4096)
                        except OSError:
                            chunk = b""
                        if not chunk:
                            break
                        self._append(session, chunk)
                    if proc.poll() is not None and not chunk:
                        try:
                            self._append(session, os.read(master_fd, 65536))
                        except OSError:
                            pass
                        break
                except Exception:  # noqa: BLE001 - a pty read can fail in odd ways; end the drain
                    break
            proc.wait()
            with session["lock"]:
                session["closed"] = True
                session["exit_code"] = proc.returncode
            try:
                os.close(master_fd)
            except OSError:
                pass
            timer = threading.Timer(self._linger_s, lambda: self._forget(sid))
            timer.daemon = True
            timer.start()

        threading.Thread(target=drain, daemon=True, name=f"login-{name}-{sid[:8]}").start()
        return sid

    def _append(self, session: dict[str, Any], chunk: bytes) -> None:
        with session["lock"]:
            session["out"].extend(chunk)
            over = len(session["out"]) - self._max_buffer
            if over > 0:
                del session["out"][:over]
                session["dropped"] += over

    def _forget(self, sid: str) -> None:
        with self._lock:
            self._sessions.pop(sid, None)

    def read(self, sid: str, offset: int = 0) -> dict[str, Any] | None:
        """`{data, offset, closed, exit_code}` from byte `offset` of everything the session has
        printed; `offset` in the reply is where the next read starts. None for an unknown id."""
        with self._lock:
            session = self._sessions.get(sid)
        if session is None:
            return None
        with session["lock"]:
            start = max(offset - session["dropped"], 0)
            data = bytes(session["out"][start:])
            return {
                "data": data,
                "offset": session["dropped"] + len(session["out"]),
                "closed": session["closed"],
                "exit_code": session["exit_code"],
            }

    def write(self, sid: str, data: bytes) -> bool:
        """Send keystrokes; False when the session is unknown or has ended."""
        with self._lock:
            session = self._sessions.get(sid)
        if session is None:
            return False
        with session["lock"]:
            if session["closed"]:
                return False
            fd = session["master_fd"]
        try:
            os.write(fd, data)
            return True
        except OSError:
            return False

    def close(self, sid: str) -> bool:
        """Kill the session's process group and forget it. False for an unknown id."""
        with self._lock:
            session = self._sessions.pop(sid, None)
        if session is None:
            return False
        proc = session["proc"]
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except OSError:
                try:
                    proc.terminate()
                except OSError:
                    pass
        return True

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""A CLI driver's context window, resolved in order (session vocabulary § S.9).

1. **Live.** The harness reports it on a call (Claude Code's `modelUsage.contextWindow`); the
   model step records it on `ModelReply.usage.context_window`, and later steps budget on it.
2. **The CLI's own settings.** Codex's `model_context_window` in `$CODEX_HOME/config.toml`.
3. **Documented.** The model's input limit from its maker's documentation, below, keyed by the id
   the session passes with `--model` or `-m` (or Codex's configured `model`).
4. **Substrate's config.** `[driver.<name>].context_tokens` in `~/.substrate/config.toml`.
5. **Default.** 100,000.

Steps 2 to 5 run at session open; `SessionStarted.driver_context_source` names the one that
answered. Where a page states a maximum input below the context window, the input limit is used:
the budget is for the prompt.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Final

# Context-window sources (SessionStarted.driver_context_source).
CONTEXT_SOURCE_LIVE: Final[str] = "live"
CONTEXT_SOURCE_CLI_SETTINGS: Final[str] = "cli_settings"
CONTEXT_SOURCE_DOCUMENTED: Final[str] = "documented"
CONTEXT_SOURCE_CONFIG: Final[str] = "config"
CONTEXT_SOURCE_DEFAULT: Final[str] = "default"
CONTEXT_SOURCE_PROBED: Final[str] = "probed"  # an adapter that reports it (Ollama's /api/show)
CONTEXT_SOURCE_FIXED: Final[str] = "fixed"  # the deterministic stand-in

_ANTHROPIC = "https://platform.claude.com/docs/en/build-with-claude/context-windows (2026-10-11)"
_OPENAI = "https://developers.openai.com/api/docs/models/{id} (2026-10-11)"

_ONE_MILLION = 1_000_000
_TWO_HUNDRED_K = 200_000

# Anthropic: "Claude Fable 5.1, …, Claude Opus 4.6, Claude Sonnet 5.5, Claude Sonnet 5, Claude
# Sonnet 4.6, Claude Haiku 5.5 … have a 1M-token context window. … Other Claude models, including
# Claude Sonnet 4.5 (deprecated), have a 200k-token context window."
_CLAUDE_1M = (
    "claude-fable-5-1",
    "claude-fable-5",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5-5",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-haiku-5-5",
)
_CLAUDE_200K = (
    "claude-opus-4-5",
    "claude-opus-4-1",
    "claude-opus-4",
    "claude-3-opus",
    "claude-sonnet-4-5",
    "claude-sonnet-4",
    "claude-3-7-sonnet",
    "claude-3-5-sonnet",
    "claude-3-sonnet",
    "claude-haiku-4-5",
    "claude-3-5-haiku",
    "claude-3-haiku",
)
# OpenAI model pages: "Maximum input tokens: 922,000" where stated; else the context window.
_OPENAI_INPUT = {
    "gpt-6-astra": 922_000,
    "gpt-6-sol": 922_000,
    "gpt-6.1-sol": 922_000,
    "gpt-6-luna": 922_000,
    "gpt-5.6-sol": 922_000,
    "gpt-5.6-terra": 922_000,
    "gpt-5.6-luna": 922_000,
    "gpt-5.5": 1_050_000,  # no separate input limit stated
    "gpt-5.4": 1_050_000,  # no separate input limit stated
    "gpt-5": 272_000,  # 400,000 window; "Maximum input tokens: 272,000"
}

# model id -> (input tokens, source). Cursor's model pages state no per-model window, so
# cursor-agent's ids have no entry and fall through to the config.
DOCUMENTED_CONTEXT_WINDOWS: Final[dict[str, tuple[int, str]]] = {
    **{m: (_ONE_MILLION, _ANTHROPIC) for m in _CLAUDE_1M},
    **{m: (_TWO_HUNDRED_K, _ANTHROPIC) for m in _CLAUDE_200K},
    **{m: (n, _OPENAI.format(id=m)) for m, n in _OPENAI_INPUT.items()},
}

DEFAULT_CLI_CONTEXT_TOKENS: Final[int] = 100_000


def model_from_command(command: Sequence[str]) -> str | None:
    """The model id a CLI command names with `--model` or `-m`, if any."""
    args = list(command)
    for i, arg in enumerate(args):
        if arg in ("--model", "-m") and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith("--model="):
            return arg.split("=", 1)[1]
    return None


def _codex_settings(codex_home: Path | None = None) -> dict[str, object]:
    home = codex_home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    path = home / "config.toml"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _substrate_config(driver_name: str, config_path: Path) -> int | None:
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    table = data.get("driver", {})
    entry = table.get(driver_name, {}) if isinstance(table, dict) else {}
    value = entry.get("context_tokens") if isinstance(entry, dict) else None
    return value if isinstance(value, int) and value > 0 else None


def resolve_cli_context(
    driver_name: str,
    command: Sequence[str],
    *,
    config_path: Path,
    codex_home: Path | None = None,
) -> tuple[int, str]:
    """Steps 2 to 5 of the module docstring for one CLI driver: the window and where it came from."""
    model = model_from_command(command)
    if driver_name == "codex":
        settings = _codex_settings(codex_home)
        window = settings.get("model_context_window")
        if isinstance(window, int) and window > 0:
            return window, CONTEXT_SOURCE_CLI_SETTINGS
        configured = settings.get("model")
        if model is None and isinstance(configured, str):
            model = configured
    if model is not None and model in DOCUMENTED_CONTEXT_WINDOWS:
        return DOCUMENTED_CONTEXT_WINDOWS[model][0], CONTEXT_SOURCE_DOCUMENTED
    configured_tokens = _substrate_config(driver_name, config_path)
    if configured_tokens is not None:
        return configured_tokens, CONTEXT_SOURCE_CONFIG
    return DEFAULT_CLI_CONTEXT_TOKENS, CONTEXT_SOURCE_DEFAULT

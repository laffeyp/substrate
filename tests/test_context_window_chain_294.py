# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""A CLI driver's context window, resolved in order (session vocabulary § S.9).

Before: every CLI driver got a flat 100,000 tokens whatever its model. Now: the harness's live
report, then the CLI's own settings, then the maker's documented window for the model the session
names, then `[driver.<name>].context_tokens`, then 100,000; SessionStarted names the source.
"""

from __future__ import annotations

from pathlib import Path

from substrate.adapters import CliResponder
from substrate.adapters.harness_streams import CLAUDE_STREAM_JSON, StreamUsage, parser_for
from substrate.topologies.session.context_windows import (
    CONTEXT_SOURCE_CLI_SETTINGS,
    CONTEXT_SOURCE_CONFIG,
    CONTEXT_SOURCE_DEFAULT,
    CONTEXT_SOURCE_DOCUMENTED,
    DOCUMENTED_CONTEXT_WINDOWS,
    model_from_command,
    resolve_cli_context,
)
from substrate.topologies.session.transcript import TURN_EVENT_KINDS, resolve_driver_context
from substrate.topologies.session.views import TurnHistory
from substrate.types import Event

FIXTURES = Path(__file__).parent / "fixtures" / "harness_streams"


def test_the_model_comes_from_the_command() -> None:
    assert model_from_command(["claude", "-p", "--model", "claude-opus-4-5"]) == "claude-opus-4-5"
    assert model_from_command(["codex", "exec", "-m", "gpt-5"]) == "gpt-5"
    assert model_from_command(["cursor-agent", "--model=sonnet-4"]) == "sonnet-4"
    assert model_from_command(["claude", "-p"]) is None


def test_the_documented_window_is_the_input_limit(tmp_path: Path) -> None:
    none = tmp_path / "none.toml"
    assert resolve_cli_context(
        "claude", ["claude", "--model", "claude-opus-5-5"], config_path=none
    ) == (
        1_000_000,
        CONTEXT_SOURCE_DOCUMENTED,
    )
    assert resolve_cli_context(
        "claude", ["claude", "--model", "claude-sonnet-4-5"], config_path=none
    ) == (
        200_000,
        CONTEXT_SOURCE_DOCUMENTED,
    )
    gpt5 = ["codex", "exec", "-m", "gpt-5"]
    assert resolve_cli_context("codex", gpt5, config_path=none, codex_home=tmp_path) == (
        272_000,  # 400,000 window, 272,000 maximum input
        CONTEXT_SOURCE_DOCUMENTED,
    )
    assert all(src.startswith("https://") for _n, src in DOCUMENTED_CONTEXT_WINDOWS.values())


def test_codexs_own_setting_comes_before_the_documented_window(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text("model_context_window = 400000\n")
    command = ["codex", "exec", "-m", "gpt-5.5"]
    assert resolve_cli_context(
        "codex", command, config_path=tmp_path / "none.toml", codex_home=tmp_path
    ) == (400_000, CONTEXT_SOURCE_CLI_SETTINGS)


def test_codexs_configured_model_is_looked_up(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text('model = "gpt-6-astra"\n')
    assert resolve_cli_context(
        "codex", ["codex", "exec"], config_path=tmp_path / "none.toml", codex_home=tmp_path
    ) == (922_000, CONTEXT_SOURCE_DOCUMENTED)


def test_an_undocumented_model_falls_to_the_config_then_the_default(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("[driver.cursor-agent]\ncontext_tokens = 150000\n")
    command = ["cursor-agent", "-p", "--model", "sonnet-4"]
    assert resolve_cli_context("cursor-agent", command, config_path=config) == (
        150_000,
        CONTEXT_SOURCE_CONFIG,
    )
    assert resolve_cli_context("cursor-agent", command, config_path=tmp_path / "x.toml") == (
        100_000,
        CONTEXT_SOURCE_DEFAULT,
    )


def test_resolve_driver_context_reads_the_responders_command(tmp_path: Path) -> None:
    r = CliResponder(["claude", "-p", "--model", "claude-haiku-4-5"], name="claude")
    assert resolve_driver_context("claude", r, config_path=tmp_path / "none.toml") == (
        200_000,
        CONTEXT_SOURCE_DOCUMENTED,
    )


def test_claudes_stream_reports_its_window() -> None:
    parser = parser_for(CLAUDE_STREAM_JSON)
    items = []
    for line in (FIXTURES / "claude.jsonl").read_text().splitlines():
        items += parser.feed(line)
    usage = [i for i in items if isinstance(i, StreamUsage)]
    assert usage and usage[-1].context_window == 1_000_000


def test_a_reported_window_reaches_the_history_view() -> None:
    view = TurnHistory(TURN_EVENT_KINDS)

    def ev(seq: int, kind: str, payload: dict[str, object]) -> Event:
        return Event(seq=seq, kind=kind, schema="", producer=None, t=0.0, payload=payload)

    view.update(ev(1, "UserMessage", {"text": "hi", "turn_index": 0}))
    assert view.value().window is None
    usage = {"model": "claude", "prompt_tokens": 9, "completion_tokens": 1, "wall_ms": 1}
    view.update(
        ev(
            2,
            "ModelReply",
            {"text": "ok", "usage": {**usage, "estimated": False, "context_window": 1_000_000}},
        )
    )
    assert view.value().window == 1_000_000

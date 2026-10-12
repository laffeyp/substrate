# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Reading a harness driver's event stream (sprint K283; session vocabulary § Q).

A harness CLI (Claude Code, Codex, cursor-agent) runs its own agent loop and, asked for a stream,
prints one JSON object per line as it works. Each parser here turns those lines into four items:
a tool call starting, its result, the final reply text, and the call's token counts. The model step
writes the first two as `HarnessToolCall` / `HarnessToolResult` and takes the last
two as the reply and its usage.

The formats were read from real runs on 2026-10-10 (`substrate-ui/process/planning/evidence-2026-
10-10-harness-streams/`): Claude Code 2.1.296 `--output-format stream-json --verbose`, Codex 0.157.0
`exec --json`, cursor-agent 2026.09.23 `--output-format stream-json`. Fields a stream carries for
dollar estimates or rate limits are never read: Substrate tracks tokens and time, not money.
A line that is not a JSON object (Codex prints "Reading additional input from stdin...") is skipped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final


@dataclass(frozen=True)
class StreamToolCall:
    call_id: str
    tool: str
    args: dict[str, Any]


@dataclass(frozen=True)
class StreamToolResult:
    call_id: str
    ok: bool
    output: str


@dataclass(frozen=True)
class StreamUsage:
    prompt_tokens: int
    completion_tokens: int
    # The model's context window, when the harness reports it (Claude Code's
    # `modelUsage.<model>.contextWindow`); session vocabulary § S.9.
    context_window: int | None = None


@dataclass(frozen=True)
class StreamReply:
    """The call's final reply text; `CliResponder.astream` yields it last, once the CLI exits."""

    text: str


StreamItem = StreamToolCall | StreamToolResult | StreamUsage | StreamReply

# The name Substrate's MCP server goes by in a harness's config (UI sprint 129, kernel K284).
SUBSTRATE_MCP_SERVER: Final[str] = "substrate"


def calls_substrate_mcp(tool: str) -> bool:
    """Whether a tool name in a harness's stream is a call to Substrate's own MCP server: Claude
    Code names it `mcp__substrate__<tool>`, Codex `substrate.<tool>`, cursor-agent
    `substrate-<tool>`. Substrate records that call as its own `ToolCall` where it runs, so the stream's
    copy is not recorded again."""
    return tool.startswith(
        (
            f"mcp__{SUBSTRATE_MCP_SERVER}__",
            f"{SUBSTRATE_MCP_SERVER}.",
            f"{SUBSTRATE_MCP_SERVER}-",
        )
    )


CLAUDE_STREAM_JSON: Final[str] = "claude-stream-json"
CODEX_JSON: Final[str] = "codex-json"
CURSOR_STREAM_JSON: Final[str] = "cursor-stream-json"


class HarnessStreamError(RuntimeError):
    """The stream reported that the harness's own run failed."""


def _text(content: Any) -> str:
    """A tool result's content: a string, or a list of `{type: text, text}` parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    return "" if content is None else json.dumps(content)


class _Parser:
    """Feed lines in order; read `final_text` once the stream ends."""

    def __init__(self) -> None:
        self.final_text: str | None = None

    def feed(self, line: str) -> list[StreamItem]:
        line = line.strip()
        if not line.startswith("{"):
            return []
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return []
        return self._event(event) if isinstance(event, dict) else []

    def _event(self, event: dict[str, Any]) -> list[StreamItem]:
        raise NotImplementedError


class ClaudeStreamParser(_Parser):
    """`tool_use` parts of `assistant` messages are calls; `tool_result` parts of `user` messages
    are results; the closing `result` event carries the reply and the token counts."""

    def _event(self, event: dict[str, Any]) -> list[StreamItem]:
        kind = event.get("type")
        items: list[StreamItem] = []
        if kind in ("assistant", "user"):
            for part in (event.get("message") or {}).get("content") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "tool_use":
                    items.append(
                        StreamToolCall(
                            call_id=str(part.get("id", "")),
                            tool=str(part.get("name", "?")),
                            args=dict(part.get("input") or {}),
                        )
                    )
                elif part.get("type") == "tool_result":
                    items.append(
                        StreamToolResult(
                            call_id=str(part.get("tool_use_id", "")),
                            ok=not part.get("is_error", False),
                            output=_text(part.get("content")),
                        )
                    )
        elif kind == "result":
            if event.get("is_error"):
                raise HarnessStreamError(str(event.get("result") or event.get("subtype")))
            self.final_text = str(event.get("result") or "")
            usage = event.get("usage") or {}
            prompt = sum(
                int(usage.get(k) or 0)
                for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
            )
            windows = [
                int(m.get("contextWindow") or 0)
                for m in (event.get("modelUsage") or {}).values()
                if isinstance(m, dict)
            ]
            window = max(windows) if windows and max(windows) > 0 else None
            items.append(StreamUsage(prompt, int(usage.get("output_tokens") or 0), window))
        return items


# Codex's own item statuses (exec_events.rs), not Substrate's session or task statuses.
_CODEX_ITEM_COMPLETED: Final[str] = "completed"
_CODEX_ITEM_FAILED: Final[str] = "failed"

# Codex items that are tool calls, and the arguments each carries (exec_events.rs item types).
_CODEX_TOOL_ITEMS: Final[dict[str, tuple[str, ...]]] = {
    "command_execution": ("command",),
    "file_change": ("changes",),
    "mcp_tool_call": ("server", "tool", "arguments"),
    "web_search": ("query",),
}


class CodexJsonParser(_Parser):
    """`item.started` / `item.completed` of a tool item type; a `file_change` may arrive only as
    completed, so a completion with no start writes its call first. The last `agent_message` is
    the reply; `turn.completed` carries the token counts; `turn.failed` and `error` raise."""

    def __init__(self) -> None:
        super().__init__()
        self._started: set[str] = set()

    def _event(self, event: dict[str, Any]) -> list[StreamItem]:
        kind = event.get("type")
        if kind in ("turn.failed", "error"):
            detail = event.get("error") or event.get("message") or event
            raise HarnessStreamError(json.dumps(detail) if not isinstance(detail, str) else detail)
        if kind == "turn.completed":
            usage = event.get("usage") or {}
            return [
                StreamUsage(
                    int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
                )
            ]
        if kind not in ("item.started", "item.completed"):
            return []
        item = event.get("item") or {}
        item_type = str(item.get("type", ""))
        item_id = str(item.get("id", ""))
        if item_type == "agent_message" and kind == "item.completed":
            self.final_text = str(item.get("text", "")).strip()
            return []
        if item_type not in _CODEX_TOOL_ITEMS:
            return []
        items: list[StreamItem] = []
        if item_id not in self._started:
            self._started.add(item_id)
            tool = (
                f"{item.get('server', '?')}.{item.get('tool', '?')}"
                if item_type == "mcp_tool_call"
                else item_type
            )
            args = {k: item.get(k) for k in _CODEX_TOOL_ITEMS[item_type] if k in item}
            items.append(StreamToolCall(call_id=item_id, tool=tool, args=args))
        if kind == "item.completed":
            items.append(self._result(item_id, item_type, item))
        return items

    @staticmethod
    def _result(item_id: str, item_type: str, item: dict[str, Any]) -> StreamToolResult:
        status = item.get("status")
        if item_type == "command_execution":
            ok = item.get("exit_code") == 0
            output = str(item.get("aggregated_output", ""))
        elif item_type == "file_change":
            ok = status == _CODEX_ITEM_COMPLETED
            output = "\n".join(
                f"{c.get('kind', '?')} {c.get('path', '?')}"
                for c in item.get("changes") or []
                if isinstance(c, dict)
            )
        elif item_type == "mcp_tool_call":
            ok = status == _CODEX_ITEM_COMPLETED and not item.get("error")
            output = json.dumps(item.get("result") if ok else item.get("error"))
        else:
            ok = status != _CODEX_ITEM_FAILED
            output = json.dumps({k: v for k, v in item.items() if k not in ("id", "type")})
        return StreamToolResult(call_id=item_id, ok=ok, output=output)


class CursorStreamParser(_Parser):
    """`tool_call` started / completed events hold one `<name>ToolCall` object each, with its
    `args` and, on completion, `result.success` or a failure; the `result` event carries the reply
    and the token counts."""

    def _event(self, event: dict[str, Any]) -> list[StreamItem]:
        kind = event.get("type")
        if kind == "tool_call":
            body = event.get("tool_call") or {}
            name = next((k for k in body if k.endswith("ToolCall")), None)
            if name is None:
                return []
            call = body[name] or {}
            call_id = str(event.get("call_id", ""))
            tool = name[: -len("ToolCall")]
            if name == "mcpToolCall":  # an MCP server's tool: args.name is `<server>-<tool>`
                tool = str((call.get("args") or {}).get("name") or tool)
            if event.get("subtype") == "started":
                return [
                    StreamToolCall(call_id=call_id, tool=tool, args=dict(call.get("args") or {}))
                ]
            if event.get("subtype") == "completed":
                result = call.get("result") or {}
                success = result.get("success")
                if isinstance(success, dict):
                    output = success.get("stdout")
                    if output is None:
                        output = success.get("diffString") or json.dumps(success)
                    exit_code = success.get("exitCode", 0)
                    return [StreamToolResult(call_id, exit_code in (0, None), str(output))]
                return [StreamToolResult(call_id, False, json.dumps(result))]
            return []
        if kind == "result":
            if event.get("is_error"):
                raise HarnessStreamError(str(event.get("result") or event.get("subtype")))
            self.final_text = str(event.get("result") or "")
            usage = event.get("usage") or {}
            prompt = int(usage.get("inputTokens") or 0) + int(usage.get("cacheReadTokens") or 0)
            return [StreamUsage(prompt, int(usage.get("outputTokens") or 0))]
        return []


_PARSERS: Final[dict[str, type[_Parser]]] = {
    CLAUDE_STREAM_JSON: ClaudeStreamParser,
    CODEX_JSON: CodexJsonParser,
    CURSOR_STREAM_JSON: CursorStreamParser,
}
STREAM_FORMATS: Final[frozenset[str]] = frozenset(_PARSERS)


def parser_for(stream_format: str) -> _Parser:
    """A fresh parser for one call's stream."""
    try:
        return _PARSERS[stream_format]()
    except KeyError:
        raise ValueError(
            f"unknown harness stream format {stream_format!r}; known: {sorted(STREAM_FORMATS)}"
        ) from None


__all__ = [
    "CLAUDE_STREAM_JSON",
    "CODEX_JSON",
    "CURSOR_STREAM_JSON",
    "STREAM_FORMATS",
    "SUBSTRATE_MCP_SERVER",
    "calls_substrate_mcp",
    "HarnessStreamError",
    "StreamItem",
    "StreamReply",
    "StreamToolCall",
    "StreamToolResult",
    "StreamUsage",
    "parser_for",
]

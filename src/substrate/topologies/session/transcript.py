# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Session prompt builder and history window (piece A, sprint 207; rebuilt in K261).

`compose_model_prompt` builds the whole prompt for one model call: the seed, the session's prompt
fragments and per_turn by precedence, the kept turns with the current one last, any interrupt,
background-task notices. The model step appends its pre-K261 endings, records the final text as
`PromptComposed` and sends it unchanged.

The history window keeps the most recent turns whose rendered size fits the budget (driver
context x headroom, minus the fixed head); the current turn always stays. When turns drop, one
`TranscriptCompacted` names the dropped range. Token estimates are a chars/4 heuristic; the driver's
own counts for each call are on `ModelReply.usage` (K262).
"""

from __future__ import annotations

import time
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

from msgspec import Struct

from ...adapters import (
    ContextTokensUnknown,
    DriverIntrospectionUnavailable,
    Responder,
)
from ..tool_loop.kinds import FINAL_ANSWER, TOOL_CALL, TOOL_RESULT
from .vocabulary import (
    BACKGROUND_TASK_ENDED,
    DRIVER_SLASH_SOURCE,
    HARNESS_TOOL_CALL,
    HARNESS_TOOL_RESULT,
    SESSION_CHANGED,
    StopReason,
)
from .vocabulary import (
    MODEL_REPLY as _KIND_MODEL_REPLY,
)
from .vocabulary import (
    PARK as _KIND_PARK,
)
from .vocabulary import (
    RETURNED as _KIND_RETURNED,
)
from .vocabulary import (
    TRANSCRIPT_COMPACTED as _KIND_TRANSCRIPT_COMPACTED,
)
from .vocabulary import (
    USER_MESSAGE as _KIND_USER_MESSAGE,
)

_CONTEXT_CACHE_TTL_SECONDS = 60.0
_CLI_CONTEXT_DEFAULT_TOKENS = 100_000
_DETERMINISTIC_CONTEXT_TOKENS = 4096

# One process-wide cache keyed by (driver_class, model_tag). Ollama's /api/show
# result is stable across the session's lifetime; a 60-second TTL lets a model
# reload after a config change without a session restart, and keeps a cluster of
# session opens on the same tag to a single HTTP call.
_context_cache: dict[tuple[str, str], tuple[float, int]] = {}

_CHARS_PER_TOKEN = 4  # coarse conservative estimator; see module docstring
# § S.1: the newest tool results always render whole; § S.5: the estimate's scale is clamped.
KEEP_WHOLE_TOOL_OUTPUTS = 3
_SCALE_MIN, _SCALE_MAX = 1.0, 4.0

# _KIND_USER_MESSAGE, _KIND_MODEL_REPLY, _KIND_PARK, _KIND_TRANSCRIPT_COMPACTED
# imported above from `.vocabulary` (single source of truth per REVIEW F5).
_KIND_TOOL_CALL = TOOL_CALL
_KIND_TOOL_RESULT = TOOL_RESULT
_KIND_FINAL_ANSWER = FINAL_ANSWER
# `TranscriptCompacted` rides a turn because the `model` producer yields it at the start
# of a firing (session/__init__.py::_model_factory). `SessionWarning` is written at session
# open by `session_prompt` and never rides a turn, so it stays out of this set.
TURN_EVENT_KINDS = frozenset(
    {
        BACKGROUND_TASK_ENDED,
        SESSION_CHANGED,
        HARNESS_TOOL_CALL,
        HARNESS_TOOL_RESULT,
        _KIND_USER_MESSAGE,
        _KIND_MODEL_REPLY,
        _KIND_TOOL_CALL,
        _KIND_TOOL_RESULT,
        _KIND_FINAL_ANSWER,
        _KIND_PARK,
        _KIND_RETURNED,
        _KIND_TRANSCRIPT_COMPACTED,
    }
)


class TranscriptCompacted(Struct, frozen=True):
    """Vocabulary lock at `substrate/process/signals/session-vocabulary.md` §D.

    Canonical Python home for the Struct. `session/__init__.py` imports it from here
    and registers it under the `model` producer's schema list, so exactly one Python
    type carries the wire name.
    """

    strategy: str
    kept_seq_start: int
    reason: str
    tokens_before: int
    tokens_after: int
    # v0.7 (§ S.4): None when no whole turn dropped; every record before v0.7 carries a range.
    dropped_seq_range: tuple[int, int] | None = None
    # v0.7: tool-output bodies at or below this seq, outside the newest kept whole, render as
    # placeholders. None: nothing cleared.
    cleared_through_seq: int | None = None
    # v0.7 (§ S.5): the factor the chars/4 estimate was multiplied by.
    token_scale: float = 1.0


def _cli_context_from_config(driver_name: str, config_path: Path | None = None) -> int:
    """Read `[driver.<driver_name>].context_tokens` from ~/.substrate/config.toml.

    Missing file or missing key falls back to `_CLI_CONTEXT_DEFAULT_TOKENS` (100 000);
    the fallback is documented as user-settable in the tech spec. `config_path` is
    injectable for tests.
    """
    from substrate.api import substrate_home

    path = config_path or (substrate_home() / "config.toml")
    if not path.exists():
        return _CLI_CONTEXT_DEFAULT_TOKENS
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return _CLI_CONTEXT_DEFAULT_TOKENS
    driver_table = data.get("driver", {})
    entry = driver_table.get(driver_name, {}) if isinstance(driver_table, dict) else {}
    if not isinstance(entry, dict):
        return _CLI_CONTEXT_DEFAULT_TOKENS
    value = entry.get("context_tokens")
    return value if isinstance(value, int) and value > 0 else _CLI_CONTEXT_DEFAULT_TOKENS


def resolve_driver_context_tokens(
    driver_name: str,
    responder: Responder,
    *,
    config_path: Path | None = None,
    now: float | None = None,
) -> int:
    """Return the driver's context window in tokens, by driver family.

    | Driver class                         | Source                                   |
    |--------------------------------------|------------------------------------------|
    | Adapter with `context_tokens()`      | live call, cached 60 s per (class, tag)  |
    | `DeterministicResponder`             | 4096 constant                            |
    | Any CLI-shaped adapter               | `[driver.<name>].context_tokens` in config, default 100 000 |

    The dispatch reads `hasattr(responder, "context_tokens")` — every custom
    `[[responder]]` in `~/.substrate/config.toml` that exposes the same method
    inherits the same path. On live-call failure, falls back to the config table
    with a `driver_name` key. `now` is injectable for tests.
    """
    responder_class = type(responder).__name__
    if responder_class == "DeterministicResponder":
        return _DETERMINISTIC_CONTEXT_TOKENS
    live_probe = getattr(responder, "context_tokens", None)
    if callable(live_probe):
        model_tag = getattr(responder, "_model", driver_name) or driver_name
        cache_key = (responder_class, model_tag)
        clock = now if now is not None else time.monotonic()
        cached = _context_cache.get(cache_key)
        if cached is not None:
            expires_at, value = cached
            if clock < expires_at:
                return value
        try:
            value = int(live_probe())
        except (ContextTokensUnknown, DriverIntrospectionUnavailable):
            return _cli_context_from_config(driver_name, config_path=config_path)
        _context_cache[cache_key] = (clock + _CONTEXT_CACHE_TTL_SECONDS, value)
        return value
    return _cli_context_from_config(driver_name, config_path=config_path)


def _est_tokens(text: str) -> int:
    return max(len(text) // _CHARS_PER_TOKEN, 1) if text else 0


def _group_by_turn(events: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group the envelope stream into turns.

    A turn opens on `UserMessage` and closes at the next `UserMessage` or at the
    stream's end. Events before the first `UserMessage` (RunStarted, SessionStarted,
    early lifecycle) do not belong to any turn and drop out here — the seed carries
    their content when the prompt renders. Every event kept in a turn is one of
    `_TURN_EVENT_KINDS`; lifecycle events (`substrate.*`) drop for prompt purposes.
    """
    turns: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] | None = None
    for env in events:
        kind = env.get("kind", "")
        if kind == _KIND_USER_MESSAGE:
            if current is not None:
                turns.append(current)
            current = [env]
            continue
        if current is None:
            continue
        if kind in TURN_EVENT_KINDS:
            current.append(env)
    if current is not None:
        turns.append(current)
    return turns


def session_changed_line(field: str, old: str, new: str) -> str:
    """The line a SessionChanged puts beside the message (§ P.4). The reminder line's own text
    is not repeated: the new one sits beside the message from the next step, and the record keeps
    both."""
    if field == "per_turn":
        return "Environment update: the reminder line beside each message changed."
    return f"Environment update: {field} changed from {old or '(none)'} to {new or '(none)'}."


def result_lines(kind: str, payload: Mapping[str, Any], tool: str, seq: int) -> tuple[str, str]:
    """A tool result's history line whole, and the placeholder that replaces it once cleared
    (§ S.3). `kind` is `ToolResult` or `HarnessToolResult`; `tool` is its call's tool."""
    ok = payload.get("ok", True)
    if kind == HARNESS_TOOL_RESULT:
        marker = "HARNESS RESULT"
        out = payload.get("output", "")
    else:
        marker = "RESULT"
        out = payload.get("output") if ok else payload.get("error", "")
    whole = f"{marker if ok else marker + '(fail)'}: {out}"
    placeholder = f"{marker} [cleared: {tool}, seq {seq}, {len(str(out))} chars]"
    return whole, placeholder


def output_savings(turn: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """For each tool result in `turn`, its seq and the estimated tokens clearing it saves."""
    tools: dict[str, str] = {}
    out: list[tuple[int, int]] = []
    for env in turn:
        kind = env.get("kind", "")
        payload = env.get("payload") or {}
        if not isinstance(payload, Mapping):
            continue
        if kind == HARNESS_TOOL_CALL:
            tools[str(payload.get("call_id", ""))] = str(payload.get("tool", "?"))
        elif kind in (_KIND_TOOL_RESULT, HARNESS_TOOL_RESULT):
            tool = (
                str(payload.get("tool", "?"))
                if kind == _KIND_TOOL_RESULT
                else tools.get(str(payload.get("call_id", "")), "?")
            )
            whole, placeholder = result_lines(kind, payload, tool, int(env.get("seq", 0)))
            out.append(
                (int(env.get("seq", 0)), max(_est_tokens(whole) - _est_tokens(placeholder), 0))
            )
    return out


def _render_turns(
    kept_turns: list[list[dict[str, Any]]],
    after_current_user: list[str] | None = None,
    cleared_through: int | None = None,
) -> list[str]:
    """The history lines for `kept_turns`: a range header, then each turn's events.
    `after_current_user` goes on the lines right after the last turn's `USER:` line: the
    session's reminder line and this step's environment updates (§ P.2, § P.4). A tool result at
    or below `cleared_through` renders as its placeholder (§ S.3)."""
    lines: list[str] = []
    harness_tools: dict[str, str] = {}
    if kept_turns:
        first = kept_turns[0][0].get("payload") or {}
        last = kept_turns[-1][0].get("payload") or {}
        first_idx = int(first.get("turn_index", 0)) if isinstance(first, Mapping) else 0
        last_idx = int(last.get("turn_index", 0)) if isinstance(last, Mapping) else 0
        lines.append(f"[transcript: turns {first_idx}..{last_idx}]")
    for turn_idx, turn in enumerate(kept_turns):
        last_reply: str | None = None  # the turn's last ModelReply text
        for env in turn:
            payload = env.get("payload") or {}
            kind = env.get("kind", "")
            if not isinstance(payload, Mapping):
                continue
            if kind == _KIND_USER_MESSAGE:
                text = str(payload.get("assembled_prompt") or payload.get("text", ""))
                lines.append(f"USER: {text}")
                if turn_idx == len(kept_turns) - 1 and after_current_user:
                    lines.extend(after_current_user)
            elif kind == SESSION_CHANGED:
                lines.append(
                    session_changed_line(
                        str(payload.get("field", "")),
                        str(payload.get("old", "")),
                        str(payload.get("new", "")),
                    )
                )
            elif kind == _KIND_MODEL_REPLY:
                # v0.3 writes a ModelReply for every call. One that requests a tool is rendered by
                # its ToolCall line; any prose the model wrote beside the call stays on the record
                # only, as the history rendered it before v0.3.
                if payload.get("stop_reason") == StopReason.TOOL_USE:
                    continue
                last_reply = str(payload.get("text", ""))
                if last_reply:
                    lines.append(f"MODEL: {last_reply}")
            elif kind == _KIND_TOOL_CALL:
                lines.append(f"TOOL {payload.get('tool', '?')}: args={payload.get('args', [])}")
            elif kind in (_KIND_TOOL_RESULT, HARNESS_TOOL_RESULT):
                seq = int(env.get("seq", 0))
                tool = (
                    str(payload.get("tool", "?"))
                    if kind == _KIND_TOOL_RESULT
                    else harness_tools.get(str(payload.get("call_id", "")), "?")
                )
                whole, placeholder = result_lines(kind, payload, tool, seq)
                cleared = cleared_through is not None and seq <= cleared_through
                lines.append(placeholder if cleared else whole)
            elif kind == HARNESS_TOOL_CALL:
                # § Q.4, § Q.6: what a harness driver did with its own tools, in record order.
                harness_tools[str(payload.get("call_id", ""))] = str(payload.get("tool", "?"))
                lines.append(
                    f"HARNESS TOOL {payload.get('tool', '?')}: args={payload.get('args', {})}"
                )
            elif kind == BACKGROUND_TASK_ENDED:
                # UI sprint 104: the model keeps hearing that a background task ended
                from . import BackgroundTaskEnded, background_notice

                try:
                    lines.append(background_notice(BackgroundTaskEnded(**payload)))
                except TypeError:
                    lines.append(f"[background task {payload.get('task_id', '?')} ended]")
            elif kind == _KIND_FINAL_ANSWER:
                # Records before v0.3 (vocabulary § K.3): a plain reply wrote a ModelReply and a
                # FinalAnswer with the same text; the driver read every answer twice (UI sprint
                # 116). A FinalAnswer with its own text (a bail-out) still renders.
                final = str(payload.get("text", ""))
                if final != last_reply:
                    lines.append(f"FINAL: {final}")
    return lines


def is_driver_turn(turn: list[dict[str, Any]]) -> bool:
    """Whether a turn is a driver pass-through (`//`, § P.11): the model never sees it."""
    payload = (turn[0].get("payload") or {}) if turn else {}
    return isinstance(payload, Mapping) and payload.get("slash_source") == DRIVER_SLASH_SOURCE


def turn_cost(turn: list[dict[str, Any]]) -> int:
    """One turn's estimated rendered size in tokens, as the history window prices it."""
    if is_driver_turn(turn):
        return 0
    return _est_tokens("\n".join(_render_turns([turn])))


def plan_window(
    costs: list[int], head_tokens: int, driver_context_tokens: int, driver_headroom_frac: float
) -> int:
    """Index of the oldest turn the prompt keeps: the newest turns whose estimated sizes fit the
    history budget (driver context x headroom, minus the head), oldest dropped first. Sized from
    each turn's rendered estimate, not a fixed 800 tokens a turn (lens F098). The current turn
    (the last) is always kept."""
    budget = int(driver_context_tokens * driver_headroom_frac) - head_tokens
    used = 0
    keep_from = len(costs)
    for i in range(len(costs) - 1, -1, -1):
        if keep_from < len(costs) and used + costs[i] > budget:
            break
        used += costs[i]
        keep_from = i
    return keep_from if costs else 0


class HistoryPlan(NamedTuple):
    """What the history window keeps (§ S): the index of the oldest kept turn, the clearing
    boundary, and the estimated tokens of head plus history before and after the cut."""

    keep_from: int
    cleared_through: int | None
    tokens_before: int
    tokens_after: int


def plan_history(
    turns: list[tuple[int, int, list[tuple[int, int]]]],
    head_tokens: int,
    driver_context_tokens: int,
    driver_headroom_frac: float,
    prev_cleared: int | None,
    scale: float = 1.0,
    keep_whole: int = KEEP_WHOLE_TOOL_OUTPUTS,
) -> HistoryPlan:
    """§ S.1, S.2: clear old tool outputs first, then drop whole turns.

    `turns` is each turn's `(from_seq, cost, savings)`, `savings` the `(seq, tokens)` that clearing
    each tool result saves. The current turn's newest `keep_whole` results clear last, and its latest
    result never does. The boundary starts at
    `prev_cleared` (the record's last cut) and moves forward only while the history passes the
    budget, until it fits within half the budget, so the prompt's start holds still between passes.
    Whole turns drop, oldest first, only once every clearable result is cleared. Pure: every input
    comes from the record."""
    budget = int(driver_context_tokens * driver_headroom_frac) - head_tokens
    # § S.7: a finished turn ended with the model's reply, so all its outputs can clear; the
    # current turn (the last) keeps its newest `keep_whole` whole. § S.8: under pressure that
    # protected set shrinks to the latest result alone before any whole turn drops.
    earlier = [s for _f, _c, savings in turns[:-1] for s in savings]
    current = sorted(turns[-1][2]) if turns else []

    def turn_costs(c: int | None) -> list[int]:
        return [
            cost - sum(t for seq, t in savings if c is not None and seq <= c)
            for _f, cost, savings in turns
        ]

    def total(c: int | None, keep_from: int = 0) -> int:
        return int(sum(turn_costs(c)[keep_from:]) * scale)

    cleared = prev_cleared
    for keep in range(max(keep_whole, 1), 0, -1):
        if total(cleared) <= budget:
            break
        clearable = sorted(earlier + current[: max(len(current) - keep, 0)])
        for seq, _t in clearable:
            if cleared is not None and seq <= cleared:
                continue
            cleared = seq
            if total(cleared) <= budget // 2:
                break
    keep_from = 0
    if total(cleared) > budget:
        scaled = [int(c * scale) for c in turn_costs(cleared)]
        keep_from = plan_window(scaled, head_tokens, driver_context_tokens, driver_headroom_frac)
    return HistoryPlan(
        keep_from=keep_from,
        cleared_through=cleared,
        tokens_before=head_tokens + total(None),
        tokens_after=head_tokens + total(cleared, keep_from),
    )


def measured_scale(reported_prompt_tokens: int, estimated_tokens: int) -> float:
    """§ S.5: reported over estimated prompt tokens, clamped to 1.0-4.0."""
    if reported_prompt_tokens <= 0 or estimated_tokens <= 0:
        return 1.0
    return min(max(reported_prompt_tokens / estimated_tokens, _SCALE_MIN), _SCALE_MAX)


def head_block(
    seed: str,
    fragments: list[tuple[int, dict[str, Any]]],
    system_sources: frozenset[str] | None = None,
) -> tuple[str, str, str, tuple[int, ...]]:
    """The prompt's system part, its head, the reminder line, and the seqs of the fragments used.

    Fragments whose source is in `SYSTEM_SOURCES` (session vocabulary § P.2) form the system
    part, by precedence. The head is the seed, then the other fragments by precedence (the
    interrupt fragment among them, at 95). The reminder line is the newest `per_turn`
    fragment's text; the composer places it after the current message. `system_sources`
    replaces `SYSTEM_SOURCES` for a session that opted into `cache_layout` (§ P.3)."""
    from .vocabulary import SYSTEM_SOURCES, PromptSource, parse_prompt_source

    system_parts: list[tuple[int, int, str]] = []  # (precedence, seq, text)
    parts: list[tuple[int, int, str]] = []
    used: list[int] = []
    per_turn: tuple[int, str] | None = None  # (seq, text) of the newest
    for seq, frag in fragments:
        text = str(frag.get("text", ""))
        if not text:
            continue
        source = parse_prompt_source(str(frag.get("source", "")))
        if source == PromptSource.USER_MESSAGE:
            continue  # records before K261; the message comes from the history
        if source == PromptSource.PER_TURN:
            # Records before K261 wrote one per turn; v0.4 writes one per session or change.
            if per_turn is None or seq > per_turn[0]:
                per_turn = (seq, text)
            continue
        on_system = system_sources if system_sources is not None else SYSTEM_SOURCES
        target = system_parts if source in on_system else parts
        target.append((int(frag.get("precedence", 0)), seq, text))
        used.append(seq)
    if per_turn is not None:
        used.append(per_turn[0])
    system_parts.sort(key=lambda p: (p[0], p[1]))
    parts.sort(key=lambda p: (p[0], p[1]))
    head = [seed.rstrip()] if seed else []
    head += [text for _p, _s, text in parts]
    system = "\n\n".join(text for _p, _s, text in system_parts)
    reminder = per_turn[1] if per_turn is not None else ""
    return system, "\n\n".join(head), reminder, tuple(sorted(used))


def compose_model_prompt(
    *,
    history: list[dict[str, Any]],
    seed: str,
    fragments: list[tuple[int, dict[str, Any]]],
    notices: list[str] | None = None,
    after_message: list[str] | None = None,
    system_sources: frozenset[str] | None = None,
    cleared_through: int | None = None,
) -> tuple[str, str, tuple[int, ...]]:
    """The system part and base prompt for one model call, and the seqs of the fragments used.

    `history` is the kept window's events (the trigger chose it with `plan_window`). Order: the
    head (`head_block`); the kept turns, the current one last, with the reminder line and
    `after_message` (this step's environment updates) right after its `USER:` line;
    background-task notices. The model
    step appends its pre-K261 endings (tool results, the tool list, the directives) and records the
    final text as `PromptComposed`.
    """
    system, head_text, reminder, used_seqs = head_block(seed, fragments, system_sources)
    beside = ([reminder] if reminder else []) + list(after_message or [])
    turns = [t for t in _group_by_turn(history) if not is_driver_turn(t)]
    blocks = [head_text] if head_text else []
    if turns:
        blocks.append("\n".join(_render_turns(turns, beside, cleared_through)))
    else:
        blocks += beside
    blocks += notices or []
    return system, "\n\n".join(blocks), used_seqs


# spec-audit: 2026-09-01

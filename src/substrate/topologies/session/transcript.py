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
from typing import Any

from msgspec import Struct

from ...adapters import (
    ContextTokensUnknown,
    DriverIntrospectionUnavailable,
    Responder,
)
from ..tool_loop.kinds import FINAL_ANSWER, TOOL_CALL, TOOL_RESULT
from .vocabulary import (
    BACKGROUND_TASK_ENDED,
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
_PER_TURN_PRECEDENCE = 10  # the per_turn band of session-vocabulary.md § I

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
    dropped_seq_range: tuple[int, int]
    kept_seq_start: int
    reason: str
    tokens_before: int
    tokens_after: int


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


def _render_turns(kept_turns: list[list[dict[str, Any]]]) -> list[str]:
    """The history lines for `kept_turns`: a range header, then each turn's events."""
    lines: list[str] = []
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
            elif kind == _KIND_TOOL_RESULT:
                ok = payload.get("ok", True)
                marker = "RESULT" if ok else "RESULT(fail)"
                out = payload.get("output") if ok else payload.get("error", "")
                lines.append(f"{marker}: {out}")
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


def turn_cost(turn: list[dict[str, Any]]) -> int:
    """One turn's estimated rendered size in tokens, as the history window prices it."""
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


def head_block(
    seed: str, per_turn: str, fragments: list[tuple[int, dict[str, Any]]]
) -> tuple[str, tuple[int, ...]]:
    """The prompt's head and the seqs of the fragments in it: the seed, then the session's prompt
    fragments and `per_turn` by precedence (the interrupt fragment among them, at 95)."""
    from .vocabulary import PromptSource

    parts: list[tuple[int, int, str]] = []  # (precedence, seq, text)
    used: list[int] = []
    for seq, frag in fragments:
        text = str(frag.get("text", ""))
        if not text:
            continue
        if frag.get("source") in (PromptSource.PER_TURN, PromptSource.USER_MESSAGE):
            continue  # records before K261; per_turn and the message come from their own fields
        parts.append((int(frag.get("precedence", 0)), seq, text))
        used.append(seq)
    if per_turn:
        parts.append((_PER_TURN_PRECEDENCE, -1, per_turn))
    parts.sort(key=lambda p: (p[0], p[1]))
    head = [seed.rstrip()] if seed else []
    head += [text for _p, _s, text in parts]
    return "\n\n".join(head), tuple(sorted(used))


def compose_model_prompt(
    *,
    history: list[dict[str, Any]],
    seed: str,
    per_turn: str,
    fragments: list[tuple[int, dict[str, Any]]],
    notices: list[str] | None = None,
) -> tuple[str, tuple[int, ...]]:
    """The base prompt for one model call and the seqs of the fragments it used.

    `history` is the kept window's events (the trigger chose it with `plan_window`). Order: the
    head (`head_block`); the kept turns, the current one last; background-task notices. The model
    step appends its pre-K261 endings (tool results, the tool list, the directives) and records the
    final text as `PromptComposed`.
    """
    head_text, used_seqs = head_block(seed, per_turn, fragments)
    turns = _group_by_turn(history)
    blocks = [head_text] if head_text else []
    if turns:
        blocks.append("\n".join(_render_turns(turns)))
    blocks += notices or []
    return "\n\n".join(blocks), used_seqs


# spec-audit: 2026-09-01

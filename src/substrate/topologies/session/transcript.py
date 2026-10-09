# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Session transcript renderer — rolling-window compaction (piece A, sprint 207).

The `model` Producer receives a rendered prompt each turn, not the raw event list.
`render_transcript` reads the persistent record, groups the envelope stream by turn,
keeps the most recent K turns, and returns a `RenderedTranscript`. When turns drop,
one `TranscriptCompacted` rides on `compaction_events`; the model Producer yields
those before its first `ToolCall`/`ModelReply` so the compaction is anchored to the
firing that drove it (the tech spec cadence).

Compaction strategy in v1 is rolling window only. `_compute_k` divides the budget
(driver context × headroom fraction, minus seed and per-turn tokens) by an
avg_turn_tokens heuristic (800). The design target reads "20 turns for a 200 K-window
model, 4 for an 8 K-window model" — that band is what 800 reproduces.

Token estimation is a coarse character-count heuristic (chars / 4). Every driver
family tokenises differently; the substrate cannot afford a per-driver tokenizer
dependency, so it errs on the conservative side and lets the driver's own limits
truncate any residual overshoot. Real spend telemetry (tokens actually charged)
flows through `ModelUsage` on `ModelReply` — that path is the audit, this one is
the budget prediction.
"""

from __future__ import annotations

import time
import tomllib
from pathlib import Path
from typing import Any

from msgspec import Struct

from ...adapters import (
    ContextTokensUnknown,
    DriverIntrospectionUnavailable,
    Responder,
)
from ...record.record import read_record
from ..tool_loop.kinds import FINAL_ANSWER, TOOL_CALL, TOOL_RESULT
from .vocabulary import (
    BACKGROUND_TASK_ENDED,
)
from .vocabulary import (
    MODEL_REPLY as _KIND_MODEL_REPLY,
)
from .vocabulary import (
    PARK as _KIND_PARK,
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
_AVG_TURN_TOKENS_DEFAULT = 800  # K-window heuristic (see module docstring)

# _KIND_USER_MESSAGE, _KIND_MODEL_REPLY, _KIND_PARK, _KIND_TRANSCRIPT_COMPACTED
# imported above from `.vocabulary` (single source of truth per REVIEW F5).
_KIND_TOOL_CALL = TOOL_CALL
_KIND_TOOL_RESULT = TOOL_RESULT
_KIND_FINAL_ANSWER = FINAL_ANSWER
# `TranscriptCompacted` rides a turn because the `model` producer yields it at the start
# of a firing (session/__init__.py::_model_factory). `SessionWarning` fires at session-open
# via the `session_warning` initial and never rides a turn, so it stays out of this set.
_TURN_EVENT_KINDS = frozenset(
    {
        _KIND_USER_MESSAGE,
        _KIND_MODEL_REPLY,
        _KIND_TOOL_CALL,
        _KIND_TOOL_RESULT,
        _KIND_FINAL_ANSWER,
        _KIND_PARK,
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


class RenderedTranscript(Struct, frozen=True):
    prompt_text: str
    threaded_from_turn: int
    turns_dropped: int
    tokens_estimated: int
    compaction_events: list[TranscriptCompacted]


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


def _compute_k(
    driver_context_tokens: int,
    seed_tokens: int,
    per_turn_tokens: int,
    driver_headroom_frac: float = 0.6,
    avg_turn_tokens: int = _AVG_TURN_TOKENS_DEFAULT,
) -> int:
    """Keep-K turns: floor(budget / avg_turn_tokens), at least 1 when budget > 0.

    Returns 0 iff the seed alone (plus per-turn) already exceeds the headroom
    budget — the caller then emits `SessionWarning{kind:"seed_alone_exceeds"}`
    at session open (piece 208).
    """
    budget = int(driver_context_tokens * driver_headroom_frac) - seed_tokens - per_turn_tokens
    if budget <= 0:
        return 0
    return max(1, budget // avg_turn_tokens)


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
        if kind in _TURN_EVENT_KINDS:
            current.append(env)
    if current is not None:
        turns.append(current)
    return turns


def _render(
    seed: str,
    per_turn: str,
    kept_turns: list[list[dict[str, Any]]],
    current: list[dict[str, Any]],
) -> str:
    """Compose the prompt string handed to the driver.

    Layout matches the tech spec: seed first, then a header line naming the
    kept turn range, then each kept turn rendered as `USER:` / `MODEL:` /
    `TOOL <name>:` / `RESULT:` / `FINAL:` blocks. The `current` turn always
    lands at the tail; per_turn precedes the current turn's user text (product
    spec the topology-layer contract). The last `UserMessage.assembled_prompt` is treated as authoritative
    for the current turn — the daemon assembles it before it lands.
    """
    del current  # positional discipline: the current turn is always kept_turns[-1]
    lines: list[str] = []
    if seed:
        lines.append(seed.rstrip())
    if kept_turns:
        first = kept_turns[0][0].get("payload") or {}
        last = kept_turns[-1][0].get("payload") or {}
        first_idx = int(first.get("turn_index", 0)) if isinstance(first, dict) else 0
        last_idx = int(last.get("turn_index", 0)) if isinstance(last, dict) else 0
        lines.append(f"[transcript: turns {first_idx}..{last_idx}]")
    for turn_idx, turn in enumerate(kept_turns):
        for env in turn:
            payload = env.get("payload") or {}
            kind = env.get("kind", "")
            if not isinstance(payload, dict):
                continue
            if kind == _KIND_USER_MESSAGE:
                # Sprint 067: per_turn no longer injects here. The fragment
                # path (per_turn_fragment producer, sprint 060) emits it as
                # PromptFragment(source=per_turn); the composer folds it
                # into PromptComposed which _model_factory prepends to the
                # transcript. `per_turn` remains a parameter for the
                # K-window budget calc (line 298-299) but is no longer
                # rendered into the prompt string.
                text = str(payload.get("assembled_prompt") or payload.get("text", ""))
                lines.append(f"USER: {text}")
            elif kind == _KIND_MODEL_REPLY:
                lines.append(f"MODEL: {payload.get('text', '')}")
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
                lines.append(f"FINAL: {payload.get('text', '')}")
    return "\n".join(lines)


def render_transcript(
    *,
    record_root: Path | str,
    seed: str,
    per_turn: str,
    driver_context_tokens: int,
    driver_headroom_frac: float = 0.6,
    strategy: str = "rolling_window",
    turn_index_now: int,
) -> RenderedTranscript:
    """Read the record, keep the most recent K turns, return a rendered prompt.

    v1 supports `strategy="rolling_window"` only. Any other value raises
    `ValueError` — the field is future-proofing for a per-turn-summariser or
    a semantic-clustering strategy the vocabulary would extend, but neither
    ships in v1 (TECH-SPEC §14 deferred list).

    `turn_index_now` is the turn about to fire; it names the current turn on
    `RenderedTranscript.threaded_from_turn` when the record has no prior
    UserMessage (session open before the first turn lands).
    """
    if strategy != "rolling_window":
        raise ValueError(
            f"render_transcript: strategy={strategy!r} unsupported in v1; "
            "only 'rolling_window' ships ."
        )
    events = list(
        read_record(record_root, resolve_blobs=True)
    )  # Sprint 095: the model reads payloads
    seed_tokens = _est_tokens(seed)
    per_turn_tokens = _est_tokens(per_turn)
    k = _compute_k(driver_context_tokens, seed_tokens, per_turn_tokens, driver_headroom_frac)
    turns = _group_by_turn(events)
    if not turns:
        prompt = _render(seed, per_turn, [], [])
        return RenderedTranscript(
            prompt_text=prompt,
            threaded_from_turn=turn_index_now,
            turns_dropped=0,
            tokens_estimated=_est_tokens(prompt),
            compaction_events=[],
        )
    if k <= 0:
        # Seed alone exceeds the budget. The renderer keeps only the most recent
        # turn so the driver still sees the current user message; sprint 208
        # emits SessionWarning{seed_alone_exceeds} at session open, upstream.
        kept_turns = turns[-1:]
    else:
        kept_turns = turns[-k:] if k < len(turns) else list(turns)
    dropped_turns = turns[: len(turns) - len(kept_turns)]
    prompt = _render(seed, per_turn, kept_turns, kept_turns[-1])
    tokens_estimated = _est_tokens(prompt)
    compaction_events: list[TranscriptCompacted] = []
    if dropped_turns:
        first_dropped = dropped_turns[0][0]
        last_dropped = dropped_turns[-1][-1]
        first_kept = kept_turns[0][0]
        reason = "driver_window_exceeded" if 0 < k < len(turns) else "K_bound"
        # `tokens_before` and `tokens_after` must live on the same axis so a reader can
        # subtract them and get a meaningful "tokens the window saved" number. Both now
        # measure the RENDERED prompt cost: `tokens_after` is what we actually send,
        # `tokens_before` is what we would have sent if we had rendered every turn.
        # One extra render on the compaction path is the honest cost for this comparability.
        full_prompt = _render(seed, per_turn, turns, turns[-1])
        compaction_events.append(
            TranscriptCompacted(
                strategy="rolling_window",
                dropped_seq_range=(int(first_dropped["seq"]), int(last_dropped["seq"])),
                kept_seq_start=int(first_kept["seq"]),
                reason=reason,
                tokens_before=_est_tokens(full_prompt),
                tokens_after=tokens_estimated,
            )
        )
    first_kept_payload = kept_turns[0][0].get("payload") or {}
    threaded_from_turn = (
        int(first_kept_payload.get("turn_index", turn_index_now))
        if isinstance(first_kept_payload, dict)
        else turn_index_now
    )
    return RenderedTranscript(
        prompt_text=prompt,
        threaded_from_turn=threaded_from_turn,
        turns_dropped=len(dropped_turns),
        tokens_estimated=tokens_estimated,
        compaction_events=compaction_events,
    )


# spec-audit: 2026-09-01

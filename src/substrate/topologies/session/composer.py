# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Prompt composer Producer — subscribes to `PromptFragment`, emits `PromptComposed`.

Sprint 059 primitive. Composer is a Producer, not a Python function on the hot
path. Each fragment-source Producer (sprints 060-064) yields typed
`PromptFragment` events at its own trigger anchor. This module's Producer reads
the current turn's fragment cohort from a `KindBuffer` View, orders by
`precedence`, joins the `text` fields with a blank line separator, and yields
one `PromptComposed` per firing. The record then carries fragment-level
provenance every turn: `PromptComposed.fragment_seqs` names every fragment that
composed the text; `record diff` shows fragment shifts by seq, not by string
diff.

The composer fires on `UserMessage` (once per turn). Sprint 064 adds
`compose-on-continue` and `compose-on-wrap-up` triggers on `ToolResult` when
the model producer migrates to read `PromptComposed.text` from its input.
Sprints 060-064 do not modify this file; each ships its own fragment-source
Producer module and registration in `session_topology`.

In sprint 059's landing state, no fragment source exists yet, so every
`PromptComposed` on the record carries `fragment_seqs=()` and `text=""`. That
is the honest cohort at this build stage; a reader can inspect the record and
see that the composer fired per turn with an empty fragment set. Sprints 060+
land fragments that the composer picks up without further code change here.

Token estimation is the same coarse chars/4 heuristic `transcript.py` uses;
per-driver tokenisation is out of scope. `total_tokens` on `PromptComposed` is
an estimate for downstream views (K-window budget in sprint 060's migration
choice, sprint-062 bundle-size warnings) — the driver's own usage telemetry
lands separately on `ModelReply.model_usage`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from . import PromptComposed
from .vocabulary import PROMPT_FRAGMENT

_CHARS_PER_TOKEN = 4  # matches transcript.py's estimator


def _est_tokens(text: str) -> int:
    return max(len(text) // _CHARS_PER_TOKEN, 1) if text else 0


def _compose_prompt(
    fragments: list[dict[str, Any]],
    fragment_seqs: list[int],
) -> PromptComposed:
    """Pure composition: order fragments by (precedence, seq), join with a
    blank-line separator, return the assembled `PromptComposed`.

    Stable ordering: fragments with equal `precedence` order by seq (kernel
    order-of-arrival), so a record is byte-reproducible across replays.

    Empty cohort yields `PromptComposed(text="", fragment_seqs=(), total_tokens=0)`
    — the honest empty case, not a skip. Downstream readers can distinguish
    "no fragments landed" from "composer never fired".
    """
    if not fragments:
        return PromptComposed(
            text="",
            fragment_seqs=(),
            total_tokens=0,
            strategy="precedence_join",
        )
    # Pair each fragment payload with its seq; sort by (precedence, seq).
    paired = list(zip(fragments, fragment_seqs, strict=True))
    paired.sort(key=lambda pair: (int(pair[0].get("precedence", 0)), pair[1]))
    ordered_texts = [str(pair[0].get("text", "")) for pair in paired]
    ordered_seqs = tuple(pair[1] for pair in paired)
    text = "\n\n".join(t for t in ordered_texts if t)
    return PromptComposed(
        text=text,
        fragment_seqs=ordered_seqs,
        total_tokens=_est_tokens(text),
        strategy="precedence_join",
    )


def composer_factory() -> Callable[[], Any]:
    """Return the composer Producer body factory. `session_topology` binds
    this under `producer_kind("prompt_composer", schemas=[PromptComposed], ...)`.
    The producer's input carries `fragments: list[dict]` (fragment payloads
    from the cohort View, populated by the trigger's `input_builder`) and
    `fragment_seqs: list[int]` (positional indices in v0.2; sprints 060+
    grow this to real seqs when the source-producer pipeline lands richer
    trigger context). Body calls the pure `_compose_prompt` and yields
    exactly one `PromptComposed`.
    """

    async def _composer(inp: Any) -> AsyncIterator[PromptComposed]:
        fragments: list[dict[str, Any]] = (
            list(inp.get("fragments", [])) if hasattr(inp, "get") else []
        )
        fragment_seqs: list[int] = list(inp.get("fragment_seqs", [])) if hasattr(inp, "get") else []
        if len(fragment_seqs) != len(fragments):
            # Fall back to positional indices when the input builder did not
            # supply a matching seq list. Sprint 059 landing state.
            fragment_seqs = list(range(len(fragments)))
        yield _compose_prompt(fragments, fragment_seqs)

    return lambda: _composer


__all__ = ["_compose_prompt", "composer_factory", "PROMPT_FRAGMENT"]

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""per_turn fragment source — sprint 060.

Fires on `UserMessage` (every turn). When `manifest.per_turn` is a non-empty
string, yields one `PromptFragment(source="per_turn", text=<value>,
precedence=10, provenance={})`. When empty, yields nothing — the composer's
empty-cohort handling from sprint 059 covers the no-fragment case cleanly.

Dual-path in this landing state: `render_transcript` still injects
`per_turn` into the current turn's prompt at `transcript.py:252-253`, and
still uses `per_turn_tokens` in the K-window budget at `transcript.py:298-
299`. Sprint 064 deletes the render-side injection and switches
`_model_factory` to read `PromptComposed.text` from the composer. Until
then, per_turn reaches the model through the existing render path AND the
record carries a `PromptFragment(source=per_turn)` for every turn where
per_turn is non-empty. Duplication is intentional through the migration.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from . import PromptFragment
from .vocabulary import PromptSource

_PRECEDENCE = 10  # reserved band from session-vocabulary.md § I


def per_turn_producer_factory(per_turn: str) -> Callable[[], Any]:
    """Return the fragment-source Producer body factory. The topology
    binds `manifest.per_turn` at build time; the closure captures that
    value so each firing sees the current session's per_turn.

    PATCH-through-session-life: `substrate-ui/server.py:_session_turn`
    rebuilds the session_topology per turn via
    `_build_session_topology_from_manifest`, so a mid-session PATCH of
    `per_turn` shows up on the very next turn — the closure over
    `per_turn` is per-topology-build, not per-session.
    """

    async def _per_turn(_inp: Any) -> AsyncIterator[PromptFragment]:
        if not per_turn:
            return
        yield PromptFragment(
            source=PromptSource.PER_TURN,
            text=per_turn,
            precedence=_PRECEDENCE,
            provenance={},
        )

    return lambda: _per_turn


__all__ = ["per_turn_producer_factory"]

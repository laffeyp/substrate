# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""user_message fragment source — sprint 064.

Fires on `substrate.ProducerCompleted{kind=per_turn_fragment}` — the
second link in the per-turn fragment chain (per_turn_fragment fires
first on UserMessage; user_message_fragment fires when per_turn
completes; composer fires when user_message completes). This gives
the composer a deterministic ordering guarantee: when the
`compose-on-cohort-complete` trigger fires, both per_turn and
user_message fragments are already in the cohort buffer.

Body reads the current UserMessage.text from the trigger input (the
input builder plumbs it from the `latest_user_message` View), yields
one `PromptFragment(source=user_message, text=<UserMessage.text>,
precedence=100, provenance={"turn_index": N})`.

Precedence 100 puts the user's actual ask last in the composed
prompt — after every session-open source (role, bundle, tools_suite,
parent_context) and after per_turn.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from . import PromptFragment
from .vocabulary import PromptSource

_PRECEDENCE = 100  # reserved band from session-vocabulary.md § I


def user_message_fragment_producer_factory() -> Callable[[], Any]:
    """Return the user_message fragment-source Producer body factory.

    Stateless factory — every session builds one. The producer body
    reads `text` and `turn_index` from its trigger input; the trigger's
    input builder populates both from views. Empty text yields nothing.
    """

    async def _user_message(inp: Any) -> AsyncIterator[PromptFragment]:
        text = str(inp.get("text", "")) if hasattr(inp, "get") else ""
        turn_index = int(inp.get("turn_index", 0)) if hasattr(inp, "get") else 0
        if not text:
            return
        yield PromptFragment(
            source=PromptSource.USER_MESSAGE,
            text=text,
            precedence=_PRECEDENCE,
            provenance={"turn_index": turn_index},
        )

    return lambda: _user_message


__all__ = ["user_message_fragment_producer_factory"]

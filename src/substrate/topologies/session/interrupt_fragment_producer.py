# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""interrupt fragment source — Phase 8 item 7.

Fires on an `InterruptRequested` envelope the daemon injects onto the
session's live record via `Runtime.inject_event` when the user presses
Shift+ESC (soft interrupt) during a tool. Yields one
`PromptFragment(source="interrupt", text=<directive>, precedence=95,
provenance={tier, source_of_interrupt})`.

Precedence 95 sits above every current fragment source (role=0,
per_turn=10, tools_suite=20, parent_context=30, bundle=50) so the
interrupt directive lands late in the composed prompt, close to the
model's action. Turn-scoped: the FragmentCohort clears the entry on the
next `PromptComposed`, so the interrupt fires exactly once and does not
bleed across subsequent turns.

The composer refires on `ToolResult` when the cohort holds a pending
interrupt (see `TRIGGER_ID_COMPOSE_ON_INTERRUPT_TOOL_RESULT` in the
session topology). `TRIGGER_ID_CONTINUE` refuses to fire on the same
condition, so exactly one of the two fires per ToolResult; the model
wakes on the fresh `PromptComposed` with both the tool result and the
interrupt directive in scope.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from . import PromptFragment
from .vocabulary import PromptSource


_PRECEDENCE = 95

_DIRECTIVE = (
    "[The user requested an interrupt. The previous tool's result is in your transcript. "
    "Do not start another tool this turn. Return a concise final answer summarising where "
    "the task stands, what has been verified, and what remains open.]"
)


def interrupt_fragment_producer_factory() -> Callable[[], Any]:
    """Return the interrupt fragment producer body factory. The trigger's
    `input_builder` reads the `InterruptRequested` payload and passes
    `tier` + `source` through as fragment provenance so a reader can
    trace which press produced the directive."""

    async def _interrupt(inp: Any) -> AsyncIterator[PromptFragment]:
        tier = str(inp.get("tier", "")) if hasattr(inp, "get") else ""
        source = str(inp.get("source", "")) if hasattr(inp, "get") else ""
        yield PromptFragment(
            source=PromptSource.INTERRUPT,
            text=_DIRECTIVE,
            precedence=_PRECEDENCE,
            provenance={"tier": tier, "source": source},
        )

    return lambda: _interrupt


__all__ = ["interrupt_fragment_producer_factory"]

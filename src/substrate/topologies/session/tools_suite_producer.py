# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""tools_suite fragment source — sprint 064.

Fires once at session open (`initial` binding). Yields one
`PromptFragment(source=tools_suite, text=<suite_describe(tools)>,
precedence=20, provenance={"tool_names": [...]})` when the session's
tool suite is non-empty, nothing when empty. Session-open scope: the
same tools ride every turn's composed prompt (tools cannot change
mid-session in v1).

The fragment text is the raw `suite_describe(tools)` output — the same
prose the model producer's described-tools fallback frames inline as
"Tools you MAY use:\\n<describe>". The two coexist by design: the
fragment is the record's snapshot of what tools this session offered;
the inline framing on the fallback path is the prompt structure the
model reads. On the native-tools path (OllamaResponder + achat_tools),
the tools JSON schema rides on the tool_calls channel and the prose
duplicate in the prompt is harmless — a framed prose header changes
the model's completion shape on llama3.2:1b and drops required tool
arguments, so the fragment stays as raw prose.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from ..tool_loop.tools import Tool, suite_describe
from . import PromptFragment
from .vocabulary import PromptSource

_PRECEDENCE = 20  # reserved band from session-vocabulary.md § I


def tools_suite_producer_factory(tools: dict[str, Tool]) -> Callable[[], Any]:
    """Return the tools_suite fragment-source Producer body factory.

    Closes over the `tools` dict from topology-build time. Empty tools
    yields no fragment (empty-body generator completes cleanly). Tool
    names are captured deterministically (sorted) so the fragment
    provenance is byte-stable across builds of the same session.
    """
    tool_names_frozen: tuple[str, ...] = tuple(sorted(tools.keys()))
    described = suite_describe(tools) if tools else ""

    async def _tools_suite(_inp: Any) -> AsyncIterator[PromptFragment]:
        if not tools:
            return
        yield PromptFragment(
            source=PromptSource.TOOLS_SUITE,
            text=described,
            precedence=_PRECEDENCE,
            provenance={"tool_names": list(tool_names_frozen)},
        )

    return lambda: _tools_suite


__all__ = ["tools_suite_producer_factory"]

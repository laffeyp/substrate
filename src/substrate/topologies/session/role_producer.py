# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""role fragment source — sprint 061.

Fires once at `substrate.RunStarted` (session-open scope). Resolves the
role prompt via the four-layer resolver at `roles.py::resolve_role_prompt_
with_source`; yields one `PromptFragment(source="role", text=<resolved>,
precedence=0, provenance={"role_name": role, "resolved_from": <path>})`.
Precedence 0 puts the role first in the composed prompt — identity before
methodology, methodology before per-turn instructions.

Wires a currently-dead concept end-to-end. Pre-sprint 061 `manifest.role`
was validated at POST /api/session and then dropped — the resolved prompt
had no consumer, and the five shipped prompts under
`topologies/session/prompts/` (reviewer.md, planner.md, tester.md,
explainer.md, default.md) were read at validation-time only. Sprint 061
puts each one on the record as a typed fragment for every session that
names it.

The composer's `FragmentCohort` View (session/views.py) owns the split.
Session-open sources (role, bundle_*, tools_suite, parent_context) land
in a per-source slot and appear in every turn's `PromptComposed`.
Turn-scoped sources (per_turn, user_message) live in a list the View
clears on every `PromptComposed` emission, so turn N cannot carry
turn N-1's user message. `_model_factory` reads `composed_prompt`
from PromptComposed on the resume-on-composed trigger.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from . import PromptFragment
from .roles import resolve_role_prompt_with_source
from .vocabulary import PromptSource

_PRECEDENCE = 0  # reserved band from session-vocabulary.md § I


def role_producer_factory(role: str, *, repo_root: Path | None = None) -> Callable[[], Any]:
    """Return the role fragment-source Producer body factory.

    The topology binds `manifest.role` and the daemon's `repo_root` at
    topology-build time. The producer fires once per session and yields a
    single `PromptFragment` when the resolver returns non-empty text.

    Resolution failure at RunStarted is a hard error — the resolver
    already validates at POST /api/session, so a resolution failure at
    RunStarted means the file was deleted or the layer was moved between
    session create and first turn. Producers that raise surface as
    `substrate.ProducerFailed`; the session's own `park-on-model-error`
    style handling belongs downstream if this pattern needs softening.
    """

    async def _role(_inp: Any) -> AsyncIterator[PromptFragment]:
        text, source_path = resolve_role_prompt_with_source(role, repo_root=repo_root)
        if not text:
            return
        yield PromptFragment(
            source=PromptSource.ROLE,
            text=text,
            precedence=_PRECEDENCE,
            provenance={"role_name": role, "resolved_from": str(source_path)},
        )

    return lambda: _role


__all__ = ["role_producer_factory"]

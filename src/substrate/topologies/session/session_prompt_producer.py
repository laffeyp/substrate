# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The `session_prompt` producer (K263): every session-open prompt source, in one step.

It runs once at session open and emits, in order:

1. `SessionWarning(kind=seed_alone_exceeds)` when the seed and `per_turn` alone pass the driver's
   headroom (sprint 208);
2. one or more `PromptFragment` per source the session names: `role` (precedence 0),
   `bundle_methodology` (50 and up, one per link of the bundle's `extends` chain, ancestor
   first), `bundle_personality` (3, the caller's or the nearest ancestor's), `parent_context`
   (30, a slice of the parent's record) and `tools_suite` (20, the tool list).

Before K263 each source was its own producer, so a failure stopped that source alone. Here each
source builds its fragments in full before any is yielded; a source that raises yields none, and
the producer records `SessionWarning(kind=fragment_source_failed, source_name=<source>,
detail=<the error>)` and goes on. The tool seam treats a tool's error the same way.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from ...bundles import Bundle, BundleNotFoundError, load_bundle, resolve_extends
from ..tool_loop.tools import Tool, suite_describe
from . import PromptFragment, SessionWarning
from .context_slice import extract_context_slice
from .roles import resolve_role_prompt_with_source
from .vocabulary import PromptSource, SessionWarningKind

# Precedence bands, session-vocabulary.md § I.
ROLE_PRECEDENCE = 0
PERSONALITY_PRECEDENCE = 3
TOOLS_SUITE_PRECEDENCE = 20
PARENT_CONTEXT_PRECEDENCE = 30
METHODOLOGY_PRECEDENCE_BASE = 50  # one per link of the extends chain: 50, 51, …
PARENT_CONTEXT_CAP_BYTES = 64 * 1024

Source = Callable[[], list[PromptFragment]]


def role_fragments(role: str, repo_root: Path | None) -> list[PromptFragment]:
    """The role prompt, from the four-layer resolver (`roles.py`). A resolver error means the
    role file went missing between session create, which validates it, and session open."""
    text, source_path = resolve_role_prompt_with_source(role, repo_root=repo_root)
    if not text:
        return []
    return [
        PromptFragment(
            source=PromptSource.ROLE,
            text=text,
            precedence=ROLE_PRECEDENCE,
            provenance={"role_name": role, "resolved_from": str(source_path)},
        )
    ]


def resolve_chain(bundle_name: str) -> list[Bundle]:
    """A bundle's `extends` chain, ancestor first. `resolve_extends` walks only
    `~/.substrate/bundles/`; a shipped bundle with no `extends` (the `session` default and the
    `<app>.bundle` defaults) is found by `load_bundle`'s package fallback instead. A missing
    ancestor further up still raises."""
    try:
        return resolve_extends(bundle_name)
    except BundleNotFoundError:
        return [load_bundle(bundle_name)]


def bundle_methodology_fragments(bundle: str) -> list[PromptFragment]:
    """One fragment per non-empty methodology in the chain, ancestor first."""
    chain = resolve_chain(bundle)
    out: list[PromptFragment] = []
    for position, entry in enumerate(chain):
        if not entry.methodology:
            continue
        out.append(
            PromptFragment(
                source=PromptSource.BUNDLE_METHODOLOGY,
                text=entry.methodology,
                precedence=METHODOLOGY_PRECEDENCE_BASE + len(out),
                provenance={"bundle_name": entry.name, "chain_position": position},
            )
        )
    return out


def bundle_personality_fragments(bundle: str) -> list[PromptFragment]:
    """The caller's personality, else the nearest ancestor's; none if every link is empty."""
    chain = resolve_chain(bundle)
    for position in range(len(chain) - 1, -1, -1):
        entry = chain[position]
        if entry.personality:
            return [
                PromptFragment(
                    source=PromptSource.BUNDLE_PERSONALITY,
                    text=entry.personality,
                    precedence=PERSONALITY_PRECEDENCE,
                    provenance={"bundle_name": entry.name, "chain_position": position},
                )
            ]
    return []


def parent_context_fragments(parent_context: dict[str, Any]) -> list[PromptFragment]:
    """A slice of the parent's record. Keys: `parent_record_root` (required),
    `parent_seq_range` ([lo, hi], default everything), `kinds` (default every kind) and
    `cap_bytes` (default 64 KiB)."""
    raw_root = parent_context.get("parent_record_root")
    if raw_root is None:
        return []
    record_root = Path(raw_root)
    seq_range_raw = parent_context.get("parent_seq_range")
    if isinstance(seq_range_raw, (list, tuple)) and len(seq_range_raw) == 2:
        seq_range: tuple[int, int] = (int(seq_range_raw[0]), int(seq_range_raw[1]))
    else:
        seq_range = (0, 2**31)
    kinds_raw = parent_context.get("kinds") or ()
    kinds: tuple[str, ...] = tuple(str(k) for k in kinds_raw)
    cap_bytes = int(parent_context.get("cap_bytes", PARENT_CONTEXT_CAP_BYTES))
    text, elided_count, elided_bytes, single_oversize = extract_context_slice(
        record_root, seq_range, kinds, cap_bytes=cap_bytes
    )
    if not text:
        return []
    return [
        PromptFragment(
            source=PromptSource.PARENT_CONTEXT,
            text=text,
            precedence=PARENT_CONTEXT_PRECEDENCE,
            provenance={
                "parent_record_root": str(record_root),
                "parent_seq_range": [seq_range[0], seq_range[1]],
                "kinds": list(kinds),
                "elided_count": elided_count,
                "elided_bytes": elided_bytes,
                "single_oversize": single_oversize,
            },
        )
    ]


def tools_suite_fragments(tools: dict[str, Tool]) -> list[PromptFragment]:
    """The raw `suite_describe` text, with the sorted tool names as provenance. The model step
    frames it for a text-only driver; a native driver gets the schemas on the tool channel."""
    if not tools:
        return []
    return [
        PromptFragment(
            source=PromptSource.TOOLS_SUITE,
            text=suite_describe(tools),
            precedence=TOOLS_SUITE_PRECEDENCE,
            provenance={"tool_names": sorted(tools)},
        )
    ]


def session_prompt_sources(
    *,
    role: str | None,
    role_repo_root: Path | None,
    bundle: str | None,
    parent_context: dict[str, Any] | None,
    tools: dict[str, Tool],
) -> dict[PromptSource, Source]:
    """The sources a session names, in the order the producer runs them."""
    sources: dict[PromptSource, Source] = {}
    if role is not None:
        sources[PromptSource.ROLE] = lambda: role_fragments(role, role_repo_root)
    if bundle is not None:
        sources[PromptSource.BUNDLE_METHODOLOGY] = lambda: bundle_methodology_fragments(bundle)
        sources[PromptSource.BUNDLE_PERSONALITY] = lambda: bundle_personality_fragments(bundle)
    if parent_context is not None:
        sources[PromptSource.PARENT_CONTEXT] = lambda: parent_context_fragments(parent_context)
    if tools:
        sources[PromptSource.TOOLS_SUITE] = lambda: tools_suite_fragments(tools)
    return sources


def session_prompt_producer_factory(
    *,
    session_id: str,
    sources: dict[PromptSource, Source],
    seed_warning: SessionWarning | None,
) -> Callable[[], Any]:
    """The producer body. `seed_warning` is built at topology build time, when the seed's size
    is known."""

    async def _session_prompt(_inp: Any) -> AsyncIterator[PromptFragment | SessionWarning]:
        if seed_warning is not None:
            yield seed_warning
        for name, source in sources.items():
            try:
                fragments = source()
            except Exception as exc:  # noqa: BLE001 — a failed source is recorded, not raised
                yield SessionWarning(
                    session_id=session_id,
                    kind=SessionWarningKind.FRAGMENT_SOURCE_FAILED,
                    seed_tokens=0,
                    driver_context_tokens=0,
                    source_name=str(name),
                    detail=repr(exc),
                )
                continue
            for fragment in fragments:
                yield fragment

    return lambda: _session_prompt


__all__ = [
    "Source",
    "bundle_methodology_fragments",
    "bundle_personality_fragments",
    "parent_context_fragments",
    "resolve_chain",
    "role_fragments",
    "session_prompt_producer_factory",
    "session_prompt_sources",
    "tools_suite_fragments",
]

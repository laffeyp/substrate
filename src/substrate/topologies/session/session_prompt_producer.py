# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The `session_prompt` producer (K263): every session-open prompt source, in one step.

It runs once at session open and emits, in order:

1. `SessionWarning(kind=seed_alone_exceeds)` when the seed and `per_turn` alone pass the driver's
   headroom (sprint 208);
2. one or more `PromptFragment` per source the session names: `role` (precedence 0),
   `bundle_style` (3) and `bundle_methodology` (5), each one fragment per non-empty link of the
   bundle's `extends` chain, ancestor first (session vocabulary § P.2), `parent_context` (30, a
   slice of the parent's record) and `tools_suite` (20, the tool list).

Before K263 each source was its own producer, so a failure stopped that source alone. Here each
source builds its fragments in full before any is yielded; a source that raises yields none, and
the producer records `SessionWarning(kind=fragment_source_failed, source_name=<source>,
detail=<the error>)` and goes on. The tool seam treats a tool's error the same way.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from ...bundles import Bundle, resolve_extends
from ..tool_loop.tools import Tool, suite_describe
from . import PromptFragment, SessionWarning
from .context_slice import extract_context_slice
from .environment import render_baseline
from .roles import resolve_role_prompt_with_source
from .vocabulary import (
    LENGTH_DEFAULT,
    LENGTH_TEXTS,
    TONE_DEFAULT,
    TONE_TEXTS,
    Control,
    LengthPosition,
    PromptSource,
    SessionWarningKind,
    TonePosition,
)

# Precedence bands, session-vocabulary.md § I.
ROLE_PRECEDENCE = 0
STYLE_PRECEDENCE = 3
CONTROL_PRECEDENCE = 3  # with the style, on the system channel; seq puts it after (§ T)
BASELINE_PRECEDENCE = 4
MEMORY_PRECEDENCE = 8
MEMORY_INDEX_MAX_LINES = 200  # Claude Code's limits for its MEMORY.md (K276)
MEMORY_INDEX_MAX_BYTES = 25 * 1024
PER_TURN_PRECEDENCE = 10  # recorded only; the composer places per_turn after the message
METHODOLOGY_PRECEDENCE = 5  # every link of the extends chain; seq keeps ancestors first
TOOLS_SUITE_PRECEDENCE = 20
PARENT_CONTEXT_PRECEDENCE = 30
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
    """A bundle's `extends` chain, ancestor first. User bundles shadow shipped ones; a chain
    reaches shipped ancestors (`harness`, `standard`) through `load_bundle`'s package fallback.
    A missing ancestor raises."""
    return resolve_extends(bundle_name)


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
                precedence=METHODOLOGY_PRECEDENCE,
                provenance={"bundle_name": entry.name, "chain_position": position},
            )
        )
    return out


def bundle_style_fragments(bundle: str) -> list[PromptFragment]:
    """One fragment per non-empty style in the chain, ancestor first (§ P.2). A child's style
    adds to what it inherits; before v0.4 the nearest one replaced the rest."""
    return [
        PromptFragment(
            source=PromptSource.BUNDLE_STYLE,
            text=entry.style,
            precedence=STYLE_PRECEDENCE,
            provenance={"bundle_name": entry.name, "chain_position": position},
        )
        for position, entry in enumerate(resolve_chain(bundle))
        if entry.style
    ]


def control_fragments(length: str, tone: str) -> list[PromptFragment]:
    """One fragment per control not at its default (§ T, K296), its provenance naming the control
    and the position. An unknown position raises, and session_prompt records the failure."""
    pairs = (
        (Control.LENGTH, LENGTH_TEXTS.get(LengthPosition(length))),
        (Control.TONE, TONE_TEXTS.get(TonePosition(tone))),
    )
    positions = {Control.LENGTH: length, Control.TONE: tone}
    return [
        PromptFragment(
            source=PromptSource.CONTROL,
            text=text,
            precedence=CONTROL_PRECEDENCE,
            provenance={"control": str(control), "position": positions[control]},
        )
        for control, text in pairs
        if text
    ]


def resolve_per_turn(per_turn: str, bundle: str | None) -> tuple[str, dict[str, Any]]:
    """The reminder line a session sends beside every message, and where it came from (§ P.2):
    the manifest's `per_turn` when set, else the bundle chain's `per_turn` slots joined ancestor
    first."""
    if per_turn:
        return per_turn, {"from": "manifest"}
    if bundle is None:
        return "", {}
    chain = [entry for entry in resolve_chain(bundle) if entry.per_turn]
    text = "\n\n".join(entry.per_turn for entry in chain)
    return text, {"from": "bundle", "bundles": [entry.name for entry in chain]}


def per_turn_fragments(per_turn: str, bundle: str | None) -> list[PromptFragment]:
    """One fragment holding the session's reminder line; none when there is none."""
    text, provenance = resolve_per_turn(per_turn, bundle)
    if not text:
        return []
    return [
        PromptFragment(
            source=PromptSource.PER_TURN,
            text=text,
            precedence=PER_TURN_PRECEDENCE,
            provenance=provenance,
        )
    ]


def memory_dirs(repo_root: Path | None) -> list[tuple[str, Path]]:
    """The memory directories a session reads (K276): the operator's, then the repo's."""
    from substrate.api import substrate_home

    dirs = [("operator", substrate_home() / "memory")]
    if repo_root is not None:
        dirs.append(("repo", repo_root / ".substrate" / "memory"))
    return dirs


def memory_fragments(repo_root: Path | None) -> list[PromptFragment]:
    """One fragment per memory index that exists, capped at 200 lines or 25 KB. The notes
    themselves are not loaded; the model reads one when its line bears on the task."""
    out: list[PromptFragment] = []
    for scope, directory in memory_dirs(repo_root):
        index = directory / "MEMORY.md"
        if not index.is_file():
            continue
        lines = index.read_text(encoding="utf-8", errors="replace").splitlines()
        kept: list[str] = []
        size = 0
        for line in lines[:MEMORY_INDEX_MAX_LINES]:
            size += len(line.encode("utf-8")) + 1
            if size > MEMORY_INDEX_MAX_BYTES:
                break
            kept.append(line)
        truncated = len(kept) < len(lines)
        # The words the guidance uses for the two folders (K287): the user's memory, the project's.
        label = "the user's memory" if scope == "operator" else "the project's memory"
        text = (
            f"Contents of {index} (the index of {label}; its notes sit beside it):\n\n"
            + "\n".join(kept)
        )
        out.append(
            PromptFragment(
                source=PromptSource.MEMORY,
                text=text,
                precedence=MEMORY_PRECEDENCE,
                provenance={"path": str(index), "lines": len(kept), "truncated": truncated},
            )
        )
    return out


def baseline_fragments(baseline: dict[str, Any]) -> list[PromptFragment]:
    """The environment the daemon computed at session open (§ P.2), as the model reads it. The
    dict itself is on `RunStarted.baseline` and `SessionStarted.baseline`; provenance names its
    keys."""
    if not baseline:
        return []
    return [
        PromptFragment(
            source=PromptSource.BASELINE,
            text=render_baseline(baseline),
            precedence=BASELINE_PRECEDENCE,
            provenance={"keys": sorted(baseline)},
        )
    ]


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
    baseline: dict[str, Any] | None = None,
    per_turn: str = "",
    memory: bool = False,
    length: str | None = None,
    tone: str | None = None,
) -> dict[PromptSource, Source]:
    """The sources a session names, in the order the producer runs them."""
    sources: dict[PromptSource, Source] = {}
    if per_turn or bundle is not None:
        sources[PromptSource.PER_TURN] = lambda: per_turn_fragments(per_turn, bundle)
    if role is not None:
        sources[PromptSource.ROLE] = lambda: role_fragments(role, role_repo_root)
    if bundle is not None:
        sources[PromptSource.BUNDLE_METHODOLOGY] = lambda: bundle_methodology_fragments(bundle)
        sources[PromptSource.BUNDLE_STYLE] = lambda: bundle_style_fragments(bundle)
    if length is not None or tone is not None:
        sources[PromptSource.CONTROL] = lambda: control_fragments(
            length or LENGTH_DEFAULT, tone or TONE_DEFAULT
        )
    if baseline:
        sources[PromptSource.BASELINE] = lambda: baseline_fragments(baseline)
    if memory:
        sources[PromptSource.MEMORY] = lambda: memory_fragments(role_repo_root)
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

    async def _session_prompt(inp: Any) -> AsyncIterator[PromptFragment | SessionWarning]:
        # A run after a SessionChanged (K274) writes only the changed sources, and marks each
        # fragment with the change's seq so the cohort keeps the newest generation.
        only = set(inp.get("only") or ()) if hasattr(inp, "get") else set()
        generation = inp.get("generation") if hasattr(inp, "get") else None
        if seed_warning is not None and not only:
            yield seed_warning
        for name, source in sources.items():
            if only and str(name) not in only:
                continue
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
            # A rewrite that leaves a source with no text writes one empty fragment, so the
            # cohort's newest generation of that source is empty and the old text stops (§ T.3).
            if only and not fragments:
                fragments = [
                    PromptFragment(
                        source=str(name), text="", precedence=0, provenance={"cleared": True}
                    )
                ]
            for fragment in fragments:
                if generation is not None:
                    fragment = PromptFragment(
                        source=fragment.source,
                        text=fragment.text,
                        precedence=fragment.precedence,
                        provenance={**fragment.provenance, "generation": int(generation)},
                    )
                yield fragment

    return lambda: _session_prompt


__all__ = [
    "Source",
    "bundle_methodology_fragments",
    "baseline_fragments",
    "memory_dirs",
    "memory_fragments",
    "per_turn_fragments",
    "resolve_per_turn",
    "bundle_style_fragments",
    "parent_context_fragments",
    "resolve_chain",
    "role_fragments",
    "session_prompt_producer_factory",
    "session_prompt_sources",
    "tools_suite_fragments",
]

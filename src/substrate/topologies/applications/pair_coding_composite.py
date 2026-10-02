# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""pair_coding session-composite — the tech spec.

Two related sessions open together: a builder session driven by
`builder_driver_model` and a standing reviewer sub-agent driven by
`reviewer_driver_model`. The reviewer's manifest carries
`composite_of=<builder_session_id>` so sprint 225b's cascade tears both
down when the parent ends or is removed.

Note the name collision with `topologies/pair_coding/__init__.py` — the
chunked-writer demo topology (renamed in BUNDLED to
`pair_coding_chunked` by sprint 224). The two shapes share only the
name; they compose from different primitives and serve different
purposes. The application catalog (this module) is what
`POST /api/topology/pair_coding/run` dispatches; BUNDLED is what
`substrate demo replay` walks.

This module deliberately does NOT open a DaemonClient — it reaches into
the SessionRegistry directly. The registry IS the composition seam
between the daemon and application code; a DaemonClient wrapper (piece
F sprint 226) exists for cross-process callers, not for co-resident
code paths like this one.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from substrate.session_registry import SessionManifest, SessionRegistry


_REVIEWER_TOOLS: tuple[str, ...] = ("read_file", "grep", "list_dir", "web_fetch")

_BUILDER_SEED_TEMPLATE = """\
You are the builder half of a pair-coding session. Your workspace is
{workspace}. A standing reviewer sub-agent is named {reviewer_name}.
After every logical unit of work — a new function, a fix, a refactor —
call the delegate tool:

    delegate(task="review the change I just made in <file>",
             child_session_name="{reviewer_name}")

Read the reviewer's answer before your next edit. Do not batch reviews.
"""

_REVIEWER_SEED_TEMPLATE = """\
You are the reviewer half of a pair-coding session for the builder
named {builder_name}. The builder will delegate review requests to you
between changes. You have read-only tools: read_file, grep, list_dir,
web_fetch. You do NOT have write_file, edit_file, or bash — this is
deliberate.

Answer plainly. Cite the file and line. When the change looks correct,
say so and stop.
"""


def pair_coding_application(
    *,
    session_registry: "SessionRegistry",
    builder_driver_model: str,
    reviewer_driver_model: str,
    workspace: str,
) -> tuple["SessionManifest", "SessionManifest"]:
    """Register the builder + reviewer pair. Returns both manifests.

    The reviewer's `composite_of` points at the builder's session_id so
    sprint 225b's cascade end/rm ties the lifecycle. Neither session
    fires a turn here — this call only registers manifests; the daemon
    returns both session_ids to the caller, who drives turns via
    `POST /api/session/<id>/turn`.
    """
    workspace_path = Path(workspace).expanduser().resolve()
    workspace_path.mkdir(parents=True, exist_ok=True)

    builder_id = f"s_pair_{uuid.uuid4().hex[:20]}"
    builder_name = f"pair-{uuid.uuid4().hex[:8]}"
    reviewer_name = f"{builder_name}-reviewer"

    reviewer_id = f"s_pair_rev_{uuid.uuid4().hex[:16]}"

    builder_seed = _BUILDER_SEED_TEMPLATE.format(
        workspace=workspace_path, reviewer_name=reviewer_name
    )
    reviewer_seed = _REVIEWER_SEED_TEMPLATE.format(builder_name=builder_name)

    builder_manifest = session_registry.create(
        session_id=builder_id,
        name=builder_name,
        driver=builder_driver_model,
        workspace=str(workspace_path),
        workspace_shape="flat",
        bundle=None,
        seed=builder_seed,
    )
    reviewer_manifest = session_registry.create(
        session_id=reviewer_id,
        name=reviewer_name,
        driver=reviewer_driver_model,
        workspace=str(workspace_path),
        workspace_shape="flat",
        bundle=None,
        seed=reviewer_seed,
        role="reviewer",
        tools=_REVIEWER_TOOLS,
        composite_of=builder_id,
    )
    return builder_manifest, reviewer_manifest


__all__ = ["pair_coding_application"]

# spec-audit: 2026-09-01

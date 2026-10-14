# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The application facade: what a daemon or a CLI built on substrate imports.

`substrate.api` is the kernel's public surface (runs, records, topologies, projections). The
standing-session registry, the local daemon's client, the session and tool-loop kind names and
the language catalog and drift detector the session's measurements use are applications built on
that kernel, and the conformance suite (the release gate) is a client
of it; they are exported here. Until 2026-10-08 `api` re-exported
them, so the kernel's facade depended on the applications above it (lens audit F042), and the
registry lived at the package root beside the kernel (F051).
"""

from __future__ import annotations

from . import _daemon as daemon_client
from .conformance.conformance import CheckResult, ConformanceReport, Status, run_conformance
from .language import catalog as language_catalog
from .language import drift as language_drift
from .interpreter import release_python_home
from .templates.interpolate import parse_template_header
from .templates.interpolate import render as render_template
from .topologies import bundled
from .topologies import workspace
from .topologies.runs import build
from .topologies.runs import hold as run_hold
from .topologies.runs import review
from .topologies.instruments.grader import score_grades
from .topologies.instruments.scoring import select_scoring_rule
from .topologies.session.handoff import handoff_calls
from .topologies.session.language_lines import language_lines, line_json
from .topologies.session.language_view import language_view
from .topologies.session.vocabulary import MODEL_REPLY
from .topologies.session_registry import (
    FreshSessionRequiresUserMessage,
    NameCollision,
    SessionEndedMidTurn,
    SessionManifest,
    SessionRegistry,
    SessionStatus,
    SessionTopologyFactory,
    TornRecordOnResume,
    manifest_from_dict,
    scan_record_status,
)
from .topologies.tool_loop.kinds import FINAL_ANSWER, TOOL_CALL, TOOL_RESULT

__all__ = [
    "CheckResult",
    "ConformanceReport",
    "Status",
    "run_conformance",
    "FINAL_ANSWER",
    "FreshSessionRequiresUserMessage",
    "MODEL_REPLY",
    "NameCollision",
    "SessionEndedMidTurn",
    "SessionManifest",
    "SessionRegistry",
    "SessionStatus",
    "SessionTopologyFactory",
    "TOOL_CALL",
    "TOOL_RESULT",
    "TornRecordOnResume",
    "build",
    "bundled",
    "daemon_client",
    "handoff_calls",
    "language_catalog",
    "language_drift",
    "language_lines",
    "language_view",
    "line_json",
    "manifest_from_dict",
    "parse_template_header",
    "release_python_home",
    "render_template",
    "review",
    "run_hold",
    "scan_record_status",
    "score_grades",
    "workspace",
    "select_scoring_rule",
]

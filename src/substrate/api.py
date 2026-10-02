# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The public API surface (F-API-1). Everything else is private; the CLI is required
to import only from here (F-API-6, enforced by import-linter in CI).

Public exception catch-surface (design §6.3): the exceptions an api-only consumer can
reasonably need to catch BY TYPE are re-exported here — the run/config errors
(SubstrateError + BusLockedError/RegistrationError/UnsupportedPlatformError/FsyncError),
the inspection errors (ProducerNotFound/SequenceOutOfRange), the input-sealing error
(InputTypeError), and the replay errors (ReplayError/RecordIncompleteError). DELIBERATELY
NOT re-exported (an explicit decision, not an oversight): the record-INTERNAL integrity
exceptions TornFrameError / CRCMismatchError / FrameTooLargeError, the cycle-internal
ReentrantAppendError, and the encoding-internal NonCanonicalValueError. These are not a
public catch surface — torn/crc faults are handled by recovery and surfaced as recovery
reports or RecordIncompleteError; a non-canonical emission becomes a recorded
ProducerEmittedInvalidEvent (never raised to the caller); FrameTooLargeError cannot reach a
caller (oversized payloads are blob-offloaded before framing); ReentrantAppendError is a
programming bug, not a condition to catch. All are reachable via the SubstrateError base if
truly needed."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from .constants import (
    INJECTION_APPLIED,
    INPUT_BUILD_FAILED,
    LIFECYCLE_KINDS,
    PREDICATE_QUARANTINED,
    PRODUCER_CANCELLED,
    PRODUCER_COMPLETED,
    PRODUCER_EMITTED_INVALID,
    PRODUCER_FAILED,
    PRODUCER_STARTED,
    RUN_FINALISED,
    RUN_STARTED,
    TERMINATION_MATCHED,
    TRIGGER_FIRED,
)
from .projections.attach import LiveRecord, attach
from .kernel.composition import EmbeddedRunFailed, embedded_substrate
from .conformance.conformance import CheckResult, ConformanceReport, Status, run_conformance
from .encoding import canonical_bytes, content_hash
from .errors import (
    BusLockedError,
    FsyncError,
    InputTypeError,
    ProducerNotFound,
    RecordGapError,
    RecordIncompleteError,
    SequenceOutOfRange,
    SubstrateError,
    UnsupportedPlatformError,
)
from .projections.inspect import (
    Divergence,
    Explanation,
    decisions_between,
    explain_producer,
    first_divergence,
    trace_ancestry,
    view_at,
)
from .projections.graph import (
    ProducerInstance,
    ProducerNode,
    RouteEdge,
    RunGraph,
    TopologyGraph,
    TriggerEdge,
    run_graph,
    topology_graph,
)
from .projections.narrate import NarrationLine, NarrationSummary, narrate, narration_summary
from .kernel.policies import (
    Decision,
    TerminationPolicy,
    all_completed,
    all_of,
    any_of,
    cancel_all_others,
    pause_await_input,
    quiescence_with_watchdog,
    threshold_count,
)
from .protocols import Producer, ProducerFactory, Responder, TriggerContext, View
from .record.record import (
    Always,
    Interval,
    NoFsync,
    read_first_envelope,
    read_record,
    recover_open_segment,
    resolve_blob_payload,
)
from .projections.replay import HashMismatch, ReplayError, ReplayResult, assert_replayable, replay
from .bundles import list_bundles, load_bundle
from .kernel.runtime import Runtime, RunResult, find_active_runtime
from .record.sidecar import read_sidecar
from .testing import assert_event, assert_no_event, assert_sequence
from .kernel.topology import (
    Budget,
    Cap,
    RegistrationError,
    TopologyBuilder,
    get_topology,
    register_topology,
)
from .kernel.triggers import Logical, Once, PerEvent, PerKey, WallClock, WhileTrue
from .types import BlobRef, Event, ProducerRef, Subscription
from .kernel.views import BufferView, KindBuffer, KindCount, PerKindLatest, StartedCompletedCounts

if TYPE_CHECKING:
    from .session_registry import (
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

__all__ = [
    # lifecycle kind constants (the locked vocabulary)
    "LIFECYCLE_KINDS",
    "RUN_STARTED",
    "TRIGGER_FIRED",
    "INPUT_BUILD_FAILED",
    "PRODUCER_STARTED",
    "PRODUCER_EMITTED_INVALID",
    "PRODUCER_COMPLETED",
    "PRODUCER_FAILED",
    "PRODUCER_CANCELLED",
    "INJECTION_APPLIED",
    "PREDICATE_QUARANTINED",
    "TERMINATION_MATCHED",
    "RUN_FINALISED",
    # data
    "Event",
    "BlobRef",
    "ProducerRef",
    "Subscription",
    # primitives / protocols
    "Producer",
    "ProducerFactory",
    "Responder",
    "View",
    "TriggerContext",
    "BufferView",
    "KindBuffer",
    "KindCount",
    "PerKindLatest",
    "StartedCompletedCounts",
    "Once",
    "PerEvent",
    "PerKey",
    "WhileTrue",
    "Logical",
    "WallClock",
    "TerminationPolicy",
    "Decision",
    "threshold_count",
    "all_completed",
    "quiescence_with_watchdog",
    "pause_await_input",
    "cancel_all_others",
    "any_of",
    "all_of",
    # topology + execution
    "TopologyBuilder",
    "register_topology",
    "get_topology",
    "Budget",
    "Cap",
    "Runtime",
    "RunResult",
    # records
    "read_record",
    "read_first_envelope",
    "resolve_blob_payload",
    "list_bundles",
    "load_bundle",
    "find_active_runtime",
    "recover_open_segment",
    "Interval",
    "Always",
    "NoFsync",
    "canonical_bytes",
    "content_hash",
    # live attach (technical §13, F-PERS-4)
    "attach",
    "LiveRecord",
    # off-bus sidecars (technical §3.8, §6.4)
    "read_sidecar",
    # composition — substrate as a Producer (technical §20, F-COMP)
    "embedded_substrate",
    "EmbeddedRunFailed",
    # conformance suite — the v1.0 release gate (product §7)
    "run_conformance",
    "ConformanceReport",
    "CheckResult",
    "Status",
    # the public exception hierarchy (design §6.3) — so an api-only consumer (the CLI is
    # the standing proof) handles errors BY TYPE, not by string-matching class names.
    "SubstrateError",
    "BusLockedError",
    "RegistrationError",
    "UnsupportedPlatformError",
    "FsyncError",
    "ProducerNotFound",
    "SequenceOutOfRange",
    "InputTypeError",
    "ReplayError",
    "RecordIncompleteError",
    "RecordGapError",
    # replay (technical §12)
    "replay",
    "assert_replayable",
    "ReplayResult",
    "HashMismatch",
    # inspection / provenance / divergence (technical §14)
    "explain_producer",
    "trace_ancestry",
    "view_at",
    "decisions_between",
    "first_divergence",
    "Explanation",
    "Divergence",
    # narration — the legible prose projection (Wave 14)
    "narrate",
    "narration_summary",
    "NarrationLine",
    "NarrationSummary",
    # graph projections — the structure + run-as-graph the UI renders (Wave 12 prep)
    "topology_graph",
    "run_graph",
    "TopologyGraph",
    "ProducerNode",
    "TriggerEdge",
    "RouteEdge",
    "RunGraph",
    "ProducerInstance",
    # test helpers
    "assert_event",
    "assert_no_event",
    "assert_sequence",
    # configuration — the per-user state root (config-externalization, sprint 246)
    "substrate_home",
    # standing sessions — the name index + manifest catalog the daemon serves (UI sprint 099:
    # one registry, here; substrate-ui's private copy had drifted from it)
    "FreshSessionRequiresUserMessage",
    "NameCollision",
    "SessionEndedMidTurn",
    "SessionManifest",
    "SessionRegistry",
    "SessionStatus",
    "SessionTopologyFactory",
    "TornRecordOnResume",
    "manifest_from_dict",
    "scan_record_status",
]


def substrate_home() -> Path:
    """The root of substrate's per-user state tree.

    Returns ``Path(os.environ["SUBSTRATE_HOME"])`` when set,
    else ``Path.home() / ".substrate"``.
    """
    raw = os.environ.get("SUBSTRATE_HOME")
    if raw:
        return Path(raw)
    return Path.home() / ".substrate"


# The session-registry names resolve on first access (PEP 562). session_registry imports this
# module, so an eager import here would cycle whichever of the two loaded first.
_SESSION_REGISTRY_NAMES = frozenset(
    {
        "FreshSessionRequiresUserMessage",
        "NameCollision",
        "SessionEndedMidTurn",
        "SessionManifest",
        "SessionRegistry",
        "SessionStatus",
        "SessionTopologyFactory",
        "TornRecordOnResume",
        "manifest_from_dict",
        "scan_record_status",
    }
)


def __getattr__(name: str) -> object:
    if name in _SESSION_REGISTRY_NAMES:
        from . import session_registry

        return getattr(session_registry, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

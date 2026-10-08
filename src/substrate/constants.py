# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Named constants and the reserved lifecycle vocabulary.

Defaults are the technical spec §19 table; all are configurable at `Runtime(...)`
construction. The reserved-namespace rule and the twelve lifecycle kinds are from
kernel v15 / product F-LIFE-1 / the locked vocabulary process/signals/0.2.json (additive
successor to process/signals/0.1.json; see process/signals/0.2-rationale.md).
"""

from __future__ import annotations

from enum import StrEnum

# ── technical spec §19 (normative defaults; all configurable) ──────────────────
SEGMENT_MAX_BYTES = 64 * 1024 * 1024  # 64 MiB — seal cadence vs file-count noise
FRAME_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB — larger payloads belong in the blob store
BLOB_THRESHOLD_BYTES = 16 * 1024  # 16 KiB — frame size vs blob-store churn
ADMISSION_BOUND = 1024  # events — backpressure latency vs burst absorption
FSYNC_INTERVAL_MS = 100  # loss window vs throughput (default policy)
BUDGET_US = 100  # per-Predicate-call budget (N-PERF-2)
HYSTERESIS_K = 3  # consecutive violations before quarantine (§9)
POLL_INTERVAL_MS = 100  # live-attach follower latency (§13)
SIDECAR_FLUSH_MS = 500  # diagnostic sidecar flush cadence (§9)
WRITER_STATS_INTERVAL_MS = 1000  # writer-observability cadence (§6.4)

# ── canonical-encoding bounds (technical spec §4.2) ────────────────────────────
# JCS numbers are IEEE-754 doubles; integers outside this range lose precision and
# MUST be schema-typed as strings instead.
JSON_SAFE_INT_MAX = 2**53 - 1
JSON_SAFE_INT_MIN = -(2**53 - 1)

# ── the active locked vocabulary version (process/signals/0.2.json) ───────────────────
# Distinct from a per-kind wire schema `<kind>@N`: this is the SIGNAL VOCABULARY version.
# v0.2 ratified the TriggerFired instance/factory fields + the $blob->input_blob rename
# (process/signals/0.2-rationale.md). Recorded in RunStarted.config.vocab_version so a record
# self-describes the vocabulary it was written against, for replay/inspection.
VOCAB_VERSION = "0.3"

# ── reserved namespace + the twelve lifecycle kinds (kernel v15 lifecycle table) ──
RESERVED_PREFIX = "substrate."

RUN_STARTED = "substrate.RunStarted"
TRIGGER_FIRED = "substrate.TriggerFired"
INPUT_BUILD_FAILED = "substrate.InputBuildFailed"
PRODUCER_STARTED = "substrate.ProducerStarted"
PRODUCER_EMITTED_INVALID = "substrate.ProducerEmittedInvalidEvent"
PRODUCER_COMPLETED = "substrate.ProducerCompleted"
PRODUCER_FAILED = "substrate.ProducerFailed"
PRODUCER_CANCELLED = "substrate.ProducerCancelled"
INJECTION_APPLIED = "substrate.InjectionApplied"
PREDICATE_QUARANTINED = "substrate.PredicateQuarantined"
TERMINATION_MATCHED = "substrate.TerminationMatched"
RUN_FINALISED = "substrate.RunFinalised"

LIFECYCLE_KINDS: tuple[str, ...] = (
    RUN_STARTED,
    TRIGGER_FIRED,
    INPUT_BUILD_FAILED,
    PRODUCER_STARTED,
    PRODUCER_EMITTED_INVALID,
    PRODUCER_COMPLETED,
    PRODUCER_FAILED,
    PRODUCER_CANCELLED,
    INJECTION_APPLIED,
    PREDICATE_QUARANTINED,
    TERMINATION_MATCHED,
    RUN_FINALISED,
)


def is_reserved(kind: str) -> bool:
    """True if `kind` is in the reserved kernel namespace (F-OBS-5). Producer-declared
    kinds MUST NOT use this prefix; registration rejects collisions."""
    return kind.startswith(RESERVED_PREFIX)


class RunStatus(StrEnum):
    """A run's outcome, as `run_graph` reads it from the record and as `Runtime.run()` returns it
    (`RunResult.status`, which is never INCOMPLETE). INCOMPLETE is no terminal RunFinalised: the
    record is still being written, or torn. UI sprint 107: bare strings before, compared in eight
    places in the console and typed as a Literal in the runtime."""

    INCOMPLETE = "incomplete"
    PAUSED = "paused"
    FINALISED = "finalised"
    FAILED = "failed"

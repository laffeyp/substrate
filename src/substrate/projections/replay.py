# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The replay engine — honest tiers of reconstruction from a record (technical §12).

Levels (the honesty ladder — a record admits exactly the tiers its content supports):

- **Level 1 — state reconstruction.** Read frames in seq order, count kinds, expose the
  event stream. Any View's state at any seq is reconstructable (see inspect.view_at);
  this level establishes the stream + counts the higher levels build on.
- **Level 2 — decision reconstruction.** Level 1 plus verification of the recorded
  runtime decisions: every substrate.TriggerFired carried its resolved input AND an
  input_sha256, and Level 2 RE-COMPUTES the canonical hash of the recorded resolved
  input and checks it matches input_sha256 (D-5). No re-execution — the decisions were
  recorded when they happened; replay reads and verifies them.
- **Level 3(a) — native re-execution (precondition check only here).** Re-run the
  topology with real Producers. Preconditioned, verified from RunStarted: every Producer
  kind author-flagged deterministic AND replay_ceiling == "3a". The runtime checks and
  REFUSES rather than producing a divergence. This module performs the precondition check
  (the gate); actually re-running the topology is the Runtime's job, driven by the CLI.
- **Level 3(b) — substitution re-execution.** DEFERRED (see BLACKBOARD ## Deferred): it
  needs a t-replay decision (deterministic clock substitution) not yet specified. Not
  faked here — replay(level="3b") raises NotImplementedError with the reason.

Inputs accept a record root path (so the blob store and manifest are reachable) or an
iterable of envelope dicts (Level 1/2 only — no blob resolution, no manifest).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from msgspec import Struct

from ..constants import RUN_FINALISED, RUN_STARTED, TRIGGER_FIRED
from ..encoding import content_hash, sha256_hex
from ..errors import CRCMismatchError, RecordIncompleteError, SubstrateError
from ..record.blobstore import BlobStore
from ..record.record import load_envelopes
from ..types import BlobRef

ReplayLevel = Literal["1", "2", "3a", "3b"]

_TRIGGER_FIRED = TRIGGER_FIRED
_RUN_STARTED = RUN_STARTED
_RUN_FINALISED = RUN_FINALISED


class ReplayError(SubstrateError):
    """A replay precondition failed or the requested level is unsupported for this
    record (technical §12). Carries a typed reason; the run record path is the evidence."""


class HashMismatch(Struct, frozen=True):
    """A Level-2 verification failure: a TriggerFired's recorded input hash does not match
    the recomputed canonical hash of its recorded resolved input (D-5 broken)."""

    seq: int
    trigger_id: str | None
    recorded: str
    recomputed: str


class ReplayResult(Struct, frozen=True):
    """The typed outcome of a replay (technical §12). `level` is the tier actually run.
    `counts` is the per-kind frame count (Level 1+). `decisions_verified` is the number of
    TriggerFired input hashes checked (Level 2). `mismatches` is empty on success.
    `preconditions_ok` / `refusal_reason` carry the Level-3(a) gate result."""

    level: str
    frame_count: int
    counts: dict[str, int]
    complete: bool
    decisions_verified: int = 0
    mismatches: tuple[HashMismatch, ...] = ()
    preconditions_ok: bool | None = None
    refusal_reason: str | None = None


def _load(record: Any) -> tuple[list[dict[str, Any]], Path | None]:
    """The envelopes, raw (the hashes compare recorded builtins), and the root when there is one."""
    root = Path(record) if isinstance(record, (str, Path)) else None
    return load_envelopes(record), root


def _level1(envelopes: list[dict[str, Any]]) -> tuple[dict[str, int], bool]:
    counts: dict[str, int] = {}
    complete = False
    for env in envelopes:
        kind = str(env.get("kind", ""))
        counts[kind] = counts.get(kind, 0) + 1
        if kind == _RUN_FINALISED:
            complete = True
    return counts, complete


# Sentinel: the input hash could not be recomputed but this is NOT a verification failure
# (a blob can't be resolved from a bare envelope iterable — no record root / no store).
_UNRESOLVABLE = "<unresolvable>"


def _resolved_input_hash(payload: dict[str, Any], root: Path | None) -> str | None:
    """The canonical hash of a TriggerFired's recorded resolved input. Inline →
    content_hash over the recorded builtins. input_blob → the blob's stored bytes are
    content, so sha256 over them (the blob id IS that hash); requires the record root.
    Returns _UNRESOLVABLE when a blob can't be read from a bare iterable (skip, not a
    failure); returns None when NEITHER input field is present (a D-5-malformed firing →
    the caller records a mismatch, not a silent skip)."""
    if "input_blob" in payload:
        blob = payload["input_blob"]
        if root is None:
            return _UNRESOLVABLE  # can't resolve a blob from a bare envelope iterable
        # Read through the BlobStore, the one blob reader: it refuses a non-hex digest before it
        # becomes a path (review #20), does not follow symlinks, and verifies the content hash
        # (lens audit F031: this rebuilt the blob path by hand and read the file directly).
        try:
            data = BlobStore(root).get(
                BlobRef(sha256=str(blob.get("$blob", "")), bytes=int(blob.get("bytes", 0)))
            )
        except (ValueError, OSError, CRCMismatchError):
            return _UNRESOLVABLE
        return sha256_hex(data)
    if "resolved_input" in payload:
        return content_hash(payload["resolved_input"])
    return None  # D-5 violated: exactly one of resolved_input | input_blob MUST be present


def _level2(
    envelopes: list[dict[str, Any]], root: Path | None
) -> tuple[int, tuple[HashMismatch, ...]]:
    """Verify each TriggerFired's input_sha256 against the recomputed canonical hash of
    its recorded resolved input (D-5). Returns (count verified, mismatches). A firing
    carrying input_sha256 but NEITHER input field is malformed (D-5) and is flagged as a
    mismatch; a blob unresolvable from a bare iterable is skipped (not counted, not a
    failure)."""
    verified = 0
    mismatches: list[HashMismatch] = []
    for env in envelopes:
        if env.get("kind") != _TRIGGER_FIRED:
            continue
        payload = env.get("payload") or {}
        recorded = payload.get("input_sha256")
        if not isinstance(recorded, str):
            continue
        recomputed = _resolved_input_hash(payload, root)
        if recomputed == _UNRESOLVABLE:
            continue  # honest skip: a blob we cannot read from a bare iterable
        verified += 1
        if recomputed is None or recomputed != recorded:
            mismatches.append(
                HashMismatch(
                    seq=int(env.get("seq", -1)),
                    trigger_id=payload.get("trigger_id"),
                    recorded=recorded,
                    recomputed=recomputed if recomputed is not None else "<no-input-field>",
                )
            )
    return verified, tuple(mismatches)


def _replay_ceiling(envelopes: list[dict[str, Any]], root: Path | None) -> str | None:
    """The record's replay_ceiling: from RunStarted.config (authoritative for the run) or
    the manifest. None if neither carries it."""
    for env in envelopes:
        if env.get("kind") == _RUN_STARTED:
            config = (env.get("payload") or {}).get("config") or {}
            ceiling = config.get("replay_ceiling")
            if isinstance(ceiling, str):
                return ceiling
    if root is not None:
        manifest_path = root / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                ceiling = manifest.get("replay_ceiling")
                if isinstance(ceiling, str):
                    return ceiling
            except (OSError, ValueError):
                pass
    return None


def _producer_kinds_deterministic(envelopes: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """From RunStarted.topology.producer_kinds: are ALL kinds author-flagged deterministic?
    Returns (all_deterministic, list of non-deterministic kind names). The manifest records
    a `deterministic` flag per kind when the topology declared it; absence is treated as
    NOT deterministic (honest refusal — F-RPLY-1)."""
    for env in envelopes:
        if env.get("kind") == _RUN_STARTED:
            topo = (env.get("payload") or {}).get("topology") or {}
            kinds = topo.get("producer_kinds") or []
            non_det = [str(pk.get("kind")) for pk in kinds if not pk.get("deterministic", False)]
            return (len(non_det) == 0 and len(kinds) > 0), non_det
    return False, []


def replay(record: Any, level: ReplayLevel = "1") -> ReplayResult:
    """Replay a record at the given honesty tier (technical §12).

    Level 1: stream + counts. Level 2: + verify every TriggerFired input hash (D-5).
    Level 3a: + the native-re-execution PRECONDITION gate (all kinds deterministic AND
    replay_ceiling=="3a"); this returns the gate result (preconditions_ok / refusal_reason)
    rather than re-running — re-execution is the Runtime's job. Level 3b: DEFERRED, raises
    NotImplementedError (needs a t-replay decision; not faked).

    SIZE NOTE: this MATERIALIZES the whole record into memory (unlike `read_record`, which
    streams). Fine for normal records (a few-thousand-frame record replays in tens of ms); for a
    very large (multi-GB) record, stream over `read_record` / `LiveRecord.follow` instead, or
    treat the record size as bounded for the analysis tools."""
    envelopes, root = _load(record)
    counts, complete = _level1(envelopes)
    frame_count = len(envelopes)

    if level == "1":
        return ReplayResult(level="1", frame_count=frame_count, counts=counts, complete=complete)

    if level == "2":
        verified, mismatches = _level2(envelopes, root)
        return ReplayResult(
            level="2",
            frame_count=frame_count,
            counts=counts,
            complete=complete,
            decisions_verified=verified,
            mismatches=mismatches,
        )

    if level == "3a":
        # Level 2 still runs (3a builds on verified decisions), then the precondition gate.
        verified, mismatches = _level2(envelopes, root)
        ceiling = _replay_ceiling(envelopes, root)
        all_det, non_det = _producer_kinds_deterministic(envelopes)
        ok = True
        reason: str | None = None
        if ceiling != "3a":
            ok = False
            reason = f"replay_ceiling is {ceiling!r}, not '3a' (a wall-clock cooldown demoted it)"
        elif not all_det:
            ok = False
            reason = f"non-deterministic Producer kinds present: {non_det}"
        elif mismatches:
            ok = False
            reason = f"{len(mismatches)} Level-2 input-hash mismatch(es); 3a refuses"
        return ReplayResult(
            level="3a",
            frame_count=frame_count,
            counts=counts,
            complete=complete,
            decisions_verified=verified,
            mismatches=mismatches,
            preconditions_ok=ok,
            refusal_reason=reason,
        )

    if level == "3b":
        # DEFERRED (spec-amended) — not faked. Level 3(b) substitution re-execution replays
        # the kernel with log-backed deterministic emitters in recorded admission order to a
        # BYTE-IDENTICAL log; byte-identity includes the envelope `t`, so it needs a t-replay
        # (replay-mode writer that replays recorded `t` instead of re-sampling the clock) —
        # a mechanism the specs leave open. Deferred to a later wave by product amendment
        # A1.1 (docs/specs/product_spec/draft7_amendment_A1_replay_3b.md): F-RPLY-1 3(b) relaxed to
        # SHOULD for the v1.0 milestone, conformance check 6 marked "deferred (spec-amended)"
        # (NOT silently failing). Levels 1/2/3a are complete. See BLACKBOARD ## Deferred.
        raise NotImplementedError(
            "replay Level 3(b) (byte-identical substitution re-execution) is deferred "
            "(spec-amended: product DRAFT 7 amendment A1.1) pending a t-replay/replay-mode-"
            "writer decision. Levels 1/2/3a are available."
        )

    raise ReplayError(f"unknown replay level {level!r}; expected one of 1, 2, 3a, 3b")


def assert_replayable(record: Any, level: ReplayLevel) -> ReplayResult:
    """Run the replay and raise if it is not honestly supported at `level`: a Level-2
    hash mismatch or a failed Level-3(a) precondition raises ReplayError (honest refusal,
    F-RPLY-1). Returns the ReplayResult on success."""
    result = replay(record, level)
    if level == "1" and not result.complete:
        raise RecordIncompleteError(
            "record has no terminal substrate.RunFinalised (torn tail or incomplete run)"
        )
    if result.mismatches:
        raise ReplayError(
            f"Level-2 verification failed: {len(result.mismatches)} input-hash mismatch(es) "
            f"(first at seq {result.mismatches[0].seq})"
        )
    if level == "3a" and result.preconditions_ok is False:
        raise ReplayError(f"Level 3(a) refused: {result.refusal_reason}")
    return result

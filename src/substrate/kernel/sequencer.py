# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The append cycle — the single-writer sequencer (technical §6.2, §8).

Extracted from the Runtime God-class: AppendCycle owns the six-step append cycle and its
helpers (resolve/validate, View update, Route staging, Trigger evaluation, quarantine,
blob offload, the view-failure terminal), operating on a shared RunState. The Runtime
keeps the run lifecycle, the writer loop, Producer tasks, locking, and termination; it
delegates each event to AppendCycle.cycle().

The six steps (kernel + tech §6.2), all synchronous, no awaits, one as-of-N snapshot:
  1 validate/resolve  2 seq+append  3 update Views  4 stage Routes
  5 evaluate Predicates / fire Triggers  6 drain the control queue FIFO.
Cascade-generated control events go on RunState.control and run their own full cycle in
step 6, in FIFO generation order (Decision #25).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import msgspec
from msgspec import Struct
from ulid import ULID

from ..constants import (
    BLOB_THRESHOLD_BYTES,
    INJECTION_APPLIED,
    INPUT_BUILD_FAILED,
    PREDICATE_QUARANTINED,
    PRODUCER_CANCELLED,
    PRODUCER_COMPLETED,
    PRODUCER_EMITTED_INVALID,
    PRODUCER_FAILED,
    PRODUCER_STARTED,
    RUN_FINALISED,
    TRIGGER_FIRED,
    InvalidReason,
    RunFailureReason,
    is_reserved,
)
from ..encoding import SafeCanonical, content_hash, safe_raw, try_canonical
from ..errors import InputTypeError
from ..record.inputs import check_input
from ..protocols import TriggerContext
from ..record.sidecar import DiagnosticSidecar
from ..types import Event, ProducerRef
from .runstate import RunPhase, RunState
from .triggers import Logical

if TYPE_CHECKING:
    from ..record.record import RecordWriter
    from .topology import Registration


@dataclass(frozen=True)
class _Emission:
    """A Producer payload emission (credit-gated)."""

    producer: dict[str, Any]
    obj: Any


@dataclass(frozen=True)
class _Lifecycle:
    """A runtime control-plane event (bypasses credits)."""

    kind: str
    payload: dict[str, Any]


class AppendCycle:
    """The single writer's append cycle over a RunState. One instance per run."""

    def __init__(
        self,
        reg: Registration,
        record: RecordWriter,
        state: RunState,
        *,
        budget_us: int,
        hysteresis_k: int,
        diagnostics: DiagnosticSidecar | None = None,
    ) -> None:
        self._reg = reg
        self._record = record
        self._st = state
        self._budget_us = budget_us
        self._hysteresis_k = hysteresis_k
        # Off-bus diagnostic sink (§3.8). None when disabled — and when None its feed is
        # NEVER called, so the bus log is bit-identical with diagnostics on or off
        # (conformance check 14). It is fed AFTER the predicate decision, buffered, and
        # never touches the appended frame's bytes.
        self._diag = diagnostics

    # ── the append cycle (technical §6.2) ───────────────────────────────────────
    def cycle(self, pending: _Emission | _Lifecycle) -> None:
        st = self._st
        # Once the run is finalised (terminal RunFinalised appended), no further event
        # may be appended — RunFinalised is terminal and last-if-present (RUN-BOUNDARY /
        # VIEW-FAILURE TERMINAL). A view-failure can finalise mid-cascade while control
        # events are still queued; drop them rather than append-after-terminal.
        if st.phase.is_terminal:
            return
        st.in_cycle = True
        try:
            kind, schema, env_producer, disk_payload, memory_payload = self._resolve(
                pending
            )  # step 1
            event = self._emit(kind, schema, env_producer, disk_payload, memory_payload)  # step 2
            self._track_lifecycle(event)
            for vname, view in self._reg.views.items():  # step 3
                if not view.subscription.matches(event):
                    continue
                try:
                    view.update(event)
                except Exception as exc:  # noqa: BLE001 — §6.3: a View raising in update() is fatal
                    self._view_failure(vname, event.seq, exc)
                    return
            self._stage_routes(event)  # step 4
            self._eval_triggers(event, event.seq)  # step 5
        finally:
            st.in_cycle = False
        while st.control:  # step 6
            self.cycle(st.control.popleft())

    def _emit(
        self,
        kind: str,
        schema: str,
        env_producer: dict[str, Any] | None,
        disk_payload: Any,
        memory_payload: Any,
    ) -> Event:
        """Assign the next dense seq, frame+append the envelope, build the typed Event ONCE,
        update counts and the last/final-event pointers. Returns the Event.

        disk_payload goes into the envelope written to the record — it may be a BlobRef
        stub for oversized payloads.  memory_payload goes into the Event object fed to
        views, routes, and triggers — it is always the full inline data, so downstream
        consumers never see a blob stub where they expect real fields."""
        st = self._st
        seq = st.next_seq
        now = time.time()
        envelope = {
            "seq": seq,
            "kind": kind,
            "schema": schema,
            "producer": env_producer,
            "t": now,
            "payload": disk_payload,
        }
        self._record.append(envelope)
        # Advance only after the frame is on the record: an append that raises (FrameTooLargeError)
        # consumed a seq before, and the next frame left a gap that made the whole record unreadable
        # (lens audit F020, probe: a 2 MB injected event).
        st.next_seq = seq + 1
        event = Event(
            seq=seq,
            kind=kind,
            schema=schema,
            producer=ProducerRef(**env_producer) if env_producer else None,
            t=now,
            payload=memory_payload,
        )
        st.counts[kind] = st.counts.get(kind, 0) + 1
        st.last_event = event
        st.final_event = event
        return event

    def _resolve(
        self, pending: _Emission | _Lifecycle
    ) -> tuple[str, str, dict[str, Any] | None, Any, Any]:
        """Returns (kind, schema, env_producer, disk_payload, memory_payload).
        disk_payload goes into the envelope on the record; memory_payload goes into the
        Event object fed to views, routes, and triggers.  They differ only when the
        payload exceeds the blob threshold — the disk side gets a BlobRef stub, the
        memory side keeps the full inline data."""
        if isinstance(pending, _Lifecycle):
            # Externally injected events (resume_event, inject_event: any kind outside the
            # reserved namespace) carry payloads from outside the topology; an oversized one is
            # offloaded like an emission (lens audit F019: a 100 KB resume_event was written
            # inline, a 2 MB one failed the frame). The kernel's own lifecycle frames are small
            # by construction and skip the extra canonicalization.
            if not is_reserved(pending.kind):
                sc = try_canonical(pending.payload)
                if sc.ok:
                    disk_payload, _ = self._maybe_offload(sc)
                    return pending.kind, f"{pending.kind}@1", None, disk_payload, pending.payload
            return pending.kind, f"{pending.kind}@1", None, pending.payload, pending.payload
        # a Producer emission — validate at the bus boundary (technical §8.1)
        ref = pending.producer
        obj = pending.obj
        reg = self._reg.producer_kinds.get(ref["kind"])
        event_kind = type(obj).__name__
        invalid: InvalidReason | None = None
        at_path: str | None = None
        if reg is None or not isinstance(obj, Struct) or is_reserved(event_kind):
            invalid = InvalidReason.UNKNOWN_KIND
        elif event_kind not in reg.schemas or not isinstance(obj, reg.schemas[event_kind][0]):
            invalid = (
                InvalidReason.UNKNOWN_KIND
                if event_kind not in reg.schemas
                else InvalidReason.SCHEMA_VIOLATION
            )
        if invalid is None:
            # Guarded canonicalization (the shared sanitize-or-log path): a non-canonical
            # emission becomes a recorded ProducerEmittedInvalidEvent, never a crash.
            sc = try_canonical(obj)
            if sc.ok:
                version = reg.schemas[event_kind][1]  # type: ignore[union-attr]
                # Blob-offload oversized payloads BEFORE framing (technical §3.7 / §3.3):
                # write-ahead the blob, replace the disk payload with a BlobRef. Frames
                # stay bounded; the in-memory payload keeps the full data so triggers and
                # views always see the real fields.
                disk_payload, memory_payload = self._maybe_offload(sc)
                return event_kind, f"{event_kind}@{version}", ref, disk_payload, memory_payload
            invalid, at_path = sc.reason, sc.at_path
            raw = sc.raw
        else:
            raw = safe_raw(obj)
        wrapper: dict[str, Any] = {"reason": invalid, "raw_payload": raw, "producer": ref}
        if at_path is not None:
            wrapper["at_path"] = at_path
        # `raw` is canonical-safe by construction (safe_raw); an oversized one is offloaded.
        wsc = try_canonical(wrapper)
        disk_wrapper = self._maybe_offload(wsc)[0] if wsc.ok else wrapper
        return (
            PRODUCER_EMITTED_INVALID,
            f"{PRODUCER_EMITTED_INVALID}@1",
            None,
            disk_wrapper,
            wrapper,
        )

    def _maybe_offload(self, sc: SafeCanonical) -> tuple[Any, Any]:
        """Returns (disk_payload, memory_payload).  When the canonical payload fits under
        BLOB_THRESHOLD_BYTES both are sc.builtins.  When it exceeds the threshold the disk
        payload is a BlobRef stub ({"$blob":..,"bytes":n}) written write-ahead to the blob
        store, while the memory payload stays as sc.builtins so triggers, views, and routes
        always see the real fields (technical §3.7)."""
        if sc.nbytes <= BLOB_THRESHOLD_BYTES:
            return sc.builtins, sc.builtins
        blob_ref = self._record.put_blob(sc.raw_bytes)
        return {"$blob": blob_ref.sha256, "bytes": blob_ref.bytes}, sc.builtins

    def _producer_input(self, resolved: Any) -> tuple[dict[str, Any], str, Any]:
        """The recorded input fields, `input_sha256` and the Producer's input, from one byte string
        (K267). The input's canonical bytes are built once: recorded (inline or as a blob), hashed,
        and decoded into a fresh value for the Producer. The Producer runs with exactly what the
        record holds, as its own copy: a change it makes reaches no View, no staged event and no
        other Producer (F-PROD-3 as amended 2026-10-09, isolation by copy). A value with no
        canonical form raises InputTypeError, recorded by the caller as InputBuildFailed.

        A frozen Struct input decodes back into its own type; any other input arrives as the
        record's JSON shape (dicts, lists, scalars)."""
        if resolved is None:
            return {"resolved_input": None}, content_hash(None), None
        check_input(resolved)
        sc = try_canonical(resolved)
        if not sc.ok:
            raise InputTypeError(
                f"producer input has no canonical form: {sc.reason} at {sc.at_path}"
            )
        if sc.nbytes <= BLOB_THRESHOLD_BYTES:
            fields: dict[str, Any] = {"resolved_input": sc.builtins}
        else:
            blob_ref = self._record.put_blob(sc.raw_bytes)
            fields = {"input_blob": {"$blob": blob_ref.sha256, "bytes": blob_ref.bytes}}
        if isinstance(resolved, Struct):
            copy = msgspec.json.decode(sc.raw_bytes, type=type(resolved))
        else:
            copy = msgspec.json.decode(sc.raw_bytes)
        return fields, sc.hash, copy

    def _resolved_input_fields(self, resolved: Any) -> dict[str, Any]:
        """The TriggerFired input field(s): per D-5, EXACTLY ONE of `resolved_input`
        (inline, ≤ threshold) or `input_blob` (the BlobRef when oversized) is present; the
        hash is always recorded separately in input_sha256. None → an inline resolved_input
        of None. Raises (caught by the caller as InputBuildFailed) if non-canonical.

        The blob field is `input_blob` (carrying the BlobRef), NOT `$blob`: the locked v0.1
        schema named it `$blob`, but that produced the footgun `{"$blob": {"$blob": ...}}`
        (field key and BlobRef key collide). Renamed under P-TRIGGERFIRED-INPUT-BLOB
        (Architect-directed, carried ahead). The emission-payload blob case keeps the bare
        BlobRef shape — there the payload genuinely IS a BlobRef, so no collision."""
        if resolved is None:
            return {"resolved_input": None}
        sc = try_canonical(resolved)
        if not sc.ok:
            raise ValueError(f"resolved input not canonical: {sc.reason} at {sc.at_path}")
        if sc.nbytes <= BLOB_THRESHOLD_BYTES:
            return {"resolved_input": sc.builtins}
        blob_ref = self._record.put_blob(sc.raw_bytes)
        return {"input_blob": {"$blob": blob_ref.sha256, "bytes": blob_ref.bytes}}

    def _track_lifecycle(self, event: Event) -> None:
        st = self._st
        if event.kind == PRODUCER_STARTED:
            st.started_total += 1
        elif event.kind in (
            PRODUCER_COMPLETED,
            PRODUCER_FAILED,
            PRODUCER_CANCELLED,
        ):
            st.ended_total += 1
            st.inflight = max(0, st.inflight - 1)

    def _view_failure(self, view_name: str, seq: int, exc: Exception) -> None:
        """A View raised in update() — fatal for the run (§6.3). Append the terminal
        RunFinalised{reason:view_failure} directly (no further views/triggers run) and mark
        the run FAILED. Appends straight to the record (not via cycle) because it must run
        inside step 3 after the cycle's accounting."""
        st = self._st
        fseq = st.next_seq
        st.next_seq += 1
        now = time.time()
        payload = {
            "reason": RunFailureReason.VIEW_FAILURE,
            "view": view_name,
            "seq": seq,
            "error": repr(exc),
        }
        schema = f"{RUN_FINALISED}@1"
        envelope = {
            "seq": fseq,
            "kind": RUN_FINALISED,
            "schema": schema,
            "producer": None,
            "t": now,
            "payload": payload,
        }
        self._record.append(envelope)
        st.final_event = Event(
            seq=fseq,
            kind=RUN_FINALISED,
            schema=schema,
            producer=None,
            t=now,
            payload=payload,
        )
        st.last_event = st.final_event
        st.counts[RUN_FINALISED] = st.counts.get(RUN_FINALISED, 0) + 1
        st.control.clear()  # abandon any queued control events: nothing follows RunFinalised
        st.phase = RunPhase.FAILED

    def _stage_routes(self, event: Event) -> None:
        st = self._st
        for r in self._reg.routes:
            if not r.subscription.matches(event):
                continue
            try:
                message = r.transform(event)
            except Exception as exc:  # noqa: BLE001 — design §6.3: route transform raises -> InputBuildFailed
                st.control.append(
                    _Lifecycle(
                        INPUT_BUILD_FAILED,
                        {"route_id": r.id, "firing_key": None, "error": repr(exc)},
                    )
                )
                continue
            st.staged[r.slot] = message
            st.control.append(
                _Lifecycle(
                    INJECTION_APPLIED,
                    {
                        "route_id": r.id,
                        "target_input_slot": r.slot,
                        "message_sha256": content_hash(message),
                    },
                )
            )

    def _eval_triggers(self, event: Event, append_index: int) -> None:
        st = self._st
        # ONE TriggerContext per appended event, shared by every Trigger's predicate +
        # input_builder (event/views/staged do not vary per Trigger) — allocates once per event.
        # views/staged are wrapped read-only (MappingProxyType): TriggerContext is public and
        # frozen, and a predicate/input_builder must not mutate the live run state — predicates in
        # particular now reach `staged` and are supposed to be pure reads (review #25). The proxy
        # is a view (no copy) and matches the documented `Mapping` type of the ctx fields.
        ctx = TriggerContext(
            event=event,
            views=MappingProxyType(self._reg.views),
            staged=MappingProxyType(st.staged),
        )
        for idx, t in enumerate(self._reg.triggers):
            if idx in st.quarantined or not t.subscription.matches(event):
                continue
            # This append matches the trigger's subscription — count it for the logical
            # cooldown (kernel §6: cooldown is measured in subscription-matching appends).
            st.trigger_match_count[idx] = st.trigger_match_count.get(idx, 0) + 1
            t0 = time.perf_counter()
            try:
                fired = t.predicate(ctx)
            except Exception as exc:  # noqa: BLE001 — design §6.3: predicate raises -> immediate quarantine
                self._quarantine(idx, t.id, reason="exception", error=repr(exc))
                continue
            elapsed_us = (time.perf_counter() - t0) * 1e6
            if elapsed_us > self._budget_us:
                st.pred_violations[idx] = st.pred_violations.get(idx, 0) + 1
                if self._diag is not None:  # off-bus, post-decision; never on a disabled run
                    self._diag.budget_violation(
                        seq=event.seq,
                        predicate_id=t.id,
                        measured_us=elapsed_us,
                        count=st.pred_violations[idx],
                    )
                if st.pred_violations[idx] >= self._hysteresis_k:
                    self._quarantine(idx, t.id, reason="budget", measured_us=elapsed_us)
                    continue
            else:
                st.pred_violations[idx] = 0
            if not fired:
                if self._diag is not None:  # record the non-firing evaluation (§3.8)
                    self._diag.predicate_evaluated(
                        seq=event.seq, predicate_id=t.id, result=False, elapsed_us=elapsed_us
                    )
                continue
            # Trigger-level logical cooldown (kernel §6 / technical §10): suppress a firing
            # within `appends` subscription-matching cycles of this trigger's last firing.
            # CHECKED BEFORE policy.admit so a cooldown-suppressed cycle does NOT consume the
            # policy's firing state — e.g. PerKey.admit mutates its seen-set, and a later
            # cooldown `continue` would permanently consume a key that never fired (silent
            # data loss). Logical cooldowns are append-counted and fully replayable;
            # wall-clock cooldowns are handled at registration (replay-ceiling demotion) —
            # pending-timer enforcement is deferred (see BLACKBOARD ## Deferred).
            cd = t.cooldown
            if isinstance(cd, Logical) and cd.appends > 0:
                last = st.trigger_last_fired_match.get(idx)
                if last is not None and st.trigger_match_count[idx] - last < cd.appends:
                    continue
            # The firing-policy admit (PerKey canonical-encodes the key for dedup) can raise
            # on a non-canonical key; treat that as an input-build failure rather than
            # crashing the writer (technical §10, §6.3).
            try:
                do_fire, firing_key = t.policy.admit(event, append_index)
            except Exception as exc:  # noqa: BLE001 — user code (View, Route, Predicate, policy, input builder) raising is recorded per §6.3, never a writer crash
                st.control.append(
                    _Lifecycle(
                        INPUT_BUILD_FAILED,
                        {"trigger_id": t.id, "firing_key": None, "error": repr(exc)},
                    )
                )
                continue
            if not do_fire:
                continue
            # Build → canonicalize → copy the resolved input, ALL inside one guard: a
            # non-canonical builder output is an InputBuildFailed (no Producer starts), never
            # an uncaught crash (technical §6.2 step 5 / §6.3 / F-TRIG-5). K267: the recorded
            # input, its hash and the Producer's copy come from one canonical byte string.
            try:
                resolved = t.input_builder(ctx)
                input_fields, input_hash, producer_input = self._producer_input(resolved)
            except Exception as exc:  # noqa: BLE001 — user code (View, Route, Predicate, policy, input builder) raising is recorded per §6.3, never a writer crash
                st.control.append(
                    _Lifecycle(
                        INPUT_BUILD_FAILED,
                        {"trigger_id": t.id, "firing_key": firing_key, "error": repr(exc)},
                    )
                )
                continue
            instance = str(ULID())
            parent = event.producer.instance if event.producer else None
            st.control.append(
                _Lifecycle(
                    TRIGGER_FIRED,
                    {
                        "trigger_id": t.id,
                        "firing_key": firing_key,
                        "factory": t.starts,
                        "instance": instance,  # the spawned Producer instance — F-OBS-2
                        **input_fields,
                        "input_sha256": input_hash,
                    },
                )
            )
            st.scheduled.append((t.starts, producer_input, instance, parent))
            st.trigger_last_fired_match[idx] = st.trigger_match_count[idx]

    def _quarantine(
        self,
        idx: int,
        trigger_id: str,
        *,
        reason: str,
        measured_us: float = 0.0,
        error: str | None = None,
    ) -> None:
        st = self._st
        st.quarantined.add(idx)
        st.pred_violations[idx] = 0
        payload: dict[str, Any] = {
            "predicate_id": trigger_id,
            "trigger_id": trigger_id,
            "reason": reason,
            "measured_us": measured_us,
            "k": self._hysteresis_k,
        }
        if error is not None:
            payload["error"] = error
        st.control.append(_Lifecycle(PREDICATE_QUARANTINED, payload))

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The Runtime: run lifecycle, the writer loop, Producer tasks, termination (technical §6, §7).

One asyncio event loop. Exactly one writer driving the append cycle; N Producer tasks
that emit by submitting to a credit-gated inbox (the credit pool = the admission bound;
control/lifecycle messages bypass credits, so a full admission queue cannot starve them
— technical §6.1). The append cycle itself lives in substrate.sequencer.AppendCycle (the
single-writer sequencer); the Runtime owns the run lifecycle, locking, the writer loop,
Producer tasks, and termination, and delegates each event to the cycle.

Per-run mutable state lives in a substrate.runstate.RunState constructed once per run()
call (no two-phase construction on the Runtime instance); the run's lifecycle phase is a
RunPhase enum (no ad-hoc booleans).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import msgspec
from msgspec import Struct
from ulid import ULID

from ..record import locking
from ..constants import (
    BUDGET_US,
    HYSTERESIS_K,
    INPUT_BUILD_FAILED,
    PRODUCER_CANCELLED,
    PRODUCER_COMPLETED,
    PRODUCER_FAILED,
    PRODUCER_STARTED,
    RUN_FINALISED,
    RUN_STARTED,
    TERMINATION_MATCHED,
    TRIGGER_FIRED,
    VOCAB_VERSION,
    is_reserved,
)
from ..encoding import content_hash, to_canonical_builtins, try_canonical
from ..errors import FsyncError, ReentrantAppendError
from .policies import Decision, TermContext, quiescence_with_watchdog
from ..record.record import (
    FsyncPolicy,
    Interval,
    RecordWriter,
    _hot_segment,
    read_record,
    recover_open_segment,
)
from .runstate import RunPhase, RunState
from ..record.sealing import seal
from .sequencer import AppendCycle, _Emission, _Lifecycle
from ..record.sidecar import DiagnosticSidecar, WriterStatsSidecar
from .topology import Registration, RegistrationError, TopologyBuilder
from ..types import Event, ProducerRef

_QUIESCENCE_POLL_S = 0.01  # writer idle-poll for the quiescence/watchdog check
# Sprint 199a (SDD vocabulary-as-contract, fold): a `Budget.wall_seconds` breach adds a
# structured `budget_exceeded` block to the `ProducerFailed` payload. Downstream readers
# check `payload.get("budget_exceeded")`; the block carries the axis, limit, and reason as
# typed fields, not embedded in a string. The `error` string is a short human tag
# ("budget_exceeded"), not the discrimination signal. This closes KIT_DIARY 44 without
# minting a new reserved kind.
BUDGET_EXCEEDED_AXIS_WALL_SECONDS = "wall_seconds"
BUDGET_EXCEEDED_ERROR_TAG = "budget_exceeded"
# Consecutive fully-quiescent idle polls where the policy still returns CONTINUE before the
# run is declared STUCK (the silent-hang guard, e.g. a resumable run on all_completed). Two
# polls is unambiguous: with logical cooldowns true quiescence is terminal — no event can
# arrive to clear it — so a second confirming poll just rules out a transient first read.
_STUCK_QUIESCENT_POLLS = 2


class RunResult(Struct, frozen=True):
    """What `Runtime.run()` / `.resume()` returns: the run's outcome and where its record lives.

    `status` is "finalised" (reached a terminal), "paused" (halted on pause-await-input,
    resumable), or "failed". `record_root` is the on-disk run record — the canonical account;
    `final_event` is the last bus event (or None); `finalisation_payload` is the optional output
    a TerminationPolicy attached at finalise. `run_id` survives across a resume."""

    run_id: str
    record_root: str
    status: Literal["finalised", "paused", "failed"]
    final_event: Event | None
    elapsed_seconds: float
    finalisation_payload: Any | None


# Process-global map of record_root → live Runtime, populated when a run
# opens the record for append and cleared when the run finalises. Peer to
# `SessionRegistry._running_handles` on the daemon side: the daemon holds
# handles to session-level runtimes it started; this map lets ANY caller
# on the same process reach a runtime by its record path — most importantly,
# the parent's daemon reaching a delegate child's runtime for a descent-
# scope interrupt. The child spawns on the tool producer's worker thread
# via `asyncio.run(Runtime(child_root).run(...))`; the child's `_drive`
# registers itself here on start and unregisters in the finally block,
# so the child's runtime is reachable exactly while it is alive.
_ACTIVE_RUNTIMES_BY_RECORD_ROOT: dict[str, "Runtime"] = {}


def find_active_runtime(record_root: str | Path) -> "Runtime | None":
    """Return the live Runtime for `record_root`, or `None` when no run is
    active at that path in this process. Reads are lock-free (Python's GIL
    covers the dict access); callers cross-thread should NOT cache the
    reference — a run that has just finalised will be unregistered from
    the map even if the caller still holds the object."""
    return _ACTIVE_RUNTIMES_BY_RECORD_ROOT.get(str(Path(record_root)))


class Runtime:
    """Executes one topology and produces one run record (single-use)."""

    def __init__(
        self,
        record_root: Path | str,
        *,
        persistent: bool = False,
        fsync: FsyncPolicy = Interval(100),
        admission: int = 1024,
        budget_us: int = BUDGET_US,
        hysteresis_k: int = HYSTERESIS_K,
        writer_stats: bool = False,
        diagnostics: bool = False,
    ) -> None:
        if admission <= 0:
            raise ValueError("admission bound must be > 0")
        self._record_root = Path(record_root)
        self._persistent = persistent
        self._fsync = fsync
        # Populated at `_drive` entry with the loop the run is on. Read by
        # cross-thread daemon callers (SessionRegistry.interrupt with
        # record_root=<child>) that need to schedule closures via
        # loop.call_soon_threadsafe on the CHILD's loop rather than the
        # parent's. `None` before a run and after finalisation.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._admission_bound = admission
        self._budget_us = budget_us
        self._hysteresis_k = hysteresis_k
        # Off-bus sidecars (§3.8 / §6.4). Both default OFF; enabling either MUST leave the
        # bus log bit-identical (conformance check 14) — guaranteed because the sidecar
        # sinks are fed off-cycle and are simply absent (never called) when disabled.
        self._writer_stats = writer_stats
        self._diagnostics = diagnostics
        self._used = False

    async def run(self, topology: Callable[[TopologyBuilder], None]) -> RunResult:
        """Run a topology to a fresh run record. Opens at seq 0 with substrate.RunStarted."""
        return await self._drive(topology, resume_event=None)

    async def resume(
        self, topology: Callable[[TopologyBuilder], None], *, resume_event: Any
    ) -> RunResult:
        """Resume a PAUSED persistent-bus run at its existing record (F-TERM-3 / F-PERS-2).

        Reattaches to the persisted bus (re-acquires the flock, opens the EXISTING record for
        append, restores next_seq + the registered Views from the log tail), then appends the
        external `resume_event` — an application event the resume Trigger subscribes to — so
        the resume Trigger fires the continuation Producer; the run continues to its next
        terminal. Seq continues the same sequence; the manifest updates. The topology is taken
        fresh (the same registration the original run used), pointed at the existing root.

        Persistent mode is required: a paused run must survive on a named persistent root under
        the exclusive lock. `resume_event` is an application event Struct. It is NOT
        schema-typed-validated the way a Producer EMISSION is (an external injection routes
        through the lifecycle-append path with a `<kind>@1` schema string — there is no
        registered producer_kind to validate it against); it IS canonical-checked (§4.2
        whitelist; a non-canonical resume_event raises) and reserved-kind-refused (a
        `substrate.*` kind is rejected so it cannot forge a lifecycle frame).

        TERMINATION CONSTRAINT (footgun): a resumable run MUST finalise on a PROCESS-LOCAL
        condition — quiescence (`quiescence_with_watchdog`) or a threshold over event counts —
        NOT `all_completed`. `all_completed` compares restored started/ended COUNTS, but a pause
        trips while the emitting Producer is still inflight, so its ProducerStarted has no
        durable end across the pause: on resume `started > ended` and `completed >= started` can
        never be met. resume() warns loudly if the topology's terminal cannot be satisfied on
        process-local state (rather than hanging silently)."""
        if not self._persistent:
            raise RegistrationError(
                "resume requires persistent=True: only a persistent-bus run can pause and "
                "resume across processes (F-TERM-3 / F-PERS-2)."
            )
        # Config-time refusal (BEFORE the lock/record are taken, like an arg error): the resume
        # event must be an APPLICATION event, never a reserved substrate.* kind — a reserved
        # kind would forge a lifecycle frame. Propagated as RegistrationError, not a failed run.
        if is_reserved(type(resume_event).__name__):
            raise RegistrationError(
                f"resume_event kind {type(resume_event).__name__!r} uses the reserved "
                f"'substrate.' namespace; the resume event must be an application event a "
                f"resume Trigger subscribes to."
            )
        return await self._drive(topology, resume_event=resume_event)

    async def _drive(
        self, topology: Callable[[TopologyBuilder], None], *, resume_event: Any
    ) -> RunResult:
        if self._used:
            raise RuntimeError("RuntimeAlreadyUsedError: a Runtime is single-use")
        self._used = True
        resuming = resume_event is not None
        started = time.monotonic()

        builder = TopologyBuilder()
        topology(builder)
        reg = builder.build()
        self._reg = reg
        self._termination = reg.termination or quiescence_with_watchdog()

        lock_fd: int | None = None
        record: RecordWriter | None = None
        st: RunState | None = None
        self._diag = None  # set after the record exists; None-safe in the finally
        self._stats = None

        # Pre-run SETUP — the lock and the record writer — happens BEFORE the run try and
        # PROPAGATES on failure (a config-time / setup refusal, NOT a failed run): a caller
        # can then distinguish "never started" (setup raised) from "started and failed"
        # (status="failed" with a record on disk). BusLockedError/UnsupportedPlatformError
        # (lock) and an OSError (record-root creation) both propagate. If the record writer
        # fails after the lock was taken, the lock is released before re-raising — no fd
        # leak / self-deadlock.
        if self._persistent:
            lock_fd = locking.acquire_lock(self._record_root, start_time=time.time())
        # Recover an existing record's torn tail (writer-side, §3.3) before reopening for append, so
        # we continue from the last complete frame. On resume this is always needed; for a FRESH run
        # aimed at a root that already holds a crash-torn open segment (operator error / a reused
        # persistent root), recover too — otherwise new frames append AFTER the torn bytes, embedding
        # a permanently-corrupt line. recover_open_segment is non-destructive of good frames.
        if resuming or (self._record_root.exists() and _hot_segment(self._record_root) is not None):
            recover_open_segment(self._record_root)
        try:
            record = RecordWriter(self._record_root, fsync=self._fsync, resume=resuming)
        except BaseException:
            if lock_fd is not None:
                locking.release_lock(lock_fd)
            raise
        self._record = record
        # Off-bus sidecars (created only when enabled; absent => never fed => bus
        # bit-identical, check 14). Live for the run; flushed off-cycle and at close.
        self._diag = DiagnosticSidecar(self._record_root) if self._diagnostics else None
        self._stats = WriterStatsSidecar(self._record_root) if self._writer_stats else None
        try:
            st = self._new_run_state(reg)
            self._st = st
            # Publish this runtime under its record_root so a cross-thread
            # daemon call can find it — Phase 8 item 9 descent-scope
            # interrupt. Registered AFTER `self._st = st` so the map only
            # ever exposes runtimes with live state.
            _ACTIVE_RUNTIMES_BY_RECORD_ROOT[str(self._record_root)] = self
            self._loop = asyncio.get_running_loop()
            self._cyc = AppendCycle(
                reg,
                record,
                st,
                budget_us=self._budget_us,
                hysteresis_k=self._hysteresis_k,
                diagnostics=self._diag,
            )
            if resuming:
                self._resume_bootstrap(reg, resume_event)
            else:
                self._bootstrap(reg)
            self._flush_scheduled()
            await self._writer_loop()
        except FsyncError:
            # fsyncgate (§5.2): the medium is untrustworthy. The writer MUST NOT append
            # RunFinalised; the torn tail (absence of RunFinalised) is the correct encoding
            # of medium failure. The record is already closed by _do_fsync.
            if st is not None:
                st.phase = RunPhase.FAILED
                st.record_closed = True  # _do_fsync already closed the fd; do not re-close
        except Exception as exc:
            # The writer itself raised (a kernel bug, §6.3 "the writer itself raises"). The
            # run did not finalise normally; record the kernel error on the log if the record
            # exists and is still open, so the failure is not silent.
            if st is not None:
                st.phase = RunPhase.FAILED
                st.kernel_error = repr(exc)
                self._try_record_kernel_error(exc)
        finally:
            # Cancellation + record close + lock release ALWAYS run, even if the writer
            # raised — tasks must not leak, the record must be finalised, the lock freed.
            if st is not None:
                for t in st.tasks:
                    t.cancel()
                if st.tasks:
                    await asyncio.gather(*st.tasks, return_exceptions=True)
            if record is not None and (st is None or not st.record_closed):
                try:
                    record.write_manifest(
                        replay_ceiling=st.replay_ceiling if st else "3a",
                        extra={"run_id": st.run_id if st else ""},
                    )
                    record.close()
                except FsyncError:
                    # A close-time fsync failure is itself the §5.2 path: no clean
                    # finalisation. Surface as a failed run rather than re-raising.
                    if st is not None:
                        st.phase = RunPhase.FAILED
            # Flush off-bus sidecars (never coupled to the bus writer; bus already closed).
            # A sidecar flush failure (e.g. disk full) must NOT turn an already-finalised bus
            # into an exception at the API boundary, nor block the lock release — the bus is
            # the record, the sidecars are advisory. Swallow with the run outcome intact.
            for sink in (self._diag, self._stats):
                if sink is not None:
                    try:
                        sink.flush()
                    except OSError:
                        pass
            if lock_fd is not None:
                locking.release_lock(lock_fd)
            # Unpublish under the record_root ONLY when the entry still
            # points at this runtime — a re-entrant call at the same
            # record_root would have overwritten it, and clobbering that
            # entry here would strand the live re-entrant handle.
            _key = str(self._record_root)
            if _ACTIVE_RUNTIMES_BY_RECORD_ROOT.get(_key) is self:
                del _ACTIVE_RUNTIMES_BY_RECORD_ROOT[_key]
            self._loop = None

        status = self._status(st)
        return RunResult(
            run_id=st.run_id if st else "",
            record_root=str(self._record_root),
            status=status,
            final_event=st.final_event if st else None,
            elapsed_seconds=time.monotonic() - started,
            finalisation_payload=st.final_payload if st else None,
        )

    @staticmethod
    def _status(st: RunState | None) -> Literal["finalised", "paused", "failed"]:
        if st is None or st.phase is RunPhase.FAILED:
            return "failed"
        if st.phase is RunPhase.PAUSED:
            return "paused"
        return "finalised"

    def _new_run_state(self, reg: Registration) -> RunState:
        """Construct the per-run mutable state. quiescence_with_watchdog(seconds=) drives
        the writer idle-poll window: the writer wakes at least every `seconds` to test
        quiescence when the inbox is idle, bounded by the fine-grained default so a large
        watchdog window never delays prompt quiescence detection (detection is immediate
        once the queues are empty); a smaller `seconds` polls faster. None → default poll."""
        ws = self._termination.watchdog_seconds
        poll_s = min(_QUIESCENCE_POLL_S, ws) if ws is not None else _QUIESCENCE_POLL_S
        st = RunState(
            run_id=str(ULID()),
            replay_ceiling="3b" if reg.has_wall_clock_cooldown else "3a",
            poll_s=poll_s,
            admission_bound=self._admission_bound,
        )
        st.credits = asyncio.Semaphore(self._admission_bound)
        return st

    def _try_record_kernel_error(self, exc: Exception) -> None:
        """On a writer-internal raise (§6.3 "the writer itself raises"), record the failure
        on the log if the record exists and is still open — so a kernel bug is not silent.
        Best-effort: a further failure here is swallowed (the run is already failing; the
        finally will still close the record)."""
        st = getattr(self, "_st", None)
        record = getattr(self, "_record", None)
        if st is None or record is None or st.record_closed:
            return
        try:
            seq = st.next_seq
            st.next_seq += 1
            record.append(
                {
                    "seq": seq,
                    "kind": RUN_FINALISED,
                    "schema": f"{RUN_FINALISED}@1",
                    "producer": None,
                    "t": time.time(),
                    "payload": {"reason": "kernel_error", "error": repr(exc)},
                }
            )
        except Exception:
            pass  # already failing; do not mask the original error or block the finally

    def _fail_stuck_quiescent(self) -> None:
        """The run is fully quiescent yet the TerminationPolicy will not finalise — it can never
        finalise (no inflight work and, with logical cooldowns, no event can ever arrive), so it
        would otherwise hang forever. Turn that silent hang into a LOUD signal: record a
        RunFinalised with reason "stuck_quiescent" naming the policy (citable on the log) and
        fail the run. The canonical cause is a RESUMABLE run whose terminal is all_completed —
        the pause leaves a Producer's start without a durable end, so restored started>ended and
        completed>=started is unmeetable; the fix is a process-local terminal (quiescence /
        threshold). (Nothing consequential is silent — product §1.)"""
        st = self._st
        policy = self._termination.name
        msg = (
            f"RunStuckQuiescent: the run went quiescent (no inflight Producers, no queued or "
            f"control work) but TerminationPolicy {policy!r} returned CONTINUE, so it can never "
            f"finalise. A resumable run MUST finalise on a PROCESS-LOCAL condition (quiescence "
            f"or a count threshold), not all_completed — see Runtime.resume / pause_await_input."
        )
        st.kernel_error = msg
        if not st.record_closed:
            try:
                seq = st.next_seq
                st.next_seq += 1
                self._record.append(
                    {
                        "seq": seq,
                        "kind": RUN_FINALISED,
                        "schema": f"{RUN_FINALISED}@1",
                        "producer": None,
                        "t": time.time(),
                        "payload": {"reason": "stuck_quiescent", "policy": policy, "error": msg},
                    }
                )
            except Exception:
                pass  # best-effort; the finally still closes the record
        st.phase = RunPhase.FAILED

    # ── bootstrap ────────────────────────────────────────────────────────────--
    def _bootstrap(self, reg: Registration) -> None:
        self._cyc.cycle(_Lifecycle(RUN_STARTED, self._manifest(reg)))  # seq 0
        for init in reg.initials:
            instance = str(ULID())
            # Guard initial-input canonicalization/sealing: a non-canonical or non-sealable
            # initial input becomes a recorded InputBuildFailed (no Producer starts) rather
            # than crashing the writer at startup.
            try:
                sealed = seal(init.input)
                # Hash + canonicalize the pre-seal object: seal() normalizes
                # dict→MappingProxyType / list→tuple (which msgspec.to_builtins cannot
                # encode), but canonical encoding of the pre-seal value folds to exactly the
                # same bytes the sealed value represents, so input_sha256 is stable and over
                # the logical value the Producer runs with (D-5).
                input_fields = self._cyc._resolved_input_fields(init.input)
                input_hash = content_hash(init.input)
            except Exception as exc:
                self._cyc.cycle(
                    _Lifecycle(
                        INPUT_BUILD_FAILED,
                        {
                            "trigger_id": "__initial__",
                            "firing_key": "__initial__",
                            "error": repr(exc),
                        },
                    )
                )
                continue
            self._cyc.cycle(
                _Lifecycle(
                    TRIGGER_FIRED,
                    {
                        "trigger_id": "__initial__",
                        "firing_key": "__initial__",
                        "factory": init.kind,
                        "instance": instance,
                        **input_fields,
                        "input_sha256": input_hash,
                    },
                )
            )
            self._st.scheduled.append((init.kind, sealed, instance, None))

    def _resume_bootstrap(self, reg: Registration, resume_event: Any) -> None:
        """Resume entry (F-TERM-3): restore state from the existing record, then inject the
        external resume event so the resume Trigger fires the continuation. No fresh
        RunStarted — the run is CONTINUING, not opening; seq continues the existing sequence."""
        st = self._st
        # 1) Restore from the log tail: next_seq (seq continuity), the registered Views (folded
        #    Level-1 over the existing record so the resume Trigger's predicate/input_builder
        #    see correct as-of state), and the kind counts + started/ended totals the
        #    TerminationPolicy reads. Views are deterministic Level-1 projections (kernel §4).
        max_seq = -1
        for env in read_record(self._record_root):
            seq = int(env.get("seq", -1))
            max_seq = max(max_seq, seq)
            kind = str(env.get("kind", ""))
            if kind == RUN_STARTED:
                # restore the ORIGINAL run_id so the resumed manifest/RunResult keep the run's
                # identity (the freshly-minted st.run_id from _new_run_state is discarded).
                rid = env.get("payload", {})
                if isinstance(rid, dict) and isinstance(rid.get("run_id"), str):
                    st.run_id = rid["run_id"]
            st.counts[kind] = st.counts.get(kind, 0) + 1
            if kind == PRODUCER_STARTED:
                st.started_total += 1
            elif kind in (
                PRODUCER_COMPLETED,
                PRODUCER_FAILED,
                PRODUCER_CANCELLED,
            ):
                st.ended_total += 1
            for vname, view in reg.views.items():
                if _resume_view_matches(view.subscription, env):
                    view.update(_as_event(env))
        st.next_seq = max_seq + 1  # resumed appends continue the SAME seq sequence
        # 2) Inject the external resume event onto the bus (producer=null — it is externally
        #    supplied, not Producer-emitted). It is canonicalized + validated here; the resume
        #    Trigger (subscribed to its kind) fires the continuation Producer in the cycle.
        kind = type(resume_event).__name__  # reserved-kind already refused in resume()
        try:
            payload = to_canonical_builtins(resume_event)
        except Exception as exc:
            raise RegistrationError(f"resume_event is not canonical: {exc!r}") from exc
        self._cyc.cycle(_Lifecycle(kind, payload))  # appends with producer=null; fires triggers

    def _manifest(self, reg: Registration) -> dict[str, Any]:
        def _no_desc(obj: Any) -> Any:
            # Drop `description` from the embedded JSON schemas. It carries the Struct's docstring,
            # which is prose, not part of the structural contract the manifest pins (types / required
            # / schema_version). It is also NON-DETERMINISTIC ACROSS PYTHON VERSIONS: CPython 3.13+
            # dedents docstrings at compile time, so a multi-line Struct docstring serializes to
            # different bytes on 3.13/3.14 vs 3.12 — which stranded three bundled topologies' committed
            # records cross-version (RunStarted divergence, CI red on the py3.13/3.14 matrix cells).
            # Stripping it makes the manifest depend only on structure, byte-identical across versions.
            if isinstance(obj, dict):
                return {k: _no_desc(v) for k, v in obj.items() if k != "description"}
            if isinstance(obj, list):
                return [_no_desc(x) for x in obj]
            return obj

        producer_kinds = []
        for pk in reg.producer_kinds.values():
            schemas = {
                name: _no_desc(msgspec.json.schema(t)) for name, (t, _v) in pk.schemas.items()
            }
            version = next(iter(pk.schemas.values()))[1] if pk.schemas else 1
            pk_entry: dict[str, Any] = {
                "kind": pk.kind,
                "schema_version": version,
                "schemas": schemas,
                # the author's determinism flag — load-bearing for the Level-3(a) replay
                # precondition (F-RPLY-1; replay._producer_kinds_deterministic).
                "deterministic": pk.deterministic,
                "fingerprint": {
                    "qualname": getattr(pk.factory, "__qualname__", repr(pk.factory)),
                    "author_version": pk.author_version,
                },
            }
            # composition export map (F-COMP-1 / §20): for an EMBEDDED-substrate kind, record
            # the {inner_kind -> outer_schema} map — DERIVED from the embedded substrate's OWN
            # map (the single source of truth), so the recorded boundary can never drift from
            # the map the translator uses. Absent for a non-embedded kind. Makes the boundary
            # observable in RunStarted (conformance check 7).
            if pk.export_map is not None:
                pk_entry["export_map"] = dict(pk.export_map)
            producer_kinds.append(pk_entry)
        return {
            "run_id": self._st.run_id,
            "topology": {
                "producer_kinds": producer_kinds,
                "triggers": [
                    {
                        "id": t.id,
                        "subscription": sorted(t.subscription.kinds),
                        "firing_policy": type(t.policy).__name__,
                        "starts": t.starts,
                    }
                    for t in reg.triggers
                ],
                "routes": [{"id": r.id, "slot": r.slot} for r in reg.routes],
                "views": sorted(reg.views),
                "policies": [self._termination.name],
                # topology-level union of every embedded kind's export map — a convenience
                # aggregate DERIVED from the per-kind producer_kinds[].export_map (the single
                # source); empty when the topology embeds no substrate. (Observability per
                # check 7; the authoritative per-kind maps are on the producer_kinds entries.)
                "exports": {
                    inner: outer
                    for pk in reg.producer_kinds.values()
                    if pk.export_map
                    for inner, outer in pk.export_map.items()
                },
            },
            "baseline": reg.baseline,
            "config": {
                "fsync": type(self._fsync).__name__,
                "admission": self._admission_bound,
                "budget_us": self._budget_us,
                "hysteresis_k": self._hysteresis_k,
                "replay_ceiling": self._st.replay_ceiling,
                # the signal-vocabulary version this record was written against — distinct
                # from a per-kind wire schema; lets replay/inspection self-describe (v0.2
                # added TriggerFired.instance/factory + input_blob).
                "vocab_version": VOCAB_VERSION,
            },
        }

    # ── producer tasks & the writer loop ─────────────────────────────────────--
    def _flush_scheduled(self) -> None:
        st = self._st
        while st.scheduled:
            kind, inp, instance, parent = st.scheduled.pop(0)
            st.inflight += 1
            task = asyncio.create_task(self._producer_task(kind, inp, instance, parent))
            st.tasks.add(task)
            st.task_by_instance[instance] = task
            st.kind_by_instance[instance] = kind

            def _done(t: asyncio.Task[None], inst: str = instance) -> None:
                st.tasks.discard(t)
                st.task_by_instance.pop(inst, None)
                st.kind_by_instance.pop(inst, None)
                st.cancel_reasons.pop(inst, None)

            task.add_done_callback(_done)

    async def _producer_task(self, kind: str, inp: Any, instance: str, parent: str | None) -> None:
        ref = {"kind": kind, "instance": instance, "parent": parent}
        inbox = self._st.inbox
        inbox.put_nowait(_Lifecycle(PRODUCER_STARTED, {"producer": ref}))
        # Sprint 199 (roadmap v2 S1b fold-in): `Budget.wall_seconds` enforcement. If the
        # producer_kind declared a wall-clock cap, wrap the async-for consumer in
        # `asyncio.wait_for`. On timeout we synthesise the exception path — ProducerFailed
        # with a typed `error="budget_exceeded: wall_seconds=<limit>s: <reason>"` — so a
        # downstream reader inspecting the error prefix can distinguish a budget breach from
        # a producer bug. Emission-count caps (`Budget.event_counts`) are a later sprint
        # (their site is emit-time inside `_submit_emission`, and this fold is wall-only).
        producer_kind = self._reg.producer_kinds[kind]
        budget = producer_kind.budget
        wall_cap = budget.wall_seconds if budget is not None else None
        try:
            start = producer_kind.factory()

            async def _consume() -> None:
                async for obj in start(inp):
                    await self._submit_emission(ref, obj)

            if wall_cap is not None:
                await asyncio.wait_for(_consume(), timeout=float(wall_cap.limit))
            else:
                await _consume()
            inbox.put_nowait(_Lifecycle(PRODUCER_COMPLETED, {"producer": ref}))
        except asyncio.CancelledError:
            # v0.3 vocabulary: ProducerCancelled payload carries `cause` and `caller`
            # when the cancel site set them. `cancel_producer` writes the annotation
            # synchronously before task.cancel() dispatches, so it is visible here.
            # `_cancel_others` writes "cause": "policy". A CancelledError with no
            # entry in `cancel_reasons` (task-cascade on run teardown) leaves the
            # fields absent — additive, non-breaking for readers who key on `producer`.
            cancel_payload: dict[str, Any] = {"producer": ref}
            reason = self._st.cancel_reasons.get(instance)
            if reason is not None:
                if "cause" in reason:
                    cancel_payload["cause"] = reason["cause"]
                if reason.get("caller") is not None:
                    cancel_payload["caller"] = reason["caller"]
            inbox.put_nowait(_Lifecycle(PRODUCER_CANCELLED, cancel_payload))
            raise
        except asyncio.TimeoutError:
            assert wall_cap is not None  # only reachable when the budget wrapped _consume
            payload: dict[str, Any] = {
                "producer": ref,
                "error": BUDGET_EXCEEDED_ERROR_TAG,
                "budget_exceeded": {
                    "axis": BUDGET_EXCEEDED_AXIS_WALL_SECONDS,
                    "limit": float(wall_cap.limit),
                    "reason": wall_cap.reason,
                },
            }
            inbox.put_nowait(_Lifecycle(PRODUCER_FAILED, payload))
        except Exception as exc:
            payload = {"producer": ref, "error": repr(exc)}
            # Composition (§20): an embedded substrate's inner-run failure surfaces as ONE
            # outer ProducerFailed carrying the inner run_id (the exception carries it).
            inner = getattr(exc, "inner_run_id", None)
            if isinstance(inner, str) and inner:
                payload["inner_run_id"] = inner
            inbox.put_nowait(_Lifecycle(PRODUCER_FAILED, payload))

    async def _submit_emission(self, ref: dict[str, Any], obj: Any) -> None:
        st = self._st
        if st.in_cycle:  # reentrancy guard (technical §6.2)
            raise ReentrantAppendError(
                "submit() reached synchronously from inside the append cycle"
            )
        await st.credits.acquire()
        st.inbox.put_nowait(_Emission(ref, obj))

    async def _writer_loop(self) -> None:
        st = self._st
        stuck_quiescent = 0  # consecutive idle polls where the run is fully quiescent yet the
        # TerminationPolicy will not finalise (CONTINUE) — the silent-hang signature.
        while st.phase is RunPhase.RUNNING:
            try:
                msg = await asyncio.wait_for(st.inbox.get(), timeout=st.poll_s)
            except asyncio.TimeoutError:
                # Quiescence (kernel §"Quiescence, defined"): no running Producers, empty
                # admission + control queues, no true-and-unfired Trigger, no pending
                # wall-clock cooldown. With logical cooldowns (v0.1 default) the
                # true-and-unfired clause is vacuous — Triggers fire only on appends, and
                # with no Producers and empty queues no further append can occur, so none can
                # mature. Wall-clock-cooldown pending-timer quiescence is deferred.
                if st.inflight == 0 and st.inbox.empty() and not st.control:
                    self._consult_termination(None, quiescent=True)
                    # STUCK-QUIESCENCE GUARD (turns a silent hang into a loud signal): the run
                    # is fully quiescent (no inflight Producer, no queued/control work, no
                    # wall-clock cooldown) yet the policy returned CONTINUE — so NOTHING can ever
                    # produce another event and the run can never finalise. The canonical cause
                    # is a resumable run whose terminal is all_completed (restored started>ended
                    # across the pause makes completed>=started unmeetable). Rather than spin
                    # forever, surface it as a recorded kernel error and fail the run (the
                    # detection is robust because true quiescence with logical cooldowns is
                    # terminal — no event can arrive to clear it).
                    if st.phase is RunPhase.RUNNING:
                        stuck_quiescent += 1
                        if stuck_quiescent >= _STUCK_QUIESCENT_POLLS:
                            self._fail_stuck_quiescent()
                            break
                continue
            stuck_quiescent = 0  # any inbound work clears the stuck-quiescence streak
            # BATCH DRAIN (perf): one `await inbox.get()` wakes the writer; then drain every
            # item ALREADY ready (get_nowait) into a batch and process the whole batch before
            # awaiting again — amortizing the per-event event-loop round-trip. This changes
            # only the WAKE granularity: the single writer still processes items strictly in
            # FIFO/seq order, one append cycle each (control-queue step-6 still drains inside
            # each cycle), credits are still released per emission as it is taken, and
            # quiescence is still detected on the idle-timeout path (only reached when the
            # inbox blocks, i.e. is empty). Total order, backpressure, step-6, and quiescence
            # are all preserved; only the asyncio hop is batched.
            batch = [msg]
            while True:
                try:
                    batch.append(st.inbox.get_nowait())
                except asyncio.QueueEmpty:
                    break
            for i, item in enumerate(batch):
                if st.phase is not RunPhase.RUNNING:
                    # a mid-batch finalise/fail (e.g. view-failure) stops processing; release
                    # credits for the UNPROCESSED emissions so no Producer task is left blocked
                    # on a credit during the run()-finally cancellation gather.
                    for rest in batch[i:]:
                        if isinstance(rest, _Emission):
                            st.credits.release()
                    break
                if isinstance(item, _Emission):
                    st.credits.release()  # release as the emission is taken (backpressure)
                self._cyc.cycle(item)
                self._flush_scheduled()
                if st.last_event is not None:
                    self._consult_termination(st.last_event, quiescent=False)
            # Writer-stats sample: BETWEEN batches (off the hot path), only when enabled.
            # Sampling/I/O here never touches the appended frame's bytes (check 14).
            if self._stats is not None:
                self._stats.sample(
                    {
                        "at_seq": st.next_seq - 1,
                        "admission_depth": st.inbox.qsize(),
                        "control_queue_depth": len(st.control),
                        "started_total": st.started_total,
                        "ended_total": st.ended_total,
                        "quarantined_count": len(st.quarantined),
                    }
                )

    def _consult_termination(self, event: Event | None, *, quiescent: bool) -> None:
        st = self._st
        if st.phase is not RunPhase.RUNNING:
            return
        ctx = TermContext(
            event=event,
            quiescent=quiescent,
            running=st.inflight,
            started=st.started_total,
            completed=st.ended_total,
            counts=lambda k: st.counts.get(k, 0),
        )
        decision = self._termination.decide(ctx)
        if decision is Decision.FINALISE_RUN:
            self._cyc.cycle(
                _Lifecycle(
                    TERMINATION_MATCHED,
                    {"policy": self._termination.name, "decision": decision.value},
                )
            )
            # The policy may attach a final output payload (RunFinalised.finalisation_payload
            # → RunResult.finalisation_payload). Sanitize it: a non-canonical (or raising)
            # payload does not crash finalisation, but the drop is NOT silent — the reason is
            # recorded on the RunFinalised frame (nothing consequential is silent, product §1).
            payload: dict[str, Any] = {}
            fp: Any = None
            drop_reason: str | None = None
            try:
                fp = self._termination.finalisation_payload(ctx)
            except Exception as exc:
                drop_reason = f"finalisation callback raised: {exc!r}"
            if fp is not None and drop_reason is None:
                sc = try_canonical(fp)
                if sc.ok:
                    final_builtins = self._cyc._maybe_offload(sc)
                    payload["finalisation_payload"] = final_builtins
                    st.final_payload = final_builtins
                else:
                    drop_reason = f"finalisation payload not canonical: {sc.reason} at {sc.at_path}"
            if drop_reason is not None:
                payload["finalisation_payload_dropped"] = drop_reason
            self._cyc.cycle(_Lifecycle(RUN_FINALISED, payload))
            # A view-failure mid-cascade may already have set FAILED; do not override it.
            if st.phase is RunPhase.RUNNING:
                st.phase = RunPhase.FINALISED
        elif decision is Decision.PAUSE_AWAIT_INPUT:
            self._cyc.cycle(
                _Lifecycle(
                    TERMINATION_MATCHED,
                    {
                        "policy": self._termination.name,
                        "decision": decision.value,
                        "resume_condition": self._termination.resume_condition,
                    },
                )
            )
            st.phase = RunPhase.PAUSED
        elif decision is Decision.CANCEL_OTHERS:
            self._cancel_others(event)

    def _cancel_others(self, event: Event | None) -> None:
        """Cancel every live Producer EXCEPT the subject (the producer of `event`) — kernel §8
        cancel-others. The run does NOT terminate: the cancelled tasks emit
        substrate.ProducerCancelled (drained by the still-running writer loop) and the run
        continues to quiescence. Idempotent — fires once per still-cancellable cohort; a
        repeat call with everyone already cancelled is a no-op (so a CANCEL_OTHERS policy that
        keeps matching does not thrash)."""
        st = self._st
        # The subject is the Producer this decision is "about" — for a lifecycle event
        # (ProducerCompleted/…) the subject rides the PAYLOAD's producer ref (P-SUBJECT-ID),
        # not the envelope `producer` (null for substrate.* events); for an application event
        # it is the envelope producer. Check both.
        subject: str | None = None
        if event is not None:
            if event.producer is not None:
                subject = event.producer.instance
            elif isinstance(event.payload, dict):
                ref = event.payload.get("producer")
                if isinstance(ref, dict):
                    subject = ref.get("instance")
        victims = [
            (inst, task)
            for inst, task in list(st.task_by_instance.items())
            if inst != subject and not task.done()
        ]
        if not victims:
            return  # nothing left to cancel — do not emit a vacuous TerminationMatched
        self._cyc.cycle(
            _Lifecycle(
                TERMINATION_MATCHED,
                {"policy": self._termination.name, "decision": Decision.CANCEL_OTHERS.value},
            )
        )
        for inst, task in victims:
            # v0.3: annotate the ProducerCancelled envelope with policy provenance
            # BEFORE task.cancel() dispatches, so the CancelledError handler reads
            # the annotation when it fires.
            st.cancel_reasons[inst] = {"cause": "policy", "caller": self._termination.name}
            task.cancel()  # the task's CancelledError handler enqueues ProducerCancelled

    def cancel_producer(
        self,
        instance: str,
        *,
        cause: str = "external",
        caller: str | None = None,
    ) -> dict[str, Any] | None:
        """Cancel one live Producer by instance id. Records `cause` and `caller` on
        the producer's `substrate.ProducerCancelled` envelope so the record carries
        who cancelled and why (v0.3 vocabulary extension).

        Returns the ProducerRef dict of the cancelled instance, or `None` if the
        instance is unknown / already completed. Never raises for "not found";
        interrupting an idle session is a no-op, not an error.

        Thread safety: call from the event-loop thread. From another thread use
        `loop.call_soon_threadsafe(runtime.cancel_producer, instance)`; Python's
        `asyncio.Task.cancel()` refuses cross-thread calls.

        Composition: replaces the shipped `cancel_producers(kind)` shape (sprint
        217c). A caller wanting kind-scoped batch cancels iterates
        `[cancel_producer(inst) for inst, k in st.kind_by_instance.items() if k == kind]`.
        """
        st = getattr(self, "_st", None)
        if st is None:
            raise RuntimeError("cancel_producer called before Runtime.run/.resume; no live state")
        task = st.task_by_instance.get(instance)
        kind = st.kind_by_instance.get(instance)
        if task is None or kind is None or task.done():
            return None
        # Write the annotation BEFORE task.cancel() dispatches so the CancelledError
        # handler in `_producer_task` reads it before enqueueing ProducerCancelled.
        reason: dict[str, Any] = {"cause": cause}
        if caller is not None:
            reason["caller"] = caller
        st.cancel_reasons[instance] = reason
        task.cancel()
        return {"kind": kind, "instance": instance, "parent": None}

    def inject_event(self, event: Any) -> None:
        """Inject an APPLICATION event onto a live run's inbox from OUTSIDE any Producer.

        Peer to `cancel_producer` for the daemon-facing surface. Where `cancel_producer`
        stops a live Producer, `inject_event` records an external decision on the run's
        record so triggers subscribed to its kind fire. The frame appends with
        `producer=null` (externally supplied, same as the resume path — see
        `_resume_bootstrap`). Seq continues the same sequence.

        Same discipline as `Runtime.resume`'s external-event surface: reserved-kind
        refused (a `substrate.*` kind would forge a lifecycle frame), payload
        canonicalized. The event is canonical-checked here, not schema-typed-validated
        the way a Producer EMISSION is (there is no registered producer_kind to
        validate an external injection against — same as `resume_event`).

        Thread safety: call from the event-loop thread. From another thread use
        `loop.call_soon_threadsafe(runtime.inject_event, event)`. The event lands on
        the inbox and the main loop cycles it on its next iteration; the caller
        cannot wait for the effect (fire-and-forget by design).

        Returns `None`. Raises `RegistrationError` on a reserved kind or a
        non-canonical payload. Raises `RuntimeError` if the run is not live.

        Not for lifecycle events. Lifecycle emissions (`substrate.ProducerStarted`,
        `substrate.ProducerCompleted`, `substrate.ProducerCancelled`,
        `substrate.ProducerFailed`, `substrate.RunStarted`, `substrate.RunFinalised`)
        are the runtime's — a caller cannot forge one.
        """
        # Config-time refusals BEFORE state consultation (same shape as
        # Runtime.resume): a reserved kind or a non-canonical payload is a
        # RegistrationError regardless of whether a run is live.
        kind = type(event).__name__
        if is_reserved(kind):
            raise RegistrationError(
                f"inject_event kind {kind!r} uses the reserved 'substrate.' namespace; "
                f"external injections must be APPLICATION events, never lifecycle frames."
            )
        try:
            payload = to_canonical_builtins(event)
        except Exception as exc:
            raise RegistrationError(f"inject_event event is not canonical: {exc!r}") from exc
        st = getattr(self, "_st", None)
        if st is None:
            raise RuntimeError("inject_event called before Runtime.run/.resume; no live state")
        st.inbox.put_nowait(_Lifecycle(kind, payload))


# ── resume helpers (fold the existing record into the registered Views, §4 Level-1) ──────
def _resume_view_matches(sub: Any, env: dict[str, Any]) -> bool:
    """Subscription match on a raw record envelope dict (the resume fold needs to feed only
    the events a View subscribes to, mirroring runtime/inspect subscription semantics)."""
    if str(env.get("kind")) in sub.kinds:
        return True
    ref = env.get("producer")
    if isinstance(ref, dict) and sub.producers:
        if ref.get("kind") in sub.producers or ref.get("instance") in sub.producers:
            return True
    return False


def _as_event(env: dict[str, Any]) -> Event:
    """Reconstruct an Event from a record envelope for the resume View fold."""
    ref = env.get("producer")
    producer = (
        ProducerRef(
            kind=str(ref.get("kind", "")),
            instance=str(ref.get("instance", "")),
            parent=ref.get("parent"),
        )
        if isinstance(ref, dict)
        else None
    )
    return Event(
        seq=int(env["seq"]),
        kind=str(env["kind"]),
        schema=str(env.get("schema", "")),
        producer=producer,
        t=float(env.get("t", 0.0)),
        payload=env.get("payload"),
    )

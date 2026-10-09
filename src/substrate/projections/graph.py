# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Graph projections — the structure and the run-as-graph the UI's graph surfaces render.

Two pure, deterministic, read-only projections (F-OBS-6: no bus emission, no record mutation),
the data layer behind the design handoff's two graph surfaces (`docs/design/ui-design-handoff.md` §6):

  - `topology_graph(record)` — the STATIC structure: Producer kinds as nodes (with the event
    kinds they emit), Triggers as the spawn edges (`on` a subscription, with a firing policy,
    `starts` a Producer), Routes as the staging edges, the Views, and the TerminationPolicy. Read
    from the RunStarted manifest (the only place a run records its topology).

  - `run_graph(record)` — the DYNAMIC run-as-graph: every Producer INSTANCE as a node, with its
    spawn link (parent instance + the Trigger that started it), its lifecycle SPAN (started_seq ..
    ended_seq) and end status, and the application events it emitted. This is the concurrent,
    causal, emergent shape the handoff doc calls the signature view — instances appearing as
    Triggers fire, running with overlapping spans, completing or being cancelled.

Like the inspect/narrate surfaces, both accept a record root path OR an iterable of envelope
dicts, and the output cites sequence numbers. Neither re-executes anything; both are a single
pass over a recorded run. `topology_graph` is built from the manifest, `run_graph` from the
lifecycle + provenance events (the same TriggerFired.instance / ProducerStarted.parent links the
inspect provenance surface uses).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from msgspec import Struct

from ..constants import (
    INITIAL_TRIGGER_ID,
    PRODUCER_CANCELLED,
    PRODUCER_COMPLETED,
    PRODUCER_FAILED,
    PRODUCER_STARTED,
    RUN_FINALISED,
    RUN_STARTED,
    TERMINATION_MATCHED,
    TRIGGER_FIRED,
    RunFailureReason,
    RunStatus,
)
from ..errors import RecordIncompleteError
from ..kernel.policies import Decision
from ..record.record import load_envelopes

_RUN_STARTED = RUN_STARTED
_TRIGGER_FIRED = TRIGGER_FIRED
_INITIAL = INITIAL_TRIGGER_ID


class ProducerStatus(StrEnum):
    """A Producer instance's status in `run_graph` (lens audit F034: a five-value string set)."""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RUNNING = "running"
    INTERRUPTED = "interrupted"


_END_KINDS = {
    PRODUCER_COMPLETED: ProducerStatus.COMPLETED,
    PRODUCER_FAILED: ProducerStatus.FAILED,
    PRODUCER_CANCELLED: ProducerStatus.CANCELLED,
}
# RunFinalised reasons that mean the RUN ITSELF failed (RunStatus.FAILED), as opposed to a clean
# finalise that nonetheless had Producer-level failures inside it (finished != worked).
_RUN_FAILURE_REASONS = frozenset(RunFailureReason)


# ── static structure (topology_graph) ───────────────────────────────────────────────────────
class ProducerNode(Struct, frozen=True):
    """A Producer KIND in the topology. `emits` are the event kinds it may emit (its declared
    schemas); `is_initial` is True when the run starts this kind at open (an entry point).

    `is_initial` is NOT "no Trigger starts it": in a cyclic topology (e.g. a round-robin where
    `after-N` wraps to start speaker-1), an entry Producer is also a Trigger's target, so the
    only reliable signal is whether it actually fired at run open — recorded as a TriggerFired
    with trigger_id `__initial__`. The manifest does not record initials; this is read from
    those firings."""

    kind: str
    emits: tuple[str, ...]
    deterministic: bool
    is_initial: bool


class TriggerEdge(Struct, frozen=True):
    """A Trigger: when an event matching `on` (its subscription) lands and its predicate holds,
    start the `starts` Producer. `policy` is the firing policy (Once / PerEvent / PerKey /
    WhileTrue). The predicate itself is code, not recorded — only its effect (a firing) is."""

    id: str
    policy: str
    on: tuple[str, ...]
    starts: str


class RouteEdge(Struct, frozen=True):
    """A Route: stages data forward into `slot` for a later Trigger's input. The manifest records
    the route's id and target slot (the citable identity); the source subscription and transform
    are code, surfaced at runtime as the InjectionApplied events in the run-as-graph."""

    id: str
    slot: str


class TopologyGraph(Struct, frozen=True):
    """The static structure of a run's topology, read from its RunStarted manifest: Producer-kind
    nodes, Trigger spawn-edges, Route staging-edges, the View names, and the TerminationPolicy
    descriptor(s)."""

    producers: tuple[ProducerNode, ...]
    triggers: tuple[TriggerEdge, ...]
    routes: tuple[RouteEdge, ...]
    views: tuple[str, ...]
    termination: tuple[str, ...]


def topology_graph(record: Any) -> TopologyGraph:
    """The STATIC topology structure, from the RunStarted manifest (the only place a run records
    its topology). Producer kinds are nodes (with what they emit and whether any Trigger starts
    them — `is_initial`); Triggers and Routes are the edges. Raises ValueError if the record has no
    RunStarted manifest (an empty or truncated record has no topology to project)."""
    envelopes = load_envelopes(record)
    manifest: dict[str, Any] | None = None
    initial_kinds: set[str] = set()
    for env in envelopes:
        kind = env.get("kind")
        if kind == _RUN_STARTED and manifest is None:
            manifest = (env.get("payload") or {}).get("topology")
        elif kind == _TRIGGER_FIRED:
            p = env.get("payload") or {}
            # an initial Producer fires at run open under trigger_id __initial__ — the only
            # reliable record of which kinds are entry points (the manifest omits initials).
            if p.get("trigger_id") == _INITIAL and isinstance(p.get("factory"), str):
                initial_kinds.add(p["factory"])
    if not isinstance(manifest, dict):
        # a typed SubstrateError (not a bare ValueError) so an api-only consumer can catch it by
        # type, like the rest of the read surface (review #29); a manifest-less record is incomplete.
        raise RecordIncompleteError(
            "no substrate.RunStarted manifest in record; cannot project a topology"
        )

    triggers = tuple(
        TriggerEdge(
            id=str(t.get("id", "?")),
            policy=str(t.get("firing_policy", "?")),
            on=tuple(str(x) for x in (t.get("subscription") or [])),
            starts=str(t.get("starts", "?")),
        )
        for t in manifest.get("triggers", [])
    )
    producers = tuple(
        ProducerNode(
            kind=str(pk.get("kind", "?")),
            emits=tuple(sorted((pk.get("schemas") or {}).keys())),
            deterministic=bool(pk.get("deterministic", False)),
            is_initial=str(pk.get("kind", "?")) in initial_kinds,
        )
        for pk in manifest.get("producer_kinds", [])
    )
    routes = tuple(
        RouteEdge(id=str(r.get("id", "?")), slot=str(r.get("slot", "?")))
        for r in manifest.get("routes", [])
    )
    views = tuple(str(v) for v in manifest.get("views", []))
    termination = tuple(str(p) for p in manifest.get("policies", []))
    return TopologyGraph(
        producers=producers,
        triggers=triggers,
        routes=routes,
        views=views,
        termination=termination,
    )


# ── dynamic run-as-graph (run_graph) ─────────────────────────────────────────────────────────
class ProducerInstance(Struct, frozen=True):
    """One Producer INSTANCE in a run: its kind, its spawn link (`parent` instance + the
    `trigger_id` that started it — `__initial__` for an initial Producer), its lifecycle SPAN
    (`fired_seq` when its Trigger SCHEDULED it; `started_seq` .. `ended_seq` when it actually ran,
    `ended_seq` None while still running) and end `status` (completed / failed / cancelled /
    running / interrupted), the resolved-input hash it ran on, and the application event kinds it
    `emitted` (in seq order). **"interrupted"** = started, no end-record, AND the run is over
    (terminal or paused) — it will never complete (e.g. a Producer cut off by a pause); "running"
    is reserved for an un-ended instance in a still-INCOMPLETE run (genuinely live).

    RENDERING CONCURRENCY — read this before drawing a run-as-graph. The seq-span faithfully
    encodes bus-timeline concurrency (a Producer is running at seq N iff started_seq <= N <
    ended_seq), BUT in fast or deterministic runs the single writer serializes near-instant
    Producers, so the spans can look SEQUENTIAL even for genuinely concurrent Producers (in the
    CI demo fixtures, the fast reviewers have disjoint spans). Derive "ran concurrently" from the
    SPAWN STRUCTURE — Producers spawned by one firing / at adjacent seqs (e.g. all sharing a
    trigger_id and spawning at adjacent `fired_seq`) are concurrent siblings — NOT from
    span-overlap alone, or a fast run will flatten the parallelism the UI must show. Anchor each
    lifespan at `fired_seq` (when it was scheduled), the t-free firing anchor the design uses."""

    kind: str
    instance: str
    parent: str | None
    trigger_id: str | None
    firing_key: str | None
    input_sha256: str | None
    fired_seq: int | None
    started_seq: int | None
    ended_seq: int | None
    status: ProducerStatus
    emitted: tuple[str, ...]


class RunGraph(Struct, frozen=True):
    """The dynamic run-as-graph: every Producer instance (the spawn forest, in spawn-seq order)
    with its span and emitted events, plus the run-level outcome the handoff's outcome surface
    needs. `status` is "incomplete" | "paused" | "finalised" | "failed" (the last three match
    RunResult.status). **"failed"** is a RUN-level failure with a terminal RunFinalised (the run
    died: view_failure / kernel_error / stuck_quiescent) — distinct from a clean "finalised" run
    that had Producer-level failures inside it (that finished-!=-worked case is the per-instance
    statuses, not the run status). **"incomplete"** is no terminal RunFinalised: either still
    being written (if live-followed) OR torn/medium-failed (the fsync-gate path fails WITHOUT a
    terminal — absence-of-terminal encodes medium failure); a static "incomplete" read is NOT a
    clean "running", so a torn record never reads as fine (§7.2). "paused" awaits external input.
    `final_reason` is the RunFinalised reason (None for an ordinary finalise; the failure reason
    for a "failed" run). `paused_on` is the resume_condition when status is PAUSED."""

    instances: tuple[ProducerInstance, ...]
    status: RunStatus
    final_reason: str | None
    paused_on: str | None


def run_graph(record: Any) -> RunGraph:
    """The DYNAMIC run-as-graph: every Producer instance with its spawn link, lifecycle span,
    status, and emitted events — the concurrent, causal shape of how the run grew. Built from the
    TriggerFired / ProducerStarted-Completed-Failed-Cancelled lifecycle events (the same instance/
    parent links the inspect provenance surface uses). Instances are returned in spawn order
    (by started_seq)."""
    envelopes = load_envelopes(record)
    fired: dict[str, dict[str, Any]] = {}  # instance -> TriggerFired payload (+ its seq)
    started: dict[str, dict[str, Any]] = {}  # instance -> {ref, seq}
    ended: dict[str, tuple[ProducerStatus, int]] = {}  # instance -> (status, end seq)
    emitted: dict[str, list[str]] = {}  # instance -> app event kinds, seq order
    finalised = False
    final_reason: str | None = None
    paused = False
    paused_at: int | None = None
    paused_resume_condition: str | None = None
    last_seq = -1

    for env in envelopes:
        kind = str(env.get("kind", ""))
        payload = env.get("payload") or {}
        seq = int(env.get("seq", -1))
        last_seq = max(last_seq, seq)
        if kind == _TRIGGER_FIRED:
            inst = payload.get("instance")
            if isinstance(inst, str):
                fired[inst] = {**payload, "_seq": seq}
        elif kind == PRODUCER_STARTED:
            ref = payload.get("producer")
            if isinstance(ref, dict) and isinstance(ref.get("instance"), str):
                started[ref["instance"]] = {"ref": ref, "seq": seq}
        elif kind in _END_KINDS:
            ref = payload.get("producer")
            if isinstance(ref, dict) and isinstance(ref.get("instance"), str):
                ended[ref["instance"]] = (_END_KINDS[kind], seq)
        elif kind == RUN_FINALISED:
            finalised = True
            reason = payload.get("reason")
            final_reason = str(reason) if reason else None
        elif (
            kind == TERMINATION_MATCHED
            and payload.get("decision") == Decision.PAUSE_AWAIT_INPUT.value
        ):
            paused_at = seq
            rc = payload.get("resume_condition")
            paused_resume_condition = str(rc) if rc else None
        elif not kind.startswith("substrate."):
            ref = env.get("producer")
            if isinstance(ref, dict) and isinstance(ref.get("instance"), str):
                emitted.setdefault(ref["instance"], []).append(kind)

    # A pause is the run's state only while nothing follows it: a session pauses at the end of
    # every turn and resumes on the next, so a pause that a resume followed is history (lens
    # audit F029: a live session mid-turn read as PAUSED, its running Producers "interrupted").
    paused = paused_at is not None and paused_at == last_seq
    instances: list[ProducerInstance] = []
    for inst in set(fired) | set(started):  # the union: a firing and/or a start witnesses it
        f = fired.get(inst, {})
        s = started.get(inst)
        ref = s["ref"] if s else {}
        end = ended.get(inst)
        if end is not None:
            status, end_seq = end
        else:
            # no end-record: "running" only while the run is still INCOMPLETE (genuinely un-ended);
            # in a terminal/paused run it will NEVER end -> "interrupted" (e.g. a Producer cut off by
            # a pause: started, never completed, run over). A finished run must not show live work. #38
            status, end_seq = (
                (ProducerStatus.INTERRUPTED if (finalised or paused) else ProducerStatus.RUNNING),
                None,
            )
        started_seq = s["seq"] if s else f.get("_seq")
        instances.append(
            ProducerInstance(
                kind=str(f.get("factory") or ref.get("kind") or "<unknown>"),
                instance=inst,
                parent=ref.get("parent"),
                trigger_id=f.get("trigger_id"),
                firing_key=f.get("firing_key"),
                input_sha256=f.get("input_sha256"),
                fired_seq=f.get("_seq"),
                started_seq=started_seq,
                ended_seq=end_seq,
                status=status,
                emitted=tuple(emitted.get(inst, [])),
            )
        )
    # spawn order: by started_seq (None sorts last), then instance for stability.
    instances.sort(
        key=lambda p: (p.started_seq if p.started_seq is not None else 1 << 62, p.instance)
    )
    # run-level outcome, matching RunResult.status: a run-level FAILURE finalise (view_failure /
    # kernel_error / stuck_quiescent) is "failed" — NOT "finalised" — so the outcome surface can't
    # render a kernel-errored run as a clean green finalise (§7.2). A clean finalise that had
    # Producer-level failures INSIDE it is still "finalised"; that finished-!=-worked case is the
    # per-instance statuses + the failure tally, not the run-level status. (review #30 finding 1.)
    if finalised:
        run_status = (
            RunStatus.FAILED if final_reason in _RUN_FAILURE_REASONS else RunStatus.FINALISED
        )
    elif paused:
        run_status = RunStatus.PAUSED
    else:
        # no terminal RunFinalised: the record is INCOMPLETE — either still being written (if it
        # is being live-followed) OR torn/medium-failed (the fsync-gate path fails the run WITHOUT
        # a RunFinalised — absence-of-terminal IS the encoding of medium failure). Events alone
        # cannot distinguish the two; that is out-of-band (the follow/liveness context). The §7.2-
        # safe default for a STATIC read is "incomplete" (indeterminate / not a clean "running"),
        # so a torn record never reads as fine. (review #31.)
        run_status = RunStatus.INCOMPLETE
    return RunGraph(
        instances=tuple(instances),
        status=run_status,
        final_reason=final_reason,
        paused_on=paused_resume_condition if run_status == RunStatus.PAUSED else None,
    )

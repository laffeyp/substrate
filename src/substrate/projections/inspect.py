# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Inspection, provenance, divergence — the read-side query surface (technical §14).

All functions are deterministic queries over a recorded run record (a root path or an
iterable of envelope dicts — the same surface the test helpers accept). They return
typed structures that cite sequence numbers; they never emit to the bus and never
mutate the record (F-OBS-6). The vocabulary discipline holds in the output: typed
fields, sequence numbers, the eight-word vocabulary — no prose.

Provenance closure (F-OBS-2 / F-OBS-3 / conformance check 11): every Producer in a
recorded run traces to exactly one of substrate.TriggerFired, a resume event, or
substrate.RunStarted; the chain is acyclic by construction (trace_ancestry follows
producer.parent, which is a strict-ancestor relation minted at spawn time). The link
from a running Producer back to its exact firing uses the TriggerFired.instance field
(P-TRIGGERFIRED-INSTANCE) — without it explain_producer would have to re-derive the
firing from the resolved-input hash.

Divergence (D-8 / conformance check 13): first_divergence builds the comparison
sequence (kind, decision_identity, payload_sha256) in seq order and returns the first
index where two records differ. Supplementary metadata (t, host, config echoes) never
enters the comparison — only kind and the canonical payload hash.
"""

from __future__ import annotations

import re
from typing import Any

from msgspec import Struct

from ..constants import INITIAL_TRIGGER_ID, PRODUCER_STARTED, RUN_STARTED, TRIGGER_FIRED
from ..encoding import content_hash
from ..errors import ProducerNotFound, SequenceOutOfRange
from ..protocols import View
from ..record.record import load_envelopes
from ..types import Event

# Producer-creating causes (F-OBS-2): a Producer traces to one of these.
_TRIGGER_FIRED = TRIGGER_FIRED
_RUN_STARTED = RUN_STARTED
_INITIAL = INITIAL_TRIGGER_ID


class Explanation(Struct, frozen=True):
    """The typed cause of one Producer's existence (technical §14: explain_producer).

    `cause` is one of "TriggerFired" | "RunStarted" (an initial Producer's firing
    attributes to the run open). `at_seq` is the seq of the firing frame. `input_sha256`
    is the resolved-input content hash recorded at the firing — the citable identity of
    what the Producer ran with.
    """

    kind: str
    instance: str
    parent: str | None
    cause: str
    trigger_id: str | None
    firing_key: str | None
    input_sha256: str | None
    at_seq: int


class Divergence(Struct, frozen=True):
    """The first point two records of the same topology diverge (technical §14 / D-8).

    `index` is the position in the seq-ordered comparison sequence; `seq` is the bus
    seq of the diverging frame in record A (or the shorter record's end). `kind_a` /
    `kind_b` and `hash_a` / `hash_b` are the (kind, canonical payload hash) pair that
    differs. When one record is a strict prefix of the other, the longer record's extra
    frame is the divergence and the shorter side's fields are None.
    """

    index: int
    seq: int
    kind_a: str | None
    kind_b: str | None
    hash_a: str | None
    hash_b: str | None


def _parse_producer_id(producer: str) -> str:
    """Accept either a bare instance id or the design `kind[instance]` form; return the
    instance id (the unique-within-run identity that lifecycle/TriggerFired frames key on)."""
    if producer.endswith("]") and "[" in producer:
        return producer[producer.index("[") + 1 : -1]
    return producer


def _firing_index(envelopes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map a spawned Producer instance -> its TriggerFired payload. The TriggerFired
    .instance field (P-TRIGGERFIRED-INSTANCE) is the spawn link used for provenance."""
    index: dict[str, dict[str, Any]] = {}
    for env in envelopes:
        if env.get("kind") == _TRIGGER_FIRED:
            payload = env.get("payload") or {}
            inst = payload.get("instance")
            if isinstance(inst, str):
                index[inst] = {"payload": payload, "seq": env.get("seq")}
    return index


def _started_index(envelopes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map a Producer instance -> its ProducerStarted producer ref {kind,instance,parent}."""
    index: dict[str, dict[str, Any]] = {}
    for env in envelopes:
        if env.get("kind") == PRODUCER_STARTED:
            ref = (env.get("payload") or {}).get("producer")
            if isinstance(ref, dict) and isinstance(ref.get("instance"), str):
                index[ref["instance"]] = ref
    return index


def _explain_one(
    instance: str,
    firings: dict[str, dict[str, Any]],
    starts: dict[str, dict[str, Any]],
) -> Explanation:
    fired = firings.get(instance)
    if fired is None:
        raise ProducerNotFound(
            f"no substrate.TriggerFired with instance={instance!r} in the record "
            f"(provenance closure broken, or the id is wrong)"
        )
    payload = fired["payload"]
    ref = starts.get(instance, {})
    # An initial Producer fires under trigger_id "__initial__" and attributes to the run
    # open (RunStarted); every other firing attributes to its TriggerFired.
    trigger_id = payload.get("trigger_id")
    cause = "RunStarted" if trigger_id == _INITIAL else "TriggerFired"
    return Explanation(
        kind=str(payload.get("factory") or ref.get("kind") or "<unknown>"),
        instance=instance,
        parent=ref.get("parent"),
        cause=cause,
        trigger_id=trigger_id,
        firing_key=payload.get("firing_key"),
        input_sha256=payload.get("input_sha256"),
        at_seq=int(fired["seq"]),
    )


def explain_producer(record: Any, producer: str) -> Explanation:
    """The typed cause of `producer`'s existence: the TriggerFired that scheduled it
    (or the run open, for an initial Producer), with its resolved-input hash. O(record)
    once. Raises ProducerNotFound if the instance has no firing on the record."""
    envelopes = load_envelopes(record)
    instance = _parse_producer_id(producer)
    return _explain_one(instance, _firing_index(envelopes), _started_index(envelopes))


def trace_ancestry(record: Any, producer: str) -> tuple[Explanation, ...]:
    """The spawn chain from `producer` up to the root, root-LAST: index 0 is `producer`
    itself, each subsequent entry its parent, ending at the initial Producer (cause
    RunStarted). Acyclic by construction; a missing link raises ProducerNotFound. The
    chain is the provenance-closure witness (conformance check 11)."""
    envelopes = load_envelopes(record)
    firings = _firing_index(envelopes)
    starts = _started_index(envelopes)
    chain: list[Explanation] = []
    seen: set[str] = set()
    current: str | None = _parse_producer_id(producer)
    while current is not None:
        if current in seen:  # defensive: the spawn relation is acyclic, but never loop
            raise ProducerNotFound(f"cycle detected in ancestry at instance={current!r}")
        seen.add(current)
        exp = _explain_one(current, firings, starts)
        chain.append(exp)
        current = exp.parent
    return tuple(chain)


def view_at(record: Any, seq: int, view: View) -> Any:
    """Reconstruct a View's state as observed at sequence `seq` (Level-1 replay truncated
    at seq): fold every matching event with seq <= `seq` into the provided View instance
    and return its value() (technical §14, conformance check 12 — view-at fidelity).

    Takes a View INSTANCE, not a name: a record stores event payloads, not View code, so
    the caller supplies the View whose update()/subscription define the fold. (Spec §16
    signature is `view_at(record, seq, view: str)` assuming the topology's View code is
    available by name; the instance form is the honest dependency — flagged as a spec
    flow-back in BLACKBOARD.) The View should be fresh; folding is not idempotent.

    Blob Claim Checks are redeemed before folding (Sprint 095), so view_at at a seq equals the
    live View value at that seq. An already-loaded envelope iterable is folded as given."""
    envelopes = load_envelopes(record, resolve_blobs=True)
    max_seq = max((int(e["seq"]) for e in envelopes if "seq" in e), default=-1)
    if seq < 0 or seq > max_seq:
        raise SequenceOutOfRange(
            f"seq {seq} is outside the record [0, {max_seq}] (view_at fidelity, §14)"
        )
    sub = view.subscription
    for env in envelopes:
        if int(env.get("seq", -1)) > seq:
            break  # envelopes are yielded in dense seq order; nothing further qualifies
        event = Event.from_envelope(env)
        if sub.matches(event):
            view.update(event)
    return view.value()


def decisions_between(record: Any, a: int, b: int) -> tuple[Any, ...]:
    """Every runtime decision (substrate.* frame) with a <= seq <= b, in seq order, as
    reconstructed Event objects (technical §14). The kernel's decision record over a
    sequence window — Level-2 reads, no re-execution."""
    if a > b:
        raise SequenceOutOfRange(f"decisions_between: a={a} > b={b}")
    envelopes = load_envelopes(record)
    out: list[Any] = []
    for env in envelopes:
        s = int(env.get("seq", -1))
        if a <= s <= b and str(env.get("kind", "")).startswith("substrate."):
            out.append(Event.from_envelope(env))
    return tuple(out)


def first_divergence(rec_a: Any, rec_b: Any) -> Divergence | None:
    """The first index where two records' D-8 comparison sequences differ, or None if
    they are equivalent (technical §14, conformance check 13). The comparison sequence is
    (kind, canonical payload hash) per frame in seq order; supplementary metadata (t,
    host, config) is excluded by construction (it is never hashed here)."""
    env_a = load_envelopes(rec_a)
    env_b = load_envelopes(rec_b)
    seq_a = [(str(e.get("kind")), _payload_hash(e)) for e in env_a]
    seq_b = [(str(e.get("kind")), _payload_hash(e)) for e in env_b]
    # (seq_a / seq_b are the D-8 comparison sequences: (kind, decision-identity hash).)
    n = min(len(seq_a), len(seq_b))
    for i in range(n):
        if seq_a[i] != seq_b[i]:
            return Divergence(
                index=i,
                seq=int(env_a[i].get("seq", i)),
                kind_a=seq_a[i][0],
                kind_b=seq_b[i][0],
                hash_a=seq_a[i][1],
                hash_b=seq_b[i][1],
            )
    if len(seq_a) == len(seq_b):
        return None
    # One record is a strict prefix of the other — the first extra frame is the divergence.
    if len(seq_a) > len(seq_b):
        extra = env_a[n]
        return Divergence(
            index=n,
            seq=int(extra.get("seq", n)),
            kind_a=seq_a[n][0],
            kind_b=None,
            hash_a=seq_a[n][1],
            hash_b=None,
        )
    extra = env_b[n]
    return Divergence(
        index=n,
        seq=int(extra.get("seq", n)),
        kind_a=None,
        kind_b=seq_b[n][0],
        hash_a=None,
        hash_b=seq_b[n][1],
    )


# ── helpers ──────────────────────────────────────────────────────────────────--
# The D-8 supplementary-metadata exclusion set (the equivalence relation's exact shape;
# documented in process/signals/0.2-rationale.md and technical_spec D-8). D-8 is "(event-kind
# sequence, DECISION-IDENTITY sequence, canonical payload hashes), supplementary metadata
# excluded" (product §D-8). On `substrate.*` lifecycle frames, the following are
# run-varying SUPPLEMENTARY noise, NOT decision identity, and are excluded from the
# comparison hash; without this, two runs of the SAME topology spuriously diverge:
#   - run_id, instance          fresh ULIDs / the run id (per-run identity)
#   - producer.{instance,parent} the subject ref's ULIDs (kind is kept — it IS identity)
#   - measured_us               wall-clock microseconds of a predicate call
#                               (PredicateQuarantined budget path) — a timing MEASUREMENT
#   - error                     a repr(exc) that can embed tmp paths / object addresses —
#                               normalized to a stable sentinel (the frame KIND already
#                               carries "a failure of this class happened here")
# The decision identity that IS kept: input_sha256, firing_key, reason, trigger_id/route_id,
# policy/decision, k (a config constant), view/seq (real positions). Application payloads
# are NEVER touched (their content IS the decision being compared).
_D8_DROP_KEYS = frozenset({"run_id", "instance", "measured_us"})
# Free-form diagnostic strings that embed a repr(exc) — a cross-run-varying tail (tmp
# paths, object addresses). Both `error` (InputBuildFailed/ProducerFailed/RunFinalised{
# kernel_error}/PredicateQuarantined{exception}) AND `finalisation_payload_dropped`'s
# raising-callback branch ("finalisation callback raised: <repr>") carry one. Normalized
# to a CLASS-PRESERVING sentinel (`<ValueError>`) so the error CLASS still localizes a
# divergence while the variable repr tail does not spuriously diverge two runs.
_D8_NORMALIZE_KEYS = frozenset({"error", "finalisation_payload_dropped"})

# An exception class name as it leads a repr(exc): `ValueError(...)`, or after a prefix
# like `finalisation callback raised: ValueError(...)`.
_EXC_CLASS_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning|Interrupt))\b")


def _error_sentinel(value: Any) -> str:
    """A stable, class-preserving sentinel for a free-form error/diagnostic string: extract
    the first exception-class token and return `<ClassName>`; fall back to `<error>` when no
    class is recognisable. Class is decision-identity-ish (a different failure class IS a
    real divergence); the repr tail (paths/addresses) is supplementary."""
    if not isinstance(value, str):
        return "<error>"
    m = _EXC_CLASS_RE.search(value)
    return f"<{m.group(1)}>" if m else "<error>"


def _d8_normalize_lifecycle(payload: Any) -> Any:
    """Normalize a substrate.* lifecycle payload for D-8: drop the run-varying supplementary
    keys (run_id/instance/measured_us), reduce any `producer` ref to {kind}, and replace
    free-form error/diagnostic reprs (`error`, `finalisation_payload_dropped`) with a
    class-preserving sentinel. Lifecycle payloads are flat (no recursion needed); the
    decision-identity fields (input_sha256/firing_key/reason/k/...) are kept."""
    if not isinstance(payload, dict):
        return payload
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _D8_DROP_KEYS:
            continue
        if key == "producer" and isinstance(value, dict):
            out[key] = {"kind": value.get("kind")}
        elif key in _D8_NORMALIZE_KEYS:
            out[key] = _error_sentinel(value)  # class-preserving; repr tail is supplementary
        else:
            out[key] = value
    return out


def _payload_hash(env: dict[str, Any]) -> str:
    """The canonical decision-identity hash for D-8 comparison. For a substrate.* frame the
    kernel-minted run identity is normalized away; an APPLICATION frame's payload is hashed
    verbatim (its content IS the decision being compared)."""
    payload = env.get("payload")
    if str(env.get("kind", "")).startswith("substrate."):
        payload = _d8_normalize_lifecycle(payload)
    return content_hash(payload)


# spec-audit: 2026-09-01

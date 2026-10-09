# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Composition — a substrate as a Producer (technical §20; kernel "composes with itself";
F-COMP-1..3; conformance check 7).

An embedded substrate is a Producer whose factory constructs an INNER `Runtime` at its own
record root and emits the inner run's events back onto the OUTER bus — but only the kinds
its ExportMap declares. It presents the ordinary Producer contract
`start(input) -> AsyncIterable[Event]`, so the outer runtime treats it like any Producer:
the translated outer-schema events it yields go through ordinary OUTER admission, and THAT
is the entire backpressure story (§20) — outer congestion slows the embedded Producer's
yields; the inner run proceeds untouched at its own root, throttled only at this export
point. There is no second backpressure path.

OPERATOR NOTE: because the inner run is NOT throttled by outer congestion, under sustained
outer backpressure with a fast inner Producer the INNER RECORD is the buffer and grows ON
DISK at the inner root (bounded by inner termination — the inner run finishes regardless of
how fast the outer side drains). A congested export point therefore manifests as inner-root
disk growth, not as inner stalling; size it for the inner run's full output, not the export
rate.

Rules (§20):
  - The boundary translator subscribes to EXACTLY the export-mapped inner kinds (an
    inner-side read of the inner record via the read-only follower). Per matching inner
    frame it builds the outer-schema event and yields it; the outer append cycle validates
    it at the outer boundary like any emission. PROVENANCE: the inner→outer link is at RUN
    granularity — the inner record root is recorded in the outer TriggerFired.resolved_input
    and an inner-run failure carries the inner run_id on substrate.ProducerFailed. §20 also
    asks for a PER-FRAME {inner_run_id, inner_seq} stamp "into producer metadata", but the
    locked wire ProducerRef is {kind,instance,parent} (no metadata slot) and an outer kind
    may not be substrate.*, so per-frame inner provenance has nowhere to ride on the current
    envelope — surfaced as P-COMPOSITION-INNER-PROVENANCE (proposals.json) for an Architect
    ruling + vocab bump; NOT stamped here.
  - Default export = the inner `substrate.RunFinalised` payload only (carrying the inner
    record root). Inner `substrate.*` control-plane events NEVER cross unless explicitly
    mapped; unmapped application kinds never cross.
  - Inner run failure surfaces as ONE `substrate.ProducerFailed` on the outer bus carrying
    the inner `run_id`; the inner record stays complete at its own root.
  - Nesting depth is unbounded (F-COMP-3) — but each level constructs its own
    Runtime/writer/admission-queue/log/root, so depth costs real RAM + tasks per level.
    Unbounded is a semantic guarantee, not a claim that depth is free.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from ..constants import RUN_FINALISED, RUN_STARTED, RunStatus
from ..errors import SubstrateError
from ..record.live import LiveRecord
from .runtime import Runtime
from .topology import TopologyBuilder

# An export rule: the outer Struct type to emit for a given inner kind, plus a transform
# that builds it from the inner frame's payload dict. The transform defaults to splatting
# the inner payload into the outer Struct (outer_type(**inner_payload)).
ExportRule = tuple[type, Callable[[dict[str, Any]], Any]]


class EmbeddedRunFailed(SubstrateError):
    """An embedded substrate's inner run did not finalise normally. Raised by the embedded
    Producer so the OUTER runtime records ONE substrate.ProducerFailed carrying the inner
    run_id (technical §20). The inner record stays complete at its own root."""

    def __init__(self, message: str, *, inner_run_id: str, inner_root: str) -> None:
        super().__init__(message)
        self.inner_run_id = inner_run_id
        self.inner_root = inner_root


def _default_transform(outer_type: type) -> Callable[[dict[str, Any]], Any]:
    """The default translator for an export rule: splat the inner frame's payload dict into
    the outer Struct. Authors pass an explicit transform when the shapes differ."""

    def _t(inner_payload: dict[str, Any]) -> Any:
        return outer_type(**inner_payload) if inner_payload else outer_type()

    return _t


_RUN_FINALISED = RUN_FINALISED


def embedded_substrate(
    topology: Callable[[TopologyBuilder], None],
    *,
    exports: dict[str, type | ExportRule] | None = None,
    default_export: type | ExportRule | None = None,
    inner_poll_ms: int = 5,
) -> Callable[[Any], AsyncIterator[Any]]:
    """Build a Producer (the `start` callable) that runs `topology` as an INNER substrate and
    exports the mapped inner kinds onto the outer bus (technical §20).

    `exports` maps an inner event kind to either an outer Struct TYPE (default transform =
    splat the inner payload) or an `(outer_type, transform)` pair. Inner `substrate.*` kinds
    NEVER cross unless explicitly mapped; unmapped application kinds never cross.

    DEFAULT EXPORT (F-COMP-1 / §20: "default export = inner RunFinalised only"): the inner
    `substrate.RunFinalised` is exported by default. Because an OUTER Producer kind may not
    emit a `substrate.*` kind (reserved namespace, F-OBS-5), the default export needs an
    author-named OUTER carrier Struct — pass it as `default_export` (a type, or an
    (outer_type, transform) pair; the transform receives the inner RunFinalised payload,
    which carries the inner root / finalisation_payload). When `default_export` is given and
    `exports` does not already map RunFinalised, a RunFinalised→default_export rule is
    installed. If NEITHER is given, the inner RunFinalised does not cross as a frame — the
    inner root is still recorded in the outer TriggerFired resolved input (the §20 provenance
    link) and the inner record is complete at its own root. (The "default export = RunFinalised"
    wording assumes an outer carrier; that the carrier must be author-named is a tech-spec §20
    flow-back — see BLACKBOARD.)

    The returned callable is the Producer `start`: the outer runtime calls it with the sealed
    resolved input (which carries the inner record root under input["inner_root"]) and
    consumes the translated outer events under outer admission.

    CONTRACT — every embedded-substrate topology MUST thread `inner_root` in the embedded
    Producer's resolved input (e.g. `b.initial("embedded", input={"inner_root": str(path)})`,
    or a trigger input_builder that supplies it). This is a deliberately STRICTER contract
    than an optional fallback: it is the correct trade for run-granularity provenance — the
    inner root is then unconditionally recorded in the outer TriggerFired.resolved_input, so
    the inner run is always citable from the outer record (§20). Omitting it raises
    InnerRootRequired, which surfaces as a recorded outer substrate.ProducerFailed (not a
    fabricated, un-citable fallback root)."""

    def _to_rule(rule: type | ExportRule) -> ExportRule:
        if isinstance(rule, tuple):
            return rule
        return (rule, _default_transform(rule))

    rules: dict[str, ExportRule] = {k: _to_rule(v) for k, v in (exports or {}).items()}
    if default_export is not None and _RUN_FINALISED not in rules:
        rules[_RUN_FINALISED] = _to_rule(default_export)

    async def start(input: Any) -> AsyncIterator[Any]:
        # Resolve the inner record root: from the input (the outer TriggerFired's resolved
        # input records it, §20) or a fresh child of the cwd. Each embedding gets its OWN
        # root — the inner record is complete and independent there.
        inner_root = _inner_root_from_input(input)
        inner_rt = Runtime(inner_root)
        run_task: asyncio.Task[Any] = asyncio.ensure_future(inner_rt.run(topology))
        follower = LiveRecord(inner_root, poll_ms=inner_poll_ms)
        inner_run_id = ""

        async def _drain_translate() -> AsyncIterator[Any]:
            nonlocal inner_run_id
            for env in follower.read_new():
                kind = str(env.get("kind", ""))
                if kind == RUN_STARTED:
                    rid = (env.get("payload") or {}).get("run_id")
                    if isinstance(rid, str):
                        inner_run_id = rid
                rule = rules.get(kind)
                if rule is None:
                    continue  # unmapped (incl. every inner substrate.* unless mapped): no cross
                payload = env.get("payload") or {}
                # A FAILURE RunFinalised (reason: view_failure / kernel_error) must NOT be
                # translated through a success carrier: its payload is {reason,view,seq,error},
                # which would mis-splat into the success Struct -> an outer
                # ProducerEmittedInvalidEvent IN ADDITION to the ProducerFailed (double signal).
                # The default/RunFinalised export carries the SUCCESS finalisation only;
                # inner-run failure surfaces solely as the one outer ProducerFailed below.
                if kind == _RUN_FINALISED and isinstance(payload, dict) and payload.get("reason"):
                    continue
                _outer_type, transform = rule
                # build the outer Struct; the outer append cycle validates it at the boundary
                yield transform(payload if isinstance(payload, dict) else {})

        result = None
        try:
            # Translate inner frames as they appear; each yield is subject to OUTER admission
            # (the runtime's _submit_emission), which is the whole backpressure story.
            # NOTE (final-drain ordering, load-bearing): run_task.done() flips only AFTER the
            # inner Runtime.run() coroutine returns, which is AFTER its finally closes+flushes
            # the inner record (runtime.py). So when the loop exits, the inner record's bytes
            # — incl. RunFinalised — are already on disk, and the final drain reads them. A
            # missed inner fsync-before-return would silently drop the last exported frames.
            while not run_task.done():
                async for outer_event in _drain_translate():
                    yield outer_event
                await asyncio.sleep(inner_poll_ms / 1000.0)
            # final drain: inner frames written between the last poll and inner completion
            async for outer_event in _drain_translate():
                yield outer_event
            result = run_task.result()  # re-raises if the inner run task itself raised
        finally:
            if not run_task.done():
                run_task.cancel()
                try:
                    await run_task
                except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001 — kernel cleanup path (REVIEW-2026-08-28 Q7): cannot propagate from finally; log the class name so a bug during teardown leaves a trace on stderr rather than silent information loss.
                    import logging

                    logging.getLogger(__name__).warning(
                        "composition cleanup swallowed inner run cancel: %r", exc
                    )

        # Inner failure surfaces as ONE outer ProducerFailed carrying the inner run_id (§20).
        # The run_id is taken from the inner RunResult (authoritative + always present), NOT
        # scraped from polled frames (which could be empty under a fast inner-failure race).
        if result is not None and getattr(result, "status", None) == RunStatus.FAILED:
            rid = getattr(result, "run_id", "") or inner_run_id
            raise EmbeddedRunFailed(
                f"embedded substrate inner run {rid} failed",
                inner_run_id=rid,
                inner_root=str(inner_root),
            )

    # SINGLE SOURCE OF TRUTH for the export map (no parallel hand-maintained b.export copy):
    # attach the {inner_kind -> outer_schema_name} map the producer ACTUALLY consumes to the
    # start callable, so the runtime can derive the RunStarted manifest's exports section from
    # the same map the boundary translates by. The manifest can never drift from the real map.
    start.__substrate_export_map__ = {  # type: ignore[attr-defined]
        inner: getattr(outer_type, "__name__", str(outer_type))
        for inner, (outer_type, _t) in rules.items()
    }
    return start


class InnerRootRequired(ValueError):
    """An embedded substrate's resolved input did not carry `inner_root`. §20 requires the
    inner record root to be RECORDED in the outer TriggerFired's resolved input so the inner
    run is citable from the outer record (run-granularity provenance). A fallback root chosen
    here would be recorded NOWHERE on the outer bus and the inner run would be un-citable, so
    we refuse rather than create an un-traceable inner run. Raised inside the embedded
    Producer; surfaces as a recorded outer event (ProducerFailed/InputBuildFailed)."""


def _inner_root_from_input(input: Any) -> Path:
    """The inner record root, read REQUIRED from the resolved input (the outer TriggerFired
    records it, §20 — that recording IS the run-granularity provenance link). Refuse if
    absent: a fabricated fallback root would be citable from nowhere on the outer record.
    The sealed input is typically a (read-only) mapping."""
    get = getattr(input, "get", None)
    if callable(get):
        root = get("inner_root")
        if root:
            return Path(root)
    raise InnerRootRequired(
        "embedded substrate input must carry 'inner_root' (the inner record root, recorded in "
        "the outer TriggerFired.resolved_input for run-granularity provenance — §20)"
    )

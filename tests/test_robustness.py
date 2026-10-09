# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Priority-1 robustness tests: the sanitize-or-log cluster, blob offload, persistent
locking, trigger-level logical cooldown, view-failure finalisation, and the empty-View
registration guard. These cover the external-review findings — every ingestion point
that accepts user values must record an event or sanitize, never crash the writer."""

import math

import pytest
from msgspec import Struct

from substrate.api import (
    Logical,
    PerEvent,
    PerKey,
    Runtime,
    Subscription,
    assert_event,
    assert_no_event,
    quiescence,
    read_record,
    threshold_count,
)
from substrate.encoding import safe_raw, try_canonical
from substrate.errors import BusLockedError
from substrate.kernel.topology import RegistrationError, TopologyBuilder


# ── shared encoding helper (try_canonical / safe_raw) ──────────────────────────
def test_try_canonical_ok_round_trip():
    sc = try_canonical({"a": 1, "b": [2, 3]})
    assert sc.ok
    assert sc.builtins == {"a": 1, "b": [2, 3]}
    assert sc.hash.startswith("sha256:")
    assert sc.nbytes == len(sc.raw_bytes)


def test_try_canonical_out_of_range_int_is_not_ok():
    sc = try_canonical({"big": 2**60})
    assert not sc.ok
    assert sc.reason == "non_canonical_value"
    assert sc.at_path == "$.big"
    # raw must itself be safe to frame: the giant int has been stringified
    assert isinstance(sc.raw["big"], str)
    assert try_canonical(sc.raw).ok


def test_try_canonical_nonfinite_float_is_not_ok():
    sc = try_canonical({"x": math.inf})
    assert not sc.ok
    assert sc.reason == "non_canonical_value"
    assert try_canonical(sc.raw).ok  # the rendering is canonical-safe


def test_safe_raw_never_reintroduces_a_crashing_value():
    # an out-of-range int passed through msgspec.to_builtins would survive raw and then
    # crash at frame-time; safe_raw stringifies it.
    rendered = safe_raw({"n": 2**60, "ok": "yes"})
    assert try_canonical(rendered).ok
    assert isinstance(rendered["n"], str)


# ── the five ingestion paths through the runtime ───────────────────────────────
class Ok(Struct, frozen=True):
    n: int


class BadInt(Struct, frozen=True):
    big: int


async def emits_bad_int(_input):
    yield BadInt(big=2**60)  # declared, but out of JCS-safe range -> non_canonical_value


def _bad_int_topo(b):
    b.producer_kind("p", schemas=[BadInt], schema_version=1, factory=lambda: emits_bad_int)
    b.initial("p", input=None)
    b.termination(quiescence())


async def test_emission_non_canonical_value_is_logged_not_crashed(tmp_path):
    # path 1: the emission boundary; reason non_canonical_value with a safe raw_payload.
    result = await Runtime(tmp_path / "run").run(_bad_int_topo)
    assert result.status == "finalised"
    inv = assert_event(
        tmp_path / "run", "substrate.ProducerEmittedInvalidEvent", reason="non_canonical_value"
    )
    assert inv["payload"]["at_path"] == "$.big"
    # the raw payload was preserved but stringified so it framed cleanly
    assert isinstance(inv["payload"]["raw_payload"]["big"], str)


async def producer_ok(_input):
    yield Ok(n=1)


def _bad_resolved_input_topo(b):
    b.producer_kind("a", schemas=[Ok], schema_version=1, factory=lambda: producer_ok)
    b.producer_kind("c", schemas=[Ok], schema_version=1, factory=lambda: producer_ok)
    b.initial("a", input=None)
    # the input_builder returns a non-canonical value (out-of-range int) -> InputBuildFailed
    b.trigger(
        "t",
        subscription=Subscription(kinds=frozenset({"Ok"})),
        predicate=lambda ctx: True,
        starts="c",
        input_builder=lambda ctx: {"big": 2**60},
        policy=PerEvent(),
    )
    b.termination(quiescence())


async def test_non_canonical_resolved_input_becomes_input_build_failed(tmp_path):
    # path 2: resolved trigger input; no Producer "c" starts.
    await Runtime(tmp_path / "run").run(_bad_resolved_input_topo)
    assert_event(tmp_path / "run", "substrate.InputBuildFailed", trigger_id="t")
    starts = [
        e
        for e in read_record(tmp_path / "run")
        if e["kind"] == "substrate.ProducerStarted" and e["payload"]["producer"]["kind"] == "c"
    ]
    assert starts == []


def _bad_initial_input_topo(b):
    b.producer_kind("p", schemas=[Ok], schema_version=1, factory=lambda: producer_ok)
    b.initial("p", input={"big": 2**60})  # non-canonical initial input
    b.termination(quiescence())


async def test_non_canonical_initial_input_becomes_input_build_failed(tmp_path):
    # path 3: initial input at bootstrap; recorded, never crashes startup.
    result = await Runtime(tmp_path / "run").run(_bad_initial_input_topo)
    assert_event(tmp_path / "run", "substrate.InputBuildFailed", trigger_id="__initial__")
    assert_no_event(tmp_path / "run", "substrate.ProducerStarted")
    assert result.status in ("finalised", "failed")


def _bad_perkey_topo(b):
    b.producer_kind("a", schemas=[Ok], schema_version=1, factory=lambda: producer_ok)
    b.producer_kind("c", schemas=[Ok], schema_version=1, factory=lambda: producer_ok)
    b.initial("a", input=None)
    # the PerKey key fn returns a non-canonical value (an out-of-JCS-range int)
    b.trigger(
        "t",
        subscription=Subscription(kinds=frozenset({"Ok"})),
        predicate=lambda ctx: True,
        starts="c",
        input_builder=lambda ctx: None,
        policy=PerKey(lambda event: 2**60),
    )
    b.termination(quiescence())


async def test_non_canonical_perkey_firing_key_does_not_crash(tmp_path):
    # path 4: the PerKey firing key canonicalization. Recorded as InputBuildFailed.
    result = await Runtime(tmp_path / "run").run(_bad_perkey_topo)
    assert result.status == "finalised"
    assert_event(tmp_path / "run", "substrate.InputBuildFailed", trigger_id="t")


# ── blob offload (technical §3.7) ──────────────────────────────────────────────
class Big(Struct, frozen=True):
    blob: str


async def emits_big(_input):
    yield Big(blob="x" * (20 * 1024))  # > 16 KiB BLOB_THRESHOLD_BYTES


def _big_topo(b):
    b.producer_kind("p", schemas=[Big], schema_version=1, factory=lambda: emits_big)
    b.initial("p", input=None)
    b.termination(quiescence())


async def test_oversized_payload_is_blob_offloaded(tmp_path):
    # a >16 KiB payload must not raise FrameTooLargeError: it is written to the blob
    # store and the frame carries a BlobRef.
    result = await Runtime(tmp_path / "run").run(_big_topo)
    assert result.status == "finalised"
    # the record as stored: `assert_event` redeems blob stubs, so read the raw envelopes
    big = next(e for e in read_record(tmp_path / "run") if e["kind"] == "Big")
    assert set(big["payload"].keys()) == {"$blob", "bytes"}
    assert big["payload"]["$blob"].startswith("sha256:")
    assert big["payload"]["bytes"] > 16 * 1024
    # the blob file exists under blobs/sha256/
    blobs = list((tmp_path / "run" / "blobs" / "sha256").rglob("*"))
    assert any(p.is_file() for p in blobs)


# ── persistent-bus locking (technical §11) ─────────────────────────────────────
async def test_persistent_lock_blocks_a_second_runtime(tmp_path):
    root = tmp_path / "persist"
    # acquire the lock manually to simulate a live holder, then a persistent Runtime
    # against the same root must fail fast.
    import time as _time

    from substrate.record import locking

    fd = locking.acquire_lock(root, start_time=_time.time())
    try:
        with pytest.raises(BusLockedError):
            await Runtime(root, persistent=True).run(_count_to_three_ok)
    finally:
        locking.release_lock(fd)


async def test_persistent_run_acquires_and_releases(tmp_path):
    # a persistent run completes and releases the lock, so a second run can acquire it.
    root = tmp_path / "persist2"
    r1 = await Runtime(root, persistent=True).run(_count_to_three_ok)
    assert r1.status == "finalised"
    # second run on the same root now succeeds (lock was released)
    r2 = await Runtime(root, persistent=True).run(_count_to_three_ok)
    assert r2.status == "finalised"


async def count_three(_input):
    for n in range(3):
        yield Ok(n=n)


def _count_to_three_ok(b):
    b.producer_kind("p", schemas=[Ok], schema_version=1, factory=lambda: count_three)
    b.initial("p", input=None)
    b.termination(threshold_count("substrate.ProducerCompleted", 1))


# ── trigger-level logical cooldown (technical §10) ─────────────────────────────
def _cooldown_topo(b):
    b.producer_kind("src", schemas=[Ok], schema_version=1, factory=lambda: count_three)
    b.producer_kind("c", schemas=[Ok], schema_version=1, factory=lambda: producer_ok)
    b.initial("src", input=None)
    # PerEvent would fire on every Ok (3 of them); a cooldown of 5 appends suppresses
    # all but the first firing within the window.
    b.trigger(
        "t",
        subscription=Subscription(kinds=frozenset({"Ok"})),
        predicate=lambda ctx: True,
        starts="c",
        input_builder=lambda ctx: None,
        policy=PerEvent(),
        cooldown=Logical(100),
    )
    b.termination(quiescence())


async def test_trigger_logical_cooldown_suppresses_rapid_refire(tmp_path):
    await Runtime(tmp_path / "run").run(_cooldown_topo)
    fired = [e for e in read_record(tmp_path / "run") if e["kind"] == "substrate.TriggerFired"]
    # one for the initial src, one for the single non-cooled-down firing of trigger t
    t_fired = [e for e in fired if e["payload"]["trigger_id"] == "t"]
    assert len(t_fired) == 1


class Spawned(Struct, frozen=True):
    tag: int


async def emit_four(_input):
    for n in range(4):
        yield Ok(n=n)


async def spawned_producer(_input):
    yield Spawned(tag=1)


def _cooldown_two_topo(b):
    # the spawned producer "c" emits a DIFFERENT kind (Spawned), so its emissions do not
    # feed back as further trigger matches — the firing count is a clean function of the
    # 4 source Ok appends.
    b.producer_kind("src", schemas=[Ok], schema_version=1, factory=lambda: emit_four)
    b.producer_kind("c", schemas=[Spawned], schema_version=1, factory=lambda: spawned_producer)
    b.initial("src", input=None)
    # cooldown counted in SUBSCRIPTION-MATCHING appends (kernel §6): with 4 Ok events and
    # Logical(2), the trigger fires on matched-append 1 and 3 (not 2 or 4) -> 2 firings.
    b.trigger(
        "t",
        subscription=Subscription(kinds=frozenset({"Ok"})),
        predicate=lambda ctx: True,
        starts="c",
        input_builder=lambda ctx: None,
        policy=PerEvent(),
        cooldown=Logical(2),
    )
    b.termination(quiescence())


async def test_logical_cooldown_counts_subscription_matched_appends(tmp_path):
    # the cooldown window is measured in matching appends, NOT raw bus seq: 4 matches with
    # Logical(2) -> firings at matches 1 and 3.
    await Runtime(tmp_path / "run").run(_cooldown_two_topo)
    fired = [
        e
        for e in read_record(tmp_path / "run")
        if e["kind"] == "substrate.TriggerFired" and e["payload"]["trigger_id"] == "t"
    ]
    assert len(fired) == 2


# ── PerKey + cooldown: the cooldown must NOT consume a PerKey key it then suppresses ──
async def emit_keys(inp):
    for n in inp["keys"]:
        yield Ok(n=n)


def _perkey_cooldown_topo(b):
    b.producer_kind("src", schemas=[Ok], schema_version=1, factory=lambda: emit_keys)
    b.producer_kind("c", schemas=[Spawned], schema_version=1, factory=lambda: spawned_producer)
    b.initial("src", input={"keys": [1, 2, 9, 9, 9, 2]})
    # PerKey on the value, cooldown of 2 matching appends. Walk (match#, key, cd-check):
    #   m1 k1: fire (last=1)              m4 k9: 4-3<2 suppress
    #   m2 k2: 2-1<2 suppress             m5 k9: 5-3>=2 pass, dedup -> no fire
    #   m3 k9: 3-1>=2 pass, fire (last=3) m6 k2: 6-3>=2 pass, fire IFF k2 not consumed
    # BUG (admit before cooldown): m2 consumes k2 -> m6 dedupes -> k2 lost -> 2 firings.
    # FIX (cooldown before admit): m2 does not consume k2 -> m6 fires k2 -> 3 firings.
    b.trigger(
        "t",
        subscription=Subscription(kinds=frozenset({"Ok"})),
        predicate=lambda ctx: True,
        starts="c",
        input_builder=lambda ctx: None,
        policy=PerKey(lambda event: event.payload["n"]),
        cooldown=Logical(2),
    )
    b.termination(quiescence())


async def test_perkey_cooldown_does_not_consume_a_suppressed_key(tmp_path):
    # regression: PerKey.admit consumes the key; if the cooldown gate ran AFTER admit and
    # suppressed that cycle, the key would be consumed-but-never-fired (silent data loss),
    # and a later post-cooldown occurrence of the same key would wrongly dedupe. The fix
    # gates the cooldown BEFORE admit, so a suppressed cycle never consumes the key.
    await Runtime(tmp_path / "run").run(_perkey_cooldown_topo)
    fired = [
        e
        for e in read_record(tmp_path / "run")
        if e["kind"] == "substrate.TriggerFired" and e["payload"]["trigger_id"] == "t"
    ]
    keys = sorted(e["payload"]["firing_key"] for e in fired)
    assert keys == [1, 2, 9]  # all three distinct keys fired; key 2 was NOT lost


# ── oversized resolved input -> input_blob field, not inside resolved_input (D-5) ──--
def _big_resolved_topo(b):
    b.producer_kind("src", schemas=[Ok], schema_version=1, factory=lambda: producer_ok)
    b.producer_kind("c", schemas=[Spawned], schema_version=1, factory=lambda: spawned_producer)
    b.initial("src", input=None)
    b.trigger(
        "t",
        subscription=Subscription(kinds=frozenset({"Ok"})),
        predicate=lambda ctx: True,
        starts="c",
        input_builder=lambda ctx: {"big": "y" * (20 * 1024)},
        policy=PerEvent(),
    )
    b.termination(quiescence())


async def test_oversized_resolved_input_uses_top_level_blob_field(tmp_path):
    await Runtime(tmp_path / "run").run(_big_resolved_topo)
    tf = [
        e
        for e in read_record(tmp_path / "run")
        if e["kind"] == "substrate.TriggerFired" and e["payload"]["trigger_id"] == "t"
    ]
    assert len(tf) == 1
    payload = tf[0]["payload"]
    # exactly one of resolved_input | input_blob present (D-5; input_blob avoids the
    # $blob/$blob field-key collision — P-TRIGGERFIRED-INPUT-BLOB)
    assert "input_blob" in payload
    assert "resolved_input" not in payload
    assert "$blob" not in payload  # not the overloaded sentinel name
    assert payload["input_blob"]["$blob"].startswith("sha256:")
    assert payload["input_blob"]["bytes"] > 16 * 1024
    # input_sha256 is always present, hashing the original canonical bytes
    assert payload["input_sha256"].startswith("sha256:")


# ── view-failure finalisation (technical §6.3) → status failed ─────────────────
class BoomView:
    deterministic = True

    def __init__(self):
        self.subscription = Subscription(kinds=frozenset({"Ok"}))

    def update(self, event):
        raise RuntimeError("view exploded")

    def value(self):
        return None


def _view_failure_topo(b):
    b.producer_kind("p", schemas=[Ok], schema_version=1, factory=lambda: count_three)
    b.view("boom", BoomView())
    b.initial("p", input=None)
    b.termination(quiescence())


async def test_view_failure_finalises_and_reports_failed(tmp_path):
    result = await Runtime(tmp_path / "run").run(_view_failure_topo)
    assert result.status == "failed"
    fin = assert_event(tmp_path / "run", "substrate.RunFinalised", reason="view_failure")
    assert fin["payload"]["view"] == "boom"
    assert "error" in fin["payload"]
    # RunFinalised is terminal and at-most-once even mid-cascade: exactly one, and it
    # is the LAST frame (nothing follows it).
    envs = list(read_record(tmp_path / "run"))
    finals = [i for i, e in enumerate(envs) if e["kind"] == "substrate.RunFinalised"]
    assert len(finals) == 1
    assert finals[0] == len(envs) - 1


class BoomOnControlView:
    """Raises on a control event (substrate.TriggerFired) — exercises the view-failure
    path while OTHER control events (the route's InjectionApplied) are queued, proving
    nothing is appended after the terminal RunFinalised."""

    deterministic = True

    def __init__(self):
        self.subscription = Subscription(kinds=frozenset({"substrate.TriggerFired"}))

    def update(self, event):
        raise RuntimeError("boom on control")

    def value(self):
        return None


def _view_failure_midcascade_topo(b):
    b.producer_kind("p", schemas=[Ok], schema_version=1, factory=lambda: count_three)
    b.view("boom", BoomOnControlView())
    b.initial("p", input=None)
    b.termination(quiescence())


async def test_view_failure_midcascade_appends_nothing_after_terminal(tmp_path):
    # the boom view subscribes to TriggerFired; the run finalises on the very first
    # TriggerFired (the initial). No frame may follow the terminal RunFinalised.
    result = await Runtime(tmp_path / "run").run(_view_failure_midcascade_topo)
    assert result.status == "failed"
    envs = list(read_record(tmp_path / "run"))
    finals = [i for i, e in enumerate(envs) if e["kind"] == "substrate.RunFinalised"]
    assert len(finals) == 1
    assert finals[0] == len(envs) - 1
    # seq stays dense up to and including the terminal
    assert [e["seq"] for e in envs] == list(range(len(envs)))


# ── empty-View subscription rejected at registration (item 6) ──────────────────
def test_empty_view_subscription_rejected():
    class Empty:
        deterministic = True
        subscription = Subscription()

        def update(self, event):
            pass

        def value(self):
            return None

    b = TopologyBuilder()
    with pytest.raises(RegistrationError, match="subscription is empty"):
        b.view("empty", Empty())


# ── finalisation payload flows policy -> RunFinalised -> RunResult (Priority B item 6) ──
from substrate.kernel.policies import Decision, TerminationPolicy  # noqa: E402


def _final_payload_policy():
    return TerminationPolicy(
        "finalise_with_payload",
        lambda c: (
            Decision.FINALISE_RUN
            if c.counts("substrate.ProducerCompleted") >= 1
            else Decision.CONTINUE
        ),
        finalisation=lambda c: {"summary": "done", "ticks": c.counts("Ok")},
    )


def _final_payload_topo(b):
    b.producer_kind("p", schemas=[Ok], schema_version=1, factory=lambda: count_three)
    b.initial("p", input=None)
    b.termination(_final_payload_policy())


async def test_finalisation_payload_flows_to_record_and_result(tmp_path):
    result = await Runtime(tmp_path / "run").run(_final_payload_topo)
    assert result.status == "finalised"
    # surfaced on RunResult
    assert result.finalisation_payload == {"summary": "done", "ticks": 3}
    # AND recorded in the RunFinalised frame
    fin = assert_event(tmp_path / "run", "substrate.RunFinalised")
    assert fin["payload"]["finalisation_payload"] == {"summary": "done", "ticks": 3}


def _no_payload_topo(b):
    b.producer_kind("p", schemas=[Ok], schema_version=1, factory=lambda: count_three)
    b.initial("p", input=None)
    b.termination(threshold_count("substrate.ProducerCompleted", 1))


async def test_no_finalisation_payload_is_none_not_empty_promise(tmp_path):
    # a policy with no finalisation callback -> RunResult.finalisation_payload is None and
    # the RunFinalised frame carries no finalisation_payload key (not a dead always-None).
    result = await Runtime(tmp_path / "run").run(_no_payload_topo)
    assert result.finalisation_payload is None
    fin = assert_event(tmp_path / "run", "substrate.RunFinalised")
    assert "finalisation_payload" not in fin["payload"]


def _bad_final_payload_topo(b):
    b.producer_kind("p", schemas=[Ok], schema_version=1, factory=lambda: count_three)
    b.initial("p", input=None)
    b.termination(
        TerminationPolicy(
            "finalise_bad_payload",
            lambda c: (
                Decision.FINALISE_RUN
                if c.counts("substrate.ProducerCompleted") >= 1
                else Decision.CONTINUE
            ),
            finalisation=lambda c: {"big": 2**60},  # non-canonical (out-of-JCS-range int)
        )
    )


async def test_non_canonical_finalisation_payload_drop_is_recorded_not_silent(tmp_path):
    # a non-canonical finalisation payload must NOT crash finalisation AND must NOT vanish
    # silently — the drop reason is recorded on the RunFinalised frame (product §1: nothing
    # consequential is silent).
    result = await Runtime(tmp_path / "run").run(_bad_final_payload_topo)
    assert result.status == "finalised"
    assert result.finalisation_payload is None
    fin = assert_event(tmp_path / "run", "substrate.RunFinalised")
    assert "finalisation_payload" not in fin["payload"]
    assert "finalisation_payload_dropped" in fin["payload"]
    assert "not canonical" in fin["payload"]["finalisation_payload_dropped"]


# ── kernel error is recorded on the log, not silent (Priority B item 5) ────────--
class _RaisingPolicy(TerminationPolicy):
    """A TerminationPolicy whose decide() raises — drives the §6.3 'the writer itself
    raises' path (an unexpected exception inside the cycle), distinct from the view-failure
    and FsyncError paths."""

    def __init__(self):
        super().__init__("raising", lambda c: Decision.CONTINUE)

    def decide(self, ctx):
        raise RuntimeError("policy exploded")


def _kernel_error_topo(b):
    b.producer_kind("p", schemas=[Ok], schema_version=1, factory=lambda: count_three)
    b.initial("p", input=None)
    b.termination(_RaisingPolicy())


async def test_kernel_error_is_recorded_not_silent(tmp_path):
    # an unexpected writer-internal raise must yield status=failed AND a RunFinalised
    # {reason: kernel_error} on the log — never a silently truncated record.
    result = await Runtime(tmp_path / "run").run(_kernel_error_topo)
    assert result.status == "failed"
    fin = assert_event(tmp_path / "run", "substrate.RunFinalised", reason="kernel_error")
    assert "policy exploded" in fin["payload"]["error"]

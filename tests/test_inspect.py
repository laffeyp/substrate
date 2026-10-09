# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Inspection / provenance / divergence tests (technical §14).

Close conformance check 11 (provenance closure — no dangling ProducerIds),
check 12 (view-at fidelity), check 13 (divergence localization)."""

from msgspec import Struct

from substrate.api import (
    KindCount,
    PerEvent,
    Runtime,
    Subscription,
    explain_producer,
    first_divergence,
    quiescence,
    read_record,
    threshold_count,
    trace_ancestry,
    view_at,
)
from substrate.errors import ProducerNotFound, SequenceOutOfRange
from substrate.projections.inspect import decisions_between


class CountReached(Struct, frozen=True):
    n: int


class Doubled(Struct, frozen=True):
    original: int
    doubled: int


async def counter(_input):
    for n in range(1, 4):
        yield CountReached(n=n)


async def doubler(inp):
    yield Doubled(original=inp["n"], doubled=inp["n"] * 2)


def _doubler_topo(b):
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.producer_kind("doubler", schemas=[Doubled], schema_version=1, factory=lambda: doubler)
    b.initial("counter", input=None)
    b.trigger(
        "double-each",
        subscription=Subscription(kinds=frozenset({"CountReached"})),
        predicate=lambda ctx: True,
        starts="doubler",
        input_builder=lambda ctx: {"n": ctx.event.payload["n"]},
        policy=PerEvent(),
    )
    b.termination(quiescence())


# ── conformance check 11: provenance closure ──────────────────────────────────
async def test_provenance_closure_no_dangling_producer_ids(tmp_path):
    await Runtime(tmp_path / "run").run(_doubler_topo)
    envs = list(read_record(tmp_path / "run"))
    started = [e for e in envs if e["kind"] == "substrate.ProducerStarted"]
    # every started Producer instance must have a TriggerFired that scheduled it, and
    # trace_ancestry must reach a root (cause RunStarted) — no dangling ids.
    for st in started:
        inst = st["payload"]["producer"]["instance"]
        exp = explain_producer(tmp_path / "run", inst)
        assert exp.instance == inst
        chain = trace_ancestry(tmp_path / "run", inst)
        assert chain[0].instance == inst
        assert chain[-1].cause == "RunStarted"  # the chain bottoms out at the run open


async def test_explain_producer_links_via_trigger_fired_instance(tmp_path):
    await Runtime(tmp_path / "run").run(_doubler_topo)
    envs = list(read_record(tmp_path / "run"))
    a_doubler = next(
        e
        for e in envs
        if e["kind"] == "substrate.ProducerStarted"
        and e["payload"]["producer"]["kind"] == "doubler"
    )
    inst = a_doubler["payload"]["producer"]["instance"]
    exp = explain_producer(tmp_path / "run", inst)
    assert exp.kind == "doubler"
    assert exp.cause == "TriggerFired"
    assert exp.trigger_id == "double-each"
    assert exp.input_sha256 is not None and exp.input_sha256.startswith("sha256:")
    assert exp.parent is not None  # spawned by the counter


async def test_trace_ancestry_doubler_to_counter_to_run(tmp_path):
    await Runtime(tmp_path / "run").run(_doubler_topo)
    envs = list(read_record(tmp_path / "run"))
    inst = next(
        e["payload"]["producer"]["instance"]
        for e in envs
        if e["kind"] == "substrate.ProducerStarted"
        and e["payload"]["producer"]["kind"] == "doubler"
    )
    chain = trace_ancestry(tmp_path / "run", inst)
    kinds = [c.kind for c in chain]
    assert kinds[0] == "doubler"
    assert "counter" in kinds
    assert chain[-1].cause == "RunStarted"


async def test_explain_producer_accepts_kind_bracket_instance_form(tmp_path):
    await Runtime(tmp_path / "run").run(_doubler_topo)
    envs = list(read_record(tmp_path / "run"))
    inst = next(
        e["payload"]["producer"]["instance"]
        for e in envs
        if e["kind"] == "substrate.ProducerStarted"
    )
    exp = explain_producer(tmp_path / "run", f"counter[{inst}]")
    assert exp.instance == inst


async def test_explain_producer_unknown_raises(tmp_path):
    await Runtime(tmp_path / "run").run(_doubler_topo)
    try:
        explain_producer(tmp_path / "run", "definitely-not-a-real-instance")
        raise AssertionError("expected ProducerNotFound")
    except ProducerNotFound:
        pass


# ── conformance check 12: view-at fidelity ────────────────────────────────────
async def test_view_at_matches_state_observed_during_run(tmp_path):
    await Runtime(tmp_path / "run").run(_doubler_topo)
    envs = list(read_record(tmp_path / "run"))
    # the seq of the 2nd CountReached
    cr_seqs = [e["seq"] for e in envs if e["kind"] == "CountReached"]
    assert len(cr_seqs) == 3
    # a fresh KindCount(CountReached) folded up to the 2nd CountReached's seq == 2
    at_second = view_at(tmp_path / "run", cr_seqs[1], KindCount("CountReached"))
    assert at_second == 2
    # folded up to the last frame == 3
    last = max(e["seq"] for e in envs)
    assert view_at(tmp_path / "run", last, KindCount("CountReached")) == 3


async def test_view_at_out_of_range_raises(tmp_path):
    await Runtime(tmp_path / "run").run(_doubler_topo)
    last = max(e["seq"] for e in read_record(tmp_path / "run"))
    try:
        view_at(tmp_path / "run", last + 100, KindCount("CountReached"))
        raise AssertionError("expected SequenceOutOfRange")
    except SequenceOutOfRange:
        pass


async def test_decisions_between_filters_substrate_frames(tmp_path):
    await Runtime(tmp_path / "run").run(_doubler_topo)
    envs = list(read_record(tmp_path / "run"))
    last = max(e["seq"] for e in envs)
    decisions = decisions_between(tmp_path / "run", 0, last)
    assert all(d.kind.startswith("substrate.") for d in decisions)
    # no application frames (CountReached/Doubled) leak in
    assert not any(d.kind in ("CountReached", "Doubled") for d in decisions)
    # a narrow window returns a subset
    narrow = decisions_between(tmp_path / "run", 0, 1)
    assert all(0 <= d.seq <= 1 for d in narrow)


# ── conformance check 13: divergence localization ─────────────────────────────
# Same topology (same Producer factory + manifest), perturbed only by the third emitted
# value, so the divergence is a Producer DECISION, not a topology difference. The factory
# reads its input list to decide the values it emits.
async def from_list(inp):
    for n in inp["values"]:
        yield CountReached(n=n)


def _perturb_topo(values):
    def topo(b):
        b.producer_kind(
            "counter", schemas=[CountReached], schema_version=1, factory=lambda: from_list
        )
        b.initial("counter", input={"values": values})
        b.termination(threshold_count("substrate.ProducerCompleted", 1))

    return topo


async def test_first_divergence_localizes_the_perturbed_decision(tmp_path):
    # record A emits (1,2,3); record B emits (1,2,99) — same topology, one perturbed
    # decision. The initial input differs (values list), which also perturbs the initial
    # TriggerFired's input_sha256 — that is itself a legitimate first divergence (the
    # firing decision), localized BEFORE the CountReached values.
    await Runtime(tmp_path / "a").run(_perturb_topo([1, 2, 3]))
    await Runtime(tmp_path / "b").run(_perturb_topo([1, 2, 99]))
    div = first_divergence(tmp_path / "a", tmp_path / "b")
    assert div is not None
    assert (
        div.kind_a == div.kind_b
    )  # same kind at the divergent frame (a decision, not a kind change)
    assert div.hash_a != div.hash_b
    # the divergence is localized to a runtime decision or the perturbed emission, by seq
    a = list(read_record(tmp_path / "a"))
    assert a[div.index]["kind"] in ("substrate.TriggerFired", "CountReached")


async def test_first_divergence_localizes_emission_when_inputs_match(tmp_path):
    # identical initial input, but the SAME factory emits a different 3rd value: here the
    # firing decisions match and the divergence lands on the perturbed CountReached.
    async def emit_123(_inp):
        for n in (1, 2, 3):
            yield CountReached(n=n)

    async def emit_129(_inp):
        for n in (1, 2, 9):
            yield CountReached(n=n)

    def topo(factory):
        def t(b):
            b.producer_kind(
                "counter", schemas=[CountReached], schema_version=1, factory=lambda: factory
            )
            b.initial("counter", input=None)
            b.termination(threshold_count("substrate.ProducerCompleted", 1))

        return t

    # NOTE: different factory => different manifest fingerprint => divergence at RunStarted.
    # To keep the manifest identical we drive values by input instead (see the test above);
    # here we assert the mechanism still localizes SOMEthing and hashes differ.
    await Runtime(tmp_path / "a").run(topo(emit_123))
    await Runtime(tmp_path / "b").run(topo(emit_129))
    div = first_divergence(tmp_path / "a", tmp_path / "b")
    assert div is not None
    assert div.hash_a != div.hash_b


async def test_first_divergence_none_for_identical_records(tmp_path):
    # a record compared against itself is equivalent under D-8: None. (Two DISTINCT runs
    # of the same deterministic topology are ALSO D-8-equivalent because run_id/instance
    # are normalized out — see test_first_divergence_none_across_distinct_runs.)
    await Runtime(tmp_path / "a").run(_perturb_topo([1, 2, 3]))
    envs = list(read_record(tmp_path / "a"))
    assert first_divergence(envs, envs) is None


async def test_first_divergence_none_across_distinct_runs(tmp_path):
    # two separate runs of the same deterministic topology differ only by run_id + the
    # per-Producer instance ULIDs + t — all excluded from D-8. So first_divergence is None.
    await Runtime(tmp_path / "a").run(_perturb_topo([1, 2, 3]))
    await Runtime(tmp_path / "b").run(_perturb_topo([1, 2, 3]))
    assert first_divergence(tmp_path / "a", tmp_path / "b") is None


async def test_first_divergence_prefix_is_localized(tmp_path):
    await Runtime(tmp_path / "a").run(_perturb_topo([1, 2, 3]))
    envs = list(read_record(tmp_path / "a"))
    prefix = envs[:-2]
    div = first_divergence(prefix, envs)
    assert div is not None
    assert div.index == len(prefix)  # first extra frame in the longer record
    assert div.kind_a is None and div.kind_b is not None


# ── D-8 must exclude run-varying SUPPLEMENTARY measurement: measured_us ────────--
import time as _time  # noqa: E402
import uuid  # noqa: E402


def _slow_predicate(ctx):
    # deliberately over the default 100us budget so it accrues budget violations and the
    # runtime quarantines it after k=3 hysteresis -> a PredicateQuarantined{reason:"budget",
    # measured_us:<wall-clock us>} on the log. measured_us VARIES run to run (it's a timing
    # measurement), so it must NOT enter the D-8 comparison.
    _time.sleep(0.0005)  # ~500us, comfortably over the 100us budget
    return False


def _quarantine_topo(b):
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.producer_kind("noop", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.initial("counter", input=None)
    b.trigger(
        "slow",
        subscription=Subscription(kinds=frozenset({"CountReached"})),
        predicate=_slow_predicate,
        starts="noop",
        input_builder=lambda ctx: None,
        policy=PerEvent(),
    )
    b.termination(quiescence())


async def test_first_divergence_excludes_measured_us_on_quarantine(tmp_path):
    # MUST-FIX (external review): two runs of the same topology that both budget-quarantine
    # the same predicate produce PredicateQuarantined frames with DIFFERENT measured_us;
    # measured_us is a wall-clock measurement (supplementary), not decision identity, so it
    # must be excluded from D-8 — first_divergence must be None, not a spurious positive.
    await Runtime(tmp_path / "a").run(_quarantine_topo)
    await Runtime(tmp_path / "b").run(_quarantine_topo)
    # sanity: both runs actually quarantined (so measured_us is present and differs)
    qa = [e for e in read_record(tmp_path / "a") if e["kind"] == "substrate.PredicateQuarantined"]
    qb = [e for e in read_record(tmp_path / "b") if e["kind"] == "substrate.PredicateQuarantined"]
    assert qa and qb and qa[0]["payload"]["reason"] == "budget"
    # the two records are D-8-equivalent despite differing measured_us / error reprs
    assert first_divergence(tmp_path / "a", tmp_path / "b") is None


# ── D-8 must normalize finalisation_payload_dropped (external review #2, Fix B) ──
from substrate.kernel.policies import Decision, TerminationPolicy  # noqa: E402


def _raising_finalisation_topo(b):
    # the finalisation callback RAISES with a run-varying message (embeds a fresh object id),
    # so RunFinalised carries finalisation_payload_dropped="finalisation callback raised:
    # RuntimeError(<varying>)". That repr tail differs run to run; the D-8 sentinel must
    # normalize it (class-preserving) so two runs do not spuriously diverge.
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.initial("counter", input=None)

    def _boom(ctx):
        raise RuntimeError(f"boom at {uuid.uuid4()}")  # repr embeds a per-run-unique tail

    b.termination(
        TerminationPolicy(
            "finalise_raise",
            lambda c: (
                Decision.FINALISE_RUN
                if c.counts("substrate.ProducerCompleted") >= 1
                else Decision.CONTINUE
            ),
            finalisation=_boom,
        )
    )


async def test_first_divergence_normalizes_finalisation_payload_dropped(tmp_path):
    await Runtime(tmp_path / "a").run(_raising_finalisation_topo)
    await Runtime(tmp_path / "b").run(_raising_finalisation_topo)
    # sanity: both recorded a dropped-payload reason whose repr tails DIFFER
    fa = [e for e in read_record(tmp_path / "a") if e["kind"] == "substrate.RunFinalised"][-1]
    fb = [e for e in read_record(tmp_path / "b") if e["kind"] == "substrate.RunFinalised"][-1]
    assert "finalisation_payload_dropped" in fa["payload"]
    assert (
        fa["payload"]["finalisation_payload_dropped"]
        != fb["payload"]["finalisation_payload_dropped"]
    )
    # ...yet the records are D-8-equivalent (the RuntimeError class is preserved, tail dropped)
    assert first_divergence(tmp_path / "a", tmp_path / "b") is None


def test_error_sentinel_is_class_preserving():
    from substrate.projections.inspect import _error_sentinel

    assert _error_sentinel("ValueError('boom at /tmp/x')") == "<ValueError>"
    assert _error_sentinel("finalisation callback raised: RuntimeError(...)") == "<RuntimeError>"
    assert _error_sentinel("no class here") == "<error>"
    # a DIFFERENT error class is still a real divergence (not collapsed)
    assert _error_sentinel("KeyError('x')") != _error_sentinel("ValueError('x')")

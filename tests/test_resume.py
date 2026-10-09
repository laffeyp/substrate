# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Persistent pause/resume (F-TERM-3 / F-PERS-2): a run pauses on pause_await_input,
the process/Runtime is discarded, and a FRESH Runtime.resume() reattaches to the existing
record, restores next_seq from the log tail, injects the external resume event so the
resume Trigger fires the continuation Producer, and drives to a terminal — on the SAME
dense seq sequence as the paused run.

These tests build the topology in the test module so the resume Runtime is genuinely a new
object that knows nothing of the paused run except its on-disk record (the F-PERS-2 promise:
a paused run survives on a named persistent root, resumable by a process that did not start
it)."""

import pytest
from msgspec import Struct

from substrate.api import (
    PerEvent,
    RegistrationError,
    Runtime,
    Subscription,
    all_completed,
    any_of,
    pause_await_input,
    quiescence,
    read_record,
)


# ── the topology: stage1 runs, the run PAUSES awaiting input, an external ApprovalGranted
#    event resumes it, firing stage2 (the continuation) to a quiescence terminal. ──────────
class Stage1Done(Struct, frozen=True):
    value: int


class Stage2Done(Struct, frozen=True):
    value: int


class ApprovalGranted(Struct, frozen=True):
    """The external resume event — what a resume Trigger subscribes to (producer=null on the
    bus; it is externally supplied, not Producer-emitted)."""

    approved: bool


async def stage1(_input):
    yield Stage1Done(value=1)


async def stage2(inp):
    yield Stage2Done(value=inp["value"] + 1)


def _paused_when(ctx):
    # Pause once stage1 has completed AND no resume event has yet arrived. After the resume
    # event is on the log, this is False, so the continuation runs to quiescence instead of
    # re-pausing. (counts() reads the run's per-kind event counts.)
    return ctx.counts("Stage1Done") >= 1 and ctx.counts("ApprovalGranted") == 0


def pause_resume_topology(b):
    b.producer_kind("stage1", schemas=[Stage1Done], schema_version=1, factory=lambda: stage1)
    b.producer_kind("stage2", schemas=[Stage2Done], schema_version=1, factory=lambda: stage2)
    b.initial("stage1", input=None)
    # the resume Trigger: subscribed to the external ApprovalGranted, fires the continuation.
    b.trigger(
        "on-approval",
        subscription=Subscription(kinds=frozenset({"ApprovalGranted"})),
        predicate=lambda ctx: bool(ctx.event.payload.get("approved")),
        starts="stage2",
        input_builder=lambda ctx: {"value": 1},
        policy=PerEvent(),
    )
    b.termination(
        any_of(
            pause_await_input(_paused_when, resume_condition="ApprovalGranted"),
            quiescence(),
        )
    )


def make_approval():
    return ApprovalGranted(approved=True)


async def test_pause_then_resume_in_fresh_runtime_continues_with_continuous_seq(tmp_path):
    root = tmp_path / "run"

    # 1) Run to the pause. Persistent so the record survives under a named root with the lock.
    paused = await Runtime(root, persistent=True).run(pause_resume_topology)
    assert paused.status == "paused"

    envs_at_pause = list(read_record(root))
    kinds_at_pause = [e["kind"] for e in envs_at_pause]
    assert "Stage1Done" in kinds_at_pause
    assert "substrate.TerminationMatched" in kinds_at_pause  # the pause decision was recorded
    assert "substrate.RunFinalised" not in kinds_at_pause  # a pause is NOT a terminal
    assert "Stage2Done" not in kinds_at_pause  # the continuation has not run yet
    seqs_at_pause = [e["seq"] for e in envs_at_pause]
    assert seqs_at_pause == list(range(len(seqs_at_pause)))  # dense 0..k
    last_seq_at_pause = seqs_at_pause[-1]
    run_id_at_pause = envs_at_pause[0]["payload"]["run_id"]

    # 2) Resume in a genuinely FRESH Runtime (a new object — the F-PERS-2 "different process"
    #    promise; it knows only the on-disk record). Inject the external resume event.
    resumed = await Runtime(root, persistent=True).resume(
        pause_resume_topology, resume_event=ApprovalGranted(approved=True)
    )
    assert resumed.status == "finalised"
    assert resumed.run_id == run_id_at_pause  # the run KEEPS its identity across resume

    envs_after = list(read_record(root))
    kinds_after = [e["kind"] for e in envs_after]
    assert "ApprovalGranted" in kinds_after  # the resume event landed on the bus
    assert "Stage2Done" in kinds_after  # the continuation Producer ran
    assert "substrate.RunFinalised" in kinds_after  # and the run finalised

    # seq continuity: the resumed appends continue the SAME dense sequence (no reset, no gap).
    seqs_after = [e["seq"] for e in envs_after]
    assert seqs_after == list(range(len(seqs_after)))
    # everything appended on resume has seq strictly greater than the pause tail.
    new_envs = envs_after[len(envs_at_pause) :]
    assert [e["seq"] for e in new_envs] == list(
        range(last_seq_at_pause + 1, last_seq_at_pause + 1 + len(new_envs))
    )
    # the resume event carries producer=null (externally supplied, not Producer-emitted).
    approval = next(e for e in new_envs if e["kind"] == "ApprovalGranted")
    assert approval["producer"] is None

    # the continuation read the resumed input and produced value+1.
    stage2 = next(e for e in envs_after if e["kind"] == "Stage2Done")
    assert stage2["payload"]["value"] == 2


class _Versioned(Struct, frozen=True):
    x: int


async def _v_producer(_input):
    yield _Versioned(x=1)


def _versioned_topology(ver):
    def topo(b):
        b.producer_kind("p", schemas=[_Versioned], schema_version=ver, factory=lambda: _v_producer)
        b.initial("p", input=None)
        from substrate.api import threshold_count

        b.termination(threshold_count("substrate.ProducerCompleted", 1))

    return topo


async def test_f_schema_2_each_run_interprets_via_its_own_manifest(tmp_path):
    # F-SCHEMA-2: schemas are fixed for the duration of a run; a persistent bus MAY hold runs
    # written at different schema versions because every event's interpretation routes through
    # its OWN run's RunStarted manifest. This implementation is one-run-per-record-root, so the
    # "persistent bus holding runs at different versions" is a SET of run records under a root;
    # the guarantee exercised here is the load-bearing one: each run's manifest carries its own
    # schema_version and each event's `schema` field names that version, so a reader decodes
    # every run with the schemas IT was written with — never the current code's, never a
    # sibling run's. (Cross-run reinterpretation is the drift F-SCHEMA-2/3 forbid.)
    persistent_bus = tmp_path / "bus"  # the named persistent root holding multiple run records
    run_v1 = persistent_bus / "run-v1"
    run_v2 = persistent_bus / "run-v2"

    r1 = await Runtime(run_v1, persistent=True).run(_versioned_topology(1))
    r2 = await Runtime(run_v2, persistent=True).run(_versioned_topology(2))
    assert r1.status == "finalised" and r2.status == "finalised"

    def _manifest_version(root):
        rs = next(e for e in read_record(root) if e["kind"] == "substrate.RunStarted")
        return rs["payload"]["topology"]["producer_kinds"][0]["schema_version"]

    def _event_schema(root):
        return next(e for e in read_record(root) if e["kind"] == "_Versioned")["schema"]

    # each run's manifest records ITS OWN version, and the on-bus event names that version.
    assert _manifest_version(run_v1) == 1
    assert _manifest_version(run_v2) == 2
    assert _event_schema(run_v1) == "_Versioned@1"
    assert _event_schema(run_v2) == "_Versioned@2"
    # the two runs coexist under the one persistent-bus root with NO shared/global schema state:
    # reading v1 after v2 still yields v1's version (no last-writer-wins reinterpretation).
    assert _manifest_version(run_v1) == 1


async def test_resume_requires_persistent_mode(tmp_path):
    # resume on a non-persistent Runtime is a registration error: only a persistent-bus run
    # can pause and survive to be resumed.
    rt = Runtime(tmp_path / "run", persistent=False)
    with pytest.raises(RegistrationError, match="resume requires persistent"):
        await rt.resume(pause_resume_topology, resume_event=ApprovalGranted(approved=True))


async def test_resume_rejects_reserved_kind_event(tmp_path):
    # the resume event must be an application event, never a reserved substrate.* kind.
    root = tmp_path / "run"
    await Runtime(root, persistent=True).run(pause_resume_topology)

    class RunStarted(Struct, frozen=True):  # name collides with a reserved kind via prefix?
        pass

    # a genuinely reserved kind: construct a Struct whose __name__ is namespaced. We cannot
    # name a class "substrate.X" in Python, so assert the guard via a crafted type name.
    reserved = type("Reserved", (Struct,), {})
    reserved.__name__ = "substrate.Injected"
    with pytest.raises(RegistrationError, match="reserved"):
        await Runtime(root, persistent=True).resume(pause_resume_topology, resume_event=reserved())


# ── stuck-quiescence guard (FOLD 2): a resumable run whose terminal is all_completed would
#    HANG on resume — the pause leaves stage1 started-but-not-ended, so restored started>ended
#    and completed>=started is unmeetable. The guard turns that silent hang into a loud,
#    recorded failure rather than spinning forever. ─────────────────────────────────────────
def _all_completed_pause_topology(b):
    b.producer_kind("stage1", schemas=[Stage1Done], schema_version=1, factory=lambda: stage1)
    b.producer_kind("stage2", schemas=[Stage2Done], schema_version=1, factory=lambda: stage2)
    b.initial("stage1", input=None)
    b.trigger(
        "on-approval",
        subscription=Subscription(kinds=frozenset({"ApprovalGranted"})),
        predicate=lambda ctx: bool(ctx.event.payload.get("approved")),
        starts="stage2",
        input_builder=lambda ctx: {"value": 1},
        policy=PerEvent(),
    )
    # WRONG terminal for a resumable run: all_completed compares restored started/ended counts.
    b.termination(
        any_of(
            pause_await_input(_paused_when, resume_condition="ApprovalGranted"),
            all_completed(),
        )
    )


@pytest.mark.timeout(10)
async def test_resume_on_all_completed_fails_loud_instead_of_hanging(tmp_path):
    root = tmp_path / "run"
    paused = await Runtime(root, persistent=True).run(_all_completed_pause_topology)
    assert paused.status == "paused"

    # Resume: stage2 runs and goes quiescent, but all_completed can never be met (the pre-pause
    # stage1 start has no durable end across the pause). The guard must FAIL the run loudly
    # within the timeout, not hang.
    resumed = await Runtime(root, persistent=True).resume(
        _all_completed_pause_topology, resume_event=ApprovalGranted(approved=True)
    )
    assert resumed.status == "failed"
    # the failure is RECORDED and citable: a RunFinalised with reason "stuck_quiescent".
    finals = [e for e in read_record(root) if e["kind"] == "substrate.RunFinalised"]
    assert finals, "the stuck run must record a RunFinalised, not hang silently"
    assert finals[-1]["payload"]["reason"] == "stuck_quiescent"
    assert "all_completed" in finals[-1]["payload"]["policy"]

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Observation contract for the reproduction-test generator (sprint 144): the fence-stripping parser, the
producer emitting a ReproductionTest, and the death-catch (a model error -> empty test, not a wedge)."""

from substrate import api
from substrate.api import Runtime, read_record
from substrate.reference._models import DeterministicResponder, ModelUsage, Responder
from substrate.topologies.swebench_solver.records import ReproductionTest
from substrate.topologies.swebench_solver.reproduction import (
    parse_repro_code,
    repro_generator_factory,
)


def test_parse_repro_code_strips_fences() -> None:
    assert parse_repro_code("```python\nprint('Issue resolved')\n```") == "print('Issue resolved')"
    assert parse_repro_code("print('x')") == "print('x')"  # no fence, unchanged


async def _run(tmp_path, responder: Responder, issue: str) -> list[dict]:  # type: ignore[no-untyped-def]
    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "repro",
            schemas=[ReproductionTest, ModelUsage],
            schema_version=1,
            factory=repro_generator_factory(responder, issue),
            deterministic=False,
        )
        b.initial("repro", input=None)
        b.termination(api.any_of(api.threshold_count("ReproductionTest", 1), api.quiescence()))

    await Runtime(tmp_path / "run").run(topo)
    return list(read_record(tmp_path / "run"))


async def test_repro_generator_emits_the_test(tmp_path) -> None:  # type: ignore[no-untyped-def]
    responder = DeterministicResponder(
        seed=0, menu=["```python\nassert True\nprint('Issue resolved')\n```"]
    )
    events = await _run(tmp_path, responder, "f returns the wrong value")
    repro = [e["payload"] for e in events if e["kind"] == "ReproductionTest"]
    assert (
        len(repro) == 1 and "Issue resolved" in repro[0]["code"] and "```" not in repro[0]["code"]
    )


class _DyingResponder:
    def respond(self, prompt: str) -> str:
        raise RuntimeError("model died")


async def test_repro_generator_model_error_records_producer_failed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # 2026-08-09 halt-on-error contract: a failed model call in repro_generator propagates.
    # The producer dies, the kernel records ProducerFailed, no ReproductionTest emits. Runner
    # halts the sweep.
    events = await _run(tmp_path, _DyingResponder(), "issue text")
    assert any(e["kind"] == "substrate.ProducerFailed" for e in events), (
        "failed model call must record ProducerFailed"
    )
    assert not any(e["kind"] == "ReproductionTest" for e in events), (
        "no fake empty ReproductionTest cover for a real crash"
    )


async def test_repro_generator_meters(tmp_path) -> None:  # type: ignore[no-untyped-def]
    responder = DeterministicResponder(seed=0, menu=["print('Issue reproduced')"])
    events = await _run(tmp_path, responder, "issue")
    assert any(e["kind"] == "ModelUsage" for e in events)  # the model call is metered (#3)


# F4 fix (review 2026-08-08): K > 1 reproduction sampling + amortized docker.


def test_combine_repro_scripts_single_script_passes_through():
    from substrate.topologies.swebench_solver.reproduction import combine_repro_scripts

    # K=1: identical to pre-fix wire behaviour — just the one script's text.
    assert combine_repro_scripts(["print('Issue reproduced')"]) == "print('Issue reproduced')"


def test_combine_repro_scripts_empty_input_returns_empty():
    from substrate.topologies.swebench_solver.reproduction import combine_repro_scripts

    assert combine_repro_scripts([]) == ""
    # All-empty entries filter out — nothing to run.
    assert combine_repro_scripts(["", "   ", ""]) == ""


def test_combine_repro_scripts_bundles_k_variants_into_one_runner():
    from substrate.topologies.swebench_solver.reproduction import combine_repro_scripts

    scripts = ["print('Issue reproduced')", "print('Issue resolved')", "print('Issue reproduced')"]
    runner = combine_repro_scripts(scripts)
    # Contains all three via exec-with-repr — the runner is a real Python script.
    assert "'Issue reproduced'" in runner  # first + third scripts' text
    assert "'Issue resolved'" in runner  # second
    # Actually execute it — verify the runner prints all three markers.
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(runner, "<test>", "exec"), {})
    out = buf.getvalue()
    assert out.count("Issue reproduced") == 2  # variants 0 and 2
    assert out.count("Issue resolved") == 1  # variant 1


def test_combine_repro_scripts_isolates_variant_exceptions():
    # A raising variant must not stop later variants from running — the runner wraps each in
    # try/except and prints "Other issues" for the failing one.
    from substrate.topologies.swebench_solver.reproduction import combine_repro_scripts

    scripts = ["raise RuntimeError('boom')", "print('Issue resolved')"]
    runner = combine_repro_scripts(scripts)
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(runner, "<test>", "exec"), {})
    out = buf.getvalue()
    assert "Other issues" in out
    assert "Issue resolved" in out  # later variant still ran


def test_reproduction_status_majority_vote_post_F4():
    from substrate.topologies.swebench_solver.records import Reproduction
    from substrate.topologies.swebench_solver.select_exec import reproduction_status

    # Clear RESOLVED majority (3 vs 1) -> RESOLVED
    assert (
        reproduction_status("Issue resolved\nIssue resolved\nIssue reproduced\nIssue resolved\n")
        == Reproduction.RESOLVED
    )
    # Clear REPRODUCED majority (3 vs 1) -> REPRODUCED
    assert (
        reproduction_status(
            "Issue reproduced\nIssue reproduced\nIssue resolved\nIssue reproduced\n"
        )
        == Reproduction.REPRODUCED
    )
    # Tie -> REPRODUCED (the safe direction; a repro should not win on equal signal)
    assert reproduction_status("Issue resolved\nIssue reproduced\n") == Reproduction.REPRODUCED
    # Neither marker -> OTHER
    assert reproduction_status("random output\ntraceback\n") == Reproduction.OTHER
    # Single-marker (K=1 case) still works
    assert reproduction_status("Issue resolved\n") == Reproduction.RESOLVED
    assert reproduction_status("Issue reproduced\n") == Reproduction.REPRODUCED


def test_reproduction_status_pre_F4_bias_no_longer_fires():
    # Pre-F4: `"Issue resolved" in output` first — any single "Issue resolved" occurrence beat
    # any number of "Issue reproduced" occurrences. Post-F4: honest majority.
    from substrate.topologies.swebench_solver.records import Reproduction
    from substrate.topologies.swebench_solver.select_exec import reproduction_status

    biased_output = "Issue reproduced\n" * 10 + "Issue resolved\n"  # 10 vs 1
    assert reproduction_status(biased_output) == Reproduction.REPRODUCED  # majority wins now


async def test_repro_generator_k_greater_than_one_gathers_k_calls(tmp_path):  # type: ignore[no-untyped-def]
    # K > 1: the generator fires K parallel model calls and combines the parsed scripts into
    # one runner. Metered K times; emits ONE ReproductionTest. A DeterministicResponder returns
    # the SAME response for K identical prompts (that IS deterministic behaviour); the K
    # variance in production comes from a real sampling model (temperature > 0). This test
    # verifies the plumbing — the K wrapper, the K metering, the single combined ReproductionTest.
    from substrate import api
    from substrate.api import Runtime, read_record
    from substrate.reference._models import DeterministicResponder, ModelUsage
    from substrate.topologies.swebench_solver.records import ReproductionTest
    from substrate.topologies.swebench_solver.reproduction import repro_generator_factory

    responder = DeterministicResponder(seed=0, menu=["print('Issue reproduced')"])

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "repro",
            schemas=[ReproductionTest, ModelUsage],
            schema_version=1,
            factory=repro_generator_factory(responder, "issue text", k=3),
            deterministic=False,
        )
        b.initial("repro", input=None)
        b.termination(api.any_of(api.threshold_count("ReproductionTest", 1), api.quiescence()))

    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))
    usages = [e for e in events if e["kind"] == "ModelUsage"]
    repros = [e for e in events if e["kind"] == "ReproductionTest"]
    assert len(usages) == 3  # K=3 parallel calls, each metered
    assert len(repros) == 1  # ONE combined ReproductionTest
    # DeterministicResponder returns the same script K times; the combined runner therefore
    # embeds 3 identical variants. Each exec block appears in the runner, so the count of
    # `repro-N` markers is 3.
    code = repros[0]["payload"]["code"]
    for i in range(3):
        assert f"<repro-{i}>" in code
    # And each variant prints the same marker — 3 occurrences in the runner text.
    assert code.count("Issue reproduced") == 3


def test_repro_generator_rejects_k_less_than_one():
    from substrate.topologies.swebench_solver.reproduction import repro_generator_factory

    class _Dummy:
        def respond(self, prompt: str) -> str:
            return ""

    import pytest as _p

    with _p.raises(ValueError, match="k must be >= 1"):
        repro_generator_factory(_Dummy(), "x", k=0)

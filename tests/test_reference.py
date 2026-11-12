# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Reference topologies R-1/R-2/R-3 — CI MODE (product §8).

These run the three reference topologies with DETERMINISTIC stand-in Producers (no network,
reproducible) and assert the wiring each topology exists to exercise. CI mode proves the
WIRING and gates every commit; it deliberately does NOT stand in for the walkthrough (the
spec is explicit that CI mode alone "sanitizes away the thing each topology exists to
demonstrate" — the real adjudication/overlap is the walkthrough, run separately against
local LLMs and documented in docs/walkthroughs/). Here we assert structure: the right events
appear on the record in the right relationships."""

import pytest
from msgspec import Struct  # noqa: F401  (re-exported shapes live in the reference modules)

from substrate.api import Runtime, read_record
from substrate.reference._models import DeterministicResponder
from substrate.reference.r1_ensemble import ensemble_topology
from substrate.reference.r2_pipeline import pipeline_topology
from substrate.reference.r3_codesynth import codesynth_composed_topology


# ── R-1 Ensemble + adjudicator ─────────────────────────────────────────────────
@pytest.mark.timeout(15)
async def test_r1_ensemble_adjudicates_after_quorum(tmp_path):
    members = {
        f"m{i}": DeterministicResponder(seed=i, menu=["Paris", "Lyon", "Nice"]) for i in range(5)
    }
    adjudicator = DeterministicResponder(seed=99, menu=["m0", "m1", "m2"])
    topo = ensemble_topology(
        "Capital of France?", members=members, adjudicator=adjudicator, quorum=3, deterministic=True
    )
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    kinds = [e["kind"] for e in envs]
    # the Bus-view predicate fired the adjudicator exactly once (Once) after >= 3 Candidates
    fired = [
        e
        for e in envs
        if e["kind"] == "substrate.TriggerFired" and e["payload"].get("trigger_id") == "adjudicate"
    ]
    assert len(fired) == 1
    # the adjudicate firing came after >= quorum Candidates appeared on the bus
    adj_seq = fired[0]["seq"]
    candidates_before_fire = sum(1 for e in envs if e["kind"] == "Candidate" and e["seq"] < adj_seq)
    assert candidates_before_fire >= 3  # quorum honored
    verdict = [e for e in envs if e["kind"] == "Verdict"]
    assert len(verdict) == 1 and verdict[0]["payload"]["chosen"].startswith("m")
    assert kinds[-1] == "substrate.RunFinalised"
    # deterministic CI -> replay ceiling stays 3a (every kind author-flagged deterministic)
    rs = next(e for e in envs if e["kind"] == "substrate.RunStarted")
    assert rs["payload"]["config"]["replay_ceiling"] == "3a"


@pytest.mark.timeout(15)
async def test_r1_cancels_lingering_losers_on_adjudication(tmp_path):
    # R-1 demonstrates cancel-all-others on its OWN record: 5 members, 3 instant + 2 lingering.
    # The 3 fast Candidates meet quorum and fire the adjudicator (Once); the adjudicator is
    # instant so it COMPLETES while slowA/slowB are still sleeping (linger_seconds=5). On the
    # adjudicator's substrate.ProducerCompleted, cancel-all-others cancels the two live
    # lingerers -> two substrate.ProducerCancelled events land on the log. The cancellation is
    # REAL here (not "maybe nothing to cancel") and the run still finalises via all-completed.
    members = {f"m{i}": DeterministicResponder(seed=i, menu=["Paris"]) for i in range(3)}
    members["slowA"] = DeterministicResponder(seed=101, menu=["Paris"])
    members["slowB"] = DeterministicResponder(seed=102, menu=["Paris"])
    topo = ensemble_topology(
        "Capital of France?",
        members=members,
        adjudicator=DeterministicResponder(seed=1, menu=["m0", "m1", "m2"]),
        quorum=3,
        deterministic=True,
        slow_members=frozenset({"slowA", "slowB"}),
        linger_seconds=5.0,
    )
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"  # did not hang on the 5s-lingering candidates
    envs = list(read_record(tmp_path / "run"))

    # the two lingering members were genuinely cancelled — ProducerCancelled is on the record
    cancelled = [e for e in envs if e["kind"] == "substrate.ProducerCancelled"]
    cancelled_kinds = sorted(e["payload"]["producer"]["kind"] for e in cancelled)
    assert cancelled_kinds == ["member-slowA", "member-slowB"]  # exactly the two lingerers
    assert len(cancelled) == 2
    # the adjudicator (the subject of cancel-others) was spared, and completed normally
    assert not any(e["payload"]["producer"]["kind"] == "adjudicator" for e in cancelled)
    adj_completed = [
        e
        for e in envs
        if e["kind"] == "substrate.ProducerCompleted"
        and e["payload"]["producer"]["kind"] == "adjudicator"
    ]
    assert len(adj_completed) == 1
    # the adjudicator produced a Verdict, and the run finalised (cancel-others is non-terminal)
    verdict = [e for e in envs if e["kind"] == "Verdict"]
    assert len(verdict) == 1 and verdict[0]["payload"]["chosen"].startswith("m")
    tm = [e for e in envs if e["kind"] == "substrate.TerminationMatched"]
    assert any(e["payload"]["decision"] == "cancel-others" for e in tm)
    assert envs[-1]["kind"] == "substrate.RunFinalised"


# ── R-2 Pipeline: structured error cascade + halt-with-resume ──────────────────
@pytest.mark.timeout(20)
async def test_r2_error_cascade_pauses_then_resumes(tmp_path):
    # The integrated R-2 demonstration on a PERSISTENT bus: a recoverable fault (retry-with-
    # enrichment success), an unrecoverable fault (RetryExhausted escalation), a malformed row
    # (InputBuildFailed), a pause_await_input on RetryExhausted, and resume in a FRESH Runtime.
    root = tmp_path / "run"
    rows = ["alpha", "beta", "gamma", "delta"]
    topo = pipeline_topology(
        rows,
        transform_model=DeterministicResponder(seed=0),
        fault_row=1,  # recoverable: fails attempt 1, retry succeeds
        hard_fault_row=2,  # unrecoverable: exhausts the retry budget -> escalation
        malformed_row=3,  # the to-transform input_builder raises -> InputBuildFailed
        deterministic=True,
    )

    # 1) run to the pause. Persistent so the record survives for a fresh-process resume.
    paused = await Runtime(root, persistent=True).run(topo)
    assert paused.status == "paused"
    envs = list(read_record(root))
    kinds = [e["kind"] for e in envs]

    # mechanism 1: a REAL invalid emission (undeclared kind) -> ProducerEmittedInvalidEvent;
    # the fabricated BadEmission NEVER reached the log.
    invalid = [e for e in envs if e["kind"] == "substrate.ProducerEmittedInvalidEvent"]
    assert len(invalid) >= 2  # fault_row first attempt + hard_fault_row (>=1 attempt)
    assert all(e["payload"]["reason"] == "unknown_kind" for e in invalid)
    assert "BadEmission" not in kinds

    # mechanism 2: retry enriched via a Route (check-1 pattern) — the failure-context Route
    # staged the reason (InjectionApplied), and the retry firing's RECORDED resolved input
    # carried it. The recoverable fault_row then produced a Transformed on attempt 2.
    assert any(e["kind"] == "substrate.InjectionApplied" for e in envs)
    retry_fires = [
        e
        for e in envs
        if e["kind"] == "substrate.TriggerFired" and e["payload"].get("trigger_id") == "retry"
    ]
    assert retry_fires, "the retry Trigger must fire on the invalid emission"
    assert any(e["payload"]["resolved_input"].get("prior_reason") for e in retry_fires)
    transformed = [e for e in envs if e["kind"] == "Transformed"]
    assert any(t["payload"]["row"] == 1 and t["payload"]["attempt"] == 2 for t in transformed)

    # mechanism 3: RetryExhausted escalation for the unrecoverable row.
    exhausted = [e for e in envs if e["kind"] == "RetryExhausted"]
    assert len(exhausted) == 1 and exhausted[0]["payload"]["row"] == 2

    # mechanism 4: the malformed row's input_builder raised -> InputBuildFailed (no transform).
    ibf = [e for e in envs if e["kind"] == "substrate.InputBuildFailed"]
    assert ibf and any(e["payload"].get("trigger_id") == "to-transform" for e in ibf)

    # mechanism 5: the run PAUSED on RetryExhausted (not finalised — no RunFinalised yet).
    assert "substrate.RunFinalised" not in kinds
    tm = [e for e in envs if e["kind"] == "substrate.TerminationMatched"]
    assert tm and tm[-1]["payload"]["decision"] == "pause-await-input"

    # 2) resume in a FRESH Runtime (the F-PERS-2 cross-process promise). Inject the operator
    #    override; the recovery Producer runs and the run finalises.
    from substrate.reference.r2_pipeline import operator_override

    resumed = await Runtime(root, persistent=True).resume(
        topo, resume_event=operator_override(row=2)
    )
    assert resumed.status == "finalised"
    assert resumed.run_id == paused.run_id  # identity preserved across resume

    after = list(read_record(root))
    after_kinds = [e["kind"] for e in after]
    assert "OperatorOverride" in after_kinds  # the external resume event landed
    assert any(e["kind"] == "Recovered" and e["payload"]["row"] == 2 for e in after)
    assert "substrate.RunFinalised" in after_kinds
    # seq continuity across the pause boundary: one dense sequence, no reset, no gap.
    seqs = [e["seq"] for e in after]
    assert seqs == list(range(len(seqs)))


# ── R-3 Code synthesis with overlap, composed ──────────────────────────────────
@pytest.mark.timeout(20)
async def test_r3_composed_exports_only_artifact_ready(tmp_path):
    # a small program in chunks that SPAN a declaration boundary (overlap): the first def is
    # split across two chunks, proving the chunk-boundary predicate fires per declaration.
    chunks = [
        "def add(a, b):\n",
        "    return a + b\n",  # completes add() across two chunks
        "def mul(a, b):\n    return a * b\n",  # mul() in one chunk
    ]
    inner_root = tmp_path / "inner"
    topo = codesynth_composed_topology(chunks, str(inner_root), deterministic=True)
    result = await Runtime(tmp_path / "outer").run(topo)
    assert result.status == "finalised"
    outer = list(read_record(tmp_path / "outer"))
    inner = list(read_record(inner_root))
    # composition boundary: only the mapped kind crossed; inner kinds did NOT
    outer_kinds = [e["kind"] for e in outer]
    assert any(k == "OuterArtifact" for k in outer_kinds)
    assert "CodeChunk" not in outer_kinds and "Declaration" not in outer_kinds
    # the inner run is complete + independent, and saw 2 declarations (add, mul) despite the
    # overlap (add() spanned two chunks but fired the AST once)
    inner_decls = [e for e in inner if e["kind"] == "Declaration"]
    assert len(inner_decls) == 2
    assert inner[-1]["kind"] == "substrate.RunFinalised"
    # the export map is observable in the outer RunStarted manifest (check 7 / F-COMP-1)
    rs = next(e for e in outer if e["kind"] == "substrate.RunStarted")
    assert rs["payload"]["topology"]["exports"] == {"ArtifactReady": "OuterArtifact"}


def test_cli_responder_shells_any_command_line_model_and_fails_loud() -> None:
    # CliResponder turns ANY command-line model into a Responder: it runs the command with the prompt
    # on its standard input (K348; before, the final argument) and returns stdout. A stub command (no real CLI needed) proves the
    # mechanism; `claude -p` / `gemini -p` are the SAME shape, exercised live. Substrate's tool loop
    # provides the tools, so even a plain prompt->text CLI drives FULL_SUITE.
    from substrate.adapters import CliResponder

    echo = CliResponder(["python3", "-c", "import sys; print('cli:' + sys.stdin.read())"])
    assert echo.respond("hello") == "cli:hello"

    # a non-zero exit is a LOUD failure, never a silent stub (the loop turns it into a typed
    # ToolResult(ok=False); the Responder itself raises).
    boom = CliResponder(["python3", "-c", "import sys; sys.exit(3)"], name="boom")
    with pytest.raises(RuntimeError, match="exit 3"):
        boom.respond("x")

    # empty output also fails loud — a CLI that printed nothing is not a valid reply.
    quiet = CliResponder(["python3", "-c", "pass"], name="quiet")
    with pytest.raises(RuntimeError, match="no output"):
        quiet.respond("x")


def test_ollama_base_url_env_lets_a_run_reach_ollama_across_a_boundary(monkeypatch) -> None:
    # The container test arena runs the agent INSIDE a container but the model stays on the HOST;
    # OLLAMA_BASE_URL points the Responder at host.docker.internal without touching any call site.
    from substrate.adapters import OllamaResponder

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    assert OllamaResponder("m")._endpoint == "http://host.docker.internal:11434/api/chat"

    # an explicit base_url always wins over the env; with neither, the host default holds.
    assert OllamaResponder("m", base_url="http://elsewhere:1234")._endpoint == (
        "http://elsewhere:1234/api/chat"
    )
    monkeypatch.delenv("OLLAMA_BASE_URL")
    assert OllamaResponder("m")._endpoint == "http://localhost:11434/api/chat"

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Real-model demo suite — every application's CLAIM, proven against a LIVE local model.

Deterministic CI proves only the wiring; per the spec it "sanitizes away the thing each topology
exists to demonstrate". This suite runs each application against a REAL local LLM (Ollama) and
asserts the claim FROM THE RECORD. The model's words are non-deterministic and irrelevant; the
topology's BEHAVIOUR is what we assert, with a deterministic predicate — NEVER an LLM-as-judge.

Every predicate here is SUBSTANTIVE and is built to FAIL on a thin/wrong run, not just on a crash:
it asserts the *thing* (distinct answers = real disagreement; the decision parsed from the real turn,
not the detector's CI fallback; recursion actually reaching the depth bound), never just "an event
exists". A predicate that cannot fail on a thin run is worthless (see the suite's history: a
div-by-zero "ensemble" where everyone agreed once passed a shell predicate).

MODELS: weak+fast `llama3.2:1b` where the claim is STRUCTURAL (it just needs real output); the
capable `qwen2.5:7b-instruct` where the claim needs reasoning (disagreement, debate progression,
role-divergent review, a real game decision). `deepseek-r1:8b` is avoided — it returns empty content.

GATING — two outcomes, never conflated:
  - a required model ABSENT  -> SKIP (reason names the model); inert on machines without it.
  - model PRESENT but the predicate FAILS -> HARD FAIL (the demo did not demonstrate).
Run here (Ollama present): part of `uv run pytest`. Deselect elsewhere: `pytest -m "not realmodel"`.
"""

from __future__ import annotations

import pytest

from substrate.api import Runtime, read_record
from substrate.reference._models import OllamaResponder
from substrate.reference.r1_ensemble import ensemble_topology
from substrate.reference.r2_pipeline import operator_override, pipeline_topology
from substrate.reference.r3_codesynth import codesynth_composed_topology
from substrate.topologies.adversarial_pair import adversarial_pair_topology
from substrate.topologies.code_review import DEFAULT_ROLES, code_review_topology
from substrate.topologies.debate import debate_topology
from substrate.topologies.intel_asymmetry import intel_asymmetry_topology
from substrate.topologies.natural_conversation import natural_conversation_topology
from substrate.topologies.prisoners_dilemma import prisoners_dilemma_topology
from substrate.topologies.pair_coding import pair_coding_topology
from substrate.topologies.recursive_decomposition import recursive_decomposition_topology

pytestmark = pytest.mark.realmodel

_OLLAMA_V1 = "http://localhost:11434/v1"
_FAST = "llama3.2:1b"  # structural claims: just needs real output
_SMART = "qwen2.5:7b-instruct"  # capability claims: disagreement, progression, real decisions


def _require(*models: str) -> None:
    """SKIP (never fail) iff Ollama or a required model is absent — the presence gate."""
    try:
        import httpx

        ids = {m["id"] for m in httpx.get(_OLLAMA_V1 + "/models", timeout=4).json().get("data", [])}
    except Exception as exc:  # noqa: BLE001 - any unreachability is a SKIP
        pytest.skip(f"real-model demo skipped — Ollama not reachable ({type(exc).__name__})")
    missing = [m for m in models if m not in ids]
    if missing:
        pytest.skip(f"real-model demo skipped — model(s) absent: {', '.join(missing)}")


def _payloads(root, kind):  # noqa: ANN001
    return [e["payload"] for e in read_record(root) if e["kind"] == kind]


# ── ensemble (R-1): real DISAGREEMENT + real adjudication + cancel-others ───────
@pytest.mark.timeout(120)
async def test_ensemble_real_disagreement_and_cancel(tmp_path):
    _require(_FAST, _SMART)
    fast = {
        f"m{i}": OllamaResponder(
            _FAST,
            max_tokens=64,
            temperature=0.9,
            system="Answer with ONE short word. No explanation.",
        )
        for i in range(3)
    }
    slow = {
        n: OllamaResponder(
            _FAST,
            max_tokens=64,
            temperature=0.9,
            system="Answer with ONE short word. No explanation.",
        )
        for n in ("slowA", "slowB")
    }
    adj = OllamaResponder(
        _SMART,
        max_tokens=64,
        system="Given candidate answers labelled by member id, pick the single best one. Reply with JUST the member id (e.g. m0).",
    )
    topo = ensemble_topology(
        "In one word, what is the most important quality in a leader?",
        members={**fast, **slow},
        adjudicator=adj,
        quorum=3,
        slow_members=frozenset(slow),
        linger_seconds=8.0,
        deterministic=False,
    )
    await Runtime(tmp_path / "run").run(topo)
    envs = list(read_record(tmp_path / "run"))
    answers = [e["payload"]["answer"].strip().lower() for e in envs if e["kind"] == "Candidate"]
    verdicts = [e for e in envs if e["kind"] == "Verdict"]
    cancelled = [e for e in envs if e["kind"] == "substrate.ProducerCancelled"]
    # SUBSTANCE: the weak members genuinely DISAGREE (>=2 distinct answers) — fails on a "2+2" prompt.
    assert len(set(answers)) >= 2, f"no real disagreement; answers={answers}"
    assert len(verdicts) == 1 and verdicts[0]["payload"]["chosen"], "no real adjudication"
    assert len(cancelled) >= 2, "cancel-all-others did not fire on both lingering members"


# ── code review: role-DIVERGENT critiques + quorum adjudication + cancel-others ──
@pytest.mark.timeout(300)
async def test_code_review_role_divergence_and_cancel(tmp_path):
    _require(_SMART)
    code = (
        "def get_user(name):\n"
        '    q = "SELECT * FROM users WHERE name = \'" + name + "\'"\n'
        "    rows = db.execute(q)\n"
        "    out = []\n"
        "    for r in rows:\n"
        "        for s in rows:\n"
        "            if r.id == s.id: out.append(r)\n"
        "    return out"
    )
    topo = code_review_topology(
        code,
        responders={r: OllamaResponder(_SMART, max_tokens=256) for r in DEFAULT_ROLES},
        judge=OllamaResponder(_SMART, max_tokens=256),
        quorum=3,
        # linger LONGER than the fast reviewers' real call latency so the lingerers are reliably still
        # running when the quorum fires the judge -> cancel-others has live victims. 0.4s worked only
        # while reviewers ran SERIALLY (blocking); now they run concurrently (the offload fix), so the
        # linger must clear the concurrent fast-path. R-1 uses 8.0 for the same reason.
        slow_roles=frozenset({"correctness", "clarity"}),
        linger_seconds=8.0,
    )
    await Runtime(tmp_path / "run").run(topo)
    envs = list(read_record(tmp_path / "run"))
    summaries = [
        str(e["payload"]["summary"]).lower() for e in envs if e["kind"] == "CritiquePosted"
    ]
    verdicts = [e for e in envs if e["kind"] == "VerdictRendered"]
    cancelled = [e for e in envs if e["kind"] == "substrate.ProducerCancelled"]
    # SUBSTANCE: different roles surface DIFFERENT issues (>=2 distinct summaries) — fails when every
    # reviewer latches onto one glaring bug (the div-by-zero / "report the worst issue" anti-pattern).
    assert len(set(summaries)) >= 2, f"no role divergence; summaries={summaries}"
    assert len(verdicts) == 1, "the judge did not adjudicate"
    assert len(cancelled) >= 1, "lingering reviewers were not cancelled"


# ── prisoner's dilemma: the prisoner emits its own DECISION (attributed to it) ──
@pytest.mark.timeout(180)
async def test_pd_real_decision_on_record(tmp_path):
    _require(_SMART)
    await Runtime(tmp_path / "run").run(
        prisoners_dilemma_topology(walkthrough=True, model=_SMART, max_rounds=1)
    )
    decisions = [e for e in read_record(tmp_path / "run") if e["kind"] == "Decision"]
    # SUBSTANCE: both prisoners decided. A Decision exists ONLY if the prisoner's own turn carried a
    # real token (the outcome fn returns None otherwise) — so its existence proves a real decision; no
    # cross-check needed. And the record ATTRIBUTES it to the prisoner (F-OBS-2), not a parser.
    by_prisoner = {e["payload"]["prisoner"]: e for e in decisions}
    assert set(by_prisoner) == {1, 2}, (
        f"both decisions not recorded: {[e['payload'] for e in decisions]}"
    )
    assert all(e["payload"]["choice"] in {"silent", "talk"} for e in decisions)
    assert all(e["producer"]["kind"] == f"speaker-{p}" for p, e in by_prisoner.items())


# ── intel asymmetry: the analyst emits its own calibrated JOINT CALL ────────────
@pytest.mark.timeout(240)
async def test_intel_real_jointcall_on_record(tmp_path):
    _require(_SMART)
    await Runtime(tmp_path / "run").run(
        intel_asymmetry_topology(walkthrough=True, model=_SMART, max_rounds=2)
    )
    calls = [e for e in read_record(tmp_path / "run") if e["kind"] == "JointCall"]
    # SUBSTANCE: a JointCall exists only if the analyst's own turn carried a real calibrated call, and
    # it is attributed to the analyst (F-OBS-2). Existence => real; provenance => the right author.
    assert calls, "no JointCall recorded — the analyst made no calibrated call"
    assert all(0 <= e["payload"]["confidence"] <= 100 for e in calls)
    assert all(e["producer"]["kind"] == f"speaker-{e['payload']['analyst']}" for e in calls)


# ── debate: a two-sided pressure test that PROGRESSES (no echo) ─────────────────
@pytest.mark.timeout(240)
async def test_debate_progresses_without_echo(tmp_path):
    _require(_SMART)
    await Runtime(tmp_path / "run").run(
        debate_topology(walkthrough=True, model=_SMART, max_rounds=2)
    )
    turns = _payloads(tmp_path / "run", "Turn")
    texts = [t["text"] for t in turns]
    # SUBSTANCE: both advocates argue across rounds AND every turn is DISTINCT (the round-2 echo bug
    # produced verbatim duplicates) — fails on the echo, which a turn-count predicate would pass.
    assert {t["speaker"] for t in turns} == {1, 2}, "both sides did not argue"
    assert len(set(texts)) == len(texts), (
        f"echo: only {len(set(texts))} distinct of {len(texts)} turns"
    )


# ── recursive decomposition: real recursion to the depth bound ─────────────────
@pytest.mark.timeout(180)
async def test_recursion_reaches_depth_bound(tmp_path):
    _require(_FAST)
    await Runtime(tmp_path / "run").run(
        recursive_decomposition_topology(
            "build an auth feature", solver_model=OllamaResponder(_FAST), max_depth=2, fanout=2
        )
    )
    envs = list(read_record(tmp_path / "run"))
    subtasks = [e["payload"] for e in envs if e["kind"] == "SubtaskProposed"]
    solutions = [e for e in envs if e["kind"] == "SolutionReached"]
    # SUBSTANCE: the cascade actually reached the depth bound AND produced real leaf solutions —
    # fails if recursion stops short of the bound or no leaves are reached.
    assert subtasks and max(s["depth"] for s in subtasks) == 2, (
        "recursion did not reach the depth bound"
    )
    assert solutions, "no leaf SolutionReached — the recursion produced nothing"


# ── pair coding: the Route carries the navigator's real Suggestion into the driver ──
@pytest.mark.timeout(180)
async def test_pair_coding_route_carries_suggestion(tmp_path):
    _require(_FAST)
    await Runtime(tmp_path / "run").run(
        pair_coding_topology(
            "write a function to validate an email",
            driver_model=OllamaResponder(_FAST),
            navigator_model=OllamaResponder(_FAST),
            chunks=[
                "def validate_email(s):\n",
                "    import re\n",
                "    return bool(re.match(r'.+@.+', s))\n",
            ],
        )
    )
    envs = list(read_record(tmp_path / "run"))
    injections = [e for e in envs if e["kind"] == "substrate.InjectionApplied"]
    suggestions = [e["payload"] for e in envs if e["kind"] == "Suggestion"]
    # SUBSTANCE: real navigator Suggestions exist AND the Route actually staged them (InjectionApplied)
    # — fails if the navigator never produced one or the Route never carried it.
    assert suggestions, "the navigator produced no Suggestion"
    assert injections, "no InjectionApplied — the Route did not carry the suggestion to the driver"


# ── natural conversation: the instrument ablation DELTA (WITH vs WITHOUT) ───────
@pytest.mark.timeout(600)
async def test_instrument_ablation_delta(tmp_path):
    _require(_FAST)
    await Runtime(tmp_path / "with").run(
        natural_conversation_topology(instruments=True, walkthrough=True, model=_FAST, max_rounds=3)
    )
    await Runtime(tmp_path / "without").run(
        natural_conversation_topology(
            instruments=False, walkthrough=True, model=_FAST, max_rounds=3
        )
    )
    with_kinds = {e["kind"] for e in read_record(tmp_path / "with")}
    without_kinds = {e["kind"] for e in read_record(tmp_path / "without")}
    instrument_kinds = {"CommonGround", "Repair", "Grade"}
    # SUBSTANCE: composition is the DELTA — instruments fire WITH and are absent WITHOUT, over the
    # same prompts. Fails if the ablation shows no difference.
    assert instrument_kinds & with_kinds, "instruments did not emit in the WITH arm"
    assert not (instrument_kinds & without_kinds), "the WITHOUT arm leaked instrument events"


class _UppercaseTransform:
    """A deterministic CODE transform — uppercasing a word is not a model task. Substrate Producers
    are heterogeneous; a 1b LLM here was 'a model where code belongs' (spec §0.1's transform/validator
    path is deterministic). R-2's claim is the CASCADE, which is model-agnostic — so this app has NO
    model role, and the demo is not gated on Ollama. respond() is the Responder seam being pure code."""

    def respond(self, text: str) -> str:
        return text.upper()


# ── adversarial pair: a bounded refinement loop with REAL findings routed back ─
@pytest.mark.timeout(180)
async def test_adversarial_pair_real_findings_and_bounded_loop(tmp_path):
    _require(_SMART)
    topo = adversarial_pair_topology(
        writer_model=OllamaResponder(
            _SMART, max_tokens=256, temperature=0.7, system="You write a short artifact."
        ),
        finder_model=OllamaResponder(_SMART, max_tokens=256, system="You find one flaw."),
        max_attempts=2,
        deterministic=False,
    )
    await Runtime(tmp_path / "run").run(topo)
    envs = list(read_record(tmp_path / "run"))
    artifacts = [e["payload"] for e in envs if e["kind"] == "Artifact"]
    challenges = [e["payload"] for e in envs if e["kind"] == "Challenge"]
    injections = [e for e in envs if e["kind"] == "substrate.InjectionApplied"]
    # SUBSTANCE: the finder emits a REAL flaw (not the old templated "issue@vN"), the Route carries it
    # into the writer's next version, and the loop is BOUNDED (stops at max_attempts, can't run away).
    # (Whether the writer's revision *improves* the artifact is model-dependent and NOT asserted here.)
    assert len(artifacts) >= 3, "the refinement loop did not produce v0..v2"
    assert challenges and all(
        len(c["issue"]) > 15 and "issue@v" not in c["issue"] for c in challenges
    ), f"findings are not real model output: {[c['issue'] for c in challenges]}"
    assert injections, "the challenge was not routed into the next writer (InjectionApplied)"
    assert max(c["version"] for c in challenges) == 2, "the loop is not bounded at max_attempts"


# ── pipeline (R-2): the structured-error cascade, with halt-and-resume (deterministic) ──
@pytest.mark.timeout(60)
async def test_pipeline_cascade_halt_and_resume(tmp_path):
    # R-2 has no model role: the transform is deterministic CODE, the faults are SEEDED. The demo
    # proves the CASCADE — invalid-emission -> retry -> RetryExhausted -> PAUSE, then resume in a
    # FRESH Runtime -> Recovered -> finalise on a continuous seq.
    topo = pipeline_topology(
        ["alpha", "beta", "gamma", "delta"],
        transform_model=_UppercaseTransform(),
        fault_row=1,
        hard_fault_row=2,
        malformed_row=3,
        deterministic=False,
    )
    root = tmp_path / "run"
    paused = await Runtime(root, persistent=True).run(topo)
    envs = list(read_record(root))
    assert paused.status == "paused", f"the cascade did not pause: {paused.status}"
    # the deterministic transform is CORRECT (code, not a flaky model): row 0 'alpha' -> 'ALPHA'.
    transformed = {
        e["payload"]["row"]: e["payload"]["out"] for e in envs if e["kind"] == "Transformed"
    }
    assert transformed.get(0) == "ALPHA", f"the code transform is wrong: {transformed}"
    assert [e for e in envs if e["kind"] == "RetryExhausted"], (
        "the unrecoverable fault did not exhaust retries"
    )
    # resume across a FRESH Runtime (the cross-process persistence promise) with the operator override
    resumed = await Runtime(root, persistent=True).resume(
        topo, resume_event=operator_override(row=2)
    )
    after = list(read_record(root))
    assert resumed.status == "finalised" and resumed.run_id == paused.run_id, (
        "resume did not continue the run"
    )
    assert [e for e in after if e["kind"] == "Recovered"], (
        "the override did not recover the paused row"
    )
    assert [e["seq"] for e in after] == list(range(len(after))), (
        "seq not continuous across pause/resume"
    )


# ── codesynth (R-3): concurrent checker over real code + composition isolation ──
@pytest.mark.timeout(180)
async def test_codesynth_concurrent_checker_isolation(tmp_path):
    _require(_SMART)
    writer = OllamaResponder(
        _SMART, max_tokens=1024, system="Write ONLY Python code, no prose, no markdown fences."
    )
    code = writer.respond(
        "Write two functions: add(a,b) returning a+b, and mul(a,b) returning a*b."
    )
    chunks = [
        code[i : i + 30] for i in range(0, len(code), 30)
    ]  # ~30-char chunks -> cross-chunk overlap
    inner_root = tmp_path / "inner"
    await Runtime(tmp_path / "run").run(
        codesynth_composed_topology(chunks, str(inner_root), deterministic=False)
    )
    inner = list(read_record(inner_root))
    outer = list(read_record(tmp_path / "run"))
    declarations = [e for e in inner if e["kind"] == "Declaration"]
    leaked = [e["kind"] for e in outer if e["kind"] in ("CodeChunk", "Declaration", "TypecheckOk")]
    artifacts = [e for e in outer if e["kind"] == "OuterArtifact"]
    # SUBSTANCE: the concurrent checker found real declarations in the streamed REAL code, the inner
    # composition stayed ISOLATED (no inner kind crossed outward), and the artifact crossed the seam.
    assert len(declarations) >= 2, (
        f"checker found <2 Declarations in the streamed code: {len(declarations)}"
    )
    assert not leaked, f"inner kinds leaked to the outer record: {leaked}"
    assert artifacts, "no OuterArtifact crossed the composition boundary"

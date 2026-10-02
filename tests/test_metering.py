# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""ModelUsage at the Responder seam — Sprint 1 of the objective-validation layer.

The matched-compute comparison the benchmarking layer rests on needs per-model-call token/latency
data, and the seam used to discard it (`OllamaResponder._content` kept only `message.content`). These
tests cover the seam in three regimes, all WITHOUT a network:

  - the deterministic stand-in derives stable usage (so a CI record stays byte-identical), verified
    end-to-end by emitting a ModelUsage event from a Producer and reading it back off the record;
  - the Ollama accounting parser reads prompt_eval_count / eval_count / total_duration off a literal
    /api/chat response dict (no daemon needed — the parse is a pure static method);
  - two runs of the metered topology are byte-identical (the derived usage did not break determinism).

The real-provider path (OllamaResponder.arespond_metered against a live daemon) is exercised in the
gated @realmodel walkthroughs, not here — the same dual-mode boundary every topology uses.
"""

from msgspec import Struct

from substrate import api
from substrate.api import Runtime, first_divergence, read_record
from substrate.reference._models import (
    DeterministicResponder,
    ModelUsage,
    OllamaResponder,
    call_responder_metered,
)

_PROMPT = "compute the joint cost"  # 4 whitespace-split words -> 4 derived prompt tokens


class _Answer(Struct, frozen=True):
    text: str


def _metered_topology(seed: int = 0):
    """A one-Producer topology whose model calls the metered seam and emits BOTH its answer and the
    ModelUsage for the call — the shape every assay Arm uses to land accounting on its inner record."""
    responder = DeterministicResponder(seed=seed)

    def _factory():
        async def model(_inp):
            text, usage = await call_responder_metered(responder, _PROMPT)
            yield usage
            yield _Answer(text=text)

        return lambda: model

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "model",
            schemas=[ModelUsage, _Answer],
            schema_version=1,
            factory=_factory(),
            deterministic=True,
        )
        b.initial("model", input=None)
        b.termination(api.all_completed())

    return topo


async def test_model_usage_lands_on_the_record(tmp_path):
    result = await Runtime(tmp_path / "run").run(_metered_topology())
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    usage = [e for e in envs if e["kind"] == "ModelUsage"]
    assert len(usage) == 1
    p = usage[0]["payload"]
    # the stand-in has no provider accounting -> deterministic word-count estimate, wall_ms=0, and a
    # model field that names the responder so a reader can tell estimate from provider truth.
    assert p["prompt_tokens"] == len(_PROMPT.split()) == 4
    assert p["completion_tokens"] == 1  # the stub answer "stub[0]:<hex>" is a single token
    assert p["wall_ms"] == 0
    assert p["model"] == "DeterministicResponder"
    assert p["estimated"] is True  # a word-count stand-in, marked as such in the data
    # the usage event precedes the answer it accounts for, both on the same log.
    kinds = [e["kind"] for e in envs]
    assert kinds.index("ModelUsage") < kinds.index("_Answer")


async def test_metered_topology_is_deterministic(tmp_path):
    # deriving usage from word counts must not perturb byte-identity (it is the CI-record guarantee).
    await Runtime(tmp_path / "a").run(_metered_topology())
    await Runtime(tmp_path / "b").run(_metered_topology())
    assert first_divergence(tmp_path / "a", tmp_path / "b") is None


async def test_call_responder_metered_returns_stable_usage():
    r = DeterministicResponder(seed=7)
    text1, u1 = await call_responder_metered(r, _PROMPT)
    text2, u2 = await call_responder_metered(r, _PROMPT)
    assert text1 == text2  # the stand-in is pure
    assert u1 == u2  # same prompt + responder -> same derived usage
    assert u1.prompt_tokens == 4 and u1.wall_ms == 0 and u1.estimated is True
    assert u1.total_tokens() == u1.prompt_tokens + u1.completion_tokens


def test_ollama_usage_parse_reads_the_discarded_fields():
    # a representative Ollama native /api/chat response: the accounting fields `_content` ignored.
    # total_duration is large (it FOLDS IN a 5s model load); wall_ms must come from the eval phases
    # (0.4s prompt-eval + 2.0s generation = 2.4s), NOT total_duration — the load-time exclusion.
    data = {
        "model": "llama3.2:1b",
        "message": {"role": "assistant", "content": "20"},
        "prompt_eval_count": 137,
        "eval_count": 12,
        "prompt_eval_duration": 400_000_000,  # 0.4s
        "eval_duration": 2_000_000_000,  # 2.0s
        "load_duration": 5_000_000_000,  # 5.0s cold VRAM load
        "total_duration": 7_400_000_000,  # 7.4s end-to-end (load + eval) — must NOT be used
        "done": True,
    }
    usage = OllamaResponder._usage(data, "llama3.2:1b")
    assert usage.model == "llama3.2:1b"
    assert usage.prompt_tokens == 137
    assert usage.completion_tokens == 12
    assert usage.wall_ms == 2400  # (0.4 + 2.0)s inference, NOT the 7.4s that includes load
    assert usage.estimated is False  # provider truth, not a stand-in
    # the content extractor still works on the same dict (refactor preserved it).
    assert OllamaResponder("m")._content(data) == "20"


def test_ollama_usage_parse_falls_back_to_total_duration_without_eval_phases():
    # some responses carry only total_duration; without the eval phases, fall back to it.
    usage = OllamaResponder._usage({"total_duration": 1_500_000_000, "eval_count": 3}, "m")
    assert usage.wall_ms == 1500 and usage.completion_tokens == 3


def test_ollama_usage_parse_degrades_on_missing_fields():
    # a truncated / error-shaped response must not raise — missing accounting degrades to 0.
    usage = OllamaResponder._usage({"message": {"content": "x"}}, "m")
    assert usage.prompt_tokens == 0 and usage.completion_tokens == 0 and usage.wall_ms == 0

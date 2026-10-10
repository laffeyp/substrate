# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Live-model compaction: a real local model, a real window, a conversation that outgrows it.

Driver: `llama3.2:1b` on the local Ollama with `num_ctx=2048`, Ollama's own default context
window, and the session told the same window. The conversation asks for a few sentences on one
topic after another until the history no longer fits the prompt budget (60% of 2,048 tokens);
from then on the session drops the oldest turns from the prompt (rolling window) and records a
`TranscriptCompacted` for each drop. The full conversation stays on the record.

Checks, all on the record:
1. at least one `TranscriptCompacted`, each with a dropped range below its kept start and fewer
   tokens after than before;
2. every turn after the first compaction still gets a non-empty reply from the model;
3. no `substrate.ProducerFailed` on the model;
4. every recorded prompt (`PromptComposed`) fits the 2,048-token window by our estimate, and
5. by Ollama's own count: every request Ollama received carried `num_ctx=2048`, and Ollama read
   fewer prompt tokens than the window (`prompt_eval_count`), so it never cut a prompt. The
   first call of the run has no prompt cache, so its count is compared with our chars/4 estimate.

The reply cap is 800 tokens: the session gives the history 60% of the window and leaves 40% for
the reply.

Marked `realmodel`; skips when Ollama or the model is absent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from substrate import api
from substrate.adapters import OllamaResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.transcript import TURN_EVENT_KINDS, compose_model_prompt

pytestmark = pytest.mark.realmodel

_MODEL = "llama3.2:1b"
_WINDOW = 2048  # Ollama's default num_ctx; the session is told the same window
_MAX_TURNS = 30
_TOPICS = [
    "how bread rises",
    "why the sky is blue",
    "how a bicycle stays upright",
    "what a river delta is",
    "how bees make honey",
    "why ice floats",
    "how a compass works",
    "what causes tides",
    "how a camera lens focuses light",
    "why leaves change color in autumn",
    "how a refrigerator keeps food cold",
    "what makes a rainbow",
    "how sound travels through air",
    "why volcanoes erupt",
    "how a lighthouse warns ships",
]


def _require_model() -> None:
    try:
        names = {
            m["name"]
            for m in httpx.get("http://127.0.0.1:11434/api/tags", timeout=4).json()["models"]
        }
    except Exception as exc:  # noqa: BLE001 — any unreachability is a SKIP
        pytest.skip(f"Ollama not reachable ({type(exc).__name__})")
    if _MODEL not in names:
        pytest.skip(f"model absent: {_MODEL}")


OBSERVED: list[dict[str, Any]] = []


class _Observed(OllamaResponder):
    """The real OllamaResponder, recording what Ollama received and reported on every call."""

    async def _achat(self, prompt: str, tools: Any = None) -> dict[str, object]:
        _headers, payload = self._request(prompt, tools)
        data = await super()._achat(prompt, tools)
        OBSERVED.append(
            {
                "num_ctx": payload["options"]["num_ctx"],  # type: ignore[index]
                "num_predict": payload["options"].get("num_predict"),  # type: ignore[union-attr]
                "prompt_chars": len(prompt),
                "prompt_eval_count": data.get("prompt_eval_count"),
                "eval_count": data.get("eval_count"),
                "done_reason": data.get("done_reason"),
            }
        )
        return data


def _topology(first: UserMessage | None, workspace: Path) -> Any:
    return session_topology(
        driver=_Observed(_MODEL, num_ctx=_WINDOW, max_tokens=800, temperature=0),
        driver_name=_MODEL,
        driver_context_tokens=_WINDOW,
        seed="You are a helpful assistant.",
        tools={},
        session_id="s_live_compaction",
        workspace_path=str(workspace),
        first_turn_user_message=first,
    )


def _turn_text(i: int) -> str:
    return f"In four or five sentences, explain {_TOPICS[i % len(_TOPICS)]}."


@pytest.mark.timeout(900)
async def test_live_compaction_fires_and_model_still_answers(tmp_path: Path) -> None:
    _require_model()
    OBSERVED.clear()
    root = tmp_path / "record"
    workspace = tmp_path / "ws"
    workspace.mkdir()

    def _compactions() -> list[dict[str, Any]]:
        return [e for e in api.read_record(root) if e["kind"] == "TranscriptCompacted"]

    first = UserMessage(text=_turn_text(0), turn_index=0, assembled_prompt="", slash_source="test")
    result = await api.Runtime(root, persistent=True).run(_topology(first, workspace))
    assert result.status == "paused", result.status
    turns_after_compaction = 0
    for i in range(1, _MAX_TURNS):
        message = UserMessage(
            text=_turn_text(i), turn_index=i, assembled_prompt="", slash_source="test"
        )
        result = await api.Runtime(root, persistent=True).resume(
            _topology(None, workspace), resume_event=message
        )
        assert result.status == "paused", f"turn {i + 1}: {result.status}"
        if _compactions():
            turns_after_compaction += 1
            if turns_after_compaction >= 3:
                break

    envelopes = list(api.read_record(root, resolve_blobs=True))
    compactions = [e for e in envelopes if e["kind"] == "TranscriptCompacted"]
    assert compactions, f"no TranscriptCompacted in {_MAX_TURNS} turns at a {_WINDOW}-token window"

    # (1) each compaction is well formed
    for env in compactions:
        p = env["payload"]
        lo, hi = p["dropped_seq_range"]
        assert lo <= hi < p["kept_seq_start"], p
        assert p["tokens_after"] < p["tokens_before"], p

    # (2) the model keeps answering after the history was trimmed
    first_seq = compactions[0]["seq"]
    later_replies = [
        e["payload"]["text"]
        for e in envelopes
        if e["kind"] == "ModelReply" and e["seq"] > first_seq
    ]
    assert later_replies and all(t.strip() for t in later_replies), later_replies

    # (3) the model never failed
    failures = [
        e
        for e in envelopes
        if e["kind"] == "substrate.ProducerFailed"
        and (e["payload"].get("producer") or {}).get("kind") == "model"
    ]
    assert not failures, failures

    # (4) every prompt the model was sent fits the real window
    sizes = [e["payload"]["total_tokens"] for e in envelopes if e["kind"] == "PromptComposed"]
    assert sizes and max(sizes) <= _WINDOW, sizes

    # (5) what Ollama actually received and read
    assert OBSERVED, "no Ollama call was observed"
    assert all(c["num_ctx"] == _WINDOW for c in OBSERVED), OBSERVED
    assert all(int(c["prompt_eval_count"] or 0) < _WINDOW for c in OBSERVED), OBSERVED
    first_call = OBSERVED[0]
    estimate = first_call["prompt_chars"] // 4
    print(
        f"first call: our estimate {estimate} tokens, Ollama read {first_call['prompt_eval_count']}"
    )
    print(
        "per call (Ollama prompt tokens, reply tokens):",
        [(c["prompt_eval_count"], c["eval_count"]) for c in OBSERVED],
    )

    # (6) K268: each model step's recorded input is a ticket, and the prompt it built from the
    # ticket equals the one built from the full record over the same range
    import json

    fires = [
        e
        for e in envelopes
        if e["kind"] == "substrate.TriggerFired" and e["payload"].get("factory") == "model"
    ]
    prompts = [e["payload"]["text"] for e in envelopes if e["kind"] == "PromptComposed"]
    assert max(len(json.dumps(f["payload"].get("resolved_input"))) for f in fires) < 400
    for fire, prompt in zip(fires, prompts, strict=True):
        ticket = fire["payload"]["resolved_input"]["history_ref"]
        kept = [
            e
            for e in envelopes
            if ticket["from_seq"] <= e["seq"] <= ticket["to_seq"] and e["kind"] in TURN_EVENT_KINDS
        ]
        base, _ = compose_model_prompt(
            history=kept, seed="You are a helpful assistant.", per_turn="", fragments=[]
        )
        assert prompt == base, (prompt[-200:], base[-200:])

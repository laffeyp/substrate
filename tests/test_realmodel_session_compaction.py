# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 050 — live-model compaction end-to-end.

The unit tests under tests/test_render_*.py feed synthetic event lists into
`render_transcript` and check the shape. None of them prove that a REAL
driver, handed the rendered prompt after older turns dropped, still returns
a coherent answer — the whole point of compaction. This test does.

Setup:
- Driver: OllamaResponder("llama3.2:1b"). Small, fast, real network I/O.
- driver_context_tokens=2048 (forced small): with default
  `_AVG_TURN_TOKENS_DEFAULT` and headroom_frac=0.6, _compute_k lands at
  a handful of turns. Later turns will drop earlier ones.
- Drive 7 turns of a trivial exchange (name a color / another / etc.),
  drive the session directly via Runtime.run + Runtime.resume — the
  same shape the daemon uses at `substrate/session_registry.py`.

Assertions:
1. At least one `TranscriptCompacted` event lands with a non-empty
   `dropped_seq_range`.
2. Every `TranscriptCompacted` has `kept_seq_start` strictly above every
   seq in `dropped_seq_range` (tech-spec §3a invariant).
3. `tokens_after < tokens_before` on each event (compaction saved tokens).
4. Turns AFTER the first compaction still land ModelReply with non-empty
   text — the driver read the compacted prompt without falling over.
5. No `substrate.ProducerFailed` on the `model` producer across the run.

`@pytest.mark.realmodel` gates it — skipped when Ollama or the model is
absent (same shape as tests/test_realmodel_demos.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from substrate import api
from substrate.adapters import OllamaResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.tool_loop.tools import CALCULATOR

pytestmark = pytest.mark.realmodel

_MODEL = "llama3.2:1b"
_OLLAMA_V1 = "http://localhost:11434/v1"


def _require_model() -> None:
    try:
        ids = {m["id"] for m in httpx.get(_OLLAMA_V1 + "/models", timeout=4).json().get("data", [])}
    except Exception as exc:  # noqa: BLE001 — any unreachability is a SKIP
        pytest.skip(f"live compaction test skipped — Ollama not reachable ({type(exc).__name__})")
    if _MODEL not in ids:
        pytest.skip(f"live compaction test skipped — model absent: {_MODEL}")


def _build(*, first_text: str, session_id: str, workspace: Path, record_root: Path) -> Any:
    """Session topology configured with a forced-small context so compaction
    kicks in inside a handful of turns.

    `record_root` MUST be threaded — the model producer's compaction path
    (session/__init__.py:259) is guarded on `record_root is not None`.
    Sprint 050 audit finding: forgetting to pass it silently disables
    every prompt-compaction the spec advertises. The daemon at
    substrate-ui/server.py:460 passes it correctly.
    """
    return session_topology(
        driver=OllamaResponder(
            _MODEL,
            max_tokens=32,
            temperature=0.2,
            # An empty suite would sidestep the tool loop entirely; a small
            # model handed a suite may randomly call tools. CALCULATOR keeps
            # the production shape and both branches are exercised.
            system="Reply with EXACTLY one word — a color. No punctuation, no explanation.",
        ),
        driver_name=_MODEL,
        driver_context_tokens=2048,  # forced small so k=1 (single turn)
        seed="you name colors",
        tools=CALCULATOR,
        per_turn="",
        max_turns=20,
        turn_max_steps=4,
        session_id=session_id,
        workspace_path=str(workspace),
        record_root=record_root,
        script=None,
        first_turn_user_message=UserMessage(
            text=first_text,
            turn_index=0,
            assembled_prompt=first_text,
            slash_source="test",
        ),
    )


@pytest.mark.timeout(300)
async def test_live_compaction_fires_and_model_still_answers(tmp_path: Path) -> None:
    _require_model()
    root = tmp_path / "live-compaction"
    workspace = tmp_path / "ws"

    turns = [
        "name a color",
        "another",
        "a warm one",
        "a cool one",
        "a rare one",
        "a bright one",
        "a dark one",
    ]

    result = await api.Runtime(root, persistent=True).run(
        _build(first_text=turns[0], session_id="s_compact", workspace=workspace, record_root=root)
    )
    assert result.status == "paused", f"turn 1 expected paused, got {result.status}"

    for i, text in enumerate(turns[1:], start=1):
        result = await api.Runtime(root, persistent=True).resume(
            _build(
                first_text="unused-on-resume",
                session_id="s_compact",
                workspace=workspace,
                record_root=root,
            ),
            resume_event=UserMessage(
                text=text, turn_index=i, assembled_prompt=text, slash_source="test"
            ),
        )
        assert result.status == "paused", f"turn {i + 1} expected paused, got {result.status}"

    envelopes = list(api.read_record(root))

    def _by_kind(kind: str) -> list[dict[str, Any]]:
        return [e for e in envelopes if e["kind"] == kind]

    compactions = _by_kind("TranscriptCompacted")
    model_replies = _by_kind("ModelReply")
    model_failures = [
        e
        for e in _by_kind("substrate.ProducerFailed")
        if ((e["payload"].get("producer") or {}).get("kind") == "model")
    ]

    # (1) at least one compaction fired
    assert compactions, (
        "expected at least one TranscriptCompacted across seven turns with "
        "driver_context_tokens=2048; got none — either compaction is not "
        "firing or K is somehow covering all turns"
    )

    # (2 + 3) shape invariants per tech-spec §3a
    for env in compactions:
        p = env["payload"]
        seq = env["seq"]
        lo, hi = p["dropped_seq_range"]
        kept_start = p["kept_seq_start"]
        assert lo <= hi, f"seq {seq}: dropped_seq_range malformed: {(lo, hi)}"
        assert kept_start > hi, (
            f"seq {seq}: kept_seq_start ({kept_start}) must be strictly above "
            f"the last dropped seq ({hi}); tech-spec §3a invariant"
        )
        assert p["tokens_after"] < p["tokens_before"], (
            f"seq {seq}: tokens_after ({p['tokens_after']}) must be less than "
            f"tokens_before ({p['tokens_before']}); compaction that does not "
            f"save tokens is a bug"
        )

    # (4) turns after the first compaction still produce ModelReply with text.
    # The record is append-order, so ModelReplies at seq > first-compaction-seq
    # are post-compaction turns.
    first_compaction_seq = compactions[0]["seq"]
    post_replies = [
        r
        for r in model_replies
        if r["seq"] > first_compaction_seq and str(r["payload"].get("text", "")).strip()
    ]
    assert post_replies, (
        f"expected at least one ModelReply with non-empty text at seq > "
        f"{first_compaction_seq} (first compaction). The compacted prompt "
        f"produced nothing coherent — probable prompt shape bug."
    )

    # (5) no model producer failures across the run
    assert not model_failures, (
        f"expected 0 substrate.ProducerFailed on the model producer, got "
        f"{len(model_failures)}: {[e['seq'] for e in model_failures]}"
    )

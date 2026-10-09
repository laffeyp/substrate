# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 053 — live-model standing sub-agent end-to-end.

The spec (product §6, tech §5) says: a standing sub-agent is a named
session with its own record. `delegate(task, child_session_name="…")`
routes the task as that session's next `UserMessage`; the reply comes
back to the parent as a tool result.

This test drives the whole loop end-to-end against real models, with
no scripting on the parent — the parent MODEL decides to call
delegate with the right kwarg.

Setup:

  1. Reviewer session runs qwen2.5:7b-instruct (light, fast, offline)
     with a role seed pinning the identity 'REVIEWER-42' so the
     assertion has teeth.
  2. Parent session runs kimi-k2.7-code:cloud. Live probe of every
     local + cloud model on this box confirmed the local 7B tier
     omits `child_session_name` on every native tool_call attempt,
     while every cloud model (kimi, glm-5.2, deepseek-v4-pro,
     nemotron-3-super) passes it 3/3 reliably at ~1s / call. Kimi
     is the shipped daily-driver default; using it here.

Probabilistic testing note (Architect ruling 2026-08-31): this is a
different class from deterministic testing. The test drives a real
model's DECISION to include an optional kwarg. That decision can go
wrong on a given run for no reason but model-behaviour variance. If
this test flakes once in a while it does not mean the substrate wire
is broken — it means the parent model made an unusual call. Retry
before treating a red as a regression. The wire itself is proven
deterministically by the substrate-side unit tests.

Gated by `@pytest.mark.realmodel`; skipped when Ollama or the parent
model is absent."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from substrate import api
from substrate.adapters import OllamaResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session_registry import SessionRegistry
from substrate.topologies.tool_loop.delegate import make_delegate

pytestmark = pytest.mark.realmodel

_REVIEWER_DRIVER = "qwen2.5:7b-instruct"  # local, fast, drives the reviewer's identity turn
_PARENT_DRIVER = "kimi-k2.7-code:cloud"  # cloud tier — reliably includes optional tool kwargs
_OLLAMA_V1 = "http://localhost:11434/v1"

_REVIEWER_SEED = (
    "Your name is REVIEWER-42. This is your permanent identity. "
    "Whenever anyone asks your name, reply with EXACTLY: REVIEWER-42. "
    "No punctuation, no explanation."
)


def _require_models() -> None:
    try:
        ids = {m["id"] for m in httpx.get(_OLLAMA_V1 + "/models", timeout=4).json().get("data", [])}
    except Exception as exc:  # noqa: BLE001 — any unreachability is a SKIP
        pytest.skip(f"live standing-session skipped — Ollama not reachable ({type(exc).__name__})")
    for name in (_REVIEWER_DRIVER, _PARENT_DRIVER):
        if name not in ids:
            pytest.skip(f"live standing-session skipped — model absent: {name}")


def _reviewer_factory(
    tmp_path: Path,
) -> Callable[[Any, Any], Callable[[api.TopologyBuilder], None]]:
    """Return a factory `(manifest, first_turn_user_message) -> topology`
    that the SessionRegistry calls to rebuild the reviewer topology on
    every turn. The reviewer's driver + seed are pinned in this closure;
    workspace + record land under tmp_path."""
    reviewer_ws = tmp_path / "reviewer_workspace"
    reviewer_ws.mkdir(parents=True, exist_ok=True)
    reviewer_record = tmp_path / "sessions" / "s_reviewer" / "record"

    def factory(manifest: Any, first_turn_user_message: Any = None) -> Any:
        del manifest, first_turn_user_message  # rebuilt from the pinned closure
        return session_topology(
            driver=OllamaResponder(_REVIEWER_DRIVER, max_tokens=32, temperature=0),
            driver_name=_REVIEWER_DRIVER,
            driver_context_tokens=8192,
            seed=_REVIEWER_SEED,
            tools={},
            per_turn="",
            max_turns=200,
            turn_max_steps=2,
            session_id="s_reviewer",
            workspace_path=str(reviewer_ws),
            record_root=reviewer_record,
            script=None,
        )

    return factory


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_live_standing_reviewer_answers_and_parent_quotes(tmp_path: Path) -> None:
    """Real reviewer session + real parent session + real delegate call.

    The reviewer's role prompt gives it a deterministic identity so the
    assertion has teeth ('REVIEWER-42'). The point is the WIRE: parent
    routes a turn into the reviewer's live record via delegate; parent
    reads the reviewer's answer back as a tool result and repeats it."""
    _require_models()

    # ── set up the registry, register the reviewer, open its record ─────
    sessions_base = tmp_path / "sessions"
    sessions_base.mkdir()
    factory = _reviewer_factory(tmp_path)
    registry = SessionRegistry(base=sessions_base, session_topology_factory=factory)
    reviewer_ws = str(tmp_path / "reviewer_workspace")
    registry.create(
        session_id="s_reviewer",
        name="reviewer",
        driver=_REVIEWER_DRIVER,
        workspace=reviewer_ws,
        workspace_shape="flat",
        bundle=None,
        seed=_REVIEWER_SEED,
    )
    reviewer_record = sessions_base / "s_reviewer" / "record"

    # First turn opens the record and confirms the reviewer's identity
    # is live in its transcript.
    await api.Runtime(reviewer_record, persistent=True).resume(
        factory(None),
        resume_event=UserMessage(
            text="what is your name?",
            turn_index=0,
            assembled_prompt="what is your name?",
            slash_source="chat",
        ),
    )
    first_finals = [e for e in api.read_record(reviewer_record) if e["kind"] == "FinalAnswer"]
    assert first_finals, "reviewer must produce a FinalAnswer on its first turn"
    assert "REVIEWER-42" in first_finals[-1]["payload"]["text"], (
        f"reviewer's own first-turn answer must carry its identity; "
        f"got {first_finals[-1]['payload']['text']!r}"
    )

    # ── set up the parent session with delegate wired to the registry ───
    parent_workspace = tmp_path / "parent_workspace"
    parent_workspace.mkdir()
    parent_record = tmp_path / "parent_record"

    delegate = make_delegate(
        responder=OllamaResponder(_PARENT_DRIVER, max_tokens=64, temperature=0),
        root=parent_workspace,
        session_registry=registry,
        parent_session_id="s_parent",
    )

    # Real parent: no script. The parent model has to decide on its own
    # to call `delegate` with `child_session_name='reviewer'`. Every
    # cloud tier model on this box (kimi, glm-5.2, deepseek-v4-pro,
    # nemotron-3-super) probed 3/3 reliably on this decision; local
    # 7B models omitted the kwarg 3/3. Kimi is the shipped daily-driver
    # default.
    parent_factory = session_topology(
        driver=OllamaResponder(
            _PARENT_DRIVER,
            max_tokens=200,
            temperature=0,
            system=(
                "You have access to the `delegate` tool. When the user asks "
                "you to route work to a named standing session, use delegate "
                "with the child_session_name kwarg set to that name."
            ),
        ),
        driver_name=_PARENT_DRIVER,
        driver_context_tokens=8192,
        seed="",
        tools={"delegate": delegate},
        per_turn="",
        max_turns=8,
        turn_max_steps=4,
        session_id="s_parent",
        workspace_path=str(parent_workspace),
        record_root=parent_record,
        script=None,
        first_turn_user_message=UserMessage(
            text=(
                "Delegate to the standing session called 'reviewer'. "
                "Ask it: 'what is your name?'. Then quote exactly what "
                "the reviewer said."
            ),
            turn_index=0,
            assembled_prompt=(
                "Delegate to the standing session called 'reviewer'. "
                "Ask it: 'what is your name?'. Then quote exactly what "
                "the reviewer said."
            ),
            slash_source="test",
        ),
    )
    # delegate.turn_sync uses threads; we drive the parent Runtime in the
    # current loop and let the tool_loop worker call turn_sync in a thread.
    result = await api.Runtime(parent_record, persistent=True).run(parent_factory)
    assert result.status == "paused", f"parent expected paused, got {result.status}"

    # ── assertions ──────────────────────────────────────────────────────
    parent_envs = list(api.read_record(parent_record))
    tool_calls = [e for e in parent_envs if e["kind"] == "ToolCall"]
    tool_results = [e for e in parent_envs if e["kind"] == "ToolResult"]
    final_answers = [e for e in parent_envs if e["kind"] == "FinalAnswer"]

    assert any(c["payload"].get("tool") == "delegate" for c in tool_calls), (
        f"parent did not call delegate; tools called: "
        f"{[c['payload'].get('tool') for c in tool_calls]}"
    )

    ok_delegates = [
        r
        for r in tool_results
        if r["payload"].get("ok") is True
        and isinstance(r["payload"].get("output"), dict)
        and str(r["payload"]["output"].get("via", "")).startswith("standing_session:")
    ]
    assert ok_delegates, (
        f"no successful standing_session delegate result; results: "
        f"{[r['payload'] for r in tool_results]}"
    )
    output = ok_delegates[0]["payload"]["output"]
    assert output["via"] == "standing_session:reviewer", output
    assert Path(output["child_root"]) == reviewer_record, output
    assert "REVIEWER-42" in output["answer"], (
        f"delegate ToolResult must carry the reviewer's answer; got {output['answer']!r}"
    )

    # The reviewer's record grew with the parent's delegated turn.
    reviewer_users = [e for e in api.read_record(reviewer_record) if e["kind"] == "UserMessage"]
    assert len(reviewer_users) >= 2, (
        f"reviewer must have received a second UserMessage from the parent; "
        f"got {len(reviewer_users)}"
    )
    delegated = reviewer_users[-1]["payload"]
    assert delegated["slash_source"] == "delegate", delegated
    assert "name" in delegated["text"].lower(), delegated

    # Parent's own FinalAnswer quotes the reviewer's identity — the whole
    # point of the round-trip.
    assert final_answers, "parent must produce a FinalAnswer"
    assert "REVIEWER-42" in final_answers[-1]["payload"]["text"], (
        f"parent's FinalAnswer must quote what the reviewer said; "
        f"got {final_answers[-1]['payload']['text']!r}"
    )

    # ── turn 2: parent resumes, delegates AGAIN to the same reviewer ────
    # The whole point of a STANDING sub-agent is that it survives across
    # parent turns and keeps its own accumulated context. Turn 2 asks a
    # different question ("what is 2 + 2?"); a fresh child would have no
    # memory of turn 1, but a standing session shares the same session_id
    # and record. Contract: same reviewer session_id, same record path,
    # reviewer's record grows again, reviewer STILL knows its identity
    # from the seed (proves the role prompt persisted, not just the wire).
    reviewer_users_after_turn_1 = len(reviewer_users)

    result_2 = await api.Runtime(parent_record, persistent=True).resume(
        parent_factory,
        resume_event=UserMessage(
            text=(
                "Delegate to the same 'reviewer' standing session again. "
                "Ask it: 'remind me — what is your name, and what is 2 + 2?' "
                "Quote exactly what it said."
            ),
            turn_index=1,
            assembled_prompt=(
                "Delegate to the same 'reviewer' standing session again. "
                "Ask it: 'remind me — what is your name, and what is 2 + 2?' "
                "Quote exactly what it said."
            ),
            slash_source="test",
        ),
    )
    assert result_2.status == "paused", f"parent turn 2 expected paused, got {result_2.status}"

    # ── turn-2 assertions ───────────────────────────────────────────────
    parent_envs_2 = list(api.read_record(parent_record))
    parent_finals_2 = [e for e in parent_envs_2 if e["kind"] == "FinalAnswer"]
    parent_tool_results_2 = [e for e in parent_envs_2 if e["kind"] == "ToolResult"]

    turn_2_delegates = [
        r
        for r in parent_tool_results_2
        if r["payload"].get("ok") is True
        and isinstance(r["payload"].get("output"), dict)
        and str(r["payload"]["output"].get("via", "")).startswith("standing_session:")
    ][len(ok_delegates) :]
    assert turn_2_delegates, (
        f"parent turn 2 must add at least one standing-session delegate call; "
        f"got {len(parent_tool_results_2) - len(tool_results)} new tool results"
    )
    output_2 = turn_2_delegates[0]["payload"]["output"]
    assert output_2["via"] == "standing_session:reviewer", output_2
    assert Path(output_2["child_root"]) == reviewer_record, (
        f"turn-2 delegate must land on the SAME reviewer record as turn 1 "
        f"(that is what 'standing' means); got {output_2['child_root']} vs {reviewer_record}"
    )
    # The reviewer must still know its identity — the seed persisted across
    # the parent's park + resume. And it must answer 2+2.
    assert "REVIEWER-42" in output_2["answer"], (
        f"reviewer lost its identity between parent turns — seed did not "
        f"persist. Got {output_2['answer']!r}"
    )
    assert "4" in output_2["answer"], (
        f"reviewer did not answer 2+2 on turn 2; got {output_2['answer']!r}"
    )

    # The reviewer's own record grew again.
    reviewer_users_final = [
        e for e in api.read_record(reviewer_record) if e["kind"] == "UserMessage"
    ]
    assert len(reviewer_users_final) > reviewer_users_after_turn_1, (
        f"reviewer's record must have grown between parent turns; "
        f"was {reviewer_users_after_turn_1}, now {len(reviewer_users_final)}"
    )
    # Both delegated UserMessages on the reviewer carry slash_source='delegate'.
    delegated_msgs = [
        u for u in reviewer_users_final if u["payload"].get("slash_source") == "delegate"
    ]
    assert len(delegated_msgs) >= 2, (
        f"reviewer must have received at least 2 delegated UserMessages "
        f"across the parent's two turns; got {len(delegated_msgs)}"
    )

    # Parent's FinalAnswer on turn 2 quotes both the identity and the math.
    assert "REVIEWER-42" in parent_finals_2[-1]["payload"]["text"], (
        f"parent turn 2 must quote the reviewer's identity again; "
        f"got {parent_finals_2[-1]['payload']['text']!r}"
    )
    assert "4" in parent_finals_2[-1]["payload"]["text"], (
        f"parent turn 2 must quote the reviewer's math answer; "
        f"got {parent_finals_2[-1]['payload']['text']!r}"
    )

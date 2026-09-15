# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""End-to-end test — Phase 8 item 7 through the full session topology.

`tests/test_inject_event.py` verifies the kernel primitive.
`tests/test_prompt_fragment_interrupt.py` verifies the fragment producer
in a minimal isolated topology. This test wires the full session
topology (chain triggers + CONTINUE / WRAP_UP gating +
compose-on-interrupt-tool-result) and injects an `InterruptRequested`
envelope while a tool is running.

The test verifies:
 - InterruptRequested lands on the record with producer=null.
 - The interrupt_fragment_producer fires and emits one
   PromptFragment(source="interrupt", precedence=95).
 - CONTINUE and WRAP_UP refuse the ToolResult (no model firing between
   the interrupt fragment and the composer refire).
 - compose-on-interrupt-tool-result fires the composer; a fresh
   PromptComposed lands whose fragments list carries the interrupt.
 - The FragmentCohort clears the turn slice on that PromptComposed —
   subsequent turns do not carry a stale interrupt directive.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.session import InterruptRequested, session_topology, UserMessage
from substrate.topologies.tool_loop.tools import Tool


def _slow_add_tool() -> dict[str, Tool]:
    """CALCULATOR's add wrapped in a 150ms sleep so the injection window
    is wide enough to be timing-tolerant. Runs on a worker thread (Sprint
    076 `asyncio.to_thread`) so the event loop stays free to drain the
    inbox during the sleep."""

    def _add(a: list[Any]) -> int:
        time.sleep(0.15)
        return int(a[0]) + int(a[1])

    return {
        "add": Tool(
            "add",
            "add(a, b) -> a+b (slow — for interrupt-timing tests)",
            True,
            _add,
        )
    }


async def _run_and_inject(tmp_path):
    """Runs the session topology in a task; a sibling task polls for the
    tool's ProducerStarted event on the runtime's live state and injects
    an InterruptRequested exactly then. Returns the run root."""

    root = tmp_path / "rec"
    runtime = api.Runtime(root)
    topology = session_topology(
        driver=DeterministicResponder(seed=0, menu=["TOOL: add args=[2,3]"]),
        driver_name="deterministic",
        driver_context_tokens=4096,
        seed="",
        tools=_slow_add_tool(),
        session_id="s_interrupt_e2e",
        workspace_path=str(tmp_path),
        script=[("add", [2, 3])],
        first_turn_user_message=UserMessage(
            text="please add 2 and 3",
            turn_index=0,
            assembled_prompt="please add 2 and 3",
            slash_source=None,
        ),
        max_turns=1,
        turn_max_steps=1,
    )

    async def _watch_and_inject():
        # Wait until the runtime is live.
        while getattr(runtime, "_st", None) is None:
            await asyncio.sleep(0.005)
        # Wait until a tool ProducerStarted appears in kind_by_instance —
        # the tool is running on a worker thread, the event loop is free,
        # and the injection window is exactly here.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            st = runtime._st  # noqa: SLF001 — test-only introspection
            if any(kind == "tool" for kind in st.kind_by_instance.values()):
                break
            await asyncio.sleep(0.01)
        runtime.inject_event(
            InterruptRequested(
                session_id="s_interrupt_e2e",
                tier="soft",
                source="test:e2e-injection",
            )
        )

    await asyncio.gather(runtime.run(topology), _watch_and_inject())
    return root


def _envs(root):
    return list(api.read_record(root))


def test_interrupt_lands_on_record_producer_null(tmp_path):
    root = asyncio.run(_run_and_inject(tmp_path))
    marks = [e for e in _envs(root) if e.get("kind") == "InterruptRequested"]
    assert len(marks) == 1, f"expected 1 InterruptRequested, got {len(marks)}"
    assert marks[0].get("producer") is None
    assert marks[0]["payload"]["tier"] == "soft"
    assert marks[0]["payload"]["source"] == "test:e2e-injection"


def test_interrupt_fragment_lands_with_directive(tmp_path):
    root = asyncio.run(_run_and_inject(tmp_path))
    fragments = [
        e
        for e in _envs(root)
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "interrupt"
    ]
    assert len(fragments) == 1, f"expected 1 interrupt fragment, got {len(fragments)}"
    payload = fragments[0]["payload"]
    assert payload["precedence"] == 95
    assert "interrupt" in payload["text"].lower()
    assert payload["provenance"]["tier"] == "soft"


def test_composer_refires_on_tool_result_with_interrupt_pending(tmp_path):
    root = asyncio.run(_run_and_inject(tmp_path))
    envs = _envs(root)

    # Baseline PromptComposed count: turn 1 always produces one. If the
    # composer refired on ToolResult (because the interrupt was pending),
    # there is a SECOND PromptComposed after the ToolResult.
    composed_events = [e for e in envs if e.get("kind") == "PromptComposed"]
    tool_results = [e for e in envs if e.get("kind") == "ToolResult"]
    assert len(tool_results) >= 1, "test scaffolding: expected the slow_add tool to complete"
    assert len(composed_events) >= 2, (
        f"expected the composer to refire after ToolResult (>=2 PromptComposed), "
        f"got {len(composed_events)}"
    )

    # The second PromptComposed lands AFTER the ToolResult by seq.
    tr_seq = tool_results[0]["seq"]
    post_tr_composed = [e for e in composed_events if e["seq"] > tr_seq]
    assert post_tr_composed, "no PromptComposed landed after the ToolResult"

    # That refired PromptComposed's fragment_seqs traces back to the
    # interrupt PromptFragment; the composed text carries the interrupt
    # directive. PromptComposed stores fragment_seqs (traceability) and
    # text (the assembled prompt) — the fragment payloads themselves are
    # not on the emitted event, only their seqs (see composer.py:53).
    refire = post_tr_composed[0]
    fragment_seqs = list(refire["payload"].get("fragment_seqs") or [])
    interrupt_fragment = next(
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "interrupt"
    )
    assert interrupt_fragment["seq"] in fragment_seqs, (
        f"refired PromptComposed.fragment_seqs did not include the interrupt "
        f"fragment (seq={interrupt_fragment['seq']}); got {fragment_seqs}"
    )
    assert "interrupt" in refire["payload"]["text"].lower(), (
        f"refired PromptComposed.text does not name the interrupt directive; "
        f"text={refire['payload']['text']!r}"
    )


def test_continue_and_wrap_up_step_aside_when_interrupt_pending(tmp_path):
    root = asyncio.run(_run_and_inject(tmp_path))
    envs = _envs(root)

    # The three ToolResult-subscribing triggers: CONTINUE, WRAP_UP,
    # COMPOSE_ON_INTERRUPT_TOOL_RESULT. Exactly one fires on the FIRST
    # ToolResult after the interrupt lands. With interrupt pending, the
    # composer trigger fires (starts prompt_composer); the model triggers
    # refuse. Subsequent turns (if the DeterministicResponder returns
    # another tool-call) are not the focus here.
    tool_results = [e for e in envs if e.get("kind") == "ToolResult"]
    assert tool_results, "test scaffolding: expected at least one ToolResult"
    tr_seq = tool_results[0]["seq"]
    composed_after_tr = [e for e in envs if e.get("kind") == "PromptComposed" and e["seq"] > tr_seq]
    assert composed_after_tr, "no fresh PromptComposed after the first ToolResult"
    next_composed_seq = composed_after_tr[0]["seq"]

    # Between the ToolResult and the fresh PromptComposed, the composer's
    # ProducerStarted must appear and no model ProducerStarted should.
    # CONTINUE / WRAP_UP would have started the model; they refused.
    between = [
        e
        for e in envs
        if tr_seq < e["seq"] < next_composed_seq and e.get("kind") == "substrate.ProducerStarted"
    ]
    kinds_between = [
        e["payload"].get("producer", {}).get("kind")
        for e in between
        if isinstance(e["payload"].get("producer"), dict)
    ]
    assert "prompt_composer" in kinds_between, (
        f"prompt_composer did not fire on the interrupt-pending ToolResult; "
        f"kinds between ToolResult and next PromptComposed: {kinds_between}"
    )
    assert "model" not in kinds_between, (
        f"model producer fired between ToolResult and the composer refire — "
        f"CONTINUE / WRAP_UP did not step aside; kinds: {kinds_between}"
    )


def test_fragment_cohort_clears_the_interrupt_on_the_composed_prompt(tmp_path):
    """The FragmentCohort clears turn-scoped entries on every PromptComposed
    emission (views.py::FragmentCohort.update line 100). The interrupt
    fragment is turn-scoped (vocabulary.py TURN_SCOPED_SOURCES), so once
    the composer folds it into a fresh PromptComposed, subsequent
    PromptComposed events must NOT carry the interrupt again."""

    root = asyncio.run(_run_and_inject(tmp_path))
    envs = _envs(root)
    composed_events = [e for e in envs if e.get("kind") == "PromptComposed"]

    # Read the interrupt fragment's seq; every PromptComposed after the
    # first one that referenced it must have it absent from fragment_seqs.
    interrupt_frags = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "interrupt"
    ]
    if not interrupt_frags:
        return  # nothing to assert on
    interrupt_seq = interrupt_frags[0]["seq"]
    saw = False
    for e in composed_events:
        seqs = list(e["payload"].get("fragment_seqs") or [])
        if interrupt_seq in seqs:
            assert not saw, (
                "the interrupt fragment's seq appeared in a second "
                "PromptComposed — FragmentCohort's turn-slice clear did "
                "not deassert the flag"
            )
            saw = True

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 210 — piece-A observation contract end-to-end (in-process discharge).

**Scope amendment folded 2026-08-26.** The sprint card names a `substrate chat
deterministic --script fixtures/three_turns.json --name test-piece-a` CLI
subprocess harness. That CLI lands in pieces B/C/D (sprints 214-221); it does
not exist yet. Rescoped: this sprint discharges the RECORD-LEVEL observation
contract in-process today. The stderr-substring checks and the terminal
screenshot check defer to sprint 221 (once `substrate chat` exists). The
application-kind sequence, the per-event payload predicates, the lifecycle
coverage, and BOTH termination shapes (production `pause_await_input(Park)`
and CI-wrapper `threshold_count(SessionEnded, 1)`) all fire here.

The fixture `tests/fixtures/three_turns.json` lives on disk so sprint 221 can
pick it up unchanged. Two conversation turns plus `/exit` — three UserMessage
events total; the filename reflects the count, not the prose gloss.

Two discharge paths per the sprint 210 closure review 2026-08-26:

  1. **Production shape via `.resume()` between pauses.** The daemon-driven
     flow uses `session_topology`'s `pause_await_input(Park)` termination.
     `test_piece_a_pauses_between_turns_and_finalises_on_exit` fires three
     `.resume()` calls against one persistent record, asserts two
     `TerminationMatched(decision="pause-await-input")` events (turns 0 and 1)
     plus one `finalise-run` on the `/exit` UserMessage's SessionEnded.

  2. **CI-mode via one `.run()` in the wrapper.** `ci_session_topology`
     overwrites the production termination with `threshold_count(SessionEnded, 1)`
     so a scripted session drives itself to finalise inside one `.run()`.
     Level-3(a) replay locks byte-identical determinism.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.testing import assert_event, assert_no_event, assert_sequence
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.ci import ci_session_topology
from substrate.topologies.tool_loop.tools import CALCULATOR

# A short scripted run inside one K-window: the documented exception to session_topology's
# record_root warning (UI sprint 107 states it here instead of letting it print on every run).
pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")


_FIXTURES = Path(__file__).parent / "fixtures"
_FIXTURE_FILE = _FIXTURES / "three_turns.json"


def _load_turns() -> tuple[str, ...]:
    entries = json.loads(_FIXTURE_FILE.read_text(encoding="utf-8"))
    return tuple(str(e["text"]) for e in entries)


def _read(record_root: Path) -> list[dict[str, Any]]:
    return list(api.read_record(record_root))


def _payload_kinds(envelopes: list[dict[str, Any]]) -> list[str]:
    return [e["kind"] for e in envelopes if not e["kind"].startswith("substrate.")]


def _count_by_kind(envelopes: list[dict[str, Any]], kind: str) -> int:
    return sum(1 for e in envelopes if e["kind"] == kind)


@pytest.mark.asyncio
async def test_piece_a_ci_wrapper_observation_contract(tmp_path: Path) -> None:
    """Discharge path 1: `ci_session_topology` drives the three-turn script
    inside one `.run()` and asserts the payload sequence + per-turn predicates.
    """
    turns = _load_turns()
    assert turns == ("say hi", "count to five", "/exit"), f"fixture drifted: {turns}"
    record_root = tmp_path / "test-piece-a"
    result = await api.Runtime(record_root).run(
        ci_session_topology(turns=turns, session_id="test-piece-a")
    )
    assert result.status == "finalised"

    envelopes = _read(record_root)
    kinds = _payload_kinds(envelopes)

    # Race-tolerant assertion on the shape. Turn 2's Park may or may not land
    # depending on whether park's ProducerCompleted races the CI-wrapper's
    # threshold_count(SessionEnded, 1) TerminationMatched. Both resolutions are
    # legitimate; both are byte-stable on this substrate build (`assert_replayable`
    # locks the actual resolution below). The bounded assertion says: three of each
    # turn kind + SessionEnded + 2-or-3 Park events + no extras.
    assert _count_by_kind(envelopes, "UserMessage") == 3
    # Sprint 067: model producer now fires on PromptComposed (via
    # resume-on-composed). Turn 3's /exit races the chain:
    # UserMessage(/exit) → per_turn → user_message → composer → PromptComposed
    # → model versus end-on-exit → session_end → SessionEnded. The
    # termination policy finalises on SessionEnded so /exit's model firing
    # may lose the race. 2 or 3 ModelReply / FinalAnswer are both
    # legitimate; the prior fixed-3 assertion held only because model
    # fired directly on UserMessage in the pre-067 shape.
    assert 2 <= _count_by_kind(envelopes, "ModelReply") <= 3
    assert 2 <= _count_by_kind(envelopes, "FinalAnswer") <= 3
    assert _count_by_kind(envelopes, "SessionEnded") == 1
    assert 2 <= _count_by_kind(envelopes, "Park") <= 3
    # SessionStarted joins the set post-sprint 240 (RunStarted instrument
    # emits one SessionStarted envelope at seq 2). PromptComposed joins the
    # set post-sprint 059 (composer trigger fires per turn). PromptFragment
    # joins post-sprints 060-064: tools_suite fragment (session-open) plus
    # per_turn / user_message per turn.
    assert set(kinds) == {
        "SessionStarted",
        "UserMessage",
        "ModelReply",
        "FinalAnswer",
        "Park",
        "SessionEnded",
        "PromptComposed",
        "PromptFragment",
    }
    assert _count_by_kind(envelopes, "SessionStarted") == 1
    # Sprint 059/064: composer fires per turn via the deterministic
    # per_turn → user_message → composer chain. Turn 3 is /exit which
    # routes to session_end → SessionEnded; the /exit turn's chain may
    # or may not complete before the run finalises on the threshold_count.
    # Assertion: at least the first two turns' composed prompts land.
    assert 2 <= _count_by_kind(envelopes, "PromptComposed") <= 3

    # The ordered subsequence of un-raced kinds is stable regardless of the tail race.
    # SessionStarted leads the sequence (sprint 240 instrument at seq 2).
    # PromptComposed and PromptFragment fire per turn/session-open (sprints
    # 059-064); their position relative to ModelReply is race-tolerant, so
    # filter them out of the strict-ordered head assertion. UserMessage /
    # ModelReply / FinalAnswer / SessionEnded ordering stays byte-stable.
    ordered_head = [k for k in kinds if k not in {"Park", "PromptComposed", "PromptFragment"}]
    # Turns 0 and 1 always complete; turn 2's model firing races /exit's
    # session_end path (sprint 067). Assert the guaranteed prefix; the
    # tail is race-tolerant.
    assert ordered_head[:7] == [
        "SessionStarted",
        "UserMessage",
        "ModelReply",
        "FinalAnswer",
        "UserMessage",
        "ModelReply",
        "FinalAnswer",
    ]
    assert "SessionEnded" in ordered_head

    # Per-turn payload predicates — verify EVERY instance, not just the first.
    user_messages = [e for e in envelopes if e["kind"] == "UserMessage"]
    assert [e["payload"]["turn_index"] for e in user_messages] == [0, 1, 2]
    assert [e["payload"]["text"] for e in user_messages] == list(turns)

    model_replies = [e for e in envelopes if e["kind"] == "ModelReply"]
    # Turn 2's model firing may lose the race with /exit's session_end;
    # the turn_index list is either [0, 1] or [0, 1, 2].
    turn_indices = [e["payload"]["turn_index"] for e in model_replies]
    assert turn_indices == [0, 1] or turn_indices == [0, 1, 2]

    final_answers = [e for e in envelopes if e["kind"] == "FinalAnswer"]
    # steps=0 for every FinalAnswer: driver-parse path, step counter fresh on each
    # resume-on-composed firing. A regression that let step drift trips here on every turn.
    assert all(e["payload"]["steps"] == 0 for e in final_answers)

    parks = [e for e in envelopes if e["kind"] == "Park"]
    assert all(e["payload"]["reason"] == "final_answer" for e in parks)
    assert all(e["payload"]["awaiting"] == "UserMessage" for e in parks)
    park_turn_indices = [e["payload"]["turn_index"] for e in parks]
    assert park_turn_indices == [0, 1] or park_turn_indices == [0, 1, 2]

    assert_event(record_root, "SessionEnded", reason="user_exit", total_turns=3)
    assert_no_event(record_root, "SessionWarning")


@pytest.mark.asyncio
async def test_piece_a_lifecycle_events_cover_each_producer(tmp_path: Path) -> None:
    """Every session producer (driver_stepper, model, park, session_end) emits
    ProducerStarted; the first three also emit ProducerCompleted; session_end's
    completion may race with TerminationMatched (see prose). Four key triggers
    fire: resume-on-composed, park-on-final, end-on-exit, advance-on-park.
    """
    record_root = tmp_path / "test-piece-a-lifecycle"
    await api.Runtime(record_root).run(
        ci_session_topology(turns=_load_turns(), session_id="test-piece-a-lifecycle")
    )
    envelopes = _read(record_root)
    started_kinds = {
        e["payload"]["producer"]["kind"]
        for e in envelopes
        if e["kind"] == "substrate.ProducerStarted"
    }
    completed_kinds = {
        e["payload"]["producer"]["kind"]
        for e in envelopes
        if e["kind"] == "substrate.ProducerCompleted"
    }
    assert {"driver_stepper", "model", "park", "session_end"} <= started_kinds, (
        f"missing ProducerStarted for one of the session producers: got {started_kinds}"
    )
    # session_end's ProducerCompleted may race with TerminationMatched: the wrapper's
    # threshold_count(SessionEnded, 1) matches on the SessionEnded emit and finalises
    # the run before session_end's completion tick lands. Honest reality.
    assert {"driver_stepper", "model", "park"} <= completed_kinds, (
        f"missing ProducerCompleted for driver_stepper/model/park: got {completed_kinds}"
    )
    trigger_ids = {
        e["payload"].get("trigger_id") for e in envelopes if e["kind"] == "substrate.TriggerFired"
    }
    assert {"resume-on-composed", "park-on-final", "end-on-exit", "advance-on-park"} <= trigger_ids


@pytest.mark.asyncio
async def test_piece_a_ci_wrapper_termination_is_finalise_run(tmp_path: Path) -> None:
    """The CI wrapper never pauses. Exactly one TerminationMatched, decision
    `finalise-run`; the last envelope is `substrate.RunFinalised`. The CI wrapper's
    advance-on-park chain bypasses production's pause_await_input path — that path
    lives in `test_piece_a_pauses_between_turns_and_finalises_on_exit` below.
    """
    record_root = tmp_path / "test-piece-a-termination"
    await api.Runtime(record_root).run(
        ci_session_topology(turns=_load_turns(), session_id="test-piece-a-termination")
    )
    envelopes = _read(record_root)
    term_events = [e for e in envelopes if e["kind"] == "substrate.TerminationMatched"]
    assert len(term_events) == 1
    assert term_events[0]["payload"].get("decision") == "finalise-run"
    assert envelopes[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.asyncio
async def test_piece_a_ci_wrapper_is_replayable(tmp_path: Path) -> None:
    """The whole scripted CI wrapper run is Level-3(a) byte-identical on replay —
    scripted driver_stepper + DeterministicResponder + deterministic CALCULATOR."""
    record_root = tmp_path / "test-piece-a-replay"
    await api.Runtime(record_root).run(
        ci_session_topology(turns=_load_turns(), session_id="test-piece-a-replay")
    )
    api.assert_replayable(record_root, "3a")


def _production_session_factory(*, session_id: str) -> Callable[[api.TopologyBuilder], None]:
    return session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=4096,
        seed="you are a companion in a terminal session",
        tools=CALCULATOR,
        per_turn="",
        max_turns=200,
        turn_max_steps=8,
        session_id=session_id,
        workspace_path="/tmp/session-test",
        script=None,
    )


@pytest.mark.asyncio
async def test_piece_a_pauses_between_turns_and_finalises_on_exit(tmp_path: Path) -> None:
    """Discharge path 2: production `session_topology` shape via three `.resume()`
    calls. Two pauses on Park (turns 0 and 1), one finalise-run on the `/exit`
    UserMessage's SessionEnded.

    Sprint 209a surfaced a substrate primitive gap: `.resume()` on a FRESH
    persistent root does not write `substrate.RunStarted` (kernel/runtime.py:409).
    Level-3(a) replay reads the deterministic-producer manifest off RunStarted, so
    `assert_replayable` refuses. This test therefore verifies the termination
    decisions on the record and defers the replay check to the CI-wrapper test
    above. Sprint 214 (daemon session API core) owns the fix.
    """
    turns = _load_turns()
    record_root = tmp_path / "test-piece-a-pauses"
    for turn_index, text in enumerate(turns):
        result = await api.Runtime(record_root, persistent=True).resume(
            _production_session_factory(session_id="test-piece-a-pauses"),
            resume_event=UserMessage(
                text=text,
                turn_index=turn_index,
                assembled_prompt=text,
                slash_source="chat",
            ),
        )
        if turn_index < 2:
            assert result.status == "paused", (
                f"turn {turn_index} expected pause, got {result.status}"
            )
        else:
            assert result.status == "finalised", (
                f"turn {turn_index} (/exit) expected finalised, got {result.status}"
            )
    envelopes = _read(record_root)
    term_events = [e for e in envelopes if e["kind"] == "substrate.TerminationMatched"]
    decisions = [e["payload"].get("decision") for e in term_events]
    assert decisions == ["pause-await-input", "pause-await-input", "finalise-run"], (
        f"unexpected TerminationMatched decisions: {decisions}"
    )
    # Every pause names UserMessage as the resume_condition.
    pause_conditions = [
        e["payload"].get("resume_condition")
        for e in term_events
        if e["payload"].get("decision") == "pause-await-input"
    ]
    assert pause_conditions == ["UserMessage", "UserMessage"]
    # SessionEnded lands exactly once, on the /exit turn.
    assert_event(record_root, "SessionEnded", reason="user_exit")
    # Both Park events land (no threshold_count race on the production shape).
    parks = [e for e in envelopes if e["kind"] == "Park"]
    park_turns = [e["payload"]["turn_index"] for e in parks]
    assert park_turns == [0, 1]


def test_fixture_shape() -> None:
    """A brittle-fixture guard. Sprint 221 will pick up the JSON verbatim; drift
    surfaces here before sprint 221 finds it. Also exercises `assert_sequence` as
    a real integration point (loads the fixture's three-entry sub-sequence and
    checks the fixture's own text list under the primitive's shape).
    """
    entries = json.loads(_FIXTURE_FILE.read_text(encoding="utf-8"))
    assert isinstance(entries, list) and len(entries) == 3
    assert all(isinstance(e, dict) and "text" in e for e in entries)
    assert entries[-1]["text"] == "/exit"
    # `assert_sequence` operates on a record OR an iterable of envelopes; feed it
    # a synthetic envelope stream shaped from the fixture and verify the exact
    # UserMessage sequence it would produce.
    synthetic = [
        {"seq": i, "kind": "UserMessage", "payload": {"text": e["text"]}, "schema": "UserMessage"}
        for i, e in enumerate(entries)
    ]
    assert_sequence(synthetic, ["UserMessage", "UserMessage", "UserMessage"])

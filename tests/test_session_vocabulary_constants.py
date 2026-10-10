# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Session-vocabulary constants — sprint 070 StrEnum classes + sprint 071
producer_kind / trigger_id `Final[str]` constants.

Pins:
 - Every StrEnum's members map to the documented wire strings.
 - PRODUCER_KIND_* and TRIGGER_ID_* Final[str] values match the strings
   used at registration sites (grep-check).
 - SESSION_PRODUCER_KINDS and SESSION_TRIGGER_IDS frozensets cover the
   full declared set.
"""

from __future__ import annotations

from substrate.topologies.session.vocabulary import (
    PRODUCER_KIND_DRIVER_STEPPER,
    PRODUCER_KIND_FIRST_MESSAGE,
    PRODUCER_KIND_INTERRUPT_FRAGMENT,
    PRODUCER_KIND_MODEL,
    PRODUCER_KIND_RETURN,
    PRODUCER_KIND_SESSION_END,
    PRODUCER_KIND_SESSION_PROMPT,
    PRODUCER_KIND_SESSION_STARTED,
    PRODUCER_KIND_TOOL,
    SESSION_PRODUCER_KINDS,
    SESSION_TRIGGER_IDS,
    TRIGGER_ID_DRIVER_STEPPER_ON_RETURNED,
    TRIGGER_ID_MODEL_ON_TOOL_RESULT,
    TRIGGER_ID_END_ON_TURN_CAP,
    TRIGGER_ID_END_ON_EXIT,
    TRIGGER_ID_END_ON_END_REQUEST,
    TRIGGER_ID_MODEL_ON_USER_MESSAGE,
    TRIGGER_ID_RETURN_ON_INTERRUPT,
    TRIGGER_ID_RETURN_ON_MODEL_ERROR,
    TRIGGER_ID_RETURN_ON_REPLY,
    TRIGGER_ID_TOOL_ON_TOOL_CALL,
    TRIGGER_ID_MODEL_WRAP_UP_ON_TOOL_RESULT,
    ParkReason,
    ReturnReason,
    StopReason,
    SessionEndReason,
    SessionWarningKind,
)


def test_session_end_reason_values() -> None:
    """Every SessionEndReason member maps to its documented wire string.
    Locks the enum against value drift."""
    assert SessionEndReason.USER_EXIT.value == "user_exit"
    assert SessionEndReason.USER_END.value == "user_end"
    assert SessionEndReason.TURN_CAP.value == "turn_cap"
    assert SessionEndReason.DAEMON_SHUTDOWN.value == "daemon_shutdown"
    assert set(SessionEndReason) == {
        SessionEndReason.USER_EXIT,
        SessionEndReason.USER_END,
        SessionEndReason.TURN_CAP,
        SessionEndReason.DAEMON_SHUTDOWN,
    }


def test_v03_turn_end_values() -> None:
    """ModelReply.stop_reason and Returned.reason wire strings (vocabulary § K)."""
    assert {s.value for s in StopReason} == {"end_turn", "tool_use", "wrap_up"}
    assert {r.value for r in ReturnReason} == {"replied", "model_error", "interrupted"}


def test_park_reason_values() -> None:
    """Every ParkReason member maps to its documented wire string."""
    assert ParkReason.FINAL_ANSWER.value == "final_answer"
    assert ParkReason.MODEL_ERROR.value == "model_error"
    assert ParkReason.INTERRUPT.value == "interrupt"
    assert len(set(ParkReason)) == 3


def test_session_warning_kind_values() -> None:
    """Three v0.2.1 SessionWarning kinds."""
    assert SessionWarningKind.SEED_ALONE_EXCEEDS.value == "seed_alone_exceeds"
    assert SessionWarningKind.BUNDLE_CHANGED.value == "bundle_changed"
    assert SessionWarningKind.FRAGMENT_SOURCE_FAILED.value == "fragment_source_failed"


def test_strenum_equals_str_wire_shape() -> None:
    """StrEnum members compare `==` with their underlying string. Locks
    the msgspec-compat invariant sprint 070 verified at start of card."""
    assert SessionEndReason.USER_EXIT == "user_exit"
    assert ParkReason.FINAL_ANSWER == "final_answer"
    assert SessionWarningKind.FRAGMENT_SOURCE_FAILED == "fragment_source_failed"


def test_producer_kind_final_strs() -> None:
    """Every PRODUCER_KIND_* constant matches its documented wire
    string. Sprint 071's block."""
    assert PRODUCER_KIND_SESSION_STARTED == "session_started"
    assert PRODUCER_KIND_MODEL == "model"
    assert PRODUCER_KIND_TOOL == "tool"
    assert PRODUCER_KIND_RETURN == "return"
    assert PRODUCER_KIND_SESSION_END == "session_end"
    assert PRODUCER_KIND_SESSION_PROMPT == "session_prompt"
    assert PRODUCER_KIND_FIRST_MESSAGE == "first_message"
    assert PRODUCER_KIND_DRIVER_STEPPER == "driver_stepper"


def test_session_producer_kinds_frozenset_covers_all() -> None:
    """SESSION_PRODUCER_KINDS holds every declared producer kind. A
    new PRODUCER_KIND_* constant that omits itself from the frozenset
    trips here rather than at a subtle predicate site."""
    expected = {
        PRODUCER_KIND_SESSION_STARTED,
        PRODUCER_KIND_MODEL,
        PRODUCER_KIND_TOOL,
        PRODUCER_KIND_RETURN,
        PRODUCER_KIND_SESSION_END,
        PRODUCER_KIND_SESSION_PROMPT,
        PRODUCER_KIND_FIRST_MESSAGE,
        PRODUCER_KIND_INTERRUPT_FRAGMENT,
        PRODUCER_KIND_DRIVER_STEPPER,
    }
    assert SESSION_PRODUCER_KINDS == expected


def test_trigger_id_final_strs() -> None:
    """Every TRIGGER_ID_* constant matches its wire string."""
    assert TRIGGER_ID_TOOL_ON_TOOL_CALL == "tool-on-tool-call"
    assert TRIGGER_ID_MODEL_ON_TOOL_RESULT == "model-on-tool-result"
    assert TRIGGER_ID_MODEL_WRAP_UP_ON_TOOL_RESULT == "model-wrap-up-on-tool-result"
    assert TRIGGER_ID_RETURN_ON_REPLY == "return-on-reply"
    assert TRIGGER_ID_RETURN_ON_MODEL_ERROR == "return-on-model-error"
    assert TRIGGER_ID_RETURN_ON_INTERRUPT == "return-on-interrupt"
    assert TRIGGER_ID_END_ON_EXIT == "end-on-exit"
    assert TRIGGER_ID_END_ON_TURN_CAP == "end-on-turn-cap"
    assert TRIGGER_ID_END_ON_END_REQUEST == "end-on-end-request"
    assert TRIGGER_ID_DRIVER_STEPPER_ON_RETURNED == "driver-stepper-on-returned"
    assert TRIGGER_ID_MODEL_ON_USER_MESSAGE == "model-on-user-message"


def test_session_trigger_ids_frozenset_covers_all() -> None:
    """SESSION_TRIGGER_IDS holds every declared trigger id. K261 removed the per-turn chain's
    four triggers and compose-on-interrupt-tool-result, and added model-on-user-message and
    first-message-on-session-prompt. K263 removed warn-on-fragment-error: session_prompt records a
    failed source itself."""
    assert len(SESSION_TRIGGER_IDS) == 13

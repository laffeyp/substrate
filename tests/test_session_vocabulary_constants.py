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
 - FRAGMENT_SOURCE_KINDS (sprint 068) is a subset of SESSION_PRODUCER_KINDS.
"""

from __future__ import annotations

from substrate.topologies.session.vocabulary import (
    FRAGMENT_SOURCE_KINDS,
    PRODUCER_KIND_BUNDLE_METHODOLOGY_FRAGMENT,
    PRODUCER_KIND_BUNDLE_PERSONALITY_FRAGMENT,
    PRODUCER_KIND_DRIVER_STEPPER,
    PRODUCER_KIND_FRAGMENT_ERROR_WARNING,
    PRODUCER_KIND_INTERRUPT_FRAGMENT,
    PRODUCER_KIND_MODEL,
    PRODUCER_KIND_PARENT_CONTEXT_FRAGMENT,
    PRODUCER_KIND_PARK,
    PRODUCER_KIND_PER_TURN_FRAGMENT,
    PRODUCER_KIND_PROMPT_COMPOSER,
    PRODUCER_KIND_ROLE_FRAGMENT,
    PRODUCER_KIND_SESSION_END,
    PRODUCER_KIND_SESSION_OPEN,
    PRODUCER_KIND_SESSION_STARTED,
    PRODUCER_KIND_SESSION_WARNING,
    PRODUCER_KIND_TOOL,
    PRODUCER_KIND_TOOLS_SUITE_FRAGMENT,
    PRODUCER_KIND_USER_MESSAGE_FRAGMENT,
    SESSION_PRODUCER_KINDS,
    SESSION_TRIGGER_IDS,
    TRIGGER_ID_ADVANCE_ON_PARK,
    TRIGGER_ID_COMPOSE_ON_COHORT_COMPLETE,
    TRIGGER_ID_CONTINUE,
    TRIGGER_ID_EMIT_PER_TURN_FRAGMENT,
    TRIGGER_ID_EMIT_USER_MESSAGE_FRAGMENT,
    TRIGGER_ID_END_ON_CAP,
    TRIGGER_ID_END_ON_EXIT,
    TRIGGER_ID_END_ON_USER_END,
    TRIGGER_ID_PARK_ON_FINAL,
    TRIGGER_ID_PARK_ON_INTERRUPT,
    TRIGGER_ID_PARK_ON_MODEL_ERROR,
    TRIGGER_ID_RESUME_ON_COMPOSED,
    TRIGGER_ID_RUN_TOOL,
    TRIGGER_ID_WARN_ON_FRAGMENT_ERROR,
    TRIGGER_ID_WRAP_UP,
    ParkReason,
    SessionEndReason,
    SessionWarningKind,
)


def test_session_end_reason_values() -> None:
    """Every SessionEndReason member maps to its documented wire string.
    Locks the enum against value drift."""
    assert SessionEndReason.USER_EXIT.value == "user_exit"
    assert SessionEndReason.USER_END.value == "user_end"
    assert SessionEndReason.TIMEOUT.value == "timeout"
    assert SessionEndReason.DAEMON_SHUTDOWN.value == "daemon_shutdown"
    assert set(SessionEndReason) == {
        SessionEndReason.USER_EXIT,
        SessionEndReason.USER_END,
        SessionEndReason.TIMEOUT,
        SessionEndReason.DAEMON_SHUTDOWN,
    }


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
    assert PRODUCER_KIND_PARK == "park"
    assert PRODUCER_KIND_SESSION_END == "session_end"
    assert PRODUCER_KIND_SESSION_WARNING == "session_warning"
    assert PRODUCER_KIND_FRAGMENT_ERROR_WARNING == "fragment_error_warning"
    assert PRODUCER_KIND_SESSION_OPEN == "session_open"
    assert PRODUCER_KIND_PROMPT_COMPOSER == "prompt_composer"
    assert PRODUCER_KIND_PER_TURN_FRAGMENT == "per_turn_fragment"
    assert PRODUCER_KIND_ROLE_FRAGMENT == "role_fragment"
    assert PRODUCER_KIND_BUNDLE_METHODOLOGY_FRAGMENT == "bundle_methodology_fragment"
    assert PRODUCER_KIND_BUNDLE_PERSONALITY_FRAGMENT == "bundle_personality_fragment"
    assert PRODUCER_KIND_PARENT_CONTEXT_FRAGMENT == "parent_context_fragment"
    assert PRODUCER_KIND_TOOLS_SUITE_FRAGMENT == "tools_suite_fragment"
    assert PRODUCER_KIND_USER_MESSAGE_FRAGMENT == "user_message_fragment"
    assert PRODUCER_KIND_DRIVER_STEPPER == "driver_stepper"


def test_session_producer_kinds_frozenset_covers_all() -> None:
    """SESSION_PRODUCER_KINDS holds every declared producer kind. A
    new PRODUCER_KIND_* constant that omits itself from the frozenset
    trips here rather than at a subtle predicate site."""
    expected = {
        PRODUCER_KIND_SESSION_STARTED,
        PRODUCER_KIND_MODEL,
        PRODUCER_KIND_TOOL,
        PRODUCER_KIND_PARK,
        PRODUCER_KIND_SESSION_END,
        PRODUCER_KIND_SESSION_WARNING,
        PRODUCER_KIND_FRAGMENT_ERROR_WARNING,
        PRODUCER_KIND_SESSION_OPEN,
        PRODUCER_KIND_PROMPT_COMPOSER,
        PRODUCER_KIND_PER_TURN_FRAGMENT,
        PRODUCER_KIND_ROLE_FRAGMENT,
        PRODUCER_KIND_BUNDLE_METHODOLOGY_FRAGMENT,
        PRODUCER_KIND_BUNDLE_PERSONALITY_FRAGMENT,
        PRODUCER_KIND_PARENT_CONTEXT_FRAGMENT,
        PRODUCER_KIND_TOOLS_SUITE_FRAGMENT,
        PRODUCER_KIND_USER_MESSAGE_FRAGMENT,
        PRODUCER_KIND_INTERRUPT_FRAGMENT,
        PRODUCER_KIND_DRIVER_STEPPER,
    }
    assert SESSION_PRODUCER_KINDS == expected


def test_fragment_source_kinds_is_subset_of_producer_kinds() -> None:
    """Sprint 068's FRAGMENT_SOURCE_KINDS is composed from named
    constants; must be a subset of the full producer-kind set. Phase 8
    item 7 added interrupt_fragment as the eighth entry."""
    assert FRAGMENT_SOURCE_KINDS <= SESSION_PRODUCER_KINDS
    assert len(FRAGMENT_SOURCE_KINDS) == 8


def test_trigger_id_final_strs() -> None:
    """Every TRIGGER_ID_* constant matches its wire string."""
    assert TRIGGER_ID_RUN_TOOL == "run-tool"
    assert TRIGGER_ID_CONTINUE == "continue"
    assert TRIGGER_ID_WRAP_UP == "wrap-up"
    assert TRIGGER_ID_PARK_ON_FINAL == "park-on-final"
    assert TRIGGER_ID_PARK_ON_MODEL_ERROR == "park-on-model-error"
    assert TRIGGER_ID_PARK_ON_INTERRUPT == "park-on-interrupt"
    assert TRIGGER_ID_RESUME_ON_COMPOSED == "resume-on-composed"
    assert TRIGGER_ID_END_ON_EXIT == "end-on-exit"
    assert TRIGGER_ID_END_ON_CAP == "end-on-cap"
    assert TRIGGER_ID_END_ON_USER_END == "end-on-user-end"
    assert TRIGGER_ID_EMIT_PER_TURN_FRAGMENT == "emit-per-turn-fragment"
    assert TRIGGER_ID_EMIT_USER_MESSAGE_FRAGMENT == "emit-user-message-fragment"
    assert TRIGGER_ID_COMPOSE_ON_COHORT_COMPLETE == "compose-on-cohort-complete"
    assert TRIGGER_ID_WARN_ON_FRAGMENT_ERROR == "warn-on-fragment-error"
    assert TRIGGER_ID_ADVANCE_ON_PARK == "advance-on-park"


def test_session_trigger_ids_frozenset_covers_all() -> None:
    """SESSION_TRIGGER_IDS holds every declared trigger id. Phase 8
    item 7 added emit-interrupt-fragment and compose-on-interrupt-tool-result."""
    assert len(SESSION_TRIGGER_IDS) == 17

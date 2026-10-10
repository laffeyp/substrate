# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Session-topology vocabulary — named constants for every kind, producer, trigger and reason.

the tech spec locks session-vocabulary.md as the topology's kind surface;
this module is the runtime enforcement layer that closes the "kind-name
typo drifts silently" class the Markdown-only vocabulary cannot catch
(REVIEW-2026-08-28 F5). The msgspec Structs at the top of `__init__.py`
type-check payload fields at the speaker's mouth; msgspec cannot check
the kind-name STRING itself, so a `"SessionEndeed"` typo in a
subscription filter or a trigger declaration would land silently.

Every reference to a session-vocabulary kind name inside
`substrate.topologies.session.*` must import from here;
`tests/test_trigger_names_264.py` scans the package for raw kind strings.

The kernel-side reserved lifecycle kinds (RunStarted, RunFinalised, …)
live in `substrate.constants`; that side is enforced by the same rule
via `is_reserved(kind)`. The two vocabularies do not overlap by design.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any, Final

from ..tool_loop.kinds import FINAL_ANSWER

# Sprint 070 (2026-09-02): closed-set string values as StrEnum. Each class
# below carries the values documented in session-vocabulary.md; wire
# representation stays the underlying string (msgspec Struct fields accept
# StrEnum and serialise as string on JSON encode/decode).


class SessionEndReason(StrEnum):
    """SessionEnded.reason — every value the session_end producer can
    emit. Four distinct paths per session-vocabulary.md § B.SessionEnded.
    """

    USER_EXIT = "user_exit"
    USER_END = "user_end"
    TURN_CAP = "turn_cap"  # "timeout" before v0.3.4; see LEGACY_SESSION_END_REASONS
    DAEMON_SHUTDOWN = "daemon_shutdown"


class ParkReason(StrEnum):
    """Park.reason — matches the terminal-event that preceded the park
    per session-vocabulary.md § C.Park invariant #5."""

    FINAL_ANSWER = "final_answer"
    MODEL_ERROR = "model_error"
    INTERRUPT = "interrupt"


class SessionWarningKind(StrEnum):
    """SessionWarning.kind — one member per warning condition. Cadence
    invariant §F #7: at most one per (session_id, kind) pair (v0.1)
    or (session_id, source_name) pair for fragment_source_failed
    (v0.2.1)."""

    SEED_ALONE_EXCEEDS = "seed_alone_exceeds"
    BUNDLE_CHANGED = "bundle_changed"
    FRAGMENT_SOURCE_FAILED = "fragment_source_failed"


# The sentinel a UserMessage.text carries to fire the session topology's
# `end-on-exit` trigger. The CLI's SlashCommand.EXIT names the same string;
# both sides reference this constant so a rename lands in one place.
END_ON_EXIT_SENTINEL: Final[str] = "/exit"


# Session-vocabulary kind names (session-vocabulary.md, ratified 2026-08-25).
SESSION_STARTED = "SessionStarted"
USER_MESSAGE = "UserMessage"
MODEL_REPLY = "ModelReply"
PARK = "Park"
SESSION_ENDED = "SessionEnded"
SESSION_END_REQUESTED = "SessionEndRequested"
TRANSCRIPT_COMPACTED = "TranscriptCompacted"
SESSION_WARNING = "SessionWarning"
BACKGROUND_TASK_ENDED = "BackgroundTaskEnded"  # UI sprint 104
# Written by the daemon on a soft interrupt (Phase 8 item 6).
INTERRUPT_REQUESTED = "InterruptRequested"

# v0.2 additions (session-vocabulary.md § I, sprint 058, 2026-09-01).
PROMPT_FRAGMENT = "PromptFragment"
PROMPT_COMPOSED = "PromptComposed"
# PromptComposed.strategy from K261: the model producer's whole input for one call.
PROMPT_STRATEGY_MODEL_INPUT: Final[str] = "model_input"

# v0.3 (session-vocabulary.md § K, sprint K259, 2026-10-09). `Returned` ends a turn; `Park` ends a
# turn on records written before v0.3. Readers accept both (§ K.3).
RETURNED = "Returned"
TURN_END_KINDS: Final[frozenset[str]] = frozenset({RETURNED, PARK})
# Kinds a session record written before v0.3 carries and v0.3 no longer writes (§ K.3); a reader
# of session records accepts them.
LEGACY_SESSION_KINDS: Final[frozenset[str]] = frozenset({PARK, FINAL_ANSWER})
# Park.reason on old records, read as Returned.reason.
LEGACY_PARK_REASONS: Final[dict[str, str]] = {"final_answer": "replied", "interrupt": "interrupted"}
# SessionEnded.reason on old records (§ K.5): the turn cap ended a session with "timeout".
LEGACY_SESSION_END_REASONS: Final[dict[str, str]] = {"timeout": "turn_cap"}


class StopReason(StrEnum):
    """ModelReply.stop_reason (§ K.1): why the model call ended."""

    END_TURN = "end_turn"
    TOOL_USE = "tool_use"
    WRAP_UP = "wrap_up"


class ReturnReason(StrEnum):
    """Returned.reason (§ K.2): how the turn ended."""

    REPLIED = "replied"
    MODEL_ERROR = "model_error"
    INTERRUPTED = "interrupted"


def turn_replies(events: Iterable[Mapping[str, Any]]) -> list[tuple[int, str]]:
    """`(seq, text)` of every turn's reply on a session record, in record order.

    v0.3 records: a `ModelReply` whose `stop_reason` is not `tool_use`. Older records: the
    `FinalAnswer` (its `ModelReply` carries no `stop_reason` and is not counted, so a reply is
    never counted twice; a bail-out `FinalAnswer` with its own text is the turn's reply).
    """
    replies: list[tuple[int, str]] = []
    for env in events:
        kind = env.get("kind")
        payload = env.get("payload") or {}
        if not isinstance(payload, Mapping):
            continue
        if kind == FINAL_ANSWER or (
            kind == MODEL_REPLY
            and "stop_reason" in payload
            and payload["stop_reason"] != StopReason.TOOL_USE
        ):
            replies.append((int(env.get("seq", -1)), str(payload.get("text", ""))))
    return replies


SESSION_KINDS: frozenset[str] = frozenset(
    {
        SESSION_STARTED,
        USER_MESSAGE,
        MODEL_REPLY,
        PARK,
        RETURNED,
        SESSION_ENDED,
        SESSION_END_REQUESTED,
        TRANSCRIPT_COMPACTED,
        SESSION_WARNING,
        PROMPT_FRAGMENT,
        PROMPT_COMPOSED,
        BACKGROUND_TASK_ENDED,
        INTERRUPT_REQUESTED,
    }
)


# v0.2 additions — `PromptSource` StrEnum for `PromptFragment.source`.
# msgspec serialises StrEnum members as their string value on encode and
# accepts the string on decode; in-memory the value is the enum member,
# so equality with a raw string is True and downstream code can compare
# either shape. Extending the enum bumps the session vocabulary version
# (v0.2 → v0.2.1 → v0.3 as sources land).


class PromptSource(StrEnum):
    """PromptFragment.source. Two disjoint sets: SESSION_OPEN_SOURCES, written once by
    `session_prompt` and used in every prompt; TURN_SCOPED_SOURCES, used in the next prompt only.
    FragmentCohort (views.py) enforces the split. `per_turn` and `user_message` appear only on
    records before K261, which wrote them as fragments."""

    PER_TURN = "per_turn"
    ROLE = "role"
    BUNDLE_METHODOLOGY = "bundle_methodology"
    BUNDLE_PERSONALITY = "bundle_personality"
    PARENT_CONTEXT = "parent_context"
    TOOLS_SUITE = "tools_suite"
    USER_MESSAGE = "user_message"
    # Phase 8 item 7 — the daemon injects InterruptRequested via
    # Runtime.inject_event on soft ESC; the interrupt_fragment_producer
    # emits a PromptFragment with this source. Turn-scoped: fires once per
    # interrupt, clears on the next PromptComposed that consumes it.
    INTERRUPT = "interrupt"


# Session-open sources: fire once at RunStarted, appear in every turn's
# PromptComposed. FragmentCohort keeps one slot per source (latest wins).
SESSION_OPEN_SOURCES: Final[frozenset[PromptSource]] = frozenset(
    {
        PromptSource.ROLE,
        PromptSource.BUNDLE_METHODOLOGY,
        PromptSource.BUNDLE_PERSONALITY,
        PromptSource.TOOLS_SUITE,
        PromptSource.PARENT_CONTEXT,
    }
)

# Turn-scoped sources: FragmentCohort clears them on every PromptComposed, so a fragment reaches
# one prompt. Since K261 only `interrupt_fragment` writes one; `per_turn` and `user_message` are
# on older records.
TURN_SCOPED_SOURCES: Final[frozenset[PromptSource]] = frozenset(
    {
        PromptSource.PER_TURN,
        PromptSource.USER_MESSAGE,
        PromptSource.INTERRUPT,
    }
)


PROMPT_SOURCES: Final[frozenset[PromptSource]] = frozenset(PromptSource)


# Sprint 071 (2026-09-02): every session-topology producer_kind name
# as a Final[str] constant. The pattern from `constants.py`'s kernel
# lifecycle names extended to the session layer. A downstream topology
# that adds its own producer kind adds a member here and to the
# SESSION_PRODUCER_KINDS frozenset below.
PRODUCER_KIND_SESSION_STARTED: Final[str] = "session_started"
PRODUCER_KIND_MODEL: Final[str] = "model"
PRODUCER_KIND_TOOL: Final[str] = "tool"
# v0.3 (§ K.4): writes Returned. Records before v0.3 name the same producer `park`.
PRODUCER_KIND_RETURN: Final[str] = "return"
PRODUCER_KIND_SESSION_END: Final[str] = "session_end"
# K263: one producer for every session-open prompt source and the session's warnings (replaces
# role_fragment, bundle_methodology_fragment, bundle_personality_fragment,
# parent_context_fragment, tools_suite_fragment, session_warning and fragment_error_warning).
PRODUCER_KIND_SESSION_PROMPT: Final[str] = "session_prompt"
# K263: writes the first turn's UserMessage on a fresh record (was session_open).
PRODUCER_KIND_FIRST_MESSAGE: Final[str] = "first_message"
# Phase 8 item 7 — emits PromptFragment(source=interrupt) in response to an
# InterruptRequested envelope the daemon injected via Runtime.inject_event.
PRODUCER_KIND_INTERRUPT_FRAGMENT: Final[str] = "interrupt_fragment"
# Also declared by the CI wrapper (ci.py); listed here so the frozenset
# below covers every kind a session-shape topology can emit.
PRODUCER_KIND_DRIVER_STEPPER: Final[str] = "driver_stepper"

SESSION_PRODUCER_KINDS: Final[frozenset[str]] = frozenset(
    {
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
)


# Sprint 071 (2026-09-02): every session-topology trigger id. K264: each is named
# `<what it starts>-on-<event>` (session-vocabulary.md § K.5, § O).
TRIGGER_ID_TOOL_ON_TOOL_CALL: Final[str] = "tool-on-tool-call"
TRIGGER_ID_MODEL_ON_TOOL_RESULT: Final[str] = "model-on-tool-result"
TRIGGER_ID_MODEL_WRAP_UP_ON_TOOL_RESULT: Final[str] = "model-wrap-up-on-tool-result"
# v0.3 (§ K.5): the turn ends with Returned. Replaces park-on-final, park-on-model-error and
# park-on-interrupt.
TRIGGER_ID_RETURN_ON_REPLY: Final[str] = "return-on-reply"
TRIGGER_ID_RETURN_ON_MODEL_ERROR: Final[str] = "return-on-model-error"
TRIGGER_ID_RETURN_ON_INTERRUPT: Final[str] = "return-on-interrupt"
TRIGGER_ID_END_ON_EXIT: Final[str] = "end-on-exit"
TRIGGER_ID_END_ON_TURN_CAP: Final[str] = "end-on-turn-cap"
TRIGGER_ID_END_ON_END_REQUEST: Final[str] = "end-on-end-request"
TRIGGER_ID_INTERRUPT_FRAGMENT_ON_INTERRUPT_REQUEST: Final[str] = (
    "interrupt-fragment-on-interrupt-request"
)
TRIGGER_ID_DRIVER_STEPPER_ON_RETURNED: Final[str] = "driver-stepper-on-returned"
# K261: a UserMessage starts the model, which builds and records its own prompt. Replaces the
# per-turn chain (emit-per-turn-fragment, emit-user-message-fragment, compose-on-cohort-complete,
# resume-on-composed) and compose-on-interrupt-tool-result.
TRIGGER_ID_MODEL_ON_USER_MESSAGE: Final[str] = "model-on-user-message"
# K261: starts first_message once session_prompt has ended (K263: one producer to wait for).
TRIGGER_ID_FIRST_MESSAGE_ON_SESSION_PROMPT: Final[str] = "first-message-on-session-prompt"

SESSION_TRIGGER_IDS: Final[frozenset[str]] = frozenset(
    {
        TRIGGER_ID_TOOL_ON_TOOL_CALL,
        TRIGGER_ID_MODEL_ON_TOOL_RESULT,
        TRIGGER_ID_MODEL_WRAP_UP_ON_TOOL_RESULT,
        TRIGGER_ID_RETURN_ON_REPLY,
        TRIGGER_ID_RETURN_ON_MODEL_ERROR,
        TRIGGER_ID_RETURN_ON_INTERRUPT,
        TRIGGER_ID_END_ON_EXIT,
        TRIGGER_ID_END_ON_TURN_CAP,
        TRIGGER_ID_END_ON_END_REQUEST,
        TRIGGER_ID_INTERRUPT_FRAGMENT_ON_INTERRUPT_REQUEST,
        TRIGGER_ID_DRIVER_STEPPER_ON_RETURNED,
        TRIGGER_ID_MODEL_ON_USER_MESSAGE,
        TRIGGER_ID_FIRST_MESSAGE_ON_SESSION_PROMPT,
    }
)


def is_prompt_source(source: str) -> bool:
    """Whether `source` is a PromptSource value."""
    try:
        PromptSource(source)
    except ValueError:
        return False
    return True


def is_session_kind(kind: str) -> bool:
    """Whether `kind` is in SESSION_KINDS. Callers use this at receipt boundaries the way
    `constants.is_reserved` is used at kernel receipt boundaries."""
    return kind in SESSION_KINDS


__all__ = [
    "END_ON_EXIT_SENTINEL",
    "LEGACY_PARK_REASONS",
    "LEGACY_SESSION_END_REASONS",
    "INTERRUPT_REQUESTED",
    "LEGACY_SESSION_KINDS",
    "ParkReason",
    "PromptSource",
    "SessionEndReason",
    "SessionWarningKind",
    "MODEL_REPLY",
    "PARK",
    "PROMPT_COMPOSED",
    "PROMPT_FRAGMENT",
    "PROMPT_SOURCES",
    "RETURNED",
    "ReturnReason",
    "SESSION_ENDED",
    "SESSION_END_REQUESTED",
    "SESSION_KINDS",
    "SESSION_OPEN_SOURCES",
    "SESSION_STARTED",
    "SESSION_WARNING",
    "StopReason",
    "TRANSCRIPT_COMPACTED",
    "TURN_END_KINDS",
    "TURN_SCOPED_SOURCES",
    "USER_MESSAGE",
    "is_prompt_source",
    "is_session_kind",
    "turn_replies",
]

# spec-audit: 2026-09-01

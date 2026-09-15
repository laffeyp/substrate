# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Session-topology vocabulary — named constants for the eight kind strings.

the tech spec locks session-vocabulary.md as the topology's kind surface;
this module is the runtime enforcement layer that closes the "kind-name
typo drifts silently" class the Markdown-only vocabulary cannot catch
(REVIEW-2026-08-28 F5). The msgspec Structs at the top of `__init__.py`
type-check payload fields at the speaker's mouth; msgspec cannot check
the kind-name STRING itself, so a `"SessionEndeed"` typo in a
subscription filter or a trigger declaration would land silently.

Every reference to a session-vocabulary kind name inside
`substrate.topologies.session.*` must import from here. Grep of the
package after the F5 adoption pass returns zero raw literals of the
eight names outside this file and the committed CI records.

The kernel-side reserved lifecycle kinds (RunStarted, RunFinalised, …)
live in `substrate.constants`; that side is enforced by the same rule
via `is_reserved(kind)`. The two vocabularies do not overlap by design.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


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
    TIMEOUT = "timeout"
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

# v0.2 additions (session-vocabulary.md § I, sprint 058, 2026-09-01).
PROMPT_FRAGMENT = "PromptFragment"
PROMPT_COMPOSED = "PromptComposed"


SESSION_KINDS: frozenset[str] = frozenset(
    {
        SESSION_STARTED,
        USER_MESSAGE,
        MODEL_REPLY,
        PARK,
        SESSION_ENDED,
        SESSION_END_REQUESTED,
        TRANSCRIPT_COMPACTED,
        SESSION_WARNING,
        PROMPT_FRAGMENT,
        PROMPT_COMPOSED,
    }
)


# v0.2 additions — `PromptSource` StrEnum for `PromptFragment.source`.
# msgspec serialises StrEnum members as their string value on encode and
# accepts the string on decode; in-memory the value is the enum member,
# so equality with a raw string is True and downstream code can compare
# either shape. Extending the enum bumps the session vocabulary version
# (v0.2 → v0.2.1 → v0.3 as sources land).


class PromptSource(StrEnum):
    """PromptFragment.source — every fragment-source Producer yields a
    fragment whose `source` is one of these members. Two disjoint sets:
    SESSION_OPEN_SOURCES fire once at RunStarted and appear in every
    turn's PromptComposed; TURN_SCOPED_SOURCES fire per turn and appear
    only in that turn's PromptComposed. FragmentCohort (views.py)
    enforces the split."""

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

# Turn-scoped sources: fire on the per-turn chain (UserMessage →
# per_turn_fragment → user_message_fragment → composer). FragmentCohort
# clears these on every PromptComposed emission so turn N's composed
# prompt does not carry turn N-1's user message.
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
PRODUCER_KIND_PARK: Final[str] = "park"
PRODUCER_KIND_SESSION_END: Final[str] = "session_end"
PRODUCER_KIND_SESSION_WARNING: Final[str] = "session_warning"
PRODUCER_KIND_FRAGMENT_ERROR_WARNING: Final[str] = "fragment_error_warning"
PRODUCER_KIND_SESSION_OPEN: Final[str] = "session_open"
PRODUCER_KIND_PROMPT_COMPOSER: Final[str] = "prompt_composer"
PRODUCER_KIND_PER_TURN_FRAGMENT: Final[str] = "per_turn_fragment"
PRODUCER_KIND_ROLE_FRAGMENT: Final[str] = "role_fragment"
PRODUCER_KIND_BUNDLE_METHODOLOGY_FRAGMENT: Final[str] = "bundle_methodology_fragment"
PRODUCER_KIND_BUNDLE_PERSONALITY_FRAGMENT: Final[str] = "bundle_personality_fragment"
PRODUCER_KIND_PARENT_CONTEXT_FRAGMENT: Final[str] = "parent_context_fragment"
PRODUCER_KIND_TOOLS_SUITE_FRAGMENT: Final[str] = "tools_suite_fragment"
PRODUCER_KIND_USER_MESSAGE_FRAGMENT: Final[str] = "user_message_fragment"
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
)


# Sprint 068 (2026-09-02): every producer_kind name that emits a
# PromptFragment. session_topology's `warn-on-fragment-error` trigger
# uses this set to decide whether a substrate.ProducerFailed matches
# a fragment source. Sprint 071 rebuilds the frozenset from the
# PRODUCER_KIND_* Final[str] constants above rather than from raw
# strings.
FRAGMENT_SOURCE_KINDS: Final[frozenset[str]] = frozenset(
    {
        PRODUCER_KIND_PER_TURN_FRAGMENT,
        PRODUCER_KIND_ROLE_FRAGMENT,
        PRODUCER_KIND_BUNDLE_METHODOLOGY_FRAGMENT,
        PRODUCER_KIND_BUNDLE_PERSONALITY_FRAGMENT,
        PRODUCER_KIND_PARENT_CONTEXT_FRAGMENT,
        PRODUCER_KIND_TOOLS_SUITE_FRAGMENT,
        PRODUCER_KIND_USER_MESSAGE_FRAGMENT,
        PRODUCER_KIND_INTERRUPT_FRAGMENT,
    }
)


# Sprint 071 (2026-09-02): every session-topology trigger id.
TRIGGER_ID_RUN_TOOL: Final[str] = "run-tool"
TRIGGER_ID_CONTINUE: Final[str] = "continue"
TRIGGER_ID_WRAP_UP: Final[str] = "wrap-up"
TRIGGER_ID_PARK_ON_FINAL: Final[str] = "park-on-final"
TRIGGER_ID_PARK_ON_MODEL_ERROR: Final[str] = "park-on-model-error"
TRIGGER_ID_PARK_ON_INTERRUPT: Final[str] = "park-on-interrupt"
TRIGGER_ID_RESUME_ON_COMPOSED: Final[str] = "resume-on-composed"
TRIGGER_ID_END_ON_EXIT: Final[str] = "end-on-exit"
TRIGGER_ID_END_ON_CAP: Final[str] = "end-on-cap"
TRIGGER_ID_END_ON_USER_END: Final[str] = "end-on-user-end"
TRIGGER_ID_EMIT_PER_TURN_FRAGMENT: Final[str] = "emit-per-turn-fragment"
TRIGGER_ID_EMIT_USER_MESSAGE_FRAGMENT: Final[str] = "emit-user-message-fragment"
TRIGGER_ID_EMIT_INTERRUPT_FRAGMENT: Final[str] = "emit-interrupt-fragment"
TRIGGER_ID_COMPOSE_ON_COHORT_COMPLETE: Final[str] = "compose-on-cohort-complete"
# Phase 8 item 7 — fires the composer on ToolResult when the FragmentCohort
# holds a pending interrupt fragment. Mirror of TRIGGER_ID_CONTINUE, which
# gains a predicate refusing the same condition, so exactly one of the two
# fires per ToolResult and the model wakes with the tool result AND the
# interrupt directive in scope.
TRIGGER_ID_COMPOSE_ON_INTERRUPT_TOOL_RESULT: Final[str] = "compose-on-interrupt-tool-result"
TRIGGER_ID_WARN_ON_FRAGMENT_ERROR: Final[str] = "warn-on-fragment-error"
TRIGGER_ID_ADVANCE_ON_PARK: Final[str] = "advance-on-park"

SESSION_TRIGGER_IDS: Final[frozenset[str]] = frozenset(
    {
        TRIGGER_ID_RUN_TOOL,
        TRIGGER_ID_CONTINUE,
        TRIGGER_ID_WRAP_UP,
        TRIGGER_ID_PARK_ON_FINAL,
        TRIGGER_ID_PARK_ON_MODEL_ERROR,
        TRIGGER_ID_PARK_ON_INTERRUPT,
        TRIGGER_ID_RESUME_ON_COMPOSED,
        TRIGGER_ID_END_ON_EXIT,
        TRIGGER_ID_END_ON_CAP,
        TRIGGER_ID_END_ON_USER_END,
        TRIGGER_ID_EMIT_PER_TURN_FRAGMENT,
        TRIGGER_ID_EMIT_USER_MESSAGE_FRAGMENT,
        TRIGGER_ID_EMIT_INTERRUPT_FRAGMENT,
        TRIGGER_ID_COMPOSE_ON_COHORT_COMPLETE,
        TRIGGER_ID_COMPOSE_ON_INTERRUPT_TOOL_RESULT,
        TRIGGER_ID_WARN_ON_FRAGMENT_ERROR,
        TRIGGER_ID_ADVANCE_ON_PARK,
    }
)


def is_prompt_source(source: str) -> bool:
    """Whether `source` is one of the seven v0.2 PromptSource enum values.
    Callers use this the way `is_session_kind` gates kind names — at the
    fragment producer's yield seam, not deep in the composer body."""
    try:
        PromptSource(source)
    except ValueError:
        return False
    return True


def is_session_kind(kind: str) -> bool:
    """Whether `kind` is one of the eight session-vocabulary names.
    Callers use this at receipt boundaries the way `constants.is_reserved`
    is used at kernel receipt boundaries."""
    return kind in SESSION_KINDS


__all__ = [
    "END_ON_EXIT_SENTINEL",
    "FRAGMENT_SOURCE_KINDS",
    "ParkReason",
    "PromptSource",
    "SessionEndReason",
    "SessionWarningKind",
    "MODEL_REPLY",
    "PARK",
    "PROMPT_COMPOSED",
    "PROMPT_FRAGMENT",
    "PROMPT_SOURCES",
    "SESSION_ENDED",
    "SESSION_END_REQUESTED",
    "SESSION_KINDS",
    "SESSION_OPEN_SOURCES",
    "SESSION_STARTED",
    "SESSION_WARNING",
    "TRANSCRIPT_COMPACTED",
    "TURN_SCOPED_SOURCES",
    "USER_MESSAGE",
    "is_prompt_source",
    "is_session_kind",
]

# spec-audit: 2026-09-01

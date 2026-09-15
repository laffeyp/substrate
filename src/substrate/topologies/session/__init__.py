# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Session topology — the daily-driver tool_loop with pause_await_input on FinalAnswer.

The session lives for the length of a driver conversation. A UserMessage opens a turn;
the `model` producer reads the transcript and yields a ToolCall (dispatch a tool), a
ModelReply (visible text), or a FinalAnswer (turn done). Tools run through the same
seam as `tool_loop`. A FinalAnswer fires the `park` producer, which emits one Park and
completes; the topology's termination pauses the run awaiting the next UserMessage.
Slash commands and daemon-injected SessionEndRequested route through the `session_end`
producer to a SessionEnded and terminate the run.

Sprint 205 registered the four Producers, three Views, and eight Structs. Sprint 206
adds the ten triggers, composes termination as
`any_of(pause_await_input(on Park, resume_condition="UserMessage"), threshold_count("SessionEnded", 1))`,
and refuses `all_completed` at build time — a pausable topology on `all_completed`
hangs on resume because the paused Producer's ProducerStarted has no durable end
(policies.py:90-97). Producer bodies stay scaffolded; sprint 207 replaces them with
the real model / tool / park / session_end loop and the rolling-window transcript.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from msgspec import Struct

from ... import api
from ...adapters import DeterministicResponder, Responder, call_responder
from ...kernel.policies import TerminationPolicy
from ..tool_loop import _tool_factory as _tool_loop_tool_factory
from ..tool_loop.tools import Tool, ollama_tools, parse_tool_call, suite_describe
from .vocabulary import (
    END_ON_EXIT_SENTINEL,
    FRAGMENT_SOURCE_KINDS,
    PARK,
    PRODUCER_KIND_BUNDLE_METHODOLOGY_FRAGMENT,
    PRODUCER_KIND_BUNDLE_PERSONALITY_FRAGMENT,
    PRODUCER_KIND_FRAGMENT_ERROR_WARNING,
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
    PRODUCER_KIND_INTERRUPT_FRAGMENT,
    PRODUCER_KIND_USER_MESSAGE_FRAGMENT,
    SESSION_END_REQUESTED,
    SESSION_ENDED,
    TRIGGER_ID_COMPOSE_ON_COHORT_COMPLETE,
    TRIGGER_ID_COMPOSE_ON_INTERRUPT_TOOL_RESULT,
    TRIGGER_ID_CONTINUE,
    TRIGGER_ID_EMIT_INTERRUPT_FRAGMENT,
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
    USER_MESSAGE,
    ParkReason,
    SessionEndReason,
    SessionWarningKind,
)

_ALL_COMPLETED_RE = re.compile(r"\ball_completed\b")


def _refuse_all_completed(policy: TerminationPolicy) -> None:
    """Reject `all_completed` at any nesting depth in the composed termination.

    Every built-in composer (`any_of`, `all_of`) concatenates its members' `.name`
    fields, so the leaf name `all_completed` from `policies.py:90` reappears verbatim
    inside the composed name. A word-boundary regex match catches direct use and every
    depth of composition (`any_of(all_completed(),...)`, `any_of(any_of(all_completed(),...),...)`,
    etc.) without paying the cost of walking closed-over sub-policies (they are not
    exposed as attributes). See `policies.py:90-97` for why a pausable topology on
    `all_completed` hangs on resume.
    """
    if _ALL_COMPLETED_RE.search(policy.name):
        raise api.RegistrationError(
            "session_topology termination policy contains `all_completed` "
            f"(name={policy.name!r}). A pausable topology on all_completed hangs on "
            "resume — the paused Producer's ProducerStarted has no durable end, so "
            "started > ended forever. See kernel/policies.py::all_completed. Compose "
            "with quiescence_with_watchdog or threshold_count instead."
        )


# Event Structs — vocabulary lock at `substrate/process/signals/session-vocabulary.md`
# v0.1 (sprint 202, RATIFIED 2026-08-25). Eight PascalCase Structs, all frozen. Every
# name is application-scoped; none uses the reserved `substrate.` prefix.


class SessionStarted(Struct, frozen=True):
    session_id: str
    seed: str
    driver_model: str
    driver_context_tokens: int
    tool_suite: tuple[str, ...]
    workspace_path: str
    workspace_shape: str
    bundle: str | None
    baseline: dict[str, Any]
    parent_session_id: str | None
    parent_seq_at_call: int | None


class UserMessage(Struct, frozen=True):
    text: str
    turn_index: int
    assembled_prompt: str
    slash_source: str | None


class ModelReply(Struct, frozen=True):
    text: str
    model_usage: dict[str, Any]
    turn_index: int


class Park(Struct, frozen=True):
    awaiting: str
    turn_index: int
    reason: str


class SessionEnded(Struct, frozen=True):
    reason: str
    total_turns: int


class SessionEndRequested(Struct, frozen=True):
    session_id: str
    source: str


# Phase 8 item 6 (2026-09-14): the envelope the daemon writes to the record
# when SessionRegistry.interrupt(tier="soft") is invoked while a tool
# producer is running. The model producer is not live at that moment; it
# has already completed the ToolCall and the tool producer is in flight.
# The daemon cannot inject via Runtime.resume(resume_event=...) because the
# runtime is not parked. Instead, the daemon writes this envelope directly
# to the record (like the daemon's session-lifecycle envelopes) and item 7
# adds a fragment producer that subscribes to it, emits a PromptFragment
# the composer folds into the model's next prompt. The model reads the
# fragment on the next turn and returns rather than starting a new tool.
class InterruptRequested(Struct, frozen=True):
    session_id: str
    tier: str  # "soft" — hard cancels a producer and needs no envelope
    source: str  # "daemon:interrupt-soft" or a delegate's caller


class SessionWarning(Struct, frozen=True):
    session_id: str
    kind: str
    seed_tokens: int
    driver_context_tokens: int
    # v0.2.1 addition (sprint 068, 2026-09-02): source_name names the failed
    # fragment producer kind when `kind == "fragment_source_failed"`. Absent
    # (None) for every other kind value.
    source_name: str | None = None


# v0.2 additions (session-vocabulary.md § I, sprint 058, 2026-09-01). Two Structs
# name the fragment/composer shape the prompt-composition arc rebuilds around.
# `PromptFragment` is emitted by each fragment-source Producer (sprints 060-064);
# `PromptComposed` is emitted by the composer Producer (sprint 059) once per
# model firing, carrying the assembled prompt plus fragment provenance so a
# record reader can trace which fragments composed each turn.


class PromptFragment(Struct, frozen=True):
    source: str  # one of session/vocabulary.py::PROMPT_SOURCES
    text: str
    precedence: int
    provenance: dict[str, Any]


class PromptComposed(Struct, frozen=True):
    text: str
    fragment_seqs: tuple[int, ...]
    total_tokens: int
    strategy: str  # "precedence_join" in v0.2


# Sprint 209a wires the four core producer bodies. The model producer reads the
# just-appended UserMessage / ToolResult and yields ToolCall / ModelReply / FinalAnswer.
# The tool producer is verbatim from `tool_loop` — same tool seam, same error-as-observation
# discipline. Park and session_end each yield one Struct and complete; both declared
# `deterministic=True` because the emission depends only on the trigger input.


_MAX_CONSECUTIVE_FAILS = 3


# Drift-grooming 2026-09-02: the three model-producer directive templates
# named as module constants. Sprint 064 promised a wrap_up_producer that
# would emit these as fragments; the fragment shape does not fit — wrap-up
# is a mid-body model-producer decision (final=True on wrap-up trigger OR
# _MAX_CONSECUTIVE_FAILS trailing tool failures) that no session-open
# producer can see. The template lives inline; naming it here removes the
# scattered f-string and gives future readers one authoritative spelling.
_WRAP_UP_DIRECTIVE = (
    "You cannot call more tools this turn ({reason}). "
    "Answer the user in plain text with what you have. If the tool "
    "failed, explain why in one or two sentences and suggest a "
    "workable next step. Do not emit a tool call — plain text only."
)
_JSON_TOOL_CALL_DIRECTIVE = (
    'Reply with EITHER a single JSON object {"name": "<tool>", "arguments": {...}} to '
    "call a tool, OR your final answer as plain text. Output only one of those."
)


def _park_factory() -> Callable[[], Any]:
    async def _park(inp: Any) -> AsyncIterator[Park]:
        turn_index = int(inp.get("turn_index", 0)) if hasattr(inp, "get") else 0
        reason = (
            str(inp.get("reason", ParkReason.FINAL_ANSWER))
            if hasattr(inp, "get")
            else str(ParkReason.FINAL_ANSWER)
        )
        yield Park(awaiting=USER_MESSAGE, turn_index=turn_index, reason=reason)

    return lambda: _park


def _session_end_factory() -> Callable[[], Any]:
    async def _session_end(inp: Any) -> AsyncIterator[SessionEnded]:
        reason = (
            str(inp.get("reason", SessionEndReason.USER_EXIT))
            if hasattr(inp, "get")
            else str(SessionEndReason.USER_EXIT)
        )
        total_turns = int(inp.get("total_turns", 0)) if hasattr(inp, "get") else 0
        yield SessionEnded(reason=reason, total_turns=total_turns)

    return lambda: _session_end


def _session_started_factory(
    session_id: str,
    seed: str,
    driver_name: str,
    driver_context_tokens: int,
    tool_names: tuple[str, ...],
    workspace_path: str,
    workspace_shape: str,
    bundle: str | None,
    parent_session_id: str | None,
    parent_seq_at_call: int | None,
) -> Callable[[], Any]:
    """Sprint 240 — the SessionStarted instrument's producer body.

    Fires exactly once on `substrate.RunStarted`, yields one SessionStarted
    envelope with every field the topology's caller passed in (the daemon
    at `substrate-ui/session_registry.py::SessionRegistry.turn_sync`, or a
    delegate-side callable). The `session_id`, `seed`, and driver identity
    are all present at topology build time — the closure captures them.

    Closes the substrate-side gap REVIEW-2026-08-28-piece-g-full SDD-1
    named: the SessionStarted Struct existed for two months without an
    emit site. Downstream readers (substrate-ui `terminal.ts`) now read
    the record for session-started as they read for Park, ModelReply,
    SessionEnded, TranscriptCompacted, SessionWarning.
    """

    async def _session_started(_inp: Any) -> AsyncIterator[SessionStarted]:
        yield SessionStarted(
            session_id=session_id,
            seed=seed,
            driver_model=driver_name,
            driver_context_tokens=driver_context_tokens,
            tool_suite=tool_names,
            workspace_path=workspace_path,
            workspace_shape=workspace_shape,
            bundle=bundle,
            baseline={},
            parent_session_id=parent_session_id,
            parent_seq_at_call=parent_seq_at_call,
        )

    return lambda: _session_started


def _session_open_factory(user_message: "UserMessage") -> Callable[[], Any]:
    """Sprint 217a: the fresh-record opener. Emits exactly one UserMessage
    (the daemon's first-turn text) and completes, so `resume-on-user` fires
    the model producer for the first turn from a `Runtime.run(topology)` call
    (rather than the previous shape's `Runtime.resume(topology, resume_event=UserMessage)`
    on an empty record, which skipped the `substrate.RunStarted` envelope
    because `_resume_bootstrap` sees `max_seq == -1` and does not open the run).

    Registered as an initial when `session_topology(first_turn_user_message=...)`
    is set (the daemon path); absent when None (the delegate path, the CI
    wrapper's driver_stepper path, and every path where the first UserMessage
    already rides on the resume-event channel).
    """

    async def _open(_inp: Any) -> AsyncIterator["UserMessage"]:
        yield user_message

    return lambda: _open


def _model_factory(
    *,
    driver: Responder,
    per_turn: str,
    script: list[tuple[str, list[Any]]] | None,
    seed: str,
    driver_context_tokens: int,
    driver_headroom_frac: float,
    record_root: Path | None,
    tools: dict[str, Tool],
) -> Callable[[], Any]:
    """Model Producer body. Yields TranscriptCompacted, ToolCall, ModelReply, or FinalAnswer.

    Sprint 209a v2 (post-review 2026-08-25) wires the four order-of-operations:

      1. **Transcript render + compaction emit.** When `record_root` is set, the body
         calls `render_transcript(...)` at the start of every firing and yields each
         `TranscriptCompacted` from `result.compaction_events` BEFORE any of the other
         schemas. This anchors the compaction to the model firing that drove it, per
         `transcript.py` §cadence and vocab-lock §F #6.
      2. **wrap-up guard.** `final=True` on the wrap-up trigger's input forces a
         `FinalAnswer` synthesized from the last tool result (or a stubbed no-result
         note when there is none).
      3. **Anti-spin.** A run of `_MAX_CONSECUTIVE_FAILS` tool failures at the tail
         bails with a truthful `FinalAnswer` citing the last error. Matches
         `tool_loop`'s guard.
      4. **Dispatch to a call.** Scripted path (CI): `script[step]` yields a
         `ToolCall`; on exhaustion, a `FinalAnswer`. Driver path (real LLM or
         DeterministicResponder): `driver.respond(prompt)` yields `ModelReply`
         then `FinalAnswer`. The prompt is `result.prompt_text` when the renderer
         ran, or a bare `assembled_prompt` when it did not (CI without a
         `record_root` binding). The reviewer-flagged `TOOL:` parse branch is
         deferred — sprint 210 (piece-A observation contract against a real LLM)
         is where a real driver-parse path lands.
    """

    async def _model(
        inp: Any,
    ) -> AsyncIterator[ToolCall | ModelReply | FinalAnswer | TranscriptCompacted]:
        step = int(inp.get("step", 0)) if hasattr(inp, "get") else 0
        results = list(inp.get("results", [])) if hasattr(inp, "get") else []
        final = bool(inp.get("final", False)) if hasattr(inp, "get") else False
        turn_index = int(inp.get("turn_index", 0)) if hasattr(inp, "get") else 0
        assembled_prompt = str(inp.get("assembled_prompt", "")) if hasattr(inp, "get") else ""
        # Sprint 067: composed_prompt carries the fragment-composed prompt
        # (role + bundle + tools + per_turn + parent_context + user_message
        # in precedence order). resume-on-composed fires on PromptComposed
        # so this always has content on turn N. Continue/wrap-up firings
        # on ToolResult read latest_composed via _read_composed_text.
        composed_prompt = str(inp.get("composed_prompt", "")) if hasattr(inp, "get") else ""

        # Prompt shape post-sprint-067:
        #   <PromptComposed.text: role + bundle + tools + per_turn + user_message>
        #   \n\n
        #   <render_transcript output: past turns' USER/MODEL/TOOL history>
        # The fragment path owns current-turn composition; render_transcript
        # owns multi-turn history (past USER/MODEL exchanges rendered from
        # the record).
        prompt_text = assembled_prompt
        if record_root is not None:
            rendered = render_transcript(
                record_root=record_root,
                seed=seed,
                per_turn=per_turn,
                driver_context_tokens=driver_context_tokens,
                driver_headroom_frac=driver_headroom_frac,
                turn_index_now=turn_index,
            )
            for compaction in rendered.compaction_events:
                yield compaction
            prompt_text = rendered.prompt_text
        if composed_prompt:
            prompt_text = f"{composed_prompt}\n\n{prompt_text}" if prompt_text else composed_prompt

        # Sprint 049: on either terminal condition — the wrap-up trigger's
        # `final=True` (max step reached) or the anti-spin guard tripping
        # after _MAX_CONSECUTIVE_FAILS failed tool calls — call the model
        # ONE more time with a directive to answer the user in plain text
        # (no more tools) using what it has. Before, both paths synthesised
        # a FinalAnswer from the raw error string and the model never got
        # to speak. The user saw "stopped after N failed tool call(s)…"
        # (or nothing, if the UI dropped FinalAnswer text) and no
        # explanation. Now the model composes the answer itself; the
        # session's own record still carries the failure evidence
        # verbatim in ToolResult events, so nothing is hidden.
        trailing_fails = 0
        for r in reversed(results):
            if r.get("ok", True):
                break
            trailing_fails += 1
        wrap_up_reason: str | None = None
        if final:
            wrap_up_reason = "budget reached"
        elif trailing_fails >= _MAX_CONSECUTIVE_FAILS:
            wrap_up_reason = f"tool failed {trailing_fails} times in a row"
        if wrap_up_reason is not None:
            progress = [
                {"tool": r.get("tool"), "ok": r.get("ok", True), "output": r.get("output", "")}
                for r in results
            ]
            last_err = str(results[-1].get("error", "")) if results else ""
            wrap_prompt = (
                f"{prompt_text}\n\n"
                f"Tool results so far, in order: {progress}\n\n"
                + _WRAP_UP_DIRECTIVE.format(reason=wrap_up_reason)
                + (f"\n\nLast error was: {last_err}" if last_err else "")
            )
            reply_text = str(await call_responder(driver, wrap_prompt))
            yield ModelReply(text=reply_text, model_usage={}, turn_index=turn_index)
            yield FinalAnswer(text=reply_text, steps=step)
            return
        if script is not None:
            if step < len(script):
                tool, args = script[step]
                yield ToolCall(call_id=f"c{step}", tool=tool, args=list(args), step=step)
            else:
                yield FinalAnswer(text=_answer_text_from_results(results), steps=step)
            return
        # Sprint 045 — expose the tool suite to the model. Ports the
        # tool_loop pattern (topologies/tool_loop/__init__.py:158-219):
        # try native tools-chat when the responder exposes achat_tools
        # (OllamaResponder does), else describe the tools in the prompt
        # and parse the reply. Parity with tool_loop is intentional so
        # the session inherits every improvement the loop earns.
        progress = [
            {"tool": r.get("tool"), "ok": r.get("ok", True), "output": r.get("output", "")}
            for r in results
        ]
        if tools:
            achat = getattr(driver, "achat_tools", None)
            if callable(achat):
                loop_prompt = prompt_text + (
                    f"\n\nTool results so far, in order: {progress}" if progress else ""
                )
                kind, chosen = parse_tool_call(await achat(loop_prompt, ollama_tools(tools)), tools)
                if kind == "tool":
                    name, call_args = chosen
                    yield ToolCall(call_id=f"c{step}", tool=name, args=list(call_args), step=step)
                    return
                text = str(chosen)
                yield ModelReply(text=text, model_usage={}, turn_index=turn_index)
                yield FinalAnswer(text=text, steps=step)
                return
            # Fallback for a text-only Responder (CliResponder, custom).
            # The tools_suite fragment carries the raw suite_describe(tools)
            # text in composed_prompt for record observability; the inline
            # "Tools you MAY use:" framing here is the prompt structure the
            # model reads. The two coexist by design — the fragment is the
            # record snapshot, the inline framing is the model's prompt
            # header. A framed fragment shifted llama3.2:1b's tool-argument
            # shape (dropped required `text` on write_file) on the
            # native-tools path where the fragment's prose lands in the
            # prompt alongside the tools JSON schema.
            described = (
                f"{prompt_text}\n\nTools you MAY use:\n{suite_describe(tools)}\n"
                + (f"Tool results so far, in order: {progress}\n" if progress else "")
                + _JSON_TOOL_CALL_DIRECTIVE
            )
            reply_text = str(await call_responder(driver, described))
            kind, chosen = parse_tool_call({"content": reply_text, "tool_calls": []}, tools)
            if kind == "tool":
                name, call_args = chosen
                yield ToolCall(call_id=f"c{step}", tool=name, args=list(call_args), step=step)
                return
            text = str(chosen)
            yield ModelReply(text=text, model_usage={}, turn_index=turn_index)
            yield FinalAnswer(text=text, steps=step)
            return
        # No tools declared: pure chat. Sprint 244's yield-through-
        # call_responder path preserved so cancel_producer still fires.
        reply_text = str(await call_responder(driver, prompt_text))
        yield ModelReply(text=reply_text, model_usage={}, turn_index=turn_index)
        yield FinalAnswer(text=reply_text, steps=step)

    return lambda: _model


def _answer_text_from_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "no result"
    last = results[-1]
    if not last.get("ok", True):
        return f"stopped: {last.get('error', 'tool failed')}"
    return str(last.get("output", ""))


def _session_warning_factory(
    *,
    session_id: str,
    kind: str,
    seed_tokens: int,
    driver_context_tokens: int,
) -> Callable[[], Any]:
    """Producer for the seed-alone-exceeds SessionWarning (sprint 208).

    Emits exactly one `SessionWarning` and completes. The topology registers this
    factory under an `initial` only when the seed + per_turn cost exceeds the
    headroom threshold at session open; the producer therefore never fires more
    than once per session, satisfying the §F #6 cadence invariant structurally.
    """

    async def _emit(inp: Any) -> AsyncIterator[SessionWarning]:
        del inp
        yield SessionWarning(
            session_id=session_id,
            kind=kind,
            seed_tokens=seed_tokens,
            driver_context_tokens=driver_context_tokens,
        )

    return lambda: _emit


def _fragment_error_warning_factory(session_id: str) -> Callable[[], Any]:
    """Sprint 068: producer for a SessionWarning(kind=fragment_source_failed)
    when any fragment source raises. The trigger `warn-on-fragment-error`
    fires this producer on `substrate.ProducerFailed` where the failed
    producer's kind is in `FRAGMENT_SOURCE_KINDS`. The trigger's input
    builder reads the failed kind from the ProducerFailed envelope and
    passes it as `source_name`.

    Cadence: at most once per (session_id, source_name) pair per session.
    The trigger enforces this via a `PerKey` policy keyed on source_name
    so a repeated failure on the same source (e.g., every turn) still
    fires the warning ONCE.
    """

    async def _emit(inp: Any) -> AsyncIterator[SessionWarning]:
        source_name = str(inp.get("source_name", "")) if hasattr(inp, "get") else ""
        yield SessionWarning(
            session_id=session_id,
            kind=SessionWarningKind.FRAGMENT_SOURCE_FAILED,
            seed_tokens=0,
            driver_context_tokens=0,
            source_name=source_name,
        )

    return lambda: _emit


def session_topology(
    *,
    driver: Responder,
    driver_name: str,
    driver_context_tokens: int,
    seed: str,
    tools: dict[str, Tool],
    per_turn: str = "",
    max_turns: int = 200,
    turn_max_steps: int = 24,
    session_id: str,
    workspace_path: str,
    workspace_shape: str = "flat",
    bundle: str | None = None,
    parent_session_id: str | None = None,
    parent_seq_at_call: int | None = None,
    script: list[tuple[str, list[Any]]] | None = None,
    record_root: Path | None = None,
    driver_headroom_frac: float = 0.6,
    first_turn_user_message: "UserMessage | None" = None,
    role: str | None = None,
    role_repo_root: Path | None = None,
    parent_context: dict[str, Any] | None = None,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the session topology.

    Thirteen keyword arguments name every input the daily-driver session opens with; the
    seed is the assembled string from the tech spec (composed by the daemon before this call).
    Sprint 205 registered Producers + Views + Structs. Sprint 206 added the ten triggers
    and composed termination. Sprint 208 added the `session_warning` producer + guard.
    Sprint 209a wires the four core producer bodies (model / tool / park / session_end).
    The `script` kwarg is the CI dispatch hook: a list of `(tool_name, args)` the model
    fires in order, matching `tool_loop`'s script convention; omit for the driver-parse
    path.

    ``record_root`` gates transcript compaction. When ``None`` the model
    producer skips ``render_transcript`` entirely and hands the driver the
    raw ``assembled_prompt`` from the last UserMessage — so a long session
    silently overruns any driver's context window. Every real caller
    (``substrate-ui/server.py:_session_factory``) passes the manifest's
    record path. Sprint 050 audit finding: not passing it during a
    handful-of-turn CI test is fine, but a fresh production caller that
    forgets is a silent bug. Warn once at build time when it is ``None``
    so the omission surfaces at review, not at first budget-exceeded turn.
    """
    if record_root is None:
        import warnings

        warnings.warn(
            "session_topology(record_root=None): transcript compaction is "
            "disabled — the model producer hands the driver the raw last-"
            "UserMessage prompt every turn, so a long session will overrun "
            "the driver's context window. Pass record_root=Path(<manifest."
            "record_root>) unless this is a short-lived CI test that stays "
            "inside one K-window of turns (see session/transcript.py). "
            "Sprint 050 audit.",
            stacklevel=2,
        )

    # `driver_name`, `workspace_path`, `parent_session_id`, `parent_seq_at_call` are
    # placeholders on the daemon's call-site contract; sprint 213/217/225 bind them.
    # They ride the signature so the outer daemon does not shift when they wire up.

    def _step_of(ctx: Any) -> int:
        # `step` rides ToolResult and continue/wrap-up input payloads. Absent means the
        # first firing of a turn (resume-on-user) — step 0. Historical default of
        # `turn_max_steps` was a coincidental failsafe that routed a missing step to
        # wrap-up; explicit 0 matches the actual semantics.
        payload = getattr(ctx.event, "payload", None) or {}
        return int(payload.get("step", 0))

    def _turn_index(ctx: Any) -> int:
        # UserMessage KindCount rides `user_turns`; the count is 1-based right after
        # the just-appended UserMessage lands, so the current turn is count-1.
        n = int(ctx.views["user_turns"].value())
        return max(n - 1, 0)

    def _producer_kind_from_ref(ctx: Any) -> str | None:
        payload = getattr(ctx.event, "payload", None) or {}
        return producer_kind_from_lifecycle_payload(payload)

    def _read_composed_text(ctx: Any) -> str:
        """Sprint 067: read the latest PromptComposed's text from the view.
        Returns empty string on the first firing before the composer has
        emitted (e.g., resume-on-user for turn 1 races the composer's
        chain). _model_factory falls back to bare assembled_prompt in
        that case."""
        latest = ctx.views["latest_composed"].value() if "latest_composed" in ctx.views else None
        if not isinstance(latest, dict):
            return ""
        return str(latest.get("text", ""))

    def _has_pending_interrupt(ctx: Any) -> bool:
        """True when the FragmentCohort holds a fresh interrupt fragment
        the composer has not yet folded. Used by CONTINUE and WRAP_UP to
        step aside so TRIGGER_ID_COMPOSE_ON_INTERRUPT_TOOL_RESULT can fire
        the composer and produce a fresh PromptComposed. The FragmentCohort
        clears its turn slice on every PromptComposed emission (see
        views.py::FragmentCohort.update), so the flag naturally deasserts
        after the composer refires."""
        if "fragment_cohort" not in ctx.views:
            return False
        for _seq, payload in ctx.views["fragment_cohort"].value():
            if isinstance(payload, dict) and payload.get("source") == "interrupt":
                return True
        return False

    def _compose_input(ctx: Any) -> dict[str, Any]:
        """Drift-grooming pass 2026-09-02: the composer's input builder
        unpacks the FragmentCohort's [(seq, payload)] into `fragments` +
        `fragment_seqs` — real record seqs, not positional indices. A
        record reader can trace each PromptComposed back to every source
        PromptFragment by seq. The View has already dropped prior turns'
        per_turn and user_message fragments; only this turn's belong."""
        cohort = list(ctx.views["fragment_cohort"].value())
        return {
            "fragments": [payload for _seq, payload in cohort],
            "fragment_seqs": [seq for seq, _payload in cohort],
        }

    def _continue_input(ctx: Any, *, final: bool) -> dict[str, Any]:
        # Sprint 047: pass this turn's ToolResults only, not the session-wide
        # buffer. The KindBuffer("ToolResult") view at line ~565 accumulates
        # every result for the life of the session, so a failed turn's
        # trailing_fails counter carried into the next turn — a session
        # with 3 failed bash calls in turn 2 tripped anti-spin on turn 3's
        # first attempt. Fix: `step` reflects THIS turn's next firing (0
        # after resume-on-user, 1 after the first ToolResult, ...); the
        # count of ToolResults produced this turn is exactly `_step_of + 1`;
        # slice the buffer tail to that count. Cross-turn ordering is
        # preserved because the buffer is append-order; the last N results
        # are always this-turn's N. Python's slice handles the edge cleanly
        # (results[-1:] on an empty list is an empty list).
        this_turn_count = _step_of(ctx) + 1
        session_results = list(ctx.views["results"].value())
        return {
            "step": _step_of(ctx) + 1,
            "results": session_results[-this_turn_count:] if this_turn_count > 0 else [],
            "final": final,
            "turn_index": _turn_index(ctx),
            "composed_prompt": _read_composed_text(ctx),
        }

    # DeterministicResponder is deterministic on (prompt, seed) by construction; both
    # the scripted path and the driver-parse path are byte-stable when the driver is
    # deterministic. A real OllamaResponder or CliResponder is not — the model producer
    # stays `deterministic=False` on those paths.
    model_is_deterministic = isinstance(driver, DeterministicResponder)

    # Sprint 240: freeze the tool_names tuple at build time so the
    # SessionStarted instrument's closure captures a snapshot even if the
    # `tools` dict is mutated later (it should not be, but the freeze is
    # defensive — the emitted envelope must reflect the boot-time suite).
    _tool_names_frozen: tuple[str, ...] = tuple(sorted(tools.keys()))

    def topo(b: api.TopologyBuilder) -> None:
        # Sprint 240: SessionStarted emit on RunStarted. Closes the
        # substrate-side gap REVIEW-2026-08-28-piece-g-full SDD-1 named.
        # `substrate.RunStarted` fires exactly once at run open (seq 0); the
        # instrument emits one SessionStarted at seq 2 (RunStarted → the
        # instrument's synthesized TriggerFired → SessionStarted).
        # Observation contract: `terminal.ts::_handleEnvelope` reads the
        # `SessionStarted` branch; the UI's `DRIVER_SESSION_STARTED` moves
        # from the daemon-ack seam to the record-envelope seam.
        b.instrument(
            PRODUCER_KIND_SESSION_STARTED,
            on=api.RUN_STARTED,
            schemas=[SessionStarted],
            input_builder=lambda _ctx: {},
            factory=_session_started_factory(
                session_id=session_id,
                seed=seed,
                driver_name=driver_name,
                driver_context_tokens=driver_context_tokens,
                tool_names=_tool_names_frozen,
                workspace_path=workspace_path,
                workspace_shape=workspace_shape,
                bundle=bundle,
                parent_session_id=parent_session_id,
                parent_seq_at_call=parent_seq_at_call,
            ),
            deterministic=True,
        )
        b.producer_kind(
            PRODUCER_KIND_MODEL,
            schemas=[ToolCall, FinalAnswer, ModelReply, TranscriptCompacted],
            schema_version=1,
            factory=_model_factory(
                driver=driver,
                per_turn=per_turn,
                script=script,
                seed=seed,
                driver_context_tokens=driver_context_tokens,
                driver_headroom_frac=driver_headroom_frac,
                record_root=record_root,
                tools=tools,
            ),
            deterministic=model_is_deterministic,
        )
        b.producer_kind(
            PRODUCER_KIND_TOOL,
            schemas=[ToolResult],
            schema_version=1,
            factory=_tool_loop_tool_factory(tools),
            deterministic=all(t.deterministic for t in tools.values()) if tools else True,
        )
        b.producer_kind(
            PRODUCER_KIND_PARK,
            schemas=[Park],
            schema_version=1,
            factory=_park_factory(),
            deterministic=True,
        )
        b.producer_kind(
            PRODUCER_KIND_SESSION_END,
            schemas=[SessionEnded],
            schema_version=1,
            factory=_session_end_factory(),
            deterministic=True,
        )
        # Seed-alone-exceeds guard. The threshold is the same
        # 60% headroom the transcript renderer uses (`driver_headroom_frac`), so a
        # session whose seed alone eats past that mark starts with zero room for
        # any turn to fit. Registration happens unconditionally; the `initial`
        # binding fires only when the check trips, which enforces the "at most
        # once per (session_id, condition_kind)" cadence structurally (the
        # producer emits once and completes; no trigger re-fires it).
        seed_tokens = _est_tokens(seed) + _est_tokens(per_turn)
        seed_alone_exceeds = seed_tokens > int(driver_context_tokens * 0.6)
        b.producer_kind(
            PRODUCER_KIND_SESSION_WARNING,
            schemas=[SessionWarning],
            schema_version=1,
            factory=_session_warning_factory(
                session_id=session_id,
                kind=SessionWarningKind.SEED_ALONE_EXCEEDS,
                seed_tokens=seed_tokens,
                driver_context_tokens=driver_context_tokens,
            ),
            deterministic=True,
        )
        # Sprint 068: separate producer_kind for fragment_source_failed
        # warnings. Fires once per (session, source_name) pair when a
        # fragment producer raises. Sibling to session_warning so each
        # factory closes over one warning shape cleanly.
        b.producer_kind(
            PRODUCER_KIND_FRAGMENT_ERROR_WARNING,
            schemas=[SessionWarning],
            schema_version=1,
            factory=_fragment_error_warning_factory(session_id=session_id),
            deterministic=True,
        )
        if seed_alone_exceeds:
            b.initial(PRODUCER_KIND_SESSION_WARNING, input={})
        # Sprint 217a: register the session_open producer + initial only when the
        # daemon path calls session_topology(first_turn_user_message=...). The
        # producer emits that one UserMessage on Runtime.run(), and
        # `resume-on-user` fires the model producer downstream. When
        # `first_turn_user_message` is None (delegate path; CI wrapper's
        # `driver_stepper` path; every path whose first UserMessage already
        # rides on the resume-event channel) the producer + initial are absent
        # and the topology's turn-1 shape is unchanged.
        if first_turn_user_message is not None:
            b.producer_kind(
                PRODUCER_KIND_SESSION_OPEN,
                schemas=[UserMessage],
                schema_version=1,
                factory=_session_open_factory(first_turn_user_message),
                deterministic=True,
            )
            b.initial(PRODUCER_KIND_SESSION_OPEN, input={})
        b.view("results", api.KindBuffer("ToolResult"))
        b.view("user_turns", api.KindCount(USER_MESSAGE))
        b.view("model_failures", ModelFailures())
        # Sprint 059 + drift-grooming pass 2026-09-02: fragment cohort View.
        # FragmentCohort splits PromptFragment events into session-open
        # (one slot per source; latest wins) and turn-scoped (list; clears
        # on every PromptComposed). value() returns [(seq, payload)] merged
        # and sorted by seq, so the composer's input builder passes real
        # record seqs on PromptComposed.fragment_seqs. Replaces the earlier
        # KindBuffer("PromptFragment") that accumulated every fragment ever
        # emitted, letting turn N-1's user_message ride turn N's composed
        # prompt (see role_producer.py:20-26's deferred note).
        b.view("fragment_cohort", FragmentCohort())
        b.producer_kind(
            PRODUCER_KIND_PROMPT_COMPOSER,
            schemas=[PromptComposed],
            schema_version=1,
            factory=composer_factory(),
            deterministic=True,
        )
        # Sprint 060: per_turn fragment source. Fires on UserMessage; yields
        # one PromptFragment(source=per_turn, ...) when manifest.per_turn is
        # non-empty, nothing when empty. Dual-path with render_transcript in
        # this landing state — sprint 064 removes the render-side injection
        # and switches _model_factory to read PromptComposed.text.
        b.producer_kind(
            PRODUCER_KIND_PER_TURN_FRAGMENT,
            schemas=[PromptFragment],
            schema_version=1,
            factory=per_turn_producer_factory(per_turn),
            deterministic=True,
        )
        # Sprint 061: role fragment source. Fires once at session open
        # (initial); resolves the role prompt via the four-layer resolver;
        # yields one PromptFragment(source=role, precedence=0). Only when
        # role is set — existing callers that don't pass role get no role
        # producer, no behavior change. Wires a currently-dead concept:
        # pre-sprint 061 manifest.role was validated at POST /api/session
        # and dropped; the resolved text now rides the record.
        if role is not None:
            b.producer_kind(
                PRODUCER_KIND_ROLE_FRAGMENT,
                schemas=[PromptFragment],
                schema_version=1,
                factory=role_producer_factory(role, repo_root=role_repo_root),
                deterministic=True,
            )
            b.initial(PRODUCER_KIND_ROLE_FRAGMENT, input={})
        # Sprint 062: bundle methodology + personality fragment sources.
        # Both fire once at session open; both read manifest.bundle via
        # bundles.load_bundle + resolve_extends and yield one or more
        # PromptFragment per non-empty slot in the chain. Register only
        # when bundle is set — empty bundle default preserves existing
        # caller behavior.
        if bundle is not None:
            b.producer_kind(
                PRODUCER_KIND_BUNDLE_METHODOLOGY_FRAGMENT,
                schemas=[PromptFragment],
                schema_version=1,
                factory=bundle_methodology_producer_factory(bundle),
                deterministic=True,
            )
            b.initial(PRODUCER_KIND_BUNDLE_METHODOLOGY_FRAGMENT, input={})
            b.producer_kind(
                PRODUCER_KIND_BUNDLE_PERSONALITY_FRAGMENT,
                schemas=[PromptFragment],
                schema_version=1,
                factory=bundle_personality_producer_factory(bundle),
                deterministic=True,
            )
            b.initial(PRODUCER_KIND_BUNDLE_PERSONALITY_FRAGMENT, input={})
        # Sprint 063: parent_context fragment source. Fires once at
        # session open when parent_context is set (a dict carrying
        # parent_record_root, parent_seq_range, kinds). Yields one
        # PromptFragment(source=parent_context, precedence=30) with the
        # extracted slice. Delegate migration deferred: delegate.py's
        # _prefix_context_slice still runs today; sprint 063 makes the
        # fragment path available to any caller that wires it directly.
        if parent_context is not None:
            b.producer_kind(
                PRODUCER_KIND_PARENT_CONTEXT_FRAGMENT,
                schemas=[PromptFragment],
                schema_version=1,
                factory=parent_context_producer_factory(parent_context),
                deterministic=True,
            )
            b.initial(PRODUCER_KIND_PARENT_CONTEXT_FRAGMENT, input={})
        # Sprint 064: tools_suite fragment source (session-open scope).
        # Fires once at RunStarted; yields one PromptFragment
        # (source=tools_suite, precedence=20) when the session's tool
        # suite is non-empty. Same shape as role_fragment and
        # bundle_*_fragment — the tools list rides the record for
        # observability, replacing the inline f-string composition
        # in _model_factory's fallback and native-tools paths.
        if tools:
            b.producer_kind(
                PRODUCER_KIND_TOOLS_SUITE_FRAGMENT,
                schemas=[PromptFragment],
                schema_version=1,
                factory=tools_suite_producer_factory(tools),
                deterministic=True,
            )
            b.initial(PRODUCER_KIND_TOOLS_SUITE_FRAGMENT, input={})
        # Sprint 064: user_message fragment source (turn-scoped, chained).
        # Fires on substrate.ProducerCompleted{kind=per_turn_fragment} so
        # the composer's downstream fire-on-user-message-completed trigger
        # sees a deterministic cohort — both per_turn and user_message
        # fragments are in the buffer by the time composer runs.
        b.producer_kind(
            PRODUCER_KIND_USER_MESSAGE_FRAGMENT,
            schemas=[PromptFragment],
            schema_version=1,
            factory=user_message_fragment_producer_factory(),
            deterministic=True,
        )
        # Phase 8 item 7: interrupt fragment source. Fires on
        # InterruptRequested envelopes the daemon injects via
        # Runtime.inject_event when the user presses Shift+ESC during a
        # tool. Yields one PromptFragment(source=interrupt,
        # precedence=95). Turn-scoped: FragmentCohort clears the entry
        # on the next PromptComposed, so the directive fires exactly
        # once per interrupt.
        b.producer_kind(
            PRODUCER_KIND_INTERRUPT_FRAGMENT,
            schemas=[PromptFragment],
            schema_version=1,
            factory=interrupt_fragment_producer_factory(),
            deterministic=True,
        )
        # Latest UserMessage view — the user_message fragment trigger reads
        # the text from here (the chained trigger fires on ProducerCompleted,
        # which does not carry the UserMessage payload).
        b.view("latest_user_message", api.PerKindLatest(USER_MESSAGE))
        # Sprint 067: latest PromptComposed view. _model_factory reads this
        # per model firing and prepends its text to the transcript-rendered
        # prompt. The fragment/composer path (sprints 059-064) becomes the
        # source of truth for role, bundle, tools, per_turn, parent_context,
        # and user_message; render_transcript retains multi-turn history.
        b.view("latest_composed", api.PerKindLatest("PromptComposed"))

        b.trigger(
            TRIGGER_ID_RUN_TOOL,
            subscription=api.Subscription(kinds=frozenset({"ToolCall"})),
            predicate=lambda ctx: True,
            starts=PRODUCER_KIND_TOOL,
            input_builder=lambda ctx: {
                "call_id": ctx.event.payload["call_id"],
                "tool": ctx.event.payload["tool"],
                "args": list(ctx.event.payload["args"]),
                "step": int(ctx.event.payload["step"]),
            },
            policy=api.PerEvent(),
        )
        b.trigger(
            TRIGGER_ID_CONTINUE,
            subscription=api.Subscription(kinds=frozenset({"ToolResult"})),
            # Phase 8 item 7: refuse when a pending interrupt fragment
            # sits in the cohort. TRIGGER_ID_COMPOSE_ON_INTERRUPT_TOOL_RESULT
            # (mirror below) fires the composer instead so the model wakes
            # on a fresh PromptComposed carrying the tool result AND the
            # interrupt directive.
            predicate=lambda ctx: (
                _step_of(ctx) + 1 < turn_max_steps and not _has_pending_interrupt(ctx)
            ),
            starts=PRODUCER_KIND_MODEL,
            input_builder=lambda ctx: _continue_input(ctx, final=False),
            policy=api.PerEvent(),
        )
        b.trigger(
            TRIGGER_ID_WRAP_UP,
            subscription=api.Subscription(kinds=frozenset({"ToolResult"})),
            predicate=lambda ctx: (
                _step_of(ctx) + 1 >= turn_max_steps and not _has_pending_interrupt(ctx)
            ),
            starts=PRODUCER_KIND_MODEL,
            input_builder=lambda ctx: _continue_input(ctx, final=True),
            policy=api.PerEvent(),
        )
        # Phase 8 item 7: fires the composer on ToolResult when the
        # cohort holds a pending interrupt fragment. Mirror of CONTINUE /
        # WRAP_UP (both refuse the same condition). Exactly one of the
        # three fires per ToolResult.
        b.trigger(
            TRIGGER_ID_COMPOSE_ON_INTERRUPT_TOOL_RESULT,
            subscription=api.Subscription(kinds=frozenset({"ToolResult"})),
            predicate=lambda ctx: _has_pending_interrupt(ctx),
            starts=PRODUCER_KIND_PROMPT_COMPOSER,
            input_builder=lambda ctx: _compose_input(ctx),
            policy=api.PerEvent(),
        )
        b.trigger(
            TRIGGER_ID_PARK_ON_FINAL,
            subscription=api.Subscription(kinds=frozenset({"FinalAnswer"})),
            predicate=lambda ctx: True,
            starts=PRODUCER_KIND_PARK,
            input_builder=lambda ctx: {
                "turn_index": _turn_index(ctx),
                "reason": ParkReason.FINAL_ANSWER,
            },
            policy=api.PerEvent(),
        )
        b.trigger(
            TRIGGER_ID_PARK_ON_MODEL_ERROR,
            subscription=api.Subscription(kinds=frozenset({api.PRODUCER_FAILED})),
            predicate=lambda ctx: _producer_kind_from_ref(ctx) == PRODUCER_KIND_MODEL,
            starts=PRODUCER_KIND_PARK,
            input_builder=lambda ctx: {
                "turn_index": _turn_index(ctx),
                "reason": ParkReason.MODEL_ERROR,
            },
            policy=api.PerEvent(),
        )
        b.trigger(
            TRIGGER_ID_PARK_ON_INTERRUPT,
            subscription=api.Subscription(kinds=frozenset({api.PRODUCER_CANCELLED})),
            predicate=lambda ctx: _producer_kind_from_ref(ctx) == PRODUCER_KIND_MODEL,
            starts=PRODUCER_KIND_PARK,
            input_builder=lambda ctx: {
                "turn_index": _turn_index(ctx),
                "reason": ParkReason.INTERRUPT,
            },
            policy=api.PerEvent(),
        )
        # Sprint 067: model producer fires on PromptComposed, not on
        # UserMessage. Composer's chain (per_turn → user_message → composer)
        # guarantees PromptComposed lands per turn with the full fragment
        # cohort. The old resume-on-user shape read the raw UserMessage
        # and passed assembled_prompt through — now the source of truth
        # is PromptComposed.text.
        b.trigger(
            TRIGGER_ID_RESUME_ON_COMPOSED,
            subscription=api.Subscription(kinds=frozenset({"PromptComposed"})),
            predicate=lambda ctx: True,
            starts=PRODUCER_KIND_MODEL,
            input_builder=lambda ctx: {
                "step": 0,
                "results": [],
                "final": False,
                "turn_index": _turn_index(ctx),
                "assembled_prompt": ctx.event.payload.get("text", ""),
                "composed_prompt": ctx.event.payload.get("text", ""),
            },
            policy=api.PerEvent(),
        )
        # Sprint 060/064 chain — deterministic turn-scoped fragment ordering.
        # UserMessage → per_turn_fragment → user_message_fragment → composer.
        # Each link fires on the prior link's substrate.ProducerCompleted,
        # so the composer's cohort read (last trigger in the chain) sees
        # every turn-scoped fragment guaranteed. Session-open fragments
        # (role, bundle_*, tools_suite, parent_context) fired at RunStarted
        # long before turn 1 and are already in the cohort buffer.

        # Chain link 1: per_turn_fragment fires on UserMessage.
        b.trigger(
            TRIGGER_ID_EMIT_PER_TURN_FRAGMENT,
            subscription=api.Subscription(kinds=frozenset({USER_MESSAGE})),
            predicate=lambda ctx: True,
            starts=PRODUCER_KIND_PER_TURN_FRAGMENT,
            input_builder=lambda ctx: {},
            policy=api.PerEvent(),
        )
        # Chain link 2: user_message_fragment fires on per_turn's terminal
        # event (Completed OR Failed — sprint 068 extension). Reads the
        # current UserMessage.text from the latest_user_message view. If
        # per_turn_fragment raised, the chain still advances so the
        # composer's cohort emits with whatever landed; the parallel
        # warn-on-fragment-error trigger surfaces the failure as a
        # SessionWarning.
        b.trigger(
            TRIGGER_ID_EMIT_USER_MESSAGE_FRAGMENT,
            subscription=api.Subscription(
                kinds=frozenset({api.PRODUCER_COMPLETED, api.PRODUCER_FAILED})
            ),
            predicate=lambda ctx: _producer_kind_from_ref(ctx) == PRODUCER_KIND_PER_TURN_FRAGMENT,
            starts=PRODUCER_KIND_USER_MESSAGE_FRAGMENT,
            input_builder=lambda ctx: {
                "text": (ctx.views["latest_user_message"].value() or {}).get("text", ""),
                "turn_index": _turn_index(ctx),
            },
            policy=api.PerEvent(),
        )
        # Phase 8 item 7: fires the interrupt fragment producer on an
        # InterruptRequested envelope the daemon injected via
        # Runtime.inject_event. Off the per-turn chain — this is a
        # side-emission the composer refire (below) folds into the next
        # PromptComposed on the next ToolResult boundary.
        b.trigger(
            TRIGGER_ID_EMIT_INTERRUPT_FRAGMENT,
            subscription=api.Subscription(kinds=frozenset({"InterruptRequested"})),
            predicate=lambda ctx: True,
            starts=PRODUCER_KIND_INTERRUPT_FRAGMENT,
            input_builder=lambda ctx: {
                "tier": ctx.event.payload.get("tier", ""),
                "source": ctx.event.payload.get("source", ""),
            },
            policy=api.PerEvent(),
        )
        # Chain link 3 (composer): fires on user_message_fragment's terminal
        # event (Completed OR Failed — sprint 068 extension). Cohort contains
        # every session-open fragment (from RunStarted) plus this turn's
        # per_turn and user_message fragments when they landed. If a fragment
        # source failed, its fragment is missing from the cohort but the
        # composer still fires so the model gets a truncated composed prompt
        # rather than a hang.
        b.trigger(
            TRIGGER_ID_COMPOSE_ON_COHORT_COMPLETE,
            subscription=api.Subscription(
                kinds=frozenset({api.PRODUCER_COMPLETED, api.PRODUCER_FAILED})
            ),
            predicate=lambda ctx: (
                _producer_kind_from_ref(ctx) == PRODUCER_KIND_USER_MESSAGE_FRAGMENT
            ),
            starts=PRODUCER_KIND_PROMPT_COMPOSER,
            input_builder=lambda ctx: _compose_input(ctx),
            policy=api.PerEvent(),
        )
        # Sprint 068: warn-on-fragment-error surfaces any fragment-source
        # Producer failure as a SessionWarning(kind=fragment_source_failed,
        # source_name=<kind>). Fires on substrate.ProducerFailed when the
        # failed producer's kind is in FRAGMENT_SOURCE_KINDS.
        b.trigger(
            TRIGGER_ID_WARN_ON_FRAGMENT_ERROR,
            subscription=api.Subscription(kinds=frozenset({api.PRODUCER_FAILED})),
            predicate=lambda ctx: _producer_kind_from_ref(ctx) in FRAGMENT_SOURCE_KINDS,
            starts=PRODUCER_KIND_FRAGMENT_ERROR_WARNING,
            input_builder=lambda ctx: {
                "source_name": _producer_kind_from_ref(ctx) or "",
            },
            policy=api.PerEvent(),
        )
        b.trigger(
            TRIGGER_ID_END_ON_EXIT,
            subscription=api.Subscription(kinds=frozenset({USER_MESSAGE})),
            predicate=lambda ctx: (
                str(ctx.event.payload.get("text", "")).strip() == END_ON_EXIT_SENTINEL
            ),
            starts=PRODUCER_KIND_SESSION_END,
            input_builder=lambda ctx: {
                "reason": SessionEndReason.USER_EXIT,
                "total_turns": _turn_index(ctx) + 1,
            },
            policy=api.Once(),
        )
        b.trigger(
            # end-on-cap fires when the (max_turns + 1)th UserMessage arrives — the intent
            # is "let max_turns turns complete, then end on the next attempt". `>= max_turns`
            # off-by-one'd (fired on the max_turnsth message so its turn never ran); `> max_turns`
            # is what the tech spec §3 wording ("SessionEnded{reason: 'timeout'} on the 201st turn
            # for max_turns=200") actually names.
            TRIGGER_ID_END_ON_CAP,
            subscription=api.Subscription(kinds=frozenset({USER_MESSAGE})),
            predicate=lambda ctx: int(ctx.views["user_turns"].value()) > max_turns,
            starts=PRODUCER_KIND_SESSION_END,
            input_builder=lambda ctx: {
                "reason": SessionEndReason.TIMEOUT,
                "total_turns": int(ctx.views["user_turns"].value()) - 1,
            },
            policy=api.Once(),
        )
        b.trigger(
            # Sprint 215d: the SessionEnded reason mirrors the requester's
            # source when the source names a distinguishable path — today
            # the only such value is "daemon_shutdown" (SIGTERM). Every
            # other source (missing, "user_end", "cli_slash_exit", etc.)
            # maps to reason="user_end". Fingerprint-neutral: input_builder
            # is not serialized into TriggerReg (kernel/topology.py:97).
            TRIGGER_ID_END_ON_USER_END,
            subscription=api.Subscription(kinds=frozenset({SESSION_END_REQUESTED})),
            predicate=lambda ctx: True,
            starts=PRODUCER_KIND_SESSION_END,
            input_builder=lambda ctx: {
                "reason": (
                    SessionEndReason.DAEMON_SHUTDOWN
                    if (ctx.event.payload or {}).get("source") == SessionEndReason.DAEMON_SHUTDOWN
                    else SessionEndReason.USER_END
                ),
                "total_turns": int(ctx.views["user_turns"].value()),
            },
            policy=api.Once(),
        )
        termination = api.any_of(
            api.pause_await_input(
                when=lambda tctx: tctx.event is not None and tctx.event.kind == PARK,
                resume_condition=USER_MESSAGE,
            ),
            api.threshold_count(SESSION_ENDED, 1),
        )
        _refuse_all_completed(termination)
        b.termination(termination)

    return topo


# `SessionStarted`, `UserMessage`, `SessionEndRequested`, and `SessionWarning` do not
# appear in any `producer_kind(schemas=[...])` above because they arrive on the record
# from a different path: `SessionStarted` fires via an instrument on `substrate.RunStarted`
# (sprint 209 wires it), `UserMessage` and `SessionEndRequested` are external events
# injected by the daemon through `Runtime.resume(resume_event=...)`, and `SessionWarning`
# rides a `session_warning` producer added in sprint 208. Declaring them here keeps
# the eight-Struct vocabulary complete at the topology's Python surface.

# ToolCall / ToolResult / FinalAnswer are borrowed from `tool_loop` so the session
# reuses tool_loop's tool seam verbatim (product spec §4). The imports live below the
# session Structs so the file reads top-down: session's own vocabulary first, then
# the tool_loop borrow. tool_loop's schemas are already frozen msgspec Structs.
from ..tool_loop import FinalAnswer, ToolCall, ToolResult  # noqa: E402
from .transcript import (  # noqa: E402
    RenderedTranscript,
    TranscriptCompacted,
    _est_tokens,
    render_transcript,
    resolve_driver_context_tokens,
)
from .bundle_producer import (  # noqa: E402  # sprint 062
    bundle_methodology_producer_factory,
    bundle_personality_producer_factory,
)
from .composer import composer_factory  # noqa: E402  # sprint 059
from .interrupt_fragment_producer import (  # noqa: E402  # phase 8 item 7
    interrupt_fragment_producer_factory,
)
from .parent_context_producer import parent_context_producer_factory  # noqa: E402  # sprint 063
from .per_turn_producer import per_turn_producer_factory  # noqa: E402  # sprint 060
from .role_producer import role_producer_factory  # noqa: E402  # sprint 061
from .tools_suite_producer import tools_suite_producer_factory  # noqa: E402  # sprint 064
from .user_message_fragment_producer import (  # noqa: E402  # sprint 064
    user_message_fragment_producer_factory,
)
from .views import (  # noqa: E402
    FragmentCohort,
    ModelFailures,
    producer_kind_from_lifecycle_payload,
)

__all__ = [
    "FinalAnswer",
    "ModelFailures",
    "ModelReply",
    "Park",
    "PromptComposed",
    "PromptFragment",
    "RenderedTranscript",
    "SessionEnded",
    "SessionEndRequested",
    "InterruptRequested",
    "SessionStarted",
    "SessionWarning",
    "ToolCall",
    "ToolResult",
    "TranscriptCompacted",
    "UserMessage",
    "render_transcript",
    "resolve_driver_context_tokens",
    "session_topology",
]

# spec-audit: 2026-09-01

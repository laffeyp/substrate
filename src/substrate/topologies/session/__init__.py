# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Session topology — the daily-driver tool loop, paused between turns.

The session lives for the length of a driver conversation. A UserMessage opens a turn; the
`model` producer builds its prompt from the record and writes one ModelReply per model call
(vocabulary § K.1). A reply with `stop_reason=tool_use` is followed by a ToolCall, and the tool
runs through the same seam as `tool_loop`. A reply that ends the turn (`end_turn`, `wrap_up`),
a model failure, or a cancelled model or tool fires the `return` producer, which writes one
Returned; termination then pauses the run until the next UserMessage. Slash commands and
daemon-injected SessionEndRequested route through the `session_end` producer to a SessionEnded
and finalise the run.

Termination is `any_of(pause_await_input(on Returned, resume_condition="UserMessage"),
finalise_on("SessionEnded"))`. The builder refuses any policy with an `all_completed` member: a
paused Producer's ProducerStarted has no durable end, so a pausable topology on `all_completed`
hangs on resume.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from msgspec import Struct

from ... import api
from ...adapters import DeterministicResponder, ModelUsage, Responder, call_responder_metered
from ...kernel.policies import TerminationPolicy
from ..tool_loop import _tool_factory as _tool_loop_tool_factory
from ..tool_loop.background import TaskStatus
from ..tool_loop.kinds import TOOL_CALL, TOOL_RESULT
from ..tool_loop.tools import Tool, ollama_tools, parse_tool_call, suite_describe
from .vocabulary import (
    END_ON_EXIT_SENTINEL,
    INTERRUPT_REQUESTED,
    MODEL_REPLY,
    RETURNED,
    PROMPT_STRATEGY_MODEL_INPUT,
    PRODUCER_KIND_FIRST_MESSAGE,
    PRODUCER_KIND_INTERRUPT_FRAGMENT,
    PRODUCER_KIND_MODEL,
    PRODUCER_KIND_RETURN,
    PRODUCER_KIND_SESSION_END,
    PRODUCER_KIND_SESSION_PROMPT,
    PRODUCER_KIND_SESSION_STARTED,
    PRODUCER_KIND_TOOL,
    SESSION_END_REQUESTED,
    SESSION_ENDED,
    TRIGGER_ID_MODEL_ON_TOOL_RESULT,
    TRIGGER_ID_INTERRUPT_FRAGMENT_ON_INTERRUPT_REQUEST,
    TRIGGER_ID_END_ON_TURN_CAP,
    TRIGGER_ID_END_ON_EXIT,
    TRIGGER_ID_END_ON_END_REQUEST,
    TRIGGER_ID_FIRST_MESSAGE_ON_SESSION_PROMPT,
    TRIGGER_ID_MODEL_ON_USER_MESSAGE,
    TRIGGER_ID_RETURN_ON_INTERRUPT,
    TRIGGER_ID_RETURN_ON_MODEL_ERROR,
    TRIGGER_ID_RETURN_ON_REPLY,
    TRIGGER_ID_TOOL_ON_TOOL_CALL,
    TRIGGER_ID_MODEL_WRAP_UP_ON_TOOL_RESULT,
    USER_MESSAGE,
    ReturnReason,
    StopReason,
    SessionEndReason,
    SessionWarningKind,
)


def _refuse_all_completed(policy: TerminationPolicy) -> None:
    """Reject a policy that cannot decide across a pause and resume (`all_completed`), at any
    nesting depth. Walks the composed policy's members (lens F097: it used to match the name
    string). See `policies.py::all_completed` for why a pausable topology on it hangs on resume.
    """
    if any(not leaf.resumable for leaf in policy.leaves()):
        raise api.RegistrationError(
            "session_topology termination policy contains `all_completed` "
            f"(name={policy.name!r}). A pausable topology on all_completed hangs on "
            "resume — the paused Producer's ProducerStarted has no durable end, so "
            "started > ended forever. See kernel/policies.py::all_completed. Compose "
            "with quiescence or threshold_count instead."
        )


# Event Structs — the session vocabulary (`substrate/process/signals/session-vocabulary.md`,
# v0.1 of 2026-08-25 through the § O addendum). Every Struct is frozen; every kind name is
# application-scoped (no reserved `substrate.` prefix) and listed in `vocabulary.SESSION_KINDS`.


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
    """One per model call (vocabulary § K.1). `stop_reason`: `end_turn` (the model answered),
    `tool_use` (a ToolCall follows; `text` is whatever the model said beside the call) or
    `wrap_up` (the step budget or repeated tool failures forced a plain answer). `usage` is the
    call's ModelUsage (`model`, `prompt_tokens`, `completion_tokens`, `wall_ms`, `estimated`)."""

    text: str
    stop_reason: str
    usage: dict[str, Any]
    turn_index: int
    step: int


class BackgroundTaskEnded(Struct, frozen=True):
    """A bash background task of this session ended without the model stopping it (UI sprint 104).
    Written by the model producer before the step that tells the model, so the record shows what
    the model was told and when."""

    task_id: str
    command: str
    status: str  # a TaskStatus value: exited or stopped (a str on the record)
    exit: int | None
    stopped_because: str | None
    runtime_s: float
    stdout_tail: str
    stderr_tail: str


def background_notice(e: BackgroundTaskEnded) -> str:
    """The one line the model reads about an ended task."""
    how = (
        f"exited {e.exit}"
        if e.status == TaskStatus.EXITED
        else f"was stopped ({e.stopped_because})"
    )
    tail = (e.stdout_tail + e.stderr_tail).strip()[-300:]
    last = f"; last output: {tail}" if tail else ""
    return f"[background task {e.task_id} ({e.command[:120]}) {how} after {e.runtime_s:g} s{last}]"


class Park(Struct, frozen=True):
    """Records before v0.3 ended a turn with Park (vocabulary § K.2); the session now writes
    Returned. Kept so readers and fixtures can build and decode the old shape."""

    awaiting: str
    turn_index: int
    reason: str
    # On an old record's `reason=model_error`, the provider's error text; empty otherwise.
    detail: str = ""


class Returned(Struct, frozen=True):
    """The turn is over and control is back with the user (vocabulary § K.2; replaces Park).
    `reason`: `replied`, `model_error` (with the error in `detail`) or `interrupted`."""

    turn_index: int
    reason: str
    detail: str = ""


class SessionEnded(Struct, frozen=True):
    reason: str
    total_turns: int


class SessionEndRequested(Struct, frozen=True):
    session_id: str
    source: str


# Phase 8 item 6 (2026-09-14): the envelope the daemon writes to the record when
# SessionRegistry.interrupt(tier="soft") is called while a tool runs. The run is not paused, so
# the daemon cannot use Runtime.resume(resume_event=...); it writes this envelope to the live
# record instead. `interrupt-fragment-on-interrupt-request` starts `interrupt_fragment`, whose
# PromptFragment the model reads on its next step, beside the tool result; the model then answers
# rather than starting another tool.
class InterruptRequested(Struct, frozen=True):
    session_id: str
    tier: str  # "soft" — hard cancels a producer and needs no envelope
    source: str  # "daemon:interrupt-soft" or a delegate's caller


class SessionWarning(Struct, frozen=True):
    """Written by `session_prompt` at session open (vocabulary § E, § J, § N).

    `seed_alone_exceeds` carries `seed_tokens` and `driver_context_tokens`.
    `fragment_source_failed` carries `source_name`, the prompt source that raised (records before
    v0.3.3 name the failed producer kind instead), and `detail`, the error."""

    session_id: str
    kind: str
    seed_tokens: int
    driver_context_tokens: int
    source_name: str | None = None
    detail: str | None = None


# v0.2 additions (session-vocabulary.md § I, sprint 058; § L, K261). `PromptFragment` is written
# by `session_prompt` (one per session-open source) and by `interrupt_fragment`. `PromptComposed`
# is written by the `model` producer once per model call: the exact text the driver reads, and the
# seqs of the fragments it used.


class PromptFragment(Struct, frozen=True):
    source: str  # one of session/vocabulary.py::PROMPT_SOURCES
    text: str
    precedence: int
    provenance: dict[str, Any]


class PromptComposed(Struct, frozen=True):
    text: str
    fragment_seqs: tuple[int, ...]
    total_tokens: int
    strategy: (
        str  # "model_input" since K261 (PROMPT_STRATEGY_MODEL_INPUT); "precedence_join" before
    )


# The core producer bodies. The model producer reads the just-appended UserMessage /
# ToolResult and yields ModelReply (and a ToolCall after a `tool_use` reply). The tool producer
# is verbatim from `tool_loop` — same tool seam, same error-as-observation discipline.
# return and session_end each yield one Struct and complete; both declared
# `deterministic=True` because the emission depends only on the trigger input.


_MAX_CONSECUTIVE_FAILS = 3


# The model step's two directives. Wrap-up is decided inside the model step (`final=True` from
# `model-wrap-up-on-tool-result`, or _MAX_CONSECUTIVE_FAILS trailing tool failures), where no
# fragment producer can see it, so the text lives here rather than in a fragment.
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


def _return_factory() -> Callable[[], Any]:
    async def _return(inp: Any) -> AsyncIterator[Returned]:
        yield Returned(
            turn_index=int(inp.get("turn_index", 0)),
            reason=str(inp.get("reason", ReturnReason.REPLIED)),
            detail=str(inp.get("detail", "")),
        )

    return lambda: _return


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
    at `substrate/session_registry.py::SessionRegistry.turn_sync`, or a
    delegate-side callable). The `session_id`, `seed`, and driver identity
    are all present at topology build time — the closure captures them.

    Closes the gap REVIEW-2026-08-28-piece-g-full SDD-1 named: the SessionStarted Struct existed
    for two months without an emit site. The UI's session controller reads it off the record
    like every other session kind.
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


def _first_message_factory(user_message: "UserMessage") -> Callable[[], Any]:
    """The `first_message` producer (sprint 217a; `session_open` before K263): writes the first
    turn's UserMessage on a fresh record, so `model-on-user-message` starts the first model call
    from `Runtime.run`. (A `Runtime.resume` on an empty record would skip `substrate.RunStarted`:
    `_resume_bootstrap` sees `max_seq == -1` and opens no run.)

    Registered when `session_topology(first_turn_user_message=...)` is set (the daemon path);
    absent on the delegate and CI paths, whose first UserMessage arrives as a resume event.
    """

    async def _first_message(_inp: Any) -> AsyncIterator["UserMessage"]:
        yield user_message

    return lambda: _first_message


def _model_factory(
    *,
    driver: Responder,
    per_turn: str,
    script: list[tuple[str, list[Any]]] | None,
    seed: str,
    driver_context_tokens: int,
    driver_headroom_frac: float,
    tools: dict[str, Tool],
    session_id: str = "",
) -> Callable[[], Any]:
    """Model Producer body: build the prompt, record it, send it, record the reply (K261).

    Each firing builds the whole prompt with `transcript.compose_model_prompt` from the turn
    history view, the session's prompt fragments, `per_turn` and this step's state, writes it as
    `PromptComposed`, and sends exactly that text. Recording where the call happens is what keeps
    the record and the call equal. Then:

      - **wrap-up**: the step budget is spent (`final=True`) or the last `_MAX_CONSECUTIVE_FAILS`
        tool calls failed; the prompt ends with the plain-answer directive and the driver gets no
        tools.
      - **script** (CI): `script[step]` yields a `ToolCall`; on exhaustion, an answer built from
        the tool results. No model is called, so `usage` holds zero counts, `estimated: true`.
      - **native tools** (`achat_tools_metered`), **text-only tools** (the tool list and the
        JSON directive are in the prompt) or **no tools**.

    Every call yields one `ModelReply` (vocabulary § K.1): `stop_reason=tool_use` followed by
    its `ToolCall`, or `end_turn` / `wrap_up` carrying the answer. The session writes no
    FinalAnswer; `return-on-reply` ends the turn.
    """
    native = callable(getattr(driver, "achat_tools", None))
    tool_mode = "none" if not tools else ("native" if native else "text")

    async def _model(
        inp: Any,
    ) -> AsyncIterator[
        ToolCall | ModelReply | TranscriptCompacted | BackgroundTaskEnded | PromptComposed
    ]:
        step = int(inp.get("step", 0)) if hasattr(inp, "get") else 0
        results = list(inp.get("results", [])) if hasattr(inp, "get") else []
        final = bool(inp.get("final", False)) if hasattr(inp, "get") else False
        turn_index = int(inp.get("turn_index", 0)) if hasattr(inp, "get") else 0
        fragments = list(inp.get("fragments", [])) if hasattr(inp, "get") else []
        ticket = inp.get("history_ref") if hasattr(inp, "get") else None
        # K268: the history is read from the record by the ticket the trigger issued (claim
        # check). The kept seqs were written before this step started, so the read is the same
        # live and on replay.
        history: list[dict[str, Any]] = []
        if ticket:
            history = [
                env
                for env in api.read_range(
                    _own_record(), ticket["from_seq"], ticket["to_seq"], resolve_blobs=True
                )
                if env.get("kind") in TURN_EVENT_KINDS
            ]

        # UI sprint 104: background tasks of this session that ended since the last step. Each is
        # recorded, then told to the model in this step's prompt; later steps read it from the
        # history. (Claude Code notifies its agent when a background command finishes.)
        notices: list[str] = []
        if session_id:
            from ..tool_loop.background import TABLE as _BG_TABLE

            for n in _BG_TABLE.drain_ended(session_id):
                ended = BackgroundTaskEnded(
                    task_id=str(n["task_id"]),
                    command=str(n["command"]),
                    status=str(n["status"]),
                    exit=n["exit"],
                    stopped_because=n["stopped_because"],
                    runtime_s=float(n["runtime_s"]),
                    stdout_tail=str(n["stdout_tail"]),
                    stderr_tail=str(n["stderr_tail"]),
                )
                yield ended
                notices.append(background_notice(ended))

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
        prompt_text, fragment_seqs = compose_model_prompt(
            history=history, seed=seed, per_turn=per_turn, fragments=fragments, notices=notices
        )
        if ticket and ticket.get("dropped"):
            lo, hi = ticket["dropped"]
            yield TranscriptCompacted(
                strategy="rolling_window",
                dropped_seq_range=(int(lo), int(hi)),
                kept_seq_start=int(ticket["from_seq"]),
                reason="driver_window_exceeded",
                tokens_before=int(ticket["tokens_before"]),
                tokens_after=_est_tokens(prompt_text),
            )
        # The endings below are the pre-K261 wording, unchanged: K261 changes where the prompt's
        # parts come from and their order, not what the model is told.
        progress = [
            {"tool": r.get("tool"), "ok": r.get("ok", True), "output": r.get("output", "")}
            for r in results
        ]
        if wrap_up_reason is not None:
            last_err = str(results[-1].get("error", "")) if results else ""
            prompt = (
                f"{prompt_text}\n\n"
                f"Tool results so far, in order: {progress}\n\n"
                + _WRAP_UP_DIRECTIVE.format(reason=wrap_up_reason)
                + (f"\n\nLast error was: {last_err}" if last_err else "")
            )
        elif script is None and tool_mode == "native":
            prompt = prompt_text + (
                f"\n\nTool results so far, in order: {progress}" if progress else ""
            )
        elif script is None and tool_mode == "text":
            prompt = (
                f"{prompt_text}\n\nTools you MAY use:\n{suite_describe(tools)}\n"
                + (f"Tool results so far, in order: {progress}\n" if progress else "")
                + _JSON_TOOL_CALL_DIRECTIVE
            )
        else:
            prompt = prompt_text

        yield PromptComposed(
            text=prompt,
            fragment_seqs=fragment_seqs,
            total_tokens=_est_tokens(prompt),
            strategy=PROMPT_STRATEGY_MODEL_INPUT,
        )
        if script is not None and wrap_up_reason is None:
            # CI: the script stands in for the model's choice; the prompt above is what a model
            # would have read on this step.
            scripted = _usage_of(
                ModelUsage(
                    model="script", prompt_tokens=0, completion_tokens=0, wall_ms=0, estimated=True
                )
            )
            if step < len(script):
                tool, args = script[step]
                yield ModelReply(
                    text="",
                    stop_reason=StopReason.TOOL_USE,
                    usage=scripted,
                    turn_index=turn_index,
                    step=step,
                )
                yield ToolCall(call_id=f"c{step}", tool=tool, args=list(args), step=step)
            else:
                text = _answer_text_from_results(results)
                yield ModelReply(
                    text=text,
                    stop_reason=StopReason.END_TURN,
                    usage=scripted,
                    turn_index=turn_index,
                    step=step,
                )
            return
        beside_call = ""  # what the model said beside a native tool call
        if wrap_up_reason is None and tool_mode == "native":
            metered = getattr(driver, "achat_tools_metered", None)
            if callable(metered):
                message, usage = await metered(prompt, ollama_tools(tools))
            else:
                message = await driver.achat_tools(prompt, ollama_tools(tools))  # type: ignore[attr-defined]
                usage = ModelUsage(
                    model=str(getattr(driver, "name", "driver")),
                    prompt_tokens=len(prompt.split()),
                    completion_tokens=len(str(message.get("content", "")).split()),
                    wall_ms=0,
                    estimated=True,
                )
            kind, chosen = parse_tool_call(message, tools)
            beside_call = str(message.get("content", "") or "")
        else:
            reply_text, usage = await call_responder_metered(driver, prompt)
            if wrap_up_reason is None and tool_mode == "text":
                kind, chosen = parse_tool_call({"content": reply_text, "tool_calls": []}, tools)
            else:
                kind, chosen = "answer", reply_text
        if kind == "tool":
            name, call_args = chosen
            yield ModelReply(
                text=beside_call.strip(),
                stop_reason=StopReason.TOOL_USE,
                usage=_usage_of(usage),
                turn_index=turn_index,
                step=step,
            )
            yield ToolCall(call_id=f"c{step}", tool=name, args=list(call_args), step=step)
            return
        stop = StopReason.WRAP_UP if wrap_up_reason is not None else StopReason.END_TURN
        yield ModelReply(
            text=str(chosen),
            stop_reason=stop,
            usage=_usage_of(usage),
            turn_index=turn_index,
            step=step,
        )

    return lambda: _model


def _usage_of(usage: ModelUsage) -> dict[str, Any]:
    """ModelReply.usage: the call's ModelUsage as a plain dict."""
    return {
        "model": usage.model,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "wall_ms": usage.wall_ms,
        "estimated": usage.estimated,
    }


def _own_record() -> Path:
    """The record of the run this model step belongs to (K268: the history ticket is a range of
    it)."""
    root = api.current_record_root()
    if root is None:
        raise RuntimeError("a session model step ran outside a run; it has no record to read")
    return root


def _answer_text_from_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "no result"
    last = results[-1]
    if not last.get("ok", True):
        return f"stopped: {last.get('error', 'tool failed')}"
    return str(last.get("output", ""))


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
    driver_headroom_frac: float = 0.6,
    first_turn_user_message: "UserMessage | None" = None,
    role: str | None = None,
    role_repo_root: Path | None = None,
    parent_context: dict[str, Any] | None = None,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the session topology.

    The seed is the assembled string from the tech spec, composed by the daemon before this
    call. Producers: `model`, `tool`, `return`, `session_end`, `interrupt_fragment`, the
    `session_started` instrument, `session_prompt` when the session names a prompt source or its
    seed alone passes the driver's headroom, and `first_message` when
    `first_turn_user_message` is set. The `script` kwarg is the CI dispatch hook: a list of
    `(tool_name, args)` the model fires in order, matching `tool_loop`'s script convention;
    omit for the driver-parse path.
    """
    # `driver_name`, `workspace_path`, `parent_session_id`, `parent_seq_at_call` are
    # placeholders on the daemon's call-site contract; sprint 213/217/225 bind them.
    # They ride the signature so the outer daemon does not shift when they wire up.

    def _step_of(ctx: Any) -> int:
        # `step` rides ToolResult. Absent means the first model call of a turn
        # (`model-on-user-message`): step 0. An earlier default of `turn_max_steps` routed a
        # missing step to wrap-up by accident.
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

    def _prompt_input(ctx: Any) -> dict[str, Any]:
        """What the model step builds a prompt from (K268): the session's prompt fragments, and a
        ticket to the history it keeps — the seq range of this record's newest turns that fit,
        chosen here from the turn sizes the history view keeps — plus the dropped range, for the
        TranscriptCompacted the model step records. The ticket names no path: it is recorded,
        and a recorded path would tie the record's bytes to where it sits."""
        fragments = list(ctx.views["fragment_cohort"].value())
        turns = ctx.views["turn_history"].value()
        if not turns:
            return {"fragments": fragments, "history_ref": None}
        head_text, _seqs = head_block(seed, per_turn, fragments)
        head_tokens = _est_tokens(head_text)
        keep = plan_window(
            [cost for _a, _b, cost in turns],
            head_tokens,
            driver_context_tokens,
            driver_headroom_frac,
        )
        dropped = [turns[0][0], turns[keep][0] - 1] if keep > 0 else None
        return {
            "fragments": fragments,
            "history_ref": {
                "from_seq": turns[keep][0],
                "to_seq": int(ctx.event.seq),
                "dropped": dropped,
                "tokens_before": head_tokens + sum(cost for _a, _b, cost in turns),
            },
        }

    def _continue_input(ctx: Any, *, final: bool) -> dict[str, Any]:
        # Sprint 047: pass this turn's ToolResults only, not the session-wide
        # buffer. The `results` view (KindBuffer of ToolResult) accumulates
        # every result for the life of the session, so a failed turn's
        # trailing_fails counter carried into the next turn — a session
        # with 3 failed bash calls in turn 2 tripped anti-spin on turn 3's
        # first attempt. Fix: `step` reflects THIS turn's next firing (0
        # after model-on-user-message, 1 after the first ToolResult, ...); the
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
            **_prompt_input(ctx),
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
            schemas=[
                ToolCall,
                ModelReply,
                TranscriptCompacted,
                BackgroundTaskEnded,
                PromptComposed,
            ],
            schema_version=1,
            factory=_model_factory(
                driver=driver,
                per_turn=per_turn,
                script=script,
                seed=seed,
                driver_context_tokens=driver_context_tokens,
                driver_headroom_frac=driver_headroom_frac,
                tools=tools,
                session_id=session_id,
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
            PRODUCER_KIND_RETURN,
            schemas=[Returned],
            schema_version=1,
            factory=_return_factory(),
            deterministic=True,
        )
        b.producer_kind(
            PRODUCER_KIND_SESSION_END,
            schemas=[SessionEnded],
            schema_version=1,
            factory=_session_end_factory(),
            deterministic=True,
        )
        b.view("results", api.KindBuffer(TOOL_RESULT))
        b.view("user_turns", api.KindCount(USER_MESSAGE))
        b.view("returned_turns", api.KindCount(RETURNED))
        # FragmentCohort: the session-open fragments (one slot per source) and any turn-scoped
        # fragment (an interrupt directive, cleared on the next PromptComposed). The model
        # triggers pass its value as the step's `fragments`.
        b.view("fragment_cohort", FragmentCohort())
        # K263: one `session_prompt` producer runs every session-open prompt source and the
        # seed-size check. It runs only when the session names a source or the seed alone passes
        # the driver's headroom (the 0.6 the history window also uses).
        seed_tokens = _est_tokens(seed) + _est_tokens(per_turn)
        seed_warning = (
            SessionWarning(
                session_id=session_id,
                kind=SessionWarningKind.SEED_ALONE_EXCEEDS,
                seed_tokens=seed_tokens,
                driver_context_tokens=driver_context_tokens,
            )
            if seed_tokens > int(driver_context_tokens * 0.6)
            else None
        )
        sources = session_prompt_sources(
            role=role,
            role_repo_root=role_repo_root,
            bundle=bundle,
            parent_context=parent_context,
            tools=tools,
        )
        has_session_prompt = bool(sources) or seed_warning is not None
        if has_session_prompt:
            b.producer_kind(
                PRODUCER_KIND_SESSION_PROMPT,
                schemas=[PromptFragment, SessionWarning],
                schema_version=1,
                factory=session_prompt_producer_factory(
                    session_id=session_id, sources=sources, seed_warning=seed_warning
                ),
                deterministic=True,
            )
            b.initial(PRODUCER_KIND_SESSION_PROMPT, input={})
        if first_turn_user_message is not None:
            b.producer_kind(
                PRODUCER_KIND_FIRST_MESSAGE,
                schemas=[UserMessage],
                schema_version=1,
                factory=_first_message_factory(first_turn_user_message),
                deterministic=True,
            )
            if has_session_prompt:
                # The first message waits for the session prompt, so the first model call's
                # prompt has its fragments (K261: started together at RunStarted, the message
                # could land first). A failed session_prompt counts as ended.
                b.trigger(
                    TRIGGER_ID_FIRST_MESSAGE_ON_SESSION_PROMPT,
                    subscription=api.Subscription(
                        kinds=frozenset({api.PRODUCER_COMPLETED, api.PRODUCER_FAILED})
                    ),
                    # Only on a fresh record: on a resume this trigger must not fire again, or a
                    # second UserMessage would split the turn.
                    predicate=lambda ctx: (
                        _producer_kind_from_ref(ctx) == PRODUCER_KIND_SESSION_PROMPT
                        and int(ctx.views["user_turns"].value()) == 0
                    ),
                    starts=PRODUCER_KIND_FIRST_MESSAGE,
                    input_builder=lambda ctx: {},
                    policy=api.Once(),
                )
            else:
                b.initial(PRODUCER_KIND_FIRST_MESSAGE, input={})
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
        # K261: the model producer builds each prompt from the turn history (this view) instead of
        # reading the whole record from disk on every call.
        b.view("turn_history", TurnHistory(TURN_EVENT_KINDS))

        b.trigger(
            TRIGGER_ID_TOOL_ON_TOOL_CALL,
            subscription=api.Subscription(kinds=frozenset({TOOL_CALL})),
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
            TRIGGER_ID_MODEL_ON_TOOL_RESULT,
            subscription=api.Subscription(kinds=frozenset({TOOL_RESULT})),
            # A pending interrupt fragment reaches the model on this step: the model builds its
            # prompt from the fragment cohort (K261).
            predicate=lambda ctx: _step_of(ctx) + 1 < turn_max_steps,
            starts=PRODUCER_KIND_MODEL,
            input_builder=lambda ctx: _continue_input(ctx, final=False),
            policy=api.PerEvent(),
        )
        b.trigger(
            TRIGGER_ID_MODEL_WRAP_UP_ON_TOOL_RESULT,
            subscription=api.Subscription(kinds=frozenset({TOOL_RESULT})),
            predicate=lambda ctx: _step_of(ctx) + 1 >= turn_max_steps,
            starts=PRODUCER_KIND_MODEL,
            input_builder=lambda ctx: _continue_input(ctx, final=True),
            policy=api.PerEvent(),
        )

        # K262: one Returned per turn. A hard interrupt can cancel the model and a tool at once,
        # and a failure can race a reply; each return trigger fires only while the turn has none.
        def _turn_open(ctx: Any) -> bool:
            return int(ctx.views["returned_turns"].value()) < int(ctx.views["user_turns"].value())

        b.trigger(
            TRIGGER_ID_RETURN_ON_REPLY,
            subscription=api.Subscription(kinds=frozenset({MODEL_REPLY})),
            predicate=lambda ctx: (
                ctx.event.payload.get("stop_reason") != StopReason.TOOL_USE and _turn_open(ctx)
            ),
            starts=PRODUCER_KIND_RETURN,
            input_builder=lambda ctx: {
                "turn_index": _turn_index(ctx),
                "reason": ReturnReason.REPLIED,
            },
            policy=api.PerEvent(),
        )
        b.trigger(
            TRIGGER_ID_RETURN_ON_MODEL_ERROR,
            subscription=api.Subscription(kinds=frozenset({api.PRODUCER_FAILED})),
            predicate=lambda ctx: (
                _producer_kind_from_ref(ctx) == PRODUCER_KIND_MODEL and _turn_open(ctx)
            ),
            starts=PRODUCER_KIND_RETURN,
            input_builder=lambda ctx: {
                "turn_index": _turn_index(ctx),
                "reason": ReturnReason.MODEL_ERROR,
                # ProducerFailed carries the exception text under `error`; it names the cause.
                "detail": str((ctx.event.payload or {}).get("error", "")),
            },
            policy=api.PerEvent(),
        )
        b.trigger(
            TRIGGER_ID_RETURN_ON_INTERRUPT,
            subscription=api.Subscription(kinds=frozenset({api.PRODUCER_CANCELLED})),
            # A hard interrupt during a tool call cancels the tool, not the model; the turn ends
            # either way (lens F093: it used to end only when the model was cancelled).
            predicate=lambda ctx: (
                _producer_kind_from_ref(ctx) in (PRODUCER_KIND_MODEL, PRODUCER_KIND_TOOL)
                and _turn_open(ctx)
            ),
            starts=PRODUCER_KIND_RETURN,
            input_builder=lambda ctx: {
                "turn_index": _turn_index(ctx),
                "reason": ReturnReason.INTERRUPTED,
            },
            policy=api.PerEvent(),
        )
        # K261: a UserMessage starts the model, which builds and records its own prompt.
        b.trigger(
            TRIGGER_ID_MODEL_ON_USER_MESSAGE,
            subscription=api.Subscription(kinds=frozenset({USER_MESSAGE})),
            predicate=lambda ctx: True,
            starts=PRODUCER_KIND_MODEL,
            input_builder=lambda ctx: {
                "step": 0,
                "results": [],
                "final": False,
                "turn_index": _turn_index(ctx),
                **_prompt_input(ctx),
            },
            policy=api.PerEvent(),
        )
        # Phase 8 item 7: an InterruptRequested the daemon wrote (Runtime.inject_event) starts the
        # interrupt fragment producer; the model reads the fragment on its next step, beside the
        # tool result.
        b.trigger(
            TRIGGER_ID_INTERRUPT_FRAGMENT_ON_INTERRUPT_REQUEST,
            subscription=api.Subscription(kinds=frozenset({INTERRUPT_REQUESTED})),
            predicate=lambda ctx: True,
            starts=PRODUCER_KIND_INTERRUPT_FRAGMENT,
            input_builder=lambda ctx: {
                "tier": ctx.event.payload.get("tier", ""),
                "source": ctx.event.payload.get("source", ""),
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
            # end-on-turn-cap fires when the (max_turns + 1)th UserMessage arrives: max_turns turns
            # complete, and the next attempt ends the session (tech spec §3: the 201st turn for
            # max_turns=200). `>= max_turns` would end it before the last allowed turn ran. The
            # reason was "timeout" before K264; the cap counts turns, not time.
            TRIGGER_ID_END_ON_TURN_CAP,
            subscription=api.Subscription(kinds=frozenset({USER_MESSAGE})),
            predicate=lambda ctx: int(ctx.views["user_turns"].value()) > max_turns,
            starts=PRODUCER_KIND_SESSION_END,
            input_builder=lambda ctx: {
                "reason": SessionEndReason.TURN_CAP,
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
            TRIGGER_ID_END_ON_END_REQUEST,
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
                when=lambda tctx: tctx.event is not None and tctx.event.kind == RETURNED,
                resume_condition=USER_MESSAGE,
            ),
            # Not threshold_count(SESSION_ENDED, 1): a resume restores counts from the whole
            # record, so an ended-then-resumed session would finalise on its next event.
            api.finalise_on(SESSION_ENDED),
        )
        _refuse_all_completed(termination)
        b.termination(termination)

    return topo


# `SessionEndRequested` and `InterruptRequested` appear in no `producer_kind(schemas=[...])`
# above: the daemon writes them to the record. A `UserMessage` arrives as a resume event, or
# from `first_message` on a fresh record.

# ToolCall / ToolResult are borrowed from `tool_loop` so the session reuses tool_loop's tool seam
# verbatim (product spec §4). FinalAnswer is re-exported for readers of records written before
# v0.3; the session no longer writes it. The imports live below the
# session Structs so the file reads top-down: session's own vocabulary first, then
# the tool_loop borrow. tool_loop's schemas are already frozen msgspec Structs.
from ..tool_loop import FinalAnswer, ToolCall, ToolResult  # noqa: E402
from .interrupt_fragment_producer import (  # noqa: E402  # phase 8 item 7
    interrupt_fragment_producer_factory,
)
from .session_prompt_producer import (  # noqa: E402
    session_prompt_producer_factory,
    session_prompt_sources,
)
from .transcript import (  # noqa: E402
    TURN_EVENT_KINDS,
    TranscriptCompacted,
    _est_tokens,
    compose_model_prompt,
    head_block,
    plan_window,
    resolve_driver_context_tokens,
)
from .views import (  # noqa: E402
    FragmentCohort,
    TurnHistory,
    producer_kind_from_lifecycle_payload,
)

__all__ = [
    "BackgroundTaskEnded",
    "FinalAnswer",
    "ModelReply",
    "Park",
    "Returned",
    "PromptComposed",
    "PromptFragment",
    "SessionEnded",
    "SessionEndRequested",
    "InterruptRequested",
    "SessionStarted",
    "SessionWarning",
    "ToolCall",
    "ToolResult",
    "TranscriptCompacted",
    "UserMessage",
    "resolve_driver_context_tokens",
    "session_topology",
]

# spec-audit: 2026-09-01

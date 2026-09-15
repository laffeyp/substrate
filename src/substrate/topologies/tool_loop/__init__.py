# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Tool-using loop topology — the classic model -> tool -> model agent loop (Wave 14).

A `model` Producer reads the task and the tool results so far and emits EITHER a `ToolCall`
(it wants a tool run) OR a `FinalAnswer` (it is done). A Trigger fires the named `tool`
Producer on each ToolCall; the `ToolResult` re-fires the model with that result appended —
the loop the whole "AI agent with tools" idea is built on, except the loop, the history, and
the replay are the runtime's job, not yours. Each model call and each tool call is its own
Producer instantiation, so every step is independently inspectable and replayable on the log.

Two properties this follows from real agent harnesses (opencode's `tool.ts` / `max-steps.ts`),
both of which fall out naturally in the substrate's typed-event model:

  - A failed tool is an OBSERVATION, not a crash. An unknown tool, a bad call, or a non-encodable
    result emits a typed `ToolResult` with `ok=False` and an `error` the model reads and reacts to —
    never an uncaught exception. (The substrate's own R-2 reference topology is the same discipline:
    a structured error on the log, then recovery.)
  - The step budget ends gracefully. At `max_steps` the loop fires the model once more with
    tools disabled (`final=True`) so the run ALWAYS ends on a `FinalAnswer`, never a silent
    quiescence stop — opencode's MAX_STEPS behavior.

CI: a deterministic scripted model — a tiny calculator agent computing (2 + 3) * 4 with `add`
and `mul` tools — pure and reproducible, so it ships a committed record. `walkthrough=True`
swaps in a real local LLM deciding via a one-line TOOL/ANSWER reply convention.

Extensions, both native to the substrate (not built here, but the shape is one Trigger away):
  - PARALLEL tool calls: a model turn emitting N ToolCalls starts N tool Producers concurrently;
    gather them with a count predicate (`KindCount`) before the continue fires — the substrate's
    concurrency is the point, where a sequential agent loop would run them one at a time.
  - HUMAN-IN-THE-LOOP: gate a side-effecting tool behind `pause_await_input` (the R-2 mechanism)
    so an irreversible action waits for approval before it runs.
  - SIDE-EFFECTING tools (real search / code-exec / HTTP) are non-deterministic: set the tool
    Producer `deterministic=False` (like `coding_flow`'s real gate). The run still produces a
    replayable record; it just is not byte-identical re-execution.

These are worked out as topology sketches in `docs/tool-loop/tool-loop-futures.md`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from typing import Any

from msgspec import Struct

from ... import api
from ...encoding import canonical_bytes
from ...adapters import Responder, call_responder
from .tools import CALCULATOR, Tool, ollama_tools, parse_tool_call, required_params, suite_describe

_Factory = Callable[[], Any]
_MAX_RESULT_BYTES = 12_000  # cap a tool output well under the 16 KiB blob-offload threshold (below)
_MAX_CONSECUTIVE_FAILS = 3  # a real model gets room to self-correct; bail if it is clearly stuck

# Loop discipline handed to the model every turn — adapted (in our own words) from best-in-class
# agent-loop prompts and sharpened on the substrate's spine (decide from the observed record; a failed
# result is information not a wall; "written" is not "working").
# HONEST NOTE (R-10, A/B-verified 2026-07-02): as an AGENTIC LEVER this prose is INERT — kimi-k2.6
# verified its own code with OR without it, and qwen ignored it either way. What actually kills the
# write-spin is the STRUCTURAL guard in `_tool_factory` (errors-as-observations on the record), not
# this text. Kept only as the cheap generative-escape carrier (the poem-refusal fix) and low-cost
# guidance; it is NOT a proven behavioural lever, so do not claim it drives anything.
_LOOP_DISCIPLINE = (
    "Work the task one step at a time. Each turn, read the results above — they are the record of "
    "what has actually happened — and choose your next move from that, not from what you meant to do:\n"
    "- If an action already succeeded above, it is done. Do not repeat it — move on: read, run, or edit.\n"
    "- A failed result (ok=false) is information, not a wall: read the error and correct your next call.\n"
    "- Writing code is not the same as it working. After you create or change code, RUN it and read "
    "the real output before you call anything done.\n"
    "- Report what actually happened, failures included; do not claim success you have not observed.\n"
    "- A purely generative ask (write a poem, explain, converse) needs no tool — just answer.\n"
    "- When the task is done and verified, stop and give a concise final answer."
)

# The tool registry lives in tools.py — PURE (the calculator) for the deterministic CI demo, plus
# the real READ-ONLY and WRITE/EXEC suite a real agent passes in. CALCULATOR is the default so the
# committed record stays byte-stable; a real run passes FULL_SUITE (deterministic=False). The suite
# design is grounded in the source of opencode / Cline / aider — see docs/tool-loop/tool-loop-tool-suite.md.


class ToolCall(Struct, frozen=True):
    call_id: str
    tool: str
    args: list[Any]  # ints for the calculator; strings (paths, patterns) for the real suite
    step: int


class ToolResult(Struct, frozen=True):
    call_id: str
    tool: str
    output: Any  # int / str / list / dict — whatever the tool returns (RFC-8785-encodable)
    step: int
    ok: bool = True
    error: str = ""


class FinalAnswer(Struct, frozen=True):
    text: str
    steps: int


def _last_bash_nonzero(results: list[dict[str, Any]]) -> bool:
    """True if the most recent `bash` the agent RAN exited non-zero — the last thing it ran FAILED.
    Externalizes the verify POLICY the model may not hold (R-11a: deepseek-v4-pro ran its code, got
    exit 1 twice, then declared 'proven working'). The harness reads the record's real exit code and
    refuses to let a 'done' answer launder an unverified failure. NB: the live view yields the tool
    output as a `mappingproxy` (sealed record state), not a plain dict — check `Mapping`, not `dict`."""
    for r in reversed(results):
        if r.get("tool") == "bash" and r.get("ok", True):
            out = r.get("output")
            return isinstance(out, Mapping) and int(out.get("exit", 0) or 0) != 0
    return False


def _answer_text(results: list[dict[str, Any]]) -> str:
    """The model's final text: the last successful output, or a note that there isn't one."""
    return (
        str(results[-1].get("output", ""))
        if results and results[-1].get("ok", True)
        else "no result"
    )


def _model_factory(
    responder: Responder | None,
    walkthrough: bool,
    script: list[tuple[str, list[Any]]] | None,
    tools: dict[str, Tool],
    task: str,
) -> _Factory:
    async def model(inp: Any) -> AsyncIterator[ToolCall | FinalAnswer]:
        step = int(inp.get("step", 0)) if hasattr(inp, "get") else 0
        results = list(inp.get("results", [])) if hasattr(inp, "get") else []
        final = bool(inp.get("final", False)) if hasattr(inp, "get") else False
        # budget wrap-up: tools are disabled, the model must answer (opencode MAX_STEPS pattern).
        if final:
            yield FinalAnswer(text=_answer_text(results), steps=step)
            return
        # a failed tool is an OBSERVATION the model can act on — not a hard wall (that would contradict
        # the loop discipline and neuter the anti-spin guard into a halt). The deterministic/default
        # path (no real model to reason) stops on the first failure. A real model in WALKTHROUGH gets
        # room to react — correct the call, or heed the anti-spin corrective and verify — but if it is
        # clearly STUCK (a RUN of consecutive failures: it keeps re-issuing a refused write, as
        # qwen3-coder:480b did on the arena's hangman build), the loop bails with a truthful report
        # rather than flailing to the step budget and answering "no result".
        trailing_fails = 0
        for r in reversed(results):
            if r.get("ok", True):
                break
            trailing_fails += 1
        if trailing_fails and (not walkthrough or trailing_fails >= _MAX_CONSECUTIVE_FAILS):
            yield FinalAnswer(
                text=f"stopped after {trailing_fails} failed tool call(s): "
                f"{results[-1].get('error', 'tool failed')}",
                steps=step,
            )
            return
        if walkthrough and responder is not None:
            achat = getattr(responder, "achat_tools", None)
            if callable(achat):
                # native tool-calling: hand the model the tool SCHEMAS + the task + the results so
                # far, and parse its reply ROBUSTLY — native `tool_calls` OR a JSON call in `content`
                # (parse_tool_call, verified against real llama/qwen output). String args + variable
                # arity fall out of the named-args schema, not the calculator's two-int convention.
                progress = [
                    {"tool": r.get("tool"), "ok": r.get("ok", True), "output": r.get("output", "")}
                    for r in results
                ]
                prompt = f"{task}\n\nTool results so far, in order: {progress}\n{_LOOP_DISCIPLINE}"
                kind, chosen = parse_tool_call(await achat(prompt, ollama_tools(tools)), tools)
                if kind == "tool":
                    name, call_args = chosen
                    yield ToolCall(call_id=f"c{step}", tool=name, args=list(call_args), step=step)
                    return
                # R-11a: refuse a "done" answer when the last thing the agent RAN exited non-zero —
                # externalize the verify policy the model may not hold. Re-prompt ONCE, firmly; if it
                # then calls a tool, the loop continues; if it STILL insists, let it answer but mark the
                # claim [unverified] so the record can't launder "proven working" over a failed run.
                if _last_bash_nonzero(results):
                    firm = (
                        f"{prompt}\n\nDO NOT answer yet. Your last bash command exited NON-ZERO — you "
                        "have NOT verified success. Call a tool to fix the problem and re-run it."
                    )
                    kind2, chosen2 = parse_tool_call(await achat(firm, ollama_tools(tools)), tools)
                    if kind2 == "tool":
                        name, call_args = chosen2
                        yield ToolCall(
                            call_id=f"c{step}", tool=name, args=list(call_args), step=step
                        )
                        return
                    yield FinalAnswer(
                        text=f"[unverified — last run exited non-zero] {chosen2}", steps=step
                    )
                    return
                yield FinalAnswer(text=str(chosen), steps=step)
                return
            # fallback — a text Responder with no native tools-chat: a CLI model (CliResponder:
            # claude/gemini/any command-line model) or any prompt->text seam. DESCRIBE the tools and
            # ask for a JSON tool call OR a final answer, then parse robustly (parse_tool_call handles
            # a JSON object anywhere in the reply). Substrate owns the tools, so even a plain
            # prompt->text CLI becomes a tool-using agent ON substrate — the CliResponder path.
            progress = [
                {"tool": r.get("tool"), "ok": r.get("ok", True), "output": r.get("output", "")}
                for r in results
            ]
            prompt = (
                f"{task}\n\nTools you MAY use:\n{suite_describe(tools)}\n"
                f"Tool results so far, in order: {progress}\n{_LOOP_DISCIPLINE}\n"
                'Reply with EITHER a single JSON object {"name": "<tool>", "arguments": {...}} to '
                "call a tool, OR your final answer as plain text. Output only one of those."
            )
            reply = await call_responder(responder, prompt)
            kind, chosen = parse_tool_call({"content": reply, "tool_calls": []}, tools)
            if kind == "tool":
                name, call_args = chosen
                yield ToolCall(call_id=f"c{step}", tool=name, args=list(call_args), step=step)
            else:
                yield FinalAnswer(text=str(chosen), steps=step)
            return
        # deterministic CI policy: a custom action script (a test hook, like recursive's `runaway`
        # or conversation's `converge_at`) or the default calculator agent.
        if script is not None:
            if step < len(script):
                tool, args = script[step]
                yield ToolCall(call_id=f"c{step}", tool=tool, args=list(args), step=step)
            else:
                yield FinalAnswer(text=_answer_text(results), steps=step)
            return
        # default calculator: (2 + 3) * 4 — calls `add`, then `mul` USING THE FIRST RESULT, then
        # answers, so it exercises the result-fed-back-in path, not a script blind to the tools.
        if step == 0:
            yield ToolCall(call_id="c0", tool="add", args=[2, 3], step=0)
        elif step == 1:
            yield ToolCall(call_id="c1", tool="mul", args=[results[-1].get("output", 0), 4], step=1)
        else:
            yield FinalAnswer(text=str(results[-1].get("output", "")), steps=step)

    return lambda: model


def _tool_factory(tools: dict[str, Tool]) -> _Factory:
    # SDD anti-spin (arena finding, 2026-07-02): a strong model, told in-prompt not to, still re-wrote
    # the SAME file 16x in a row without ever running it. A prompt is a request; the LOOP can enforce.
    # Two CONSECUTIVE write_files to the same file with no run/read between is a redundant action — the
    # second becomes a typed ToolResult(ok=False) telling the model to verify (bash/read) before
    # rewriting. Errors-as-observations on the record, not exhortation the model can ignore.
    # `prev_write` persists across firings (the factory is instantiated once per run); the CI
    # calculator never writes, so committed records stay byte-identical.
    state: dict[str, str | None] = {"prev_write": None}

    async def run_tool(inp: Any) -> AsyncIterator[ToolResult]:
        tool = str(inp.get("tool")) if hasattr(inp, "get") else ""
        args = list(inp.get("args", [])) if hasattr(inp, "get") else []
        call_id = str(inp.get("call_id", "?")) if hasattr(inp, "get") else "?"
        step = int(inp.get("step", 0)) if hasattr(inp, "get") else 0
        prev_write = state["prev_write"]
        state["prev_write"] = (
            None  # any action other than a fresh successful write breaks the streak
        )
        entry = tools.get(tool)
        if entry is None:
            # unknown tool -> a typed failure the model reads, NOT a crash.
            yield ToolResult(
                call_id=call_id,
                tool=tool,
                output="",
                step=step,
                ok=False,
                error=f"unknown tool '{tool}'",
            )
            return
        missing = required_params(tool, tools)[len(args) :]
        if missing:
            # under-specified call (model supplied too few args) -> a CLEAR typed error it can act on,
            # not the raw IndexError the tool body would throw (surfaced by a live llama3.2:1b run).
            yield ToolResult(
                call_id=call_id,
                tool=tool,
                output="",
                step=step,
                ok=False,
                error=f"{tool}: missing required argument(s): {', '.join(missing)}",
            )
            return
        if tool == "write_file" and args and Path(str(args[0])).name == prev_write:
            # a SECOND consecutive write to the same file, with no run/read between — a spin. Do not
            # write again; hand back a typed observation that redirects to verification.
            yield ToolResult(
                call_id=call_id,
                tool=tool,
                output="",
                step=step,
                ok=False,
                error=(
                    f"you already wrote {prev_write} and have not run or read it — run it (bash) or "
                    "read it to verify before writing it again"
                ),
            )
            state["prev_write"] = (
                prev_write  # keep the marker so a 3rd consecutive write is caught too
            )
            return
        try:
            # Phase 8 item 5 · unblock the interrupt path. Tool bodies do
            # blocking work — subprocess.run for `bash`, filesystem walks
            # for `read_file`/`grep`. Calling them on the loop pins it for
            # the duration; while pinned, `SessionRegistry.interrupt` cannot
            # reach `runtime.cancel_producer` because its
            # `call_soon_threadsafe` closure never gets a slice, its 1s
            # future times out, and the daemon returns `{interrupted:
            # false}`. Running the body in a worker thread through
            # `asyncio.to_thread` releases the loop so the interrupt
            # closure lands within its 1s window. `entry.run` remains
            # synchronous; nothing about the tool contract changes.
            import asyncio as _asyncio

            output = await _asyncio.to_thread(entry.run, args)
            # pre-validate encodability so a non-RFC-8785-encodable return becomes a typed failure
            # HERE, not an emit-time crash (the yield's encode runs in the runtime, outside this try).
            raw = canonical_bytes(output)
        except (
            Exception
        ) as exc:  # bad args / not-found / IO / non-encodable output -> ok=False, no crash
            yield ToolResult(
                call_id=call_id,
                tool=tool,
                output="",
                step=step,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
            )
            return
        if len(raw) > _MAX_RESULT_BYTES:
            # keep the ToolResult INLINE (under the 16 KiB blob-offload threshold). An offloaded
            # payload strips the loop-control fields (step) off the frame AND hands the model a $blob
            # ref instead of the output — wedging the loop (a live glob over a big tree hit exactly
            # this). One general byte-cap covers every tool; the model reads a bounded notice instead.
            output = (
                f"[{tool} output was {len(raw)} bytes — too large to inline; narrow the request]"
            )
        if tool == "write_file" and args:
            state["prev_write"] = Path(str(args[0])).name  # arm the streak marker for the next call
        yield ToolResult(call_id=call_id, tool=tool, output=output, step=step, ok=True)

    return lambda: run_tool


def tool_loop_topology(
    *,
    model: Responder | None = None,
    script: list[tuple[str, list[Any]]] | None = None,
    max_steps: int = 4,
    walkthrough: bool = False,
    deterministic: bool = True,
    tools: dict[str, Tool] | None = None,
    task: str | None = None,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the tool-using loop. The `model` emits a ToolCall or a FinalAnswer; the named tool
    runs and its ToolResult re-fires the model with the result appended, until a FinalAnswer
    lands. The loop is bounded by `max_steps`: at the budget the model is fired once more with
    tools disabled so the run always ends on a FinalAnswer. A failed tool emits a typed
    ToolResult(ok=False) the model reacts to. CI uses a deterministic calculator agent (or a
    `script` of (tool, args) calls as a test hook); `walkthrough=True` swaps in a real local LLM."""

    from ...adapters import OllamaResponder

    responder = (model or OllamaResponder("llama3.2:1b")) if walkthrough else model
    # default to the PURE calculator (the byte-reproducible CI demo); a real agent passes FULL_SUITE.
    # the run is deterministic only if every tool is pure AND it is NOT the walkthrough path: a real
    # model is not author-deterministic, so a walkthrough must never be stamped deterministic in the
    # manifest (CI runs walkthrough=False, so the committed calculator record is unaffected).
    suite = tools if tools is not None else CALCULATOR
    det = deterministic and not walkthrough and all(t.deterministic for t in suite.values())

    def _step(ctx: Any) -> int:
        # the loop-control step lives on the ToolResult payload. If a tool returned something so large
        # the payload BLOB-OFFLOADED (the fields leave the frame), `step` is unreadable — default to
        # max_steps so the loop WRAPS UP cleanly (a final answer) instead of the predicate crashing and
        # quarantining (which wedges the run). Tools cap their output so this shouldn't happen; this is
        # the belt-and-braces so an oversized result can never hard-wedge the loop.
        return int(ctx.event.payload.get("step", max_steps))

    def _continue_input(ctx: Any, *, final: bool) -> dict[str, Any]:
        return {
            "step": _step(ctx) + 1,
            "results": list(ctx.views["results"].value()),
            "final": final,
        }

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "model",
            schemas=[ToolCall, FinalAnswer],
            schema_version=1,
            factory=_model_factory(
                responder, walkthrough, script, suite, task or "Use the available tools to help."
            ),
            deterministic=det,
        )
        b.producer_kind(
            "tool",
            schemas=[ToolResult],
            schema_version=1,
            factory=_tool_factory(suite),
            deterministic=det,
        )
        b.initial("model", input={"step": 0, "results": [], "final": False})
        # the running transcript of tool results — the model reads it to decide the next step
        # (the full structured result is on the log; the model is handed exactly this).
        b.view("results", api.KindBuffer("ToolResult"))
        # each ToolCall runs its tool.
        b.trigger(
            "run-tool",
            subscription=api.Subscription(kinds=frozenset({"ToolCall"})),
            predicate=lambda ctx: True,
            starts="tool",
            input_builder=lambda ctx: {
                "call_id": ctx.event.payload["call_id"],
                "tool": ctx.event.payload["tool"],
                "args": list(ctx.event.payload["args"]),
                "step": int(ctx.event.payload["step"]),
            },
            policy=api.PerEvent(),
        )
        # within budget: each ToolResult re-fires the model with the result appended.
        b.trigger(
            "continue",
            subscription=api.Subscription(kinds=frozenset({"ToolResult"})),
            predicate=lambda ctx: _step(ctx) + 1 < max_steps,
            starts="model",
            input_builder=lambda ctx: _continue_input(ctx, final=False),
            policy=api.PerEvent(),
        )
        # at the budget: fire the model once more with tools disabled so the run ends on a
        # FinalAnswer rather than a silent quiescence stop (the bound is on the log).
        b.trigger(
            "wrap-up",
            subscription=api.Subscription(kinds=frozenset({"ToolResult"})),
            predicate=lambda ctx: _step(ctx) + 1 >= max_steps,
            starts="model",
            input_builder=lambda ctx: _continue_input(ctx, final=True),
            policy=api.PerEvent(),
        )
        # end the instant the model answers; quiescence backstops a wedged Producer.
        b.termination(
            api.any_of(
                api.threshold_count("FinalAnswer", 1),
                api.quiescence_with_watchdog(seconds=1),
            )
        )

    return topo

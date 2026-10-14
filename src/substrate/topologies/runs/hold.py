# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The caller's hold on its runs (kernel sprint 330; session vocabulary § Z.1, research r9 § 4).

A run started by a session belongs to that session. `RunTable.start` runs it on its own event loop in
a worker thread and returns at once. When the run is started from inside the caller's tool, its
`TopologyRunStarted` is posted into the caller's record then, with the seq of the `ToolCall` that
started it. When the run ends, the caller's next model step writes `TopologyRunEnded` and tells the
model once, as it does for a background command (`BackgroundTaskEnded`). The caller can stop a run:
its session is asked to end, and ends with reason `caller_stop`. Ending the caller stops all of its
runs.

The caller also steps through a run's events from a seq, and replays it (the kernel's level-2 check
of every recorded decision). The caller's model reaches these through the `run` tool
(`make_run_tool`); the app reads `listing`.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import msgspec

from ... import api
from ...constants import RUN_FINALISED
from ...errors import describe_error
from ..compose.parts import main_field
from ..compose.vocabulary import RUN_STOP_REQUESTED, Plan, RunStopRequested, StopSource, kind_of
from ..compose.wire import which_end
from ..session import (
    ComposedResult,
    ReportWritten,
    SessionEndRequested,
    TopologyRunEnded,
    TopologyRunStarted,
)
from ..session.vocabulary import (
    REPORT_WRITTEN,
    SESSION_ENDED,
    RunOutcome,
    RunSession,
    SessionEndReason,
)
from ..tool_loop.kinds import TOOL_CALL
from ..tool_loop.tools import TOOL_NAME_RUN, Tool


@dataclass
class HeldRun:
    owner: str
    run_id: str
    topology: str
    sessions: list[RunSession]
    record_root: Path
    factory: Callable[[api.TopologyBuilder], None]
    loop: asyncio.AbstractEventLoop | None = None
    runtime: Any = None
    done: threading.Event = field(default_factory=threading.Event)  # set when it has ended
    error: str = ""
    reported: bool = False
    # Session vocabulary § AA: a composed run carries its plan; it has no sessions of its own.
    plan: Plan | None = None


def _caller_call_seq() -> tuple[Any, int] | None:
    """The caller's runtime and the seq of the ToolCall whose tool is running now, when this runs
    inside a caller's tool; None outside one."""
    from ...kernel.runtime import _CURRENT_RUNTIME
    from ..tool_loop.tools import _BASH_PROGRESS_CTX

    runtime = _CURRENT_RUNTIME.get()
    call = _BASH_PROGRESS_CTX.get()
    root = api.current_record_root()
    if runtime is None or call is None or root is None:
        return None
    call_id = call[0]
    seq = -1
    for env in api.read_record(root):
        if env.get("kind") == TOOL_CALL and (env.get("payload") or {}).get("call_id") == call_id:
            seq = int(env["seq"])
    return runtime, seq


class RunTable:
    """The runs each session holds, by owner session id."""

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, HeldRun]] = {}
        self._lock = threading.Lock()

    def start(
        self,
        owner: str,
        run_id: str,
        topology: str,
        sessions: list[RunSession],
        factory: Callable[[api.TopologyBuilder], None],
        record_root: Path,
        plan: Plan | None = None,
    ) -> HeldRun:
        """Start the run and return at once. Posts `TopologyRunStarted` into the caller's record when
        called from inside the caller's tool. A composed run passes its `plan` (§ AA)."""
        held = HeldRun(
            owner=owner,
            run_id=run_id,
            topology=topology,
            sessions=sessions,
            record_root=Path(record_root),
            factory=factory,
            plan=plan,
        )
        with self._lock:
            runs = self._runs.setdefault(owner, {})
            if run_id in runs:
                raise ValueError(f"session {owner!r} already holds a run {run_id!r}")
            runs[run_id] = held
        self._run_on_thread(held, lambda runtime: runtime.run(factory, name=topology))
        caller = _caller_call_seq()
        if caller is not None:
            runtime, call_seq = caller
            started = TopologyRunStarted(
                run_id=run_id, topology=topology, call_seq=call_seq, sessions=sessions
            )
            runtime._loop.call_soon_threadsafe(runtime.inject_event, started)  # noqa: SLF001 — as emit_tool_progress
        return held

    @staticmethod
    def _run_on_thread(held: HeldRun, body: Callable[[Any], Any]) -> None:
        """Run `body(runtime)` on a fresh event loop in a worker thread; return once it is live."""
        ready = threading.Event()
        held.done.clear()

        def worker() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            runtime = api.Runtime(held.record_root)
            held.loop, held.runtime = loop, runtime
            ready.set()
            try:
                loop.run_until_complete(body(runtime))
            except BaseException as exc:  # noqa: BLE001 — carried to the caller as the run's failure
                held.error = describe_error(exc)
            finally:
                loop.close()
                held.done.set()

        threading.Thread(target=worker, name=f"run-{held.run_id}", daemon=True).start()
        ready.wait(5.0)

    def _get(self, owner: str, run_id: str) -> HeldRun:
        with self._lock:
            held = self._runs.get(owner, {}).get(run_id)
        if held is None:
            raise KeyError(f"session {owner!r} holds no run {run_id!r}")
        return held

    def running(self, owner: str, run_id: str) -> bool:
        return not self._get(owner, run_id).done.is_set()

    def stop(self, owner: str, run_id: str, source: StopSource = StopSource.CALLER_STOP) -> None:
        """Ask the run's session to end; it ends with reason `caller_stop`. A composed run is sent
        `RunStopRequested` and finalises at it (§ AA.3)."""
        held = self._get(owner, run_id)
        if held.done.is_set() or held.loop is None or held.loop.is_closed():
            return
        request: Any = (
            RunStopRequested(source=source)
            if held.plan is not None
            else SessionEndRequested(
                session_id=held.sessions[0].session_id, source=SessionEndReason.CALLER_STOP
            )
        )
        try:
            held.loop.call_soon_threadsafe(held.runtime.inject_event, request)
        except RuntimeError:  # the run's loop closed as we asked: it had ended
            pass

    def wait(self, owner: str, run_id: str, timeout: float | None = None) -> TopologyRunEnded:
        """Block until the run ends, then its end (an agent step waits on its run this way). Its end
        is still told to the caller once, as every run's is."""
        held = self._get(owner, run_id)
        held.done.wait(timeout)
        return self._ended(held)

    def events(
        self, owner: str, run_id: str, from_seq: int = 0, limit: int = 50
    ) -> list[dict[str, Any]]:
        """The run's events in order from `from_seq`, at most `limit`: seq, kind and payload."""
        held = self._get(owner, run_id)
        out: list[dict[str, Any]] = []
        for env in api.read_record(held.record_root, resolve_blobs=True):
            if int(env["seq"]) < from_seq:
                continue
            out.append({"seq": env["seq"], "kind": env["kind"], "payload": env.get("payload")})
            if len(out) >= limit:
                break
        return out

    def replay(self, owner: str, run_id: str) -> dict[str, Any]:
        """The kernel's level-2 replay of the run's record: every recorded decision checked by hash."""
        held = self._get(owner, run_id)
        result = api.replay(held.record_root, "2")
        return {
            "frame_count": result.frame_count,
            "complete": result.complete,
            "decisions_verified": result.decisions_verified,
            "mismatches": [m.seq for m in result.mismatches],
        }

    def stop_owner(self, owner: str) -> int:
        """Stop every running run `owner` holds; returns how many."""
        with self._lock:
            runs = list(self._runs.get(owner, {}).values())
        stopped = 0
        for held in runs:
            if not held.done.is_set():
                self.stop(owner, held.run_id)
                stopped += 1
        return stopped

    def listing(self, owner: str) -> list[dict[str, Any]]:
        """`owner`'s runs in start order: id, topology, sessions, whether each runs, and the outcome
        of one that ended. Reading it reports nothing: `drain_ended` still tells
        the caller's model once."""
        with self._lock:
            runs = list(self._runs.get(owner, {}).values())
        out: list[dict[str, Any]] = []
        for held in runs:
            ended = held.done.is_set()
            out.append(
                {
                    "run_id": held.run_id,
                    "topology": held.topology,
                    "sessions": [msgspec.to_builtins(s) for s in held.sessions],
                    "running": not held.done.is_set(),
                    "outcome": self._ended(held).outcome.value if ended else None,
                }
            )
        return out

    def drain_ended(self, owner: str) -> list[TopologyRunEnded]:
        """Each of `owner`'s runs that ended and has not been reported, once."""
        with self._lock:
            runs = list(self._runs.get(owner, {}).values())
        out: list[TopologyRunEnded] = []
        for held in runs:
            if held.reported or not held.done.is_set():
                continue
            held.reported = True
            out.append(self._ended(held))
        return out

    def _ended(self, held: HeldRun) -> TopologyRunEnded:
        if held.plan is not None:
            return self._composed_end(held, held.plan)
        report: ReportWritten | None = None
        report_seq: int | None = None
        stopped = False
        try:
            events = list(api.read_record(held.record_root, resolve_blobs=True))
        except Exception:  # noqa: BLE001 — an unreadable record is a failed run, said so below
            events = []
        for env in events:
            if env.get("kind") == REPORT_WRITTEN:
                report = msgspec.convert(env["payload"], ReportWritten)
                report_seq = int(env["seq"])
            elif (
                env.get("kind") == SESSION_ENDED
                and (env.get("payload") or {}).get("reason") == SessionEndReason.CALLER_STOP
            ):
                stopped = True
        if report is not None:
            outcome = report.outcome
        elif stopped:
            outcome = RunOutcome.STOPPED
        else:
            outcome = RunOutcome.FAILED
        return TopologyRunEnded(
            run_id=held.run_id,
            topology=held.topology,
            outcome=outcome,
            report_seq=report_seq,
            report=report,
        )

    def _composed_end(self, held: HeldRun, plan: Plan) -> TopologyRunEnded:
        """A composed run's end (§ AA.4): which end held, its event, each step's count."""
        steps = {kind_of(s.id): s.id for s in plan.steps}
        counts: dict[str, int] = {}
        latest: dict[str, dict[str, Any]] = {}
        last: dict[str, Any] | None = None
        stopped = False
        finalised = False
        try:
            events = list(api.read_record(held.record_root, resolve_blobs=True))
        except Exception:  # noqa: BLE001 — an unreadable record is a failed run, said so below
            events = []
        for env in events:
            kind = str(env.get("kind"))
            if kind in steps:
                counts[kind] = counts.get(kind, 0) + 1
                latest[kind] = dict(env.get("payload") or {})
                last = latest[kind]
            elif kind == RUN_STOP_REQUESTED:
                stopped = True
            elif kind == RUN_FINALISED:
                # A failed run's RunFinalised names its RunFailureReason; a clean one has none.
                finalised = "reason" not in (env.get("payload") or {})
        end = which_end(plan.end, counts)
        if stopped:
            outcome = RunOutcome.STOPPED
        elif finalised and not held.error:
            outcome = RunOutcome.DONE
        else:
            outcome = RunOutcome.FAILED
        result = ComposedResult(
            ended_on=end.kind if end is not None else None,
            event=latest.get(end.kind) if end is not None else last,
            counts={steps[k]: n for k, n in counts.items()},
            record_root=str(held.record_root),
        )
        return TopologyRunEnded(
            run_id=held.run_id,
            topology=held.topology,
            outcome=outcome,
            report_seq=None,
            report=None,
            result=result,
        )


# A run's words can be its whole output (a review), so the notice carries them up to this length;
# past it, the notice says how to read the rest.
_NOTICE_CAP_CHARS = 4000


def run_notice(e: TopologyRunEnded) -> str:
    """What the caller's model reads about an ended run: its outcome and what it said."""
    said = ""
    if e.report is not None:
        said = e.report.reply.strip()
    elif e.result is not None:
        said = composed_said(e.result)
    if len(said) > _NOTICE_CAP_CHARS:
        said = (
            said[:_NOTICE_CAP_CHARS]
            + f"\n[cut at {_NOTICE_CAP_CHARS:,} characters; run(run_id={e.run_id!r}, "
            "action='events') reads the report]"
        )
    tail = f": {said}" if said else ""
    return f"[run {e.run_id} ({e.topology}) ended {e.outcome.value}{tail}]"


def composed_said(r: ComposedResult) -> str:
    """A composed run's end in words: which end held, the event's main field, each step's count."""
    on = f"on {r.ended_on}" if r.ended_on else "when nothing was left to run"
    text = main_field(r.event) if r.event else ""
    counts = ", ".join(f"{step} {n}" for step, n in r.counts.items()) or "no step ran"
    return f"ended {on} ({counts}); record {r.record_root}" + (f"\n{text}" if text else "")


# The process's table: one app per machine, as the background-task table.
TABLE = RunTable()

RUN_TOOL_NAME = TOOL_NAME_RUN
RUN_ACTIONS = ("stop", "events", "replay")
_RUN_TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "run_id": {"type": "string", "description": "a run this session started"},
        "action": {"type": "string", "enum": list(RUN_ACTIONS)},
        "from_seq": {"type": "integer", "description": "events: the first seq to read"},
        "limit": {"type": "integer", "description": "events: how many to read"},
    },
    "required": ["run_id", "action"],
    "x-args-passthrough": True,
}


def make_run_tool(owner: str) -> Tool:
    """The `run` tool for the session `owner`: stop, step through or replay a run it started. A
    run another session started is refused."""

    def _run(args: list[Any]) -> dict[str, Any]:
        a = dict(args[0]) if args and isinstance(args[0], dict) else {}
        run_id, action = str(a.get("run_id", "")), str(a.get("action", ""))
        if action not in RUN_ACTIONS:
            raise ValueError(f"run: action must be one of {list(RUN_ACTIONS)}; got {action!r}")
        table = TABLE
        try:
            if action == "events":
                rows = table.events(
                    owner, run_id, int(a.get("from_seq", 0)), int(a.get("limit", 50))
                )
                return {"events": rows}
            if action == "replay":
                return table.replay(owner, run_id)
            table.stop(owner, run_id)
        except KeyError as exc:
            raise ValueError(f"run: {exc.args[0]}") from exc
        return {"run_id": run_id, "action": action, "ok": True}

    return Tool(
        name=RUN_TOOL_NAME,
        describe=(
            "run(run_id, action=stop|events|replay, from_seq?, limit?): "
            "control a run this session started"
        ),
        deterministic=False,
        run=_run,
        schema=_RUN_TOOL_SCHEMA,
    )


__all__ = [
    "RUN_ACTIONS",
    "RUN_TOOL_NAME",
    "TABLE",
    "HeldRun",
    "RunTable",
    "make_run_tool",
    "run_notice",
]

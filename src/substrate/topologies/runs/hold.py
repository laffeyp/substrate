# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The caller's hold on its runs (kernel sprint 319; session vocabulary § X.2, research r8 § 3.6).

A run started by a session belongs to that session. `RunTable.start` runs it on its own event loop in
a worker thread and returns at once. When the run is started from inside the caller's tool, its
`TopologyRunStarted` is posted into the caller's record then, with the seq of the `ToolCall` that
started it. When the run ends, the caller's next model step writes `TopologyRunEnded` and tells the
model once, as it does for a background command (`BackgroundTaskEnded`). The caller can stop a run:
its session is asked to end, and ends with reason `caller_stop`. Ending the caller stops all of its
runs. Pause, resume, step and replay are K319b.
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
from ...errors import describe_error
from ..session import ReportWritten, SessionEndRequested, TopologyRunEnded, TopologyRunStarted
from ..tool_loop.kinds import TOOL_CALL
from ..session.vocabulary import (
    REPORT_WRITTEN,
    SESSION_ENDED,
    RunOutcome,
    RunSession,
    SessionEndReason,
)


@dataclass
class HeldRun:
    owner: str
    run_id: str
    topology: str
    sessions: list[RunSession]
    record_root: Path
    loop: asyncio.AbstractEventLoop | None = None
    runtime: Any = None
    done: threading.Event = field(default_factory=threading.Event)
    error: str = ""
    reported: bool = False


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
    ) -> HeldRun:
        """Start the run and return at once. Posts `TopologyRunStarted` into the caller's record when
        called from inside the caller's tool."""
        held = HeldRun(
            owner=owner,
            run_id=run_id,
            topology=topology,
            sessions=sessions,
            record_root=Path(record_root),
        )
        with self._lock:
            runs = self._runs.setdefault(owner, {})
            if run_id in runs:
                raise ValueError(f"session {owner!r} already holds a run {run_id!r}")
            runs[run_id] = held
        ready = threading.Event()

        def worker() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            runtime = api.Runtime(held.record_root)
            held.loop, held.runtime = loop, runtime
            ready.set()
            try:
                loop.run_until_complete(runtime.run(factory, name=topology))
            except BaseException as exc:  # noqa: BLE001 — carried to the caller as the run's failure
                held.error = describe_error(exc)
            finally:
                loop.close()
                held.done.set()

        threading.Thread(target=worker, name=f"run-{run_id}", daemon=True).start()
        ready.wait(5.0)
        caller = _caller_call_seq()
        if caller is not None:
            runtime, call_seq = caller
            started = TopologyRunStarted(
                run_id=run_id, topology=topology, call_seq=call_seq, sessions=sessions
            )
            runtime._loop.call_soon_threadsafe(runtime.inject_event, started)  # noqa: SLF001 — as emit_tool_progress
        return held

    def _get(self, owner: str, run_id: str) -> HeldRun:
        with self._lock:
            held = self._runs.get(owner, {}).get(run_id)
        if held is None:
            raise KeyError(f"session {owner!r} holds no run {run_id!r}")
        return held

    def running(self, owner: str, run_id: str) -> bool:
        return not self._get(owner, run_id).done.is_set()

    def stop(self, owner: str, run_id: str) -> None:
        """Ask the run's session to end; it ends with reason `caller_stop`."""
        held = self._get(owner, run_id)
        if held.done.is_set() or held.loop is None or held.loop.is_closed():
            return
        request = SessionEndRequested(
            session_id=held.sessions[0].session_id, source=SessionEndReason.CALLER_STOP
        )
        try:
            held.loop.call_soon_threadsafe(held.runtime.inject_event, request)
        except RuntimeError:  # the run's loop closed as we asked: it had ended
            pass

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


def run_notice(e: TopologyRunEnded) -> str:
    """The one line the caller's model reads about an ended run."""
    said = ""
    if e.report is not None:
        said = e.report.left or e.report.done
    tail = f": {said.strip()[:300]}" if said.strip() else ""
    return f"[run {e.run_id} ({e.topology}) ended {e.outcome.value}{tail}]"


# The process's table: one app per machine, as the background-task table.
TABLE = RunTable()

__all__ = ["TABLE", "HeldRun", "RunTable", "run_notice"]

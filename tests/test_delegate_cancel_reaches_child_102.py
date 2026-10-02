"""UI sprint 102: interrupting the parent's turn stops the delegated child.

The parent's `delegate` call runs on a worker thread and waits for the child's run, which lives
on its own thread and event loop. Cancelling the parent's tool call stopped neither: the child
kept working after the parent's turn had parked. Now the call registers a stop for each child,
and run_tool fires it on cancel.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest

from substrate.adapters import DeterministicResponder
from substrate.topologies.tool_loop import tool_loop_topology
from substrate.topologies.tool_loop.delegate import _run_child_to_answer
from substrate.topologies.tool_loop.tools import _TOOL_CANCEL_HOOKS


class _Thinks(DeterministicResponder):
    async def arespond(self, prompt: str) -> str:
        await asyncio.sleep(30)
        return self.respond(prompt)


def test_cancelling_the_delegate_call_cancels_the_child_run(tmp_path: Path) -> None:
    hooks: list = []
    box: dict = {}

    def call() -> None:
        _TOOL_CANCEL_HOOKS.set(hooks)
        try:
            _run_child_to_answer(
                tool_loop_topology(
                    model=_Thinks(seed=0),
                    tools={},
                    task="think",
                    walkthrough=True,
                    deterministic=False,
                ),
                tmp_path / "child",
                timeout_seconds=None,
            )
        except BaseException as exc:  # noqa: BLE001 — the test reads what came back
            box["exc"] = exc

    worker = threading.Thread(target=call, daemon=True)
    t0 = time.monotonic()
    worker.start()
    while not hooks and time.monotonic() - t0 < 5:
        time.sleep(0.05)
    assert hooks, "the delegate call registered no stop for its child"
    time.sleep(0.3)  # the child's model call is in flight
    for hook in hooks:
        hook()
    worker.join(10)
    assert not worker.is_alive(), (
        "the delegate call kept waiting on a child that should have stopped"
    )
    assert time.monotonic() - t0 < 10
    with pytest.raises(TimeoutError, match="was cancelled"):
        raise box["exc"]

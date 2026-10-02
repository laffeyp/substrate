"""UI sprint 102: cancelling a CLI-driven model call stops the CLI and everything it started.

Interrupting a turn cancels the model producer's task. CliResponder.arespond killed its
subprocess only on its own timeout, so an interrupted CLI agent kept running after the turn
had parked.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from substrate.adapters.models import CliResponder


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_cancel_kills_the_cli_and_its_children(tmp_path: Path) -> None:
    pids = tmp_path / "pids"
    # The prompt is appended as the last argv entry; `sh -c` binds it to $0 and ignores it.
    cmd = ["sh", "-c", f"sleep 30 & echo $! > {pids}; echo $$ >> {pids}; wait"]
    r = CliResponder(cmd, name="fake")

    async def go() -> None:
        task = asyncio.create_task(r.arespond("hello"))
        for _ in range(100):
            await asyncio.sleep(0.05)
            if pids.exists() and len(pids.read_text().split()) == 2:
                break
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(go())
    child, shell = (int(x) for x in pids.read_text().split())
    for _ in range(40):
        if not _alive(child) and not _alive(shell):
            break
        asyncio.run(asyncio.sleep(0.05))
    assert not _alive(shell), "the CLI process survived the cancel"
    assert not _alive(child), "a process the CLI started survived the cancel"

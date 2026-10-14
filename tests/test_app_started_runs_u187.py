# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""UI sprint 187, kernel side (session vocabulary v0.16.2): a run the person starts from the app is
written into its session's record at the session's next model step, start before end."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.compose.check import check
from substrate.topologies.compose.parts import Deps
from substrate.topologies.compose.run import start_composed
from substrate.topologies.runs.hold import RunTable
from substrate.topologies.session import UserMessage, session_topology

pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")


class Says:
    def respond(self, prompt: str) -> str:
        return "an answer"


def test_an_app_started_run_is_written_at_the_next_step_start_before_end(tmp_path: Path) -> None:
    from substrate.topologies.runs import hold

    table = RunTable()
    plan = check('ask: model "Answer."').plan
    assert plan is not None
    held = start_composed(
        table,
        owner="s_caller",
        run_id="r_app",
        plan=plan,
        run_input="q",
        deps=Deps(responder=lambda _s: Says(), start_agent=lambda _c: {}, workdir=tmp_path),
        records=tmp_path / "runs",
    )
    deadline = time.monotonic() + 30
    while table.running("s_caller", "r_app"):
        assert time.monotonic() < deadline
        time.sleep(0.05)

    def caller() -> Any:
        return session_topology(
            driver=DeterministicResponder(seed=0),
            driver_name="deterministic",
            driver_context_tokens=4096,
            seed="",
            tools={},
            session_id="s_caller",
            workspace_path=str(tmp_path),
            script=[],
        )

    original = hold.TABLE
    hold.TABLE = table
    try:
        root = tmp_path / "caller"
        asyncio.run(
            api.Runtime(root, persistent=True).resume(
                caller(),
                resume_event=UserMessage(
                    text="hello", turn_index=0, assembled_prompt="", slash_source="chat"
                ),
            )
        )
    finally:
        hold.TABLE = original
    events = list(api.read_record(root, resolve_blobs=True))
    kinds = [e["kind"] for e in events if e["kind"].startswith("TopologyRun")]
    assert kinds == ["TopologyRunStarted", "TopologyRunEnded"]
    (started,) = [e["payload"] for e in events if e["kind"] == "TopologyRunStarted"]
    assert started["call_seq"] == -1 and started["sessions"] == []
    assert started["record_root"] == str(held.record_root)
    assert table.drain_started("s_caller") == []  # told once

"""A coding gate that times out leaves no process behind.

`subprocess.run(shell=True, timeout=…)` killed only the shell; the candidate's grandchildren kept
running in a deleted sandbox (lens audit F176: measured with `sleep 8; echo done` and
`sleep 8 & wait` under a 1 s timeout, both `sleep` processes survived).
"""

from __future__ import annotations

import subprocess
import time

import pytest

from substrate.topologies.coding_flow.gate import run_gate


def _sleepers(tag: str) -> list[str]:
    out = subprocess.run(["ps", "-axo", "command="], capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if tag in line and "ps -axo" not in line]


@pytest.mark.parametrize("gate", ["sleep 8.{tag}; echo done", "sleep 8.{tag} & wait"])
def test_a_timed_out_gate_leaves_no_grandchild(gate: str) -> None:
    tag = str(time.monotonic_ns() % 10_000_000).zfill(7)  # a unique `sleep 8.<tag>` per run
    result = run_gate({"a.txt": "x"}, gate.format(tag=tag), timeout=1.0)
    assert not result.passed and "timed out" in result.summary
    deadline = time.monotonic() + 3
    while _sleepers(f"sleep 8.{tag}") and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _sleepers(f"sleep 8.{tag}") == []

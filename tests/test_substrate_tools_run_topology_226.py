# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 226 — substrate toolkit: run_topology + run_topology_poll.

Two tools, two behaviors each: sync (await_completion=true) returns
{output, child_root, run_id}; async (await_completion=false) returns
{run_id, record_root, status: running}. Polling returns the daemon's
status shape.

Tests inject a stub DaemonClient — no daemon spins up. The tool's
dispatch shape + schema is what's under test here; the wire round-trip
is verified by the substrate-ui side (sprint 225a's tests).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from substrate.topologies.tool_loop.substrate_tools import (
    _extract_terminal_output,
    make_run_topology,
    make_run_topology_poll,
)


class _StubClient:
    """Records every daemon call; returns queued responses."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.run_response: dict[str, Any] = {}
        self.status_response: dict[str, Any] = {}

    def run_topology(
        self,
        application_name: str,
        inputs: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(("run_topology", (application_name, inputs), dict(kwargs)))
        return self.run_response

    def topology_status(self, application_name: str, run_id: str) -> dict[str, Any]:
        self.calls.append(("topology_status", (application_name, run_id), {}))
        return self.status_response


def _fake_record(tmp_path: Path, terminal_kind: str = "Verdict") -> Path:
    """Write a two-envelope record: substrate.RunStarted + one application
    terminal. `_extract_terminal_output` reads the tail non-substrate.*
    envelope's payload."""
    record = tmp_path / "fake-record"
    record.mkdir()
    # Real records go through framing; this test writes a minimal
    # envelope shape that api.read_record refuses to parse. So use the
    # framing helper directly.
    from substrate.record import framing

    segment = record / "events-000001.jsonl"
    with segment.open("wb") as fp:
        fp.write(
            framing.frame(
                {
                    "seq": 0,
                    "kind": "substrate.RunStarted",
                    "payload": {"config": {}},
                }
            )
        )
        fp.write(
            framing.frame(
                {
                    "seq": 1,
                    "kind": terminal_kind,
                    "payload": {"answer": "the-answer"},
                }
            )
        )
    return record


def test_run_topology_sync_flattens_to_output_child_root_run_id(tmp_path: Path) -> None:
    record = _fake_record(tmp_path)
    client = _StubClient()
    client.run_response = {
        "run_id": "s_topo_abc",
        "record_root": str(record),
        "status": "finalised",
        "final_seq": 1,
        "application": "code_review",
    }
    tool = make_run_topology(client)
    result = tool.run(
        [
            {
                "name": "code_review",
                "inputs": {"repo": "/tmp/x"},
            }
        ]
    )
    assert result["run_id"] == "s_topo_abc"
    assert result["child_root"] == str(record)
    assert result["status"] == "finalised"
    assert result["output"] == {"answer": "the-answer"}


def test_run_topology_async_returns_running_shape(tmp_path: Path) -> None:
    client = _StubClient()
    client.run_response = {
        "run_id": "s_topo_async",
        "record_root": str(tmp_path / "any"),
        "status": "running",
        "application": "code_review",
    }
    tool = make_run_topology(client)
    result = tool.run(
        [
            {
                "name": "code_review",
                "inputs": {"repo": "/tmp/x"},
                "await_completion": False,
            }
        ]
    )
    assert result == {
        "run_id": "s_topo_async",
        "record_root": str(tmp_path / "any"),
        "status": "running",
    }
    _method, _args, kwargs = client.calls[0]
    assert kwargs["await_completion"] is False


def test_run_topology_passes_bundle_baseline_context(tmp_path: Path) -> None:
    client = _StubClient()
    client.run_response = {"run_id": "s_topo_x", "record_root": str(tmp_path), "status": "running"}
    tool = make_run_topology(client)
    tool.run(
        [
            {
                "name": "code_review",
                "inputs": {"repo": "."},
                "bundle": "reviewer",
                "baseline": {"foo": 1},
                "context": {"parent_seq_range": [0, 10]},
            }
        ]
    )
    _method, _args, kwargs = client.calls[0]
    assert kwargs["bundle"] == "reviewer"
    assert kwargs["baseline"] == {"foo": 1}
    assert kwargs["context"] == {"parent_seq_range": [0, 10]}


def test_run_topology_poll_passes_through_daemon_response(tmp_path: Path) -> None:
    client = _StubClient()
    client.status_response = {
        "run_id": "s_topo_p",
        "status": "finalised",
        "record_root": str(tmp_path),
        "elapsed_seconds": 12.5,
        "application": "code_review",
        "output": {"answer": "42"},
    }
    tool = make_run_topology_poll(client)
    result = tool.run([{"name": "code_review", "run_id": "s_topo_p"}])
    assert result == client.status_response


def test_run_topology_missing_name_raises_typed_valueerror() -> None:
    """Drift-grooming 2026-09-02: the previous shape raised a bare
    KeyError; the tool_loop layer wraps that as ToolResult(ok=False,
    error="'name'") — cryptic and gives the model no tool context. Now
    typed ValueError names both the tool and the missing key so the
    model can recover on retry."""
    tool = make_run_topology(_StubClient())
    with pytest.raises(ValueError, match=r"run_topology: missing required argument 'name'"):
        tool.run([{"inputs": {"repo": "."}}])


def test_run_topology_missing_inputs_raises_typed_valueerror() -> None:
    tool = make_run_topology(_StubClient())
    with pytest.raises(ValueError, match=r"run_topology: missing required argument 'inputs'"):
        tool.run([{"name": "code_review"}])


def test_run_topology_poll_missing_run_id_raises_typed_valueerror() -> None:
    tool = make_run_topology_poll(_StubClient())
    with pytest.raises(ValueError, match=r"run_topology_poll: missing required argument 'run_id'"):
        tool.run([{"name": "code_review"}])


def test_run_topology_schema_is_declared_on_the_tool() -> None:
    tool = make_run_topology(_StubClient())
    assert tool.schema is not None
    assert tool.schema["required"] == ["name", "inputs"]
    poll = make_run_topology_poll(_StubClient())
    assert poll.schema["required"] == ["name", "run_id"]


def test_extract_terminal_output_returns_none_on_empty_record(tmp_path: Path) -> None:
    empty = tmp_path / "empty-record"
    empty.mkdir()
    assert _extract_terminal_output(str(empty)) is None

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 052 — spawn tools comprehension: delegate, run_topology,
run_topology_poll.

Each of these spawns work outside the parent turn: `delegate` runs a
child agent, `run_topology` dispatches a topology to the daemon,
`run_topology_poll` checks its progress. The sandbox layers are the
same as the write / exec files — Layer 1 workspace jail via tmp_path,
plus stubs for the pieces we do NOT want to exercise (a real live
child model, a real daemon).

Sandboxing per tool:

- delegate: parent runs qwen2.5:7b-instruct (real live model, real
  tool-calling). Child runs DeterministicResponder — no second live
  model, no host artefact outside tmp_path. Child workspace + record
  both land under tmp_path. Layer 3 no_escape_guard also holds.

- run_topology / run_topology_poll: DaemonClient is a stub in this
  file. The stub returns canned {run_id, status, record} shapes; no
  real daemon spins up. Parent model still picks the tool and reads
  the result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from substrate.topologies.session.vocabulary import turn_replies
from substrate import api
from substrate.adapters import DeterministicResponder, OllamaResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.tool_loop.delegate import make_delegate
from substrate.topologies.tool_loop.substrate_tools import (
    make_run_topology,
    make_run_topology_poll,
)

pytestmark = [pytest.mark.realmodel, pytest.mark.usefixtures("no_escape_guard")]

_DRIVER = "qwen2.5:7b-instruct"
_OLLAMA_V1 = "http://localhost:11434/v1"


def _require_model() -> None:
    try:
        ids = {m["id"] for m in httpx.get(_OLLAMA_V1 + "/models", timeout=4).json().get("data", [])}
    except Exception as exc:  # noqa: BLE001 — any unreachability is a SKIP
        pytest.skip(f"spawn-tool skipped — Ollama not reachable ({type(exc).__name__})")
    if _DRIVER not in ids:
        pytest.skip(f"spawn-tool skipped — model absent: {_DRIVER}")


def _open(*, tmp_path: Path, tools: dict, first_text: str) -> Any:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace, session_topology(
        driver=OllamaResponder(
            _DRIVER,
            max_tokens=220,
            temperature=0,
            system="You have access to tools. Call the RIGHT one. Do EXACTLY what the user asks.",
        ),
        driver_name=_DRIVER,
        driver_context_tokens=8192,
        seed="",
        tools=tools,
        per_turn="",
        max_turns=6,
        turn_max_steps=4,
        session_id="s_spawn_test",
        workspace_path=str(workspace),
        script=None,
        first_turn_user_message=UserMessage(
            text=first_text, turn_index=0, assembled_prompt=first_text, slash_source="test"
        ),
    )


def _events(root: Path) -> list[dict]:
    return list(api.read_record(root))


def _by_kind(envs: list[dict], kind: str) -> list[dict]:
    return [e for e in envs if e["kind"] == kind]


def _last_answer(envs: list[dict]) -> str:
    finals = turn_replies(envs)
    return finals[-1][1] if finals else ""


# ── delegate ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.timeout(90)
async def test_delegate_child_returns_and_parent_quotes_it(tmp_path: Path) -> None:
    """Parent (qwen2.5) calls `delegate(task=...)`. Child runs a
    DeterministicResponder — deterministic reply, no second live model.
    ToolResult carries `{answer, child_root, steps}`. Parent's answer
    quotes something from the child_root path.

    Every artefact lands under tmp_path: parent workspace + record,
    child delegation dir + its workspace + its record."""
    _require_model()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    child_responder = DeterministicResponder(seed=0)
    # child_record_root: place child records as siblings of the parent
    # record, inside tmp_path/child_records/<n>/. Sprint 052 sandbox:
    # every child artefact stays under tmp_path.
    child_records_base = tmp_path / "child_records"
    child_records_base.mkdir()

    def _child_record_root(n: int) -> Path:
        p = child_records_base / f"child_{n}"
        # `_default_child_factory` creates parent dirs; return the path
        # it should mkdir under, not the dir itself.
        return p

    delegate = make_delegate(
        responder=child_responder,
        root=workspace,
        child_record_root=_child_record_root,
        max_depth=1,
        max_children=2,
        child_max_steps=4,
        timeout_seconds=60.0,
    )
    tools = {"delegate": delegate}
    _ws, factory = _open(
        tmp_path=tmp_path,
        tools=tools,
        first_text=(
            "Call delegate with task='add 2 and 3 using the calculator'. "
            "Then tell me what child_root path the tool returned."
        ),
    )
    result = await api.Runtime(tmp_path / "record", persistent=True).run(factory)
    assert result.status == "paused"
    envs = _events(tmp_path / "record")
    assert any(c["payload"].get("tool") == "delegate" for c in _by_kind(envs, "ToolCall"))
    tr = _by_kind(envs, "ToolResult")
    ok = [r for r in tr if r["payload"].get("ok") is True]
    assert ok, f"no successful delegate: {[r['payload'] for r in tr]}"
    output = ok[0]["payload"].get("output") or {}
    assert "answer" in output and "child_root" in output and "steps" in output, (
        f"delegate ToolResult must carry (answer, child_root, steps); got {output}"
    )
    child_root = str(output["child_root"])
    # SANDBOX: child_root must live under tmp_path.
    assert child_root.startswith(str(tmp_path)), (
        f"child_root {child_root!r} escaped tmp_path {tmp_path!r}"
    )
    # COMPREHENSION: parent's reply references the child_root path
    # (fragment enough — full paths are noisy for a small model).
    answer = _last_answer(envs)
    fragment = Path(child_root).name  # e.g. "child_0" or a hash
    assert fragment in answer or "child" in answer.lower(), (
        f"parent must quote the child_root; got answer={answer!r}, child_root={child_root!r}"
    )


# ── run_topology / run_topology_poll (stubbed daemon) ────────────────────


class _StubDaemonClient:
    """Duck-type of DaemonClient. Captures calls; returns canned shapes.
    No real daemon spins up; the tool wire is what the test exercises."""

    def __init__(self, *, record_dir: Path) -> None:
        self.run_topology_calls: list[dict] = []
        self.topology_status_calls: list[dict] = []
        self._record_dir = record_dir

    def run_topology(
        self,
        application_name: str,
        inputs: dict[str, Any],
        *,
        bundle: str | None = None,
        baseline: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        await_completion: bool = False,
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        self.run_topology_calls.append(
            {
                "application_name": application_name,
                "inputs": inputs,
                "await_completion": await_completion,
            }
        )
        return {
            "run_id": "run_1234",
            "status": "running",
            "record_root": str(self._record_dir / f"{application_name}-run_1234.record"),
        }

    def topology_status(self, application_name: str, run_id: str) -> dict[str, Any]:
        self.topology_status_calls.append({"application_name": application_name, "run_id": run_id})
        return {
            "run_id": run_id,
            "status": "finalised",
            "output_events": [{"kind": "Answer", "text": "42"}],
        }


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_run_topology_dispatches_via_stub_daemon(tmp_path: Path) -> None:
    """Model calls run_topology(name='code_review', inputs={pr: 1}).
    The stub captures the call; the tool returns run_id. Parent's
    answer must reference the run_id or the record path — both come
    from the ToolResult."""
    _require_model()
    stub = _StubDaemonClient(record_dir=tmp_path / "records")
    tools = {"run_topology": make_run_topology(stub)}
    _ws, factory = _open(
        tmp_path=tmp_path,
        tools=tools,
        first_text=(
            "Call run_topology with name='code_review' and inputs={'pr': 1}. "
            "Then tell me the run_id it returned."
        ),
    )
    result = await api.Runtime(tmp_path / "record", persistent=True).run(factory)
    assert result.status == "paused"
    envs = _events(tmp_path / "record")
    assert any(c["payload"].get("tool") == "run_topology" for c in _by_kind(envs, "ToolCall"))
    tr = _by_kind(envs, "ToolResult")
    ok = [r for r in tr if r["payload"].get("ok") is True]
    assert ok, f"no successful run_topology: {[r['payload'] for r in tr]}"
    assert stub.run_topology_calls, "stub daemon was not called"
    call = stub.run_topology_calls[-1]
    assert call["application_name"] == "code_review", call
    assert call["inputs"].get("pr") == 1, call
    # Comprehension: model's answer names the run_id from the ToolResult.
    assert "run_1234" in _last_answer(envs), _last_answer(envs)


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_run_topology_poll_reads_status_via_stub(tmp_path: Path) -> None:
    """Model calls run_topology_poll(name, run_id). Stub returns
    status=finalised; parent's answer names the finalised state."""
    _require_model()
    stub = _StubDaemonClient(record_dir=tmp_path / "records")
    tools = {"run_topology_poll": make_run_topology_poll(stub)}
    _ws, factory = _open(
        tmp_path=tmp_path,
        tools=tools,
        first_text=(
            "Call run_topology_poll with name='code_review' and run_id='run_abcd'. "
            "Tell me the status."
        ),
    )
    result = await api.Runtime(tmp_path / "record", persistent=True).run(factory)
    assert result.status == "paused"
    envs = _events(tmp_path / "record")
    assert any(c["payload"].get("tool") == "run_topology_poll" for c in _by_kind(envs, "ToolCall"))
    tr = _by_kind(envs, "ToolResult")
    ok = [r for r in tr if r["payload"].get("ok") is True]
    assert ok, f"no successful poll: {[r['payload'] for r in tr]}"
    assert stub.topology_status_calls, "stub daemon poll was not called"
    call = stub.topology_status_calls[-1]
    assert call["run_id"] == "run_abcd", call
    assert "finalised" in _last_answer(envs).lower() or "final" in _last_answer(envs).lower(), (
        f"parent must name the finalised status; got {_last_answer(envs)!r}"
    )

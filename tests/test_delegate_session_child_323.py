# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 323: every delegate child is a session in the registry (research r8 § 4.6). It
runs on the caller's model unless the call names another, in the caller's workspace, with the
caller's bundle, length, tone and tools, and the caller as its parent; its turn runs to the
session's own step limit; its answer folds back as the tool's result."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.session import session_topology
from substrate.topologies.session_registry import SessionManifest, SessionRegistry
from substrate.topologies.tool_loop.delegate import make_delegate
from substrate.topologies.tool_loop.tools import _TOOL_CANCEL_HOOKS, full_suite

pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")

# A child's turn: eight tool calls, more than the old six-step cap, then its reply.
CHILD_SCRIPT: list[tuple[str, list[Any]]] = [("list_dir", ["."])] * 8


def _factory(m: SessionManifest, first_turn_user_message: Any = None) -> Any:
    """A child (a session with a parent) runs the eight-call script; any session runs the
    deterministic stand-in, with the tools its manifest allows."""
    suite = full_suite(Path(m.workspace), owner=m.session_id)
    if m.tools:
        suite = {k: v for k, v in suite.items() if k in m.tools}
    return session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name=m.driver,
        driver_context_tokens=8192,
        seed="",
        tools=suite,
        turn_max_steps=24,
        session_id=m.session_id,
        workspace_path=m.workspace,
        script=CHILD_SCRIPT if m.composite_of else None,
        first_turn_user_message=first_turn_user_message,
    )


def _registry(tmp_path: Path, **parent: Any) -> SessionRegistry:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.txt").write_text("a\n")
    reg = SessionRegistry(base=tmp_path / "sessions", session_topology_factory=_factory)
    reg.create(
        session_id="s_parent",
        name=None,
        driver=parent.pop("driver", "parent-model"),
        workspace=str(ws),
        workspace_shape="flat",
        bundle=parent.pop("bundle", "standard"),
        seed="",
        **parent,
    )
    return reg


def _child_events(result: dict[str, Any]) -> list[dict[str, Any]]:
    return list(api.read_record(Path(result["child_root"]), resolve_blobs=True))


def test_a_child_is_a_session_on_the_callers_model(tmp_path: Path) -> None:
    reg = _registry(tmp_path, length="terse", tone="blunt", tools=("list_dir", "read_file"))
    parent = reg.get("s_parent")
    result = make_delegate(session_registry=reg, parent_session_id="s_parent").run(
        [{"task": "list the folder"}]
    )
    child = reg.get(result["session_id"])
    assert child is not None and child.composite_of == "s_parent"
    assert child.driver == "parent-model" and child.workspace == parent.workspace
    assert (child.bundle, child.length, child.tone) == ("standard", "terse", "blunt")
    assert child.tools == ("list_dir", "read_file")
    assert child.driver_params is None
    events = _child_events(result)
    first = next(e for e in events if e["kind"] == "UserMessage")["payload"]
    assert first["text"] == "list the folder" and first["slash_source"] == "delegate"
    assert result["answer"]  # the child's reply folds back


def test_a_childs_turn_is_not_capped_at_six_steps(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    result = make_delegate(session_registry=reg, parent_session_id="s_parent").run(
        [{"task": "look around"}]
    )
    calls = [e for e in _child_events(result) if e["kind"] == "ToolCall"]
    assert len(calls) == 8


def test_the_call_can_name_another_model(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    result = make_delegate(session_registry=reg, parent_session_id="s_parent").run(
        [{"task": "x", "model": "other-model"}]
    )
    assert reg.get(result["session_id"]).driver == "other-model"
    assert result["via"] == "different_driver:other-model"


def test_context_from_the_callers_record_reaches_the_child(tmp_path: Path) -> None:
    from collections.abc import AsyncIterator

    import asyncio

    from msgspec import Struct

    class ParentReply(Struct, frozen=True):
        text: str

    async def _emit(_inp: Any) -> AsyncIterator[ParentReply]:
        yield ParentReply(text="parent said HELLO WORLD")

    def parent_topology(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "emitter",
            schemas=[ParentReply],
            schema_version=1,
            factory=lambda: _emit,
            deterministic=True,
        )
        b.initial("emitter", input={})
        b.termination(api.threshold_count("ParentReply", 1))

    parent_root = tmp_path / "parent-record"
    asyncio.run(api.Runtime(parent_root).run(parent_topology))
    reg = _registry(tmp_path)
    result = make_delegate(
        session_registry=reg, parent_session_id="s_parent", parent_record_root=parent_root
    ).run(
        [
            {
                "task": "continue the parent's thought",
                "context": {"parent_seq_range": [0, 20], "kinds": ["ParentReply"]},
            }
        ]
    )
    assert result["via"] == "context_slice"
    first = next(e for e in _child_events(result) if e["kind"] == "UserMessage")["payload"]
    assert "HELLO WORLD" in first["text"] and first["text"].endswith(
        "continue the parent's thought"
    )


def test_fan_out_children_run_on_the_callers_model(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    result = make_delegate(session_registry=reg, parent_session_id="s_parent").run(
        [{"task": "", "children": [{"task": "one"}, {"task": "two", "driver": "third-model"}]}]
    )
    assert result["ok"] and set(result["answers"]) == {"c0", "c1"}
    drivers = {n: reg.get(sid).driver for n, sid in result["session_ids"].items()}
    assert drivers == {"c0": "parent-model", "c1": "third-model"}


def test_depth_counts_the_callers_ancestors(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    parent = "s_parent"
    for i in range(2):
        reg.create(
            session_id=f"s_d{i}",
            name=None,
            driver="m",
            workspace=str(tmp_path / "ws"),
            workspace_shape="flat",
            bundle=None,
            seed="",
            composite_of=parent,
        )
        parent = f"s_d{i}"
    with pytest.raises(ValueError, match="max delegation depth"):
        make_delegate(session_registry=reg, parent_session_id=parent, max_depth=2).run(
            [{"task": "x"}]
        )


def test_the_caps_refuse_the_extra_child(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    d = make_delegate(session_registry=reg, parent_session_id="s_parent", max_children=1)
    d.run([{"task": "first"}])
    with pytest.raises(ValueError, match="max_children=1"):
        d.run([{"task": "second"}])
    d2 = make_delegate(session_registry=reg, parent_session_id="s_parent", max_total_children=1)
    with pytest.raises(ValueError, match="tree budget"):
        d2.run([{"task": "third"}])  # the tree already holds one child


def test_interrupting_the_caller_interrupts_the_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reg = _registry(tmp_path)
    interrupted: list[str] = []
    monkeypatch.setattr(reg, "interrupt", lambda sid, tier="hard": interrupted.append(sid))
    hooks: list[Any] = []
    token = _TOOL_CANCEL_HOOKS.set(hooks)
    try:
        result = make_delegate(session_registry=reg, parent_session_id="s_parent").run(
            [{"task": "x"}]
        )
    finally:
        _TOOL_CANCEL_HOOKS.reset(token)
    assert len(hooks) == 1
    hooks[0]()
    assert interrupted == [result["session_id"]]


def test_descendants_are_listed_deepest_first(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    parent = "s_parent"
    for i in range(3):
        reg.create(
            session_id=f"s_n{i}",
            name=None,
            driver="m",
            workspace=str(tmp_path / "ws"),
            workspace_shape="flat",
            bundle=None,
            seed="",
            composite_of=parent,
        )
        parent = f"s_n{i}"
    assert [m.session_id for m in reg.descendants("s_parent")] == ["s_n2", "s_n1", "s_n0"]

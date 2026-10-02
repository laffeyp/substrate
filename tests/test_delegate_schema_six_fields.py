# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 212 — delegate's schema declares six properties + the passthrough marker.

TECH-SPEC-2026-08-25-round6 §5:
  - `task` (string, required) — the self-contained subtask
  - `model` (string, optional) — driver override
  - `child_session_name` (string, optional) — standing-session routing
  - `context` (object, optional) — parent-record slice
  - `baseline` (object, optional) — child TopologyBuilder baseline override
  - `timeout_seconds` (number, optional) — per-call wall-clock cap

Plus the sprint 212-only `x-args-passthrough: true` extension key on the schema
root, which tells `tools.py::_named_to_positional` to hand the full named-args
dict to `Tool.run` as a single positional element (rather than iterating schema
properties and dropping trailing optionals at the first missing prop).

The schema must reach `ollama_tools(suite)` so native tool-calling models see
every field. This file locks that visibility.
"""

from __future__ import annotations

from pathlib import Path

from substrate.adapters import DeterministicResponder
from substrate.topologies.tool_loop.delegate import make_delegate
from substrate.topologies.tool_loop.tools import _named_to_positional, ollama_tools


def _suite(root: Path) -> dict:
    return {"delegate": make_delegate(responder=DeterministicResponder(seed=0), root=root)}


def test_schema_declares_all_six_properties(tmp_path: Path) -> None:
    suite = _suite(tmp_path)
    props = suite["delegate"].schema["properties"]
    assert set(props) == {
        "task",
        "model",
        "child_session_name",
        "context",
        "baseline",
        "timeout_seconds",
        "children",  # sprint 245 fan-out (the test predates it; updated in UI sprint 097)
    }


def test_only_task_is_required(tmp_path: Path) -> None:
    suite = _suite(tmp_path)
    assert suite["delegate"].schema["required"] == ["task"]


def test_x_args_passthrough_marker_set(tmp_path: Path) -> None:
    suite = _suite(tmp_path)
    assert suite["delegate"].schema.get("x-args-passthrough") is True


def test_ollama_tools_exposes_all_six_fields_to_native_calling(tmp_path: Path) -> None:
    """`ollama_tools` returns the wire shape a native-tool-calling model sees. Every
    delegate property must land in the exposed function parameters so the model
    can set any subset.
    """
    suite = _suite(tmp_path)
    tools_wire = ollama_tools(suite)
    delegate_wire = next(t for t in tools_wire if t["function"]["name"] == "delegate")
    props = delegate_wire["function"]["parameters"]["properties"]
    assert set(props) == {
        "task",
        "model",
        "child_session_name",
        "context",
        "baseline",
        "timeout_seconds",
        "children",  # sprint 245 fan-out (the test predates it; updated in UI sprint 097)
    }


def test_named_to_positional_hands_delegate_a_single_dict(tmp_path: Path) -> None:
    """The `x-args-passthrough` marker turns delegate's args parse into a single
    positional dict. Every arg the model set is preserved, even with gaps in
    the middle (task + timeout_seconds, no model).
    """
    suite = _suite(tmp_path)
    positional = _named_to_positional(
        "delegate",
        {"task": "hi", "timeout_seconds": 30, "baseline": {"foo": "bar"}},
        suite,
    )
    assert len(positional) == 1
    assert isinstance(positional[0], dict)
    assert positional[0] == {
        "task": "hi",
        "timeout_seconds": 30,
        "baseline": {"foo": "bar"},
    }


def test_named_to_positional_preserves_optional_gap_that_would_otherwise_drop(
    tmp_path: Path,
) -> None:
    """Prior to the passthrough marker, `_named_to_positional` iterated schema
    properties and stopped at the first missing one — a model that skipped a
    middle-schema optional would lose every arg after it. This test locks the
    fix: with the passthrough marker, every set arg reaches the tool regardless
    of intermediate gaps.
    """
    suite = _suite(tmp_path)
    # task set, model absent, child_session_name absent, context absent, baseline absent,
    # timeout_seconds set. Without the marker, positional would be [task] and timeout_seconds
    # would drop. With the marker, positional is [{task, timeout_seconds}] and both survive.
    positional = _named_to_positional("delegate", {"task": "hi", "timeout_seconds": 45}, suite)
    assert positional == [{"task": "hi", "timeout_seconds": 45}]


def test_run_reads_every_per_call_arg_from_the_dict(tmp_path: Path) -> None:
    """`Tool.run(a)` with `a = [args_dict]` reads task and does not raise on the
    other args. Actual dispatch behavior for model/context/baseline/child_session_name
    is sprint 213 scope; sprint 212 just parses.
    """
    suite = _suite(tmp_path)
    result = suite["delegate"].run(
        [
            {
                "task": "hi",
                "model": "deterministic",
                "context": {"parent_seq_range": [0, 5], "kinds": ["FinalAnswer"]},
                "baseline": {"foo": "bar"},
                "timeout_seconds": 30,
            }
        ]
    )
    assert isinstance(result, dict)
    assert "answer" in result
    assert "child_root" in result
    assert "steps" in result

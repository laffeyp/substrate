# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Observation contract for delegate (sprint 141, application-parity W2.1).

CI, deterministic, no network: a parent tool_loop scripted to call `delegate` once; the child is the
built-in calculator agent ((2+3)*4 = 20), pure and reproducible. Asserts the child runs as its OWN record,
the answer folds back into the parent's ToolResult, the parent's result cites the child root
(run-granularity provenance), and the depth/fan-out caps refuse with typed failures.

The review (2026-07-31) caught that the deterministic child hides the one thing delegate exists to do —
carry the task to a real model. `test_default_child_runs_the_real_model_on_the_task` (F-2/F-12) closes
that with a spy Responder; `test_read_only_suite_propagates` (F-5) and
`test_timed_out_child_is_cancelled_and_its_record_sealed` (F-8, the timed-out child is now cancelled +
sealed, not abandoned) close the other two delegate defects.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from substrate import api
from substrate.topologies.tool_loop import tool_loop_topology
from substrate.topologies.tool_loop.delegate import make_delegate
from substrate.topologies.tool_loop.tools import full_suite, ollama_tools, parse_tool_call


def _calculator_child(task: str, child_root: Path) -> object:
    # the built-in calculator agent: add(2,3) -> mul(5,4) -> answer "20". Pure -> the child record is
    # deterministic. Stands in for "a real sub-agent" while keeping CI byte-reproducible. It ignores
    # `task` on purpose (it is a fixed demo); the task-reaches-the-model guarantee is proven separately
    # by test_default_child_runs_the_real_model_on_the_task with a spy Responder.
    return tool_loop_topology(max_steps=4)


class _SpyResponder:
    """Records every prompt it is handed and returns a fixed reply — a stand-in for a real model that lets
    a test assert what the child model actually SAW (DeterministicResponder hashes its prompt, so a spy is
    the direct way to check the task text reached the model)."""

    def __init__(self, reply: str = "the answer is 42", *, delay: float = 0.0) -> None:
        self.prompts: list[str] = []
        self._reply = reply
        self._delay = delay

    def respond(self, prompt: str) -> str:
        if self._delay:
            time.sleep(self._delay)
        self.prompts.append(prompt)
        return self._reply


def test_delegate_runs_a_child_and_folds_the_answer_back(tmp_path: Path) -> None:
    delegate = make_delegate(child_factory=_calculator_child, root=tmp_path)
    parent = tool_loop_topology(
        script=[("delegate", ["compute (2+3)*4"])],  # the parent's one move: hand it off
        tools={"delegate": delegate},
        max_steps=3,
    )
    result = asyncio.run(api.Runtime(tmp_path / "parent").run(parent))
    events = list(api.read_record(tmp_path / "parent"))
    kinds = [e["kind"] for e in events]

    assert result.status == "finalised"
    assert "ToolCall" in kinds and "ToolResult" in kinds and "FinalAnswer" in kinds
    tr = next(e for e in events if e["kind"] == "ToolResult")
    assert tr["payload"]["ok"] is True  # the child ran without error
    out = tr["payload"]["output"]
    assert out["answer"] == "20"  # the calculator child's answer folded back
    assert out["steps"] >= 1

    # run-granularity provenance: the parent's ToolResult names the child record root, and it is a real,
    # complete record (the child is citable from the parent — composition.py §20's guarantee).
    child_root = Path(out["child_root"])
    child_kinds = [e["kind"] for e in api.read_record(child_root)]
    assert child_kinds[-1] == "substrate.RunFinalised"
    assert child_kinds.count("FinalAnswer") == 1

    # no invented vocabulary on the parent — delegate is a tool, its result is an ordinary ToolResult
    known = {"ToolCall", "ToolResult", "FinalAnswer"}
    assert not any(k not in known and not k.startswith("substrate.") for k in kinds)


def test_delegate_is_visible_and_callable_via_native_tool_calling(tmp_path: Path) -> None:
    # regression (walkthrough-caught): the scripted CI path calls delegate DIRECTLY, bypassing tool
    # presentation. A real model traverses ollama_tools (the schema list it is shown) + parse_tool_call
    # (mapping its reply back to positional args). A walkthrough found delegate invisible there — no
    # schema entry, so ollama_tools dropped it and its args were unmappable. Assert the real path.
    suite = {
        **full_suite(tmp_path),
        "delegate": make_delegate(child_factory=_calculator_child, root=tmp_path),
    }
    names = {t["function"]["name"] for t in ollama_tools(suite)}
    assert "delegate" in names  # the model is actually shown the tool
    msg = {"tool_calls": [{"function": {"name": "delegate", "arguments": {"task": "do X"}}}]}
    kind, chosen = parse_tool_call(msg, suite)
    # Sprint 212: delegate opts into `x-args-passthrough`, so `_named_to_positional` hands
    # `Tool.run` a single-element list wrapping the full args dict — the shape delegate needs
    # to read its five optional per-call kwargs without middle-gap drop. The task arg still
    # reaches the tool; the delivery wire is `[{"task": "do X"}]`, not `["do X"]`.
    assert kind == "tool" and chosen == (
        "delegate",
        [{"task": "do X"}],
    )


def test_child_writes_to_workspace_not_its_own_record(tmp_path: Path) -> None:
    # C-1: an autonomous child must not hold write access to the immutable record of its own run. The
    # delegation dir splits into workspace/ (where bash/write_file operate) and record/ (the append-only
    # record). A child that writes a file must land it in workspace/, never beside the record segments.
    from substrate.topologies.tool_loop.tools import full_suite

    def _writing_child(task: str, workspace_root: Path) -> object:
        return tool_loop_topology(
            script=[("write_file", ["notes.txt", "child work product"])],
            tools=full_suite(workspace_root),  # rooted at the workspace, not the record
            max_steps=2,
        )

    out = make_delegate(child_factory=_writing_child, root=tmp_path).run(["write a note"])
    record_dir = Path(out["child_root"])
    assert record_dir.name == "record"  # child_root is the RECORD, not the workspace
    assert (record_dir / "manifest.json").exists()  # a real record lives there
    assert not (record_dir / "notes.txt").exists()  # the child's file did NOT land in the record
    workspace_dir = record_dir.parent / "workspace"
    assert (
        workspace_dir / "notes.txt"
    ).read_text() == "child work product"  # it landed in workspace


def test_child_record_root_redirects_the_record_but_not_the_workspace(tmp_path: Path) -> None:
    # W2.2 follow-on: the cockpit places delegate child RECORDS as flat served records (so the UI can
    # navigate to them) while the WORKSPACE stays under the delegation dir. child_record_root(n) redirects
    # the record; child_root on the result points at the redirected path.
    records = tmp_path / "served"
    records.mkdir()

    def _writing_child(task: str, workspace_root: Path) -> object:
        return tool_loop_topology(
            script=[("write_file", ["scratch.txt", "child scratch"])],
            tools=full_suite(workspace_root),
            max_steps=2,
        )

    out = make_delegate(
        child_factory=_writing_child,
        root=tmp_path,
        child_record_root=lambda n: records / f"child_{n}.record",
    ).run(["do a thing"])
    record_root = Path(out["child_root"])
    assert (
        record_root.parent == records and record_root.name == "child_0.record"
    )  # record redirected
    assert (record_root / "manifest.json").exists()  # a real record landed at the redirected path
    # the child's tool scratch stayed under the delegation dir's workspace, NOT beside the redirected record
    assert not (record_root / "scratch.txt").exists()
    (delegation_dir,) = list((tmp_path / "delegate-runs").iterdir())
    assert (delegation_dir / "workspace" / "scratch.txt").read_text() == "child scratch"


def test_default_child_runs_the_real_model_on_the_task(tmp_path: Path) -> None:
    # F-2/F-12: the DEFAULT factory (responder, no child_factory) must run the real model AND carry the
    # task to it. The pre-fix default made the child deterministic, discarding both — every delegation
    # folded a canned "20" back with zero model calls. A spy proves the task text reaches the child model
    # and its reply (not "20") folds back.
    spy = _SpyResponder(reply="Paris is the capital of France.")
    delegate = make_delegate(responder=spy, root=tmp_path, max_depth=1, child_max_steps=2)
    out = delegate.run(["What is the capital of France?"])
    assert len(spy.prompts) >= 1  # the child model was actually called
    assert any("France" in p for p in spy.prompts)  # the DELEGATED TASK reached the child model
    assert (
        out["answer"] == "Paris is the capital of France."
    )  # the real reply folded back, not "20"


def test_read_only_suite_propagates_to_the_child(tmp_path: Path) -> None:
    # F-5: the child must inherit the PARENT's suite factory, not silently rebuild the full suite. A
    # read-only parent handed bash/write_file/edit_file to the child before this fix. Prove the child's
    # suite is built from the injected factory by capturing what it builds.
    built: dict[str, set[str]] = {}

    def read_only_factory(root: Path) -> dict[str, object]:
        suite = {"read_file": full_suite(root)["read_file"]}  # inspect-only, no bash/write/edit
        built["tools"] = set(suite)
        return suite  # type: ignore[return-value]

    spy = _SpyResponder(reply="done")
    delegate = make_delegate(
        responder=spy,
        root=tmp_path,
        child_suite_factory=read_only_factory,  # type: ignore[arg-type]
        max_depth=1,
        child_max_steps=2,
    )
    delegate.run(["read the file"])
    assert built["tools"] == {"read_file"}  # the child was built from the parent's factory
    assert "bash" not in built["tools"] and "write_file" not in built["tools"]  # no capability leak


def test_timed_out_child_is_cancelled_and_its_record_sealed(tmp_path: Path) -> None:
    # F-8 (fixed): a child that outruns timeout_seconds is CANCELLED cooperatively, not abandoned. The
    # failure names the root, and the child's record is SEALED at that root (Runtime.run's finally runs on
    # cancellation) — so the orphan stops writing and its record agrees with the parent's timeout.
    slow = _SpyResponder(reply="eventually", delay=1.0)
    delegate = make_delegate(
        responder=slow, root=tmp_path, max_depth=1, child_max_steps=1, timeout_seconds=0.1
    )
    try:
        delegate.run(["a slow task"])
        assert False, "expected a timeout"
    except TimeoutError as exc:
        assert "delegate-runs" in str(exc) and "cancelled" in str(exc)

    # the child record exists, is READABLE (sealed, not a half-written open segment), and has no
    # FinalAnswer — the run was cancelled, so its record and the parent's timeout tell the same story.
    (delegation_dir,) = list((tmp_path / "delegate-runs").iterdir())
    record_root = delegation_dir / "record"
    kinds = [e["kind"] for e in api.read_record(record_root)]
    assert "substrate.RunStarted" in kinds  # the child did start
    assert "FinalAnswer" not in kinds  # but never finished — cancelled, no answer

    # and it STAYS stopped: no new events land after cancellation (the orphan is not still writing)
    import time

    before = len(kinds)
    time.sleep(
        1.3
    )  # past the child's own 1.0s model-call sleep — an un-cancelled orphan would emit here
    after = len(list(api.read_record(record_root)))
    assert after == before  # the record did not grow — the child was really stopped


def test_depth_cap_refuses_instead_of_recursing(tmp_path: Path) -> None:
    # a delegate already at the chain limit must refuse — the guard against unbounded delegation
    at_limit = make_delegate(child_factory=_calculator_child, root=tmp_path, depth=2, max_depth=2)
    try:
        at_limit.run(["anything"])
        assert False, "expected a max-depth refusal"
    except ValueError as exc:
        assert "max delegation depth" in str(exc)


def test_fanout_cap_refuses_the_extra_child(tmp_path: Path) -> None:
    once = make_delegate(child_factory=_calculator_child, root=tmp_path, max_children=1)
    first = once.run(["first"])  # allowed
    assert first["answer"] == "20"
    try:
        once.run(["second"])  # over the fan-out cap
        assert False, "expected a max-children refusal"
    except ValueError as exc:
        assert "max children" in str(exc)


def test_a_cap_hit_surfaces_as_a_typed_result_through_the_loop_not_a_crash(tmp_path: Path) -> None:
    # a delegate cap is not just a raise in isolation — through the real loop it becomes a
    # ToolResult(ok=False) the parent model reads, exactly like any other tool failure (errors are
    # observations, never a crash). Parent delegates twice with max_children=1: first ok, second refused.
    parent = tool_loop_topology(
        script=[("delegate", ["first"]), ("delegate", ["second"])],
        tools={
            "delegate": make_delegate(
                child_factory=_calculator_child, root=tmp_path, max_children=1
            )
        },
        max_steps=4,
    )
    result = asyncio.run(api.Runtime(tmp_path / "p2").run(parent))
    events = list(api.read_record(tmp_path / "p2"))
    results = [e for e in events if e["kind"] == "ToolResult"]

    assert result.status == "finalised"
    assert results[0]["payload"]["ok"] is True  # first child ran and folded back
    assert results[1]["payload"]["ok"] is False  # second refused by the fan-out cap
    assert "max children" in results[1]["payload"]["error"]

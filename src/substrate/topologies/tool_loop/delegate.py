# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""delegate — a tool that hands a subtask to a CHILD agent and folds the answer back (application-parity W2.1).

The "subagent" the CLI products ship, on substrate: a tool-using agent calls `delegate(task)` mid-run;
a child agent runs the subtask to completion as its OWN replayable record; its answer folds back into the
parent's transcript as an ordinary ToolResult. The child record root rides on that result, so the parent
record cites the child — run-granularity provenance, the same guarantee `embedded_substrate` gives
(composition.py §20), reached through the tool result because the tool seam cannot mount a Producer.

WHY A THREAD. `tool_loop`'s `Tool.run` is synchronous and blocks the outer loop while it runs (`bash`
already does — `subprocess.run(timeout=60)`). A child substrate run is async. So the child runs to
completion in a worker thread hosting its own `asyncio.run`, and this tool blocks on it exactly as `bash`
blocks — no async contract is added to the tool seam. A concurrent child (running alongside the parent's
other work) would be the `embedded_substrate` Producer path instead; that is a separate, later shape.

THE CHILD RUNS THE REAL MODEL. The default child factory runs `tool_loop` in walkthrough mode with the
supplied `responder` and the delegated `task` — it does NOT run the deterministic calculator demo. (An
earlier version defaulted `walkthrough=False`, which made the child deterministic and discarded both the
model and the task, folding a canned "20" back for every delegation; review F-2. A responder — or an
explicit `child_factory` — is now required, and the task is asserted to reach the child model in the
contract test.) Inject a `child_factory` for a deterministic child in CI.

CAPS + FAILURE. Depth (`max_depth`) bounds the delegation CHAIN; fan-out (`max_children`) bounds how many
children one delegate spawns. At either cap the tool returns a typed failure the model reads. A child that
raises or produces no FinalAnswer is a typed `ToolResult(ok=False)`, not a crash. A child that runs past
`timeout_seconds` is CANCELLED cooperatively (review F-8): the worker holds the child on a loop the caller
can reach, so on timeout the child's run task is cancelled across the thread boundary, `Runtime.run`'s
finally cancels the child's producers and SEALS its record, and the parent records `ToolResult(ok=False)`.
The child stops writing; its sealed record (no FinalAnswer) and the parent's timeout AGREE.
The child's tools write ONLY under its `workspace/` subdir — its record is a SIBLING `record/` subdir, so
an autonomous child cannot write over the immutable evidence of its own run (C-1) — and it inherits the
parent's capability set via `child_suite_factory` (so `--read-only` survives delegation; review F-5). The real bound on a
child is its own `child_max_steps × the model call timeout`; set `timeout_seconds` above that — it is the
safety net, not the primary bound. Unset (the default since UI sprint 101) there is no wall-clock
limit: models can work for a long time, and a step cap or an interrupt ends a child, not a clock.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ... import api
from ...adapters import (
    CliResponder,
    DeterministicResponder,
    DriverFamily,
    OllamaResponder,
    Responder,
)
from ..session.context_slice import extract_context_slice
from ..session.vocabulary import turn_replies
from ..session_registry import SessionEndedMidTurn, SessionRegistry
from .kinds import FINAL_ANSWER
from .tools import _TOOL_CANCEL_HOOKS, Tool, full_suite, on_tool_cancel

# Sprint 224a — wire-error contract constant. The delegate raises a
# ValueError containing this tag when the reviewer session ended between
# the caller's resolve and the reach into `turn_sync`. tool_loop reads
# the string and shapes `ToolResult(ok=false, error=...)`. The daemon
# (substrate-ui/server.py) writes the same tag on `/turn` responses via
# its `session_errors.py` import. One string, one place.
SESSION_ENDED_MID_DELEGATE = "session_ended_mid_delegate"

_CONTEXT_SLICE_CAP_BYTES = 8192  # the tech spec explicit cap

# What the child IS, given a subtask and its WORKSPACE root (where its tools operate — distinct from the
# record root, review C-1). Caller-supplied so delegate is agnostic to session-vs-named-topology, and CI
# can inject a deterministic child. Returns a topology builder callable.
ChildFactory = Callable[[str, Path], Callable[[api.TopologyBuilder], None]]
# How the child's tool suite is built at its own root — the seam through which the parent's capability set
# (e.g. read-only) propagates to the child instead of being silently rebuilt as the full suite.
SuiteFactory = Callable[[Path], dict[str, Tool]]


# Grace period, after we ask the child's run task to cancel, for `Runtime.run`'s finally to unwind its
# producers and SEAL the record before we give up on the worker thread. Cancellation is cooperative
# (`await` points); this bounds how long we wait for the child to notice.
_CANCEL_GRACE_SECONDS = 10.0


def _interrupter(registry: SessionRegistry, session_id: str) -> Callable[[], None]:
    """A cancel hook that interrupts `session_id`'s running turn (hard tier), as ctrl+c would."""

    def stop() -> None:
        registry.interrupt(session_id, tier="hard")

    return stop


def _run_child_to_answer(
    topology: Callable[[api.TopologyBuilder], None],
    root: Path,
    *,
    timeout_seconds: float | None,
    cancel_hooks: list[Callable[[], None]] | None = None,
) -> tuple[str, int]:
    """Run `topology` to completion at `root` in a worker thread (its own event loop, isolated from the
    outer runtime's), then read the child's FinalAnswer off its record. Blocks the caller like `bash`.

    On timeout the child is CANCELLED, not abandoned (review F-8, the accepted risk now closed): the
    worker runs the child on a loop this function holds a handle to, so on timeout we
    `call_soon_threadsafe(task.cancel)` across the thread boundary. `Runtime.run`'s finally then cancels
    the child's producers and seals the record (runtime.py) — so the orphan actually stops writing and its
    record is sealed, rather than running on and contradicting the parent's ToolResult. Raises TimeoutError
    (child cancelled) / the child's exception / ValueError (no FinalAnswer) — the tool body turns any of
    these into a typed ToolResult the parent reads."""
    box: dict[str, Any] = {}
    ready = (
        threading.Event()
    )  # set once the loop + run task exist (so cancel has something to target)
    done = (
        threading.Event()
    )  # set when the worker's run_until_complete returns (normally OR cancelled)
    handle: dict[str, Any] = {}  # {"loop", "task"} — the cross-thread cancellation handle

    def worker() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            task = loop.create_task(api.Runtime(root).run(topology, name="tool_loop"))
            handle["loop"], handle["task"] = loop, task
            ready.set()
            box["result"] = loop.run_until_complete(task)
        except asyncio.CancelledError:
            box["cancelled"] = True  # we asked for this on timeout
        except BaseException as exc:  # noqa: BLE001 — carried back to the caller thread, not swallowed
            box["error"] = exc
        finally:
            loop.close()
            done.set()

    threading.Thread(target=worker, daemon=True).start()
    if ready.wait(5.0):
        # UI sprint 102: interrupting the parent's turn cancels this tool call; stop the child too.
        child_loop, child_task = handle["loop"], handle["task"]

        def _stop_child() -> None:
            try:
                child_loop.call_soon_threadsafe(child_task.cancel)
            except RuntimeError:  # the child's loop already closed: it finished
                pass

        (cancel_hooks.append if cancel_hooks is not None else on_tool_cancel)(_stop_child)
    if not done.wait(timeout_seconds):
        # timeout — cancel the child cooperatively and wait for its record to seal.
        ready.wait(1.0)  # the loop+task should exist by now; tiny wait covers the startup race
        loop, task = handle.get("loop"), handle.get("task")
        if loop is not None and task is not None:
            loop.call_soon_threadsafe(task.cancel)
            done.wait(_CANCEL_GRACE_SECONDS)  # let Runtime.run's finally seal the record
        raise TimeoutError(
            f"delegate child at {root} exceeded {timeout_seconds}s and was cancelled; its record is "
            "sealed at that root (no FinalAnswer)"
        )
    if box.get(
        "cancelled"
    ):  # only reachable if cancelled without a timeout (not on the normal path)
        raise TimeoutError(f"delegate child at {root} was cancelled")
    if "error" in box:
        raise box["error"]
    events = list(
        api.read_record(root, resolve_blobs=True)
    )  # Sprint 095: a FinalAnswer may exceed 16 KiB
    answer = next((e for e in events if e["kind"] == FINAL_ANSWER), None)
    if answer is None:
        raise ValueError(f"delegate child at {root} produced no FinalAnswer")
    payload = answer["payload"]
    return str(payload.get("text", "")), int(payload.get("steps", 0))


def _default_child_factory(
    responder: Responder,
    suite_factory: SuiteFactory,
    depth: int,
    max_depth: int,
    max_children: int,
    max_total_children: int,
    tree_budget: dict[str, int],
    child_max_steps: int,
    timeout_seconds: float | None,
    model_resolver: Callable[[str], Responder] | None = None,
) -> ChildFactory:
    """The child is a real tool_loop agent (walkthrough mode — it runs `responder` on the delegated task)
    over `suite_factory(workspace_root)`, plus a DEEPER delegate (depth+1) when the chain has room — so a
    delegated agent can itself delegate, bounded by max_depth, inheriting the same suite factory and
    `model_resolver`. A nested delegate roots at the DELEGATION dir (`workspace_root.parent`), not the
    workspace, so a grandchild's record is a sibling of this child's workspace — never underneath it
    (review C-1). A CLI responder runs in the child's workspace (UI sprint 115)."""
    from . import tool_loop_topology

    def factory(task: str, workspace_root: Path) -> Callable[[api.TopologyBuilder], None]:
        workspace_root.mkdir(parents=True, exist_ok=True)
        suite = suite_factory(workspace_root)
        if depth + 1 < max_depth:
            suite = {
                **suite,
                "delegate": make_delegate(
                    responder=responder,
                    root=workspace_root.parent,
                    child_suite_factory=suite_factory,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_children=max_children,
                    max_total_children=max_total_children,
                    tree_budget=tree_budget,
                    child_max_steps=child_max_steps,
                    timeout_seconds=timeout_seconds,
                    model_resolver=model_resolver,
                ),
            }
        return tool_loop_topology(
            model=_in_workspace(responder, workspace_root),
            task=task,
            tools=suite,
            walkthrough=True,  # run the REAL model on the REAL task (F-2), never the scripted demo
            max_steps=child_max_steps,
            deterministic=False,
        )

    return factory


def _in_workspace(responder: Responder, workspace_root: Path) -> Responder:
    """`responder` as the child runs it. A CLI agent reads and writes relative to the directory it
    starts in, so a CLI responder is rebound to the child's workspace; the parent's responder, or a
    resolver's cached one, ran in the parent's workspace or the daemon's own directory (UI sprint
    115). Any other responder has no directory and is used as is."""
    if isinstance(responder, CliResponder):
        return responder.at(workspace_root)
    return responder


def _default_model_resolver(name: str) -> Responder:
    """The substrate-side fallback when the daemon injects nothing: `deterministic`
    is the CI-mode stand-in; every other name is treated as an Ollama tag.

    The daemon (substrate-ui/server.py `_agent_models`) injects its own richer
    resolver at construction time — one that knows the CLI shells (Claude, Gemini,
    Codex) and the rate-limited wrappers. This fallback keeps the substrate-side
    tests self-contained without pulling substrate-ui into the boundary (F-API-6).
    """
    if name == DriverFamily.DETERMINISTIC:
        return DeterministicResponder(seed=0)
    return OllamaResponder(name)


def prefix_context_slice(
    parent_record_root: Path,
    task: str,
    context: dict[str, Any],
) -> str:
    """Build a child task string prefixed with the extracted parent-record slice.

    Today's delegate drives tool_loop children; tool_loop has no PromptFragment
    surface, so path-3 context rides on the task string. A session-shaped child
    can take the same slice as a `parent_context` PromptFragment instead
    (`session_topology(parent_context=...)`); both paths call
    `session/context_slice.py::extract_context_slice`."""
    seq_range_raw = context.get("parent_seq_range")
    if isinstance(seq_range_raw, (list, tuple)) and len(seq_range_raw) == 2:
        seq_range: tuple[int, int] = (int(seq_range_raw[0]), int(seq_range_raw[1]))
    else:
        seq_range = (0, 2**31)
    kinds_raw = context.get("kinds") or ()
    kinds: tuple[str, ...] = tuple(str(k) for k in kinds_raw) if kinds_raw else ()
    text, _elided_count, _elided_bytes, _single_oversize = extract_context_slice(
        parent_record_root, seq_range, kinds, cap_bytes=_CONTEXT_SLICE_CAP_BYTES
    )
    if not text:
        return task
    header = (
        f"[context from parent record — seq {seq_range[0]}..{seq_range[1]}, kinds={list(kinds)}]"
    )
    return f"{header}\n{text}\n---\n{task}"


def _with_baseline(
    topology: Callable[[api.TopologyBuilder], None],
    merged: dict[str, Any],
) -> Callable[[api.TopologyBuilder], None]:
    """Wrap a topology so its builder gets `b.baseline(**merged)` called after the
    inner topology registers everything else. Used to inject per-call `baseline`
    overrides and provenance (`parent_session_id`, `parent_seq_at_call`) into the
    child's `substrate.RunStarted.payload.baseline` for downstream `trace_ancestry`.
    """
    if not merged:
        return topology

    def wrapped(b: api.TopologyBuilder) -> None:
        topology(b)
        b.baseline(**merged)

    return wrapped


def _run_fanout(
    *,
    children_spec: Any,
    spawned: dict[str, int],
    tree_budget: dict[str, int],
    max_children: int,
    depth: int,
    r: Path,
    session_registry: "SessionRegistry | None",
    parent_session_id: str | None,
    parent_record_root: Path | None,
    model_resolver: Callable[[str], Any] | None,
    per_call_timeout: float | None,
) -> dict[str, Any]:
    """Fan-out execution: mint N sessions in parallel through
    SessionRegistry.create + turn_sync, wait for all to Park or End,
    fold the answers into one ToolResult shape.

    Every child is a session. No new topology. Per
    delegation-research-r5. Partial fold: answers and failed are disjoint
    maps keyed by child name; ok:false only when every child failed.
    """
    if session_registry is None:
        raise ValueError(
            "delegate: children requires session_registry — the daemon injects one "
            "(substrate-ui/server.py); no registry was bound"
        )
    if not isinstance(children_spec, (list, tuple)) or not children_spec:
        raise ValueError("delegate: children must be a non-empty list of session specs")
    # Normalise and name every child; validate name uniqueness.
    normalised: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for idx, entry in enumerate(children_spec):
        if not isinstance(entry, Mapping):
            raise ValueError(f"delegate: children[{idx}] must be a dict of session spec fields")
        spec = dict(entry)
        name = str(spec.get("name") or f"c{idx}")
        if name in seen_names:
            raise ValueError(
                f"delegate: children carry duplicate name {name!r}; names must be unique"
            )
        seen_names.add(name)
        spec["_name"] = name
        normalised.append(spec)
    n_children = len(normalised)
    # Cap checks — per-parent AND tree-wide.
    if spawned["n"] + n_children > max_children:
        raise ValueError(
            f"delegate: fan-out of {n_children} would exceed max_children={max_children} "
            f"(already spawned {spawned['n']}); refuse"
        )
    if tree_budget["remaining"] < n_children:
        raise ValueError(
            f"delegate: fan-out of {n_children} exceeds tree budget "
            f"(remaining={tree_budget['remaining']})"
        )
    spawned["n"] += n_children
    tree_budget["remaining"] -= n_children

    from ..session import UserMessage

    # UI sprint 102: the children run on executor threads, which do not inherit context
    # variables; capture this tool call's cancel hooks here so each child can register its stop.
    parent_cancel_hooks = _TOOL_CANCEL_HOOKS.get()

    # Kick off N sessions in parallel via SessionRegistry.create + turn_sync.
    def _run_one(spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        name = spec["_name"]
        task = str(spec.get("task", ""))
        driver = str(spec.get("driver") or "deterministic")
        workspace = spec.get("workspace")
        workspace_shape = str(spec.get("workspace_shape") or "flat")
        bundle = spec.get("bundle", "session")
        tools_raw = spec.get("tools")
        tools = tuple(str(t) for t in tools_raw) if tools_raw else None
        # Session_id fresh per child; workspace defaults to a child of the
        # delegation dir so records live where prior delegate calls did.
        session_id = f"s_{uuid.uuid4().hex[:24]}"
        if workspace is None:
            workspace = str(r / "delegate-runs" / f"fan-{session_id}" / "workspace")
            Path(workspace).mkdir(parents=True, exist_ok=True)
        try:
            manifest = session_registry.create(
                session_id=session_id,
                name=str(spec.get("session_name")) if spec.get("session_name") else None,
                driver=driver,
                workspace=str(workspace),
                workspace_shape=workspace_shape,
                bundle=str(bundle) if bundle is not None else None,
                seed="",
                role="default",
                tools=tools,
                driver_params=None,
            )
        except Exception as exc:  # noqa: BLE001 — surface as a per-child failure
            return name, {
                "error": f"session_create_failed: {type(exc).__name__}: {exc}",
                "child_root": "",
                "steps": -1,
                "ok": False,
            }
        resume_event = UserMessage(
            text=task,
            turn_index=0,
            assembled_prompt="",
            slash_source="delegate",
        )
        if parent_cancel_hooks is not None:
            # interrupting the parent's turn interrupts this child's turn (UI sprint 102)
            parent_cancel_hooks.append(_interrupter(session_registry, session_id))
        try:
            _final_manifest, record_root = session_registry.turn_sync(
                session_id, resume_event, timeout_seconds=per_call_timeout
            )
        except Exception as exc:  # noqa: BLE001 — surface as a per-child failure
            return name, {
                "error": f"turn_failed: {type(exc).__name__}: {exc}",
                "child_root": str(Path(manifest.record_root)),
                "steps": -1,
                "ok": False,
            }
        # Read the tail FinalAnswer off this child's record.
        finals = turn_replies(_iter_record(Path(record_root)))
        if not finals:
            return name, {
                "error": "no_final_answer",
                "child_root": str(record_root),
                "steps": -1,
                "ok": False,
            }
        answer = finals[-1][1]
        return name, {"answer": answer, "child_root": str(record_root), "steps": -1, "ok": True}

    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=n_children) as executor:
        futures = [executor.submit(_run_one, spec) for spec in normalised]
        for fut in futures:
            name, entry = fut.result()
            results[name] = entry

    answers: dict[str, str] = {}
    failed: dict[str, dict[str, Any]] = {}
    child_roots: dict[str, str] = {}
    steps: dict[str, int] = {}
    for name, entry in results.items():
        child_roots[name] = entry["child_root"]
        steps[name] = entry["steps"]
        if entry.get("ok"):
            answers[name] = entry["answer"]
        else:
            failed[name] = {
                "error": entry.get("error", "unknown"),
                "failure_class": _classify_failure(entry.get("error")),
            }

    ok = len(answers) > 0
    result: dict[str, Any] = {
        "ok": ok,
        "answers": answers,
        "child_roots": child_roots,
        "steps": steps,
    }
    if failed:
        result["failed"] = failed
    result["via"] = f"fanout:{n_children}"
    return result


def _iter_record(record_root: Path) -> Any:
    """Read a record's events. Small wrapper so _run_fanout does not
    couple directly to api.read_record; keeps testing easier."""
    from ... import api

    return list(api.read_record(record_root, resolve_blobs=True))  # Sprint 095


def _classify_failure(error: Any) -> str:
    """Cheap classification of a fan-out child's failure string. Any
    'no_final_answer' → 'no_answer'; anything else → 'error'."""
    if not isinstance(error, str):
        return "error"
    if "no_final_answer" in error:
        return "no_answer"
    if "session_create_failed" in error:
        return "create_failed"
    if "turn_failed" in error:
        return "turn_failed"
    return "error"


def _unique_child_root(base: Path, depth: int, start: int) -> tuple[Path, int]:
    """A delegation dir (holding the child's `workspace/` + `record/`) that does not already exist on
    disk. Probing disk (not just an in-memory counter) is what prevents a FRESH delegate instance in a
    persistent workspace from reusing `d1-c1` and appending onto a sealed record — the RecordGapError
    data-loss path (review F-3)."""
    n = start
    child_root = base / f"d{depth + 1}-c{n}"
    while child_root.exists():
        n += 1
        child_root = base / f"d{depth + 1}-c{n}"
    return child_root, n


def make_delegate(
    *,
    child_factory: ChildFactory | None = None,
    responder: Responder | None = None,
    root: Path | str = ".",
    child_suite_factory: SuiteFactory | None = None,
    child_record_root: Callable[[int], Path] | None = None,
    depth: int = 0,
    # Sprint 245: defaults bumped from the old delegation-conservative values
    # (max_depth=2, max_children=4) to values that support real fan-out
    # orchestration per delegation-research-r5. max_depth=5 matches Claude
    # Code's built-in subagent cap and shell direction section 20f's five-level
    # illustration. max_children=16 is four times the vertical cap per the
    # Architect's steer that horizontal should be looser. max_total_children
    # is new: a tree-wide budget shared by every descendant delegate call
    # under the same root, refuses when exhausted regardless of per-parent
    # fan-out or chain depth. All three caps: any one firing refuses.
    max_depth: int = 5,
    max_children: int = 16,
    max_total_children: int = 64,
    # Tree budget counter; when None (root call), a fresh dict is made and
    # inherited down through _default_child_factory to every descendant.
    tree_budget: dict[str, int] | None = None,
    child_max_steps: int = 6,
    timeout_seconds: float | None = None,
    # Sprint 212 added the daemon-injected fields; sprint 213a wires paths 2/3/4
    # against them and stubs path 1 for sprint 213b. Every kwarg defaults None so
    # every existing `make_delegate(...)` call in the tree keeps working.
    # Sprint 054 phase C: retyped `Any` -> `SessionRegistry | None` after the
    # registry moved into substrate (was substrate-ui-side, F-API-6 forbade the
    # import from here, hence the Any escape hatch — no longer needed).
    session_registry: "SessionRegistry | None" = None,
    parent_session_id: str | None = None,
    parent_record_root: Path | None = None,
    # Sprint 213a: path 2 needs a caller-supplied string → Responder resolver. The
    # daemon (substrate-ui/server.py `_agent_models`) injects its own richer resolver;
    # substrate ships the small `_default_model_resolver` fallback (deterministic +
    # OllamaResponder) so substrate-side tests self-contain.
    model_resolver: Callable[[str], Responder] | None = None,
) -> Tool:
    """A `delegate` Tool the caller composes into a tool_loop suite: `{**full_suite(root), "delegate":
    make_delegate(responder=..., root=...)}`. Calling `delegate(task)` runs a child agent on `task` to a
    FinalAnswer at its own record root and returns `{answer, child_root, steps}`.

    The child runs the REAL model on the REAL task. Supply either `responder` (the default factory runs a
    tool_loop agent with it) or `child_factory` (what the child is — a session, a named topology, or a
    deterministic scripted agent for CI); one is required. `child_suite_factory(workspace_root) -> suite`
    builds the child's tools (default `full_suite`) — pass the parent's own suite builder so a restricted
    parent (e.g. read-only) yields a restricted child. The `full_suite` default matches `tools.py`'s
    full-autonomy posture and is the INTENDED default (Architect-ruled 2026-08-03, review C-9): a child is
    as capable as the suite it is given, restricted by passing a narrower `child_suite_factory`. The child's tools operate in a `workspace/` subdir
    of the delegation dir; its record lives in a sibling `record/` subdir, so the child cannot write over
    its own record (C-1). `child_record_root(n) -> Path` optionally REDIRECTS the child's record root (n is
    the fan-out index) — the cockpit uses it to place child records as flat served records so the UI can
    navigate to them (W2.2 follow-on); the workspace stays under the delegation dir either way. Depth and
    fan-out are capped; at either cap the call raises, which the loop turns into a typed ToolResult(ok=False)."""
    r = Path(root)
    if child_factory is None and responder is None:
        raise ValueError("make_delegate requires either a responder or a child_factory")
    suite_factory: SuiteFactory = child_suite_factory or full_suite
    # Sprint 245: shared tree budget. Root call mints one; descendant delegate
    # calls inherit the same dict so `remaining` decrements from a single
    # counter across the whole delegation tree. When it hits zero, refuse.
    if tree_budget is None:
        tree_budget = {"remaining": max_total_children}
    if child_factory is not None:
        factory: ChildFactory = child_factory
    else:
        if responder is None:  # guarded above
            raise ValueError("delegate needs a responder or a child_factory")
        factory = _default_child_factory(
            responder,
            suite_factory,
            depth,
            max_depth,
            max_children,
            max_total_children,
            tree_budget,
            child_max_steps,
            timeout_seconds,
            model_resolver,
        )
    spawned = {"n": 0}  # per-instance fan-out counter (the factory is built once per run)

    # `session_registry` stays typed `Any`: the daemon injects a
    # `substrate_ui.session_registry.SessionRegistry` at call time; substrate itself
    # holds no dependency on the substrate-ui module (F-API-6 stays honest).
    # The `run` closure below captures the parameter directly — no local rebind needed.

    def run(a: list[Any]) -> dict[str, Any]:
        # Parse per-call args from either a dict (the x-args-passthrough path from
        # tools.py::_named_to_positional) or a plain string (backwards-compat).
        # Sprint 053 widened this to Mapping when the runtime sealed inputs (MappingProxyType
        # failed `isinstance(a[0], dict)` and every kwarg past `task` was dropped). Since K267 a
        # Producer's input is a plain decode of the record; the check stays general.
        if a and isinstance(a[0], Mapping):
            args_dict = dict(a[0])
        elif a:
            args_dict = {"task": str(a[0])}
        else:
            args_dict = {"task": ""}
        task = str(args_dict.get("task", ""))
        per_call_model = args_dict.get("model")
        per_call_session_name = args_dict.get("child_session_name")
        per_call_context = args_dict.get("context")
        per_call_baseline = args_dict.get("baseline")
        per_call_children = args_dict.get("children")
        per_call_timeout_raw = args_dict.get("timeout_seconds")
        per_call_timeout = (
            float(per_call_timeout_raw) if per_call_timeout_raw is not None else timeout_seconds
        )

        if depth >= max_depth:
            raise ValueError(
                f"delegate: max delegation depth ({max_depth}) reached — solve it directly"
            )
        # Sprint 245: fan-out path branches here.
        if per_call_children is not None:
            return _run_fanout(
                children_spec=per_call_children,
                spawned=spawned,
                tree_budget=tree_budget,
                max_children=max_children,
                depth=depth,
                r=r,
                session_registry=session_registry,
                parent_session_id=parent_session_id,
                parent_record_root=parent_record_root,
                model_resolver=model_resolver,
                per_call_timeout=per_call_timeout,
            )
        if spawned["n"] >= max_children:
            raise ValueError(
                f"delegate: max children ({max_children}) already spawned by this agent"
            )
        if tree_budget["remaining"] <= 0:
            raise ValueError(
                f"delegate: tree budget exhausted (max_total_children={max_total_children}) — "
                "the whole delegation tree cannot spawn another child"
            )
        tree_budget["remaining"] -= 1

        # Compute the parent record's seq at delegate-call time. `parent_seq_at_call`
        # is the seq of the LAST envelope on the parent record at this moment — the
        # ToolCall that fired us (or the tick immediately before it) — for downstream
        # `api.trace_ancestry` to walk parent → child → parent.
        parent_seq_at_call: int | None = None
        if parent_record_root is not None and Path(parent_record_root).exists():
            try:
                count = sum(1 for _ in api.read_record(parent_record_root))
                parent_seq_at_call = count - 1 if count > 0 else None
            except Exception:  # noqa: BLE001 — a stale/torn parent record is not our concern
                parent_seq_at_call = None

        # ── path 1: standing session ──────────────────────────────────────────
        if per_call_session_name is not None:
            if session_registry is None:
                raise ValueError(
                    f"delegate: child_session_name={per_call_session_name!r} requires "
                    "session_registry at construction (daemon injects it via "
                    "substrate-ui/server.py); no registry was bound"
                )
            resolved = session_registry.by_name(str(per_call_session_name))
            if resolved is None:
                raise ValueError(f"delegate: unknown session name: {per_call_session_name!r}")
            # Import the session vocab lazily to avoid dragging session_topology
            # into every tool_loop test that does not touch the standing-session path.
            from ..session import UserMessage
            from ..session.vocabulary import USER_MESSAGE

            # Reviewer's turn_index is the reviewer's own per-turn counter, NOT the
            # parent's record seq (review finding 1): the reviewer's tail UserMessage
            # turn_index + 1, or 0 when it has none. The index and the tail-seq snapshot
            # are read UNDER the session's turn lock (turn_sync's resume_event_builder):
            # read before it, two parents delegating at once got the same turn_index, and
            # a parent could take the other parent's FinalAnswer (UI sprint 109, N003).
            snapshot = {"tail_seq": -1}

            def _build(_manifest: Any, reviewer_record_path: Path) -> Any:
                next_turn_index = 0
                tail_seq = -1
                if reviewer_record_path.exists():
                    for env in api.read_record(reviewer_record_path):
                        tail_seq = max(tail_seq, int(env.get("seq", -1)))
                        if env.get("kind") == USER_MESSAGE:
                            payload = env.get("payload") or {}
                            if isinstance(payload, dict) and "turn_index" in payload:
                                next_turn_index = int(payload["turn_index"]) + 1
                snapshot["tail_seq"] = tail_seq
                return UserMessage(
                    text=task,
                    turn_index=next_turn_index,
                    assembled_prompt="",
                    slash_source="delegate",
                )

            # interrupting the parent's turn interrupts the standing session's turn (UI sprint 102)
            on_tool_cancel(_interrupter(session_registry, resolved))
            try:
                _final_manifest, reviewer_root = session_registry.turn_sync(
                    resolved, timeout_seconds=per_call_timeout, resume_event_builder=_build
                )
            except SessionEndedMidTurn as exc:
                # Sprint 054 phase C: the exception is imported directly now
                # that SessionRegistry lives in substrate. The pre-054 hack —
                # `if type(exc).__name__ == "SessionEndedMidTurn"` with a
                # bare `Exception` catch — was the workaround for the wrong
                # side of the F-API-6 boundary. Real typed catch replaces it.
                raise ValueError(
                    f"delegate: {SESSION_ENDED_MID_DELEGATE} ({per_call_session_name!r}): {exc}"
                ) from exc
            # This turn's FinalAnswer: the FIRST one past the snapshot taken under the
            # lock (review finding 2). An earlier turn's answer is at or below the
            # snapshot; a turn another parent queued after this one writes its answer
            # later, so it is never the first. A turn with no FinalAnswer raises.
            reviewer_tail_seq_before_turn = snapshot["tail_seq"]
            this_turn_finals = [
                (seq, text)
                for seq, text in turn_replies(
                    api.read_record(Path(reviewer_root), resolve_blobs=True)  # Sprint 095
                )
                if seq > reviewer_tail_seq_before_turn
            ]
            if not this_turn_finals:
                raise ValueError(
                    f"delegate: standing session {per_call_session_name!r} produced no "
                    f"FinalAnswer for this turn (reviewer tail seq at turn start: "
                    f"{reviewer_tail_seq_before_turn})"
                )
            answer_text = this_turn_finals[0][1]
            return {
                "answer": answer_text,
                "child_root": str(reviewer_root),
                "steps": -1,
                "via": f"standing_session:{per_call_session_name}",
            }

        # ── path 2: different-driver child ────────────────────────────────────
        if per_call_model is not None:
            resolver = model_resolver or _default_model_resolver
            try:
                resolved_responder = resolver(str(per_call_model))
            except Exception as exc:  # noqa: BLE001 — surface as typed tool failure
                raise ValueError(
                    f"delegate: unknown model {per_call_model!r}: {type(exc).__name__}: {exc}"
                ) from exc
            run_factory: ChildFactory = _default_child_factory(
                resolved_responder,
                suite_factory,
                depth,
                max_depth,
                max_children,
                max_total_children,
                tree_budget,
                child_max_steps,
                per_call_timeout,
                model_resolver,
            )
            via = f"different_driver:{per_call_model}"
        elif per_call_context is not None:
            # ── path 3: same-driver child with context slice ──────────────────
            run_factory = factory
            via = "context_slice"
        else:
            # ── path 4: fresh child on parent driver (unchanged from sprint 212) ──
            run_factory = factory
            via = None  # keep the return shape identical to pre-213 for backwards compat

        # Path 3: prefix the extracted parent-record slice to the task.
        effective_task = task
        if per_call_context is not None and parent_record_root is not None:
            if isinstance(per_call_context, dict):
                effective_task = prefix_context_slice(
                    Path(parent_record_root), task, per_call_context
                )

        # Allocate a fresh delegation dir (F-3): reuse would append onto a sealed
        # record and lose data.
        delegation_dir, n = _unique_child_root(r / "delegate-runs", depth, spawned["n"])
        spawned["n"] = n + 1
        workspace_root = delegation_dir / "workspace"
        record_root = (
            child_record_root(n) if child_record_root is not None else delegation_dir / "record"
        )

        # Merge per-call baseline + provenance into a single TopologyBuilder.baseline() call.
        # The provenance keys `parent_session_id` and `parent_seq_at_call` are reserved for
        # constructor-injected values — a per-call baseline cannot spoof them, even when the
        # constructor did NOT set them (review finding 6). Strip the reserved keys off the
        # per-call dict BEFORE the merge; the constructor values then land unconditionally.
        merged_baseline: dict[str, Any] = {}
        if isinstance(per_call_baseline, dict):
            filtered = {
                k: v
                for k, v in per_call_baseline.items()
                if k not in ("parent_session_id", "parent_seq_at_call")
            }
            merged_baseline.update(filtered)
        if parent_session_id is not None:
            merged_baseline["parent_session_id"] = parent_session_id
        if parent_seq_at_call is not None:
            merged_baseline["parent_seq_at_call"] = parent_seq_at_call

        inner_topology = run_factory(effective_task, workspace_root)
        topology = _with_baseline(inner_topology, merged_baseline)
        try:
            answer, steps = _run_child_to_answer(
                topology, record_root, timeout_seconds=per_call_timeout
            )
        finally:
            # UI sprint 103 (Claude Code: a foreground subagent's background commands stop when its
            # run ends): the child's suite owns its tasks by workspace path.
            from .background import TABLE

            TABLE.stop_owner(str(workspace_root.resolve()), "its delegated run ended")
        result: dict[str, Any] = {
            "answer": answer,
            "child_root": str(record_root),
            "steps": steps,
        }
        if via is not None:
            result["via"] = via
        return result

    return Tool(
        "delegate",
        "delegate(task, [model], [child_session_name], [context], [baseline], [timeout_seconds]) -> "
        "{answer, child_root, steps}: hand a self-contained subtask to a child agent; "
        "it runs to an answer as its own record and the answer folds back (SIDE EFFECT). "
        "model swaps the driver; child_session_name routes to a standing session; context selects "
        "parent events by seq range and kind; baseline overrides the child's TopologyBuilder baseline; "
        "timeout_seconds caps the child's wall clock",
        False,  # runs a real child agent — not deterministic in the pure sense
        run,
        # The schema travels WITH the tool (review C-10) so delegate is visible to native tool-calling
        # without tools.py needing to know delegate exists.
        #
        # `x-args-passthrough: true` is the sprint-212 opt-in that tells `_named_to_positional` in
        # `tools.py` to hand the full named-args dict to `Tool.run` as a single positional element
        # (rather than iterating schema properties in order, which stops at the first missing prop
        # and drops trailing optionals — see `tools.py` for the rationale). Delegate's five optional
        # kwargs need this: a model that sent `task` + `timeout_seconds` but skipped `model` in the
        # middle would otherwise lose `timeout_seconds` at the seam.
        {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "the self-contained subtask for the child",
                },
                "model": {
                    "type": "string",
                    "description": "optional driver override — a model tag like 'kimi-k2.6:cloud'",
                },
                "child_session_name": {
                    "type": "string",
                    "description": (
                        "optional standing-session name — routes the task to an existing named session "
                        "instead of a fresh child"
                    ),
                },
                "context": {
                    "type": "object",
                    "description": (
                        "optional slice of the parent's record to hand the child as prefix; "
                        "shape: {parent_seq_range: [int, int], kinds: [str, ...]}"
                    ),
                    "properties": {
                        "parent_seq_range": {"type": "array", "items": {"type": "integer"}},
                        "kinds": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "baseline": {
                    "type": "object",
                    "description": (
                        "optional override for the child TopologyBuilder's baseline — a bare dict "
                        "merged into whatever the child factory declares"
                    ),
                },
                "timeout_seconds": {
                    "type": "number",
                    "description": "optional per-call wall-clock cap (seconds); default 600.0",
                },
                "children": {
                    "type": "array",
                    "description": (
                        "optional fan-out. When present, spawn each entry as a "
                        "session in parallel; wait for all to Park or End; fold "
                        "one ToolResult with answers keyed by child name (partial "
                        "fold: successful children in answers, errored children "
                        "in failed). When children is set, ignore the single-child "
                        "fields above."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "task": {"type": "string", "description": "the child's task"},
                            "driver": {
                                "type": "string",
                                "description": "optional model tag for this child",
                            },
                            "workspace": {
                                "type": "string",
                                "description": "optional workspace path",
                            },
                            "workspace_shape": {
                                "type": "string",
                                "description": "flat | worktree; default flat",
                            },
                            "bundle": {
                                "type": "string",
                                "description": "optional session bundle; default session",
                            },
                            "tools": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "optional tools allowlist",
                            },
                            "isolate": {
                                "type": "boolean",
                                "description": "optional isolation flag",
                            },
                            "name": {
                                "type": "string",
                                "description": "optional stable name for this child; "
                                "defaults to c0, c1, ... by index",
                            },
                        },
                        "required": ["task"],
                    },
                },
            },
            "required": ["task"],
            "x-args-passthrough": True,
        },
    )


# spec-audit: 2026-09-01

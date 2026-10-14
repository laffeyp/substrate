# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""delegate — a session hands a subtask to a child session and the answer folds back (application-
parity W2.1; kernel sprint 323, research r8 § 4.6).

Every child is a session in the registry: it has a record, a pane a person can write to, and its
caller as its parent (`composite_of`), so ending or deleting the caller ends or deletes it. A child
runs on the model the call names, else on the caller's; in the caller's workspace; with the caller's
guidance bundle, length, tone and tool allow-list (a read-only caller makes a read-only child). Its
turn runs to the session's own step limit, and its answer is the tool's result. A call can instead
route the task to a standing session by name, or fan out to several children at once.

Before K323 the default child was a bare `tool_loop` agent capped at six steps, with no pane, and a
fan-out child with no driver ran on the deterministic stand-in.

CAPS. Depth counts the caller's ancestors in the registry (a child that delegates is one deeper);
`max_children` bounds how many children one tool instance starts; `max_total_children` bounds the
whole tree under the topmost ancestor. At any cap the call raises, which the loop records as a failed
`ToolResult` the model reads. Interrupting the caller's turn interrupts its children's turns.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ... import api
from ...errors import describe_error
from ..session.context_slice import extract_context_slice
from ..session.vocabulary import DELEGATE_SLASH_SOURCE, turn_replies
from ..session_registry import SessionEndedMidTurn, SessionManifest, SessionRegistry
from .tools import _TOOL_CANCEL_HOOKS, TOOL_NAME_DELEGATE, Tool, on_tool_cancel

# Sprint 224a — wire-error contract constant. The delegate raises a
# ValueError containing this tag when the reviewer session ended between
# the caller's resolve and the reach into `turn_sync`. tool_loop reads
# the string and shapes `ToolResult(ok=false, error=...)`. The daemon
# (substrate-ui/server.py) writes the same tag on `/turn` responses via
# its `session_errors.py` import. One string, one place.
SESSION_ENDED_MID_DELEGATE = "session_ended_mid_delegate"

_CONTEXT_SLICE_CAP_BYTES = 8192  # the tech spec explicit cap


def _interrupter(registry: SessionRegistry, session_id: str) -> Callable[[], None]:
    """A cancel hook that interrupts `session_id`'s running turn (hard tier), as ctrl+c would."""

    def stop() -> None:
        registry.interrupt(session_id, tier="hard")

    return stop


def prefix_context_slice(
    parent_record_root: Path,
    task: str,
    context: dict[str, Any],
) -> str:
    """The child's task prefixed with the slice of the caller's record that `context` selects
    (`session/context_slice.py::extract_context_slice`)."""
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


def _ancestors(registry: SessionRegistry, session_id: str) -> list[str]:
    """`session_id`'s parents, nearest first, through `composite_of`."""
    out: list[str] = []
    m = registry.get(session_id)
    while m is not None and m.composite_of and m.composite_of not in out:
        out.append(m.composite_of)
        m = registry.get(m.composite_of)
    return out


def _tree_size(registry: SessionRegistry, session_id: str) -> int:
    """How many sessions descend from the topmost ancestor of `session_id`."""
    top = ([session_id, *_ancestors(registry, session_id)])[-1]
    return len(registry.descendants(top))


def _iter_record(record_root: Path) -> Any:
    return list(api.read_record(record_root, resolve_blobs=True))  # Sprint 095


def _classify_failure(error: Any) -> str:
    """Cheap classification of a fan-out child's failure string."""
    if not isinstance(error, str):
        return "error"
    if "no_final_answer" in error:
        return "no_answer"
    if "session_create_failed" in error:
        return "create_failed"
    if "turn_failed" in error:
        return "turn_failed"
    return "error"


def _session_child(
    registry: SessionRegistry,
    parent: SessionManifest,
    *,
    task: str,
    driver: str,
    workspace: str,
    workspace_shape: str,
    bundle: str | None,
    tools: tuple[str, ...] | None,
    name: str | None,
    timeout_seconds: float | None,
    cancel_hooks: list[Callable[[], None]] | None,
) -> dict[str, Any]:
    """Open one child session under `parent`, run its first turn on `task`, and return its answer
    (`ok`, `answer` or `error`, `session_id`, `child_root`)."""
    session_id = f"s_{uuid.uuid4().hex[:24]}"
    try:
        manifest = registry.create(
            session_id=session_id,
            name=name,
            driver=driver,
            workspace=workspace,
            workspace_shape=workspace_shape,
            bundle=bundle,
            seed="",
            role="default",
            tools=tools,
            composite_of=parent.session_id,
            driver_params=None,  # a parent's knobs (or its script) are not the child's
            length=parent.length,
            tone=parent.tone,
        )
    except Exception as exc:  # noqa: BLE001 — surfaced as this child's failure
        return {
            "ok": False,
            "error": f"session_create_failed: {describe_error(exc)}",
            "session_id": session_id,
            "child_root": "",
        }
    from ..session import UserMessage

    if cancel_hooks is not None:
        # interrupting the parent's turn interrupts this child's turn (UI sprint 102)
        cancel_hooks.append(_interrupter(registry, session_id))
    try:
        _final, record_root = registry.turn_sync(
            session_id,
            UserMessage(
                text=task, turn_index=0, assembled_prompt="", slash_source=DELEGATE_SLASH_SOURCE
            ),
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001 — surfaced as this child's failure
        return {
            "ok": False,
            "error": f"turn_failed: {describe_error(exc)}",
            "session_id": session_id,
            "child_root": str(manifest.record_root),
        }
    finals = turn_replies(_iter_record(Path(record_root)))
    if not finals:
        return {
            "ok": False,
            "error": "no_final_answer",
            "session_id": session_id,
            "child_root": str(record_root),
        }
    return {
        "ok": True,
        "answer": finals[-1][1],
        "session_id": session_id,
        "child_root": str(record_root),
    }


def make_delegate(
    *,
    session_registry: SessionRegistry,
    parent_session_id: str,
    parent_record_root: Path | None = None,
    # Sprint 245: max_depth=5 matches Claude Code's subagent cap; horizontal looser than vertical.
    max_depth: int = 5,
    max_children: int = 16,
    max_total_children: int = 64,
    timeout_seconds: float | None = None,
) -> Tool:
    """The `delegate` tool for the session `parent_session_id`. `delegate(task)` opens a child
    session on the caller's model and returns `{answer, session_id, child_root}`; `model` names
    another model, `context` prefixes a slice of the caller's record, `child_session_name` routes
    the task to a standing session, `children` fans out."""
    spawned = {"n": 0}  # children this tool instance started

    def _parent() -> SessionManifest:
        parent = session_registry.get(parent_session_id)
        if parent is None:
            raise ValueError(
                f"delegate: the calling session {parent_session_id!r} is not registered"
            )
        return parent

    def _reserve(n: int) -> None:
        if spawned["n"] + n > max_children:
            raise ValueError(
                f"delegate: {n} more children would exceed max_children={max_children} "
                f"(already started {spawned['n']})"
            )
        in_tree = _tree_size(session_registry, parent_session_id)
        if in_tree + n > max_total_children:
            raise ValueError(
                f"delegate: tree budget exhausted (max_total_children={max_total_children}; "
                f"{in_tree} sessions in this tree)"
            )
        spawned["n"] += n

    def run(a: list[Any]) -> dict[str, Any]:
        if a and isinstance(a[0], Mapping):
            args = dict(a[0])
        elif a:
            args = {"task": str(a[0])}
        else:
            args = {"task": ""}
        if "baseline" in args:
            raise ValueError(
                "delegate: `baseline` is not taken; a child session records its own environment"
            )
        task = str(args.get("task", ""))
        raw_timeout = args.get("timeout_seconds")
        timeout = float(raw_timeout) if raw_timeout is not None else timeout_seconds
        depth = len(_ancestors(session_registry, parent_session_id))
        if depth >= max_depth:
            raise ValueError(
                f"delegate: max delegation depth ({max_depth}) reached — solve it directly"
            )

        # ── a standing session ────────────────────────────────────────────
        standing = args.get("child_session_name")
        if standing is not None:
            return _to_standing(str(standing), task, timeout)

        parent = _parent()
        # ── fan-out ───────────────────────────────────────────────────────
        if args.get("children") is not None:
            return _fanout(parent, args["children"], timeout)

        # ── one child ─────────────────────────────────────────────────────
        _reserve(1)
        context = args.get("context")
        if isinstance(context, dict) and parent_record_root is not None:
            task = prefix_context_slice(Path(parent_record_root), task, context)
        model = args.get("model")
        child = _session_child(
            session_registry,
            parent,
            task=task,
            driver=str(model) if model else parent.driver,
            workspace=parent.workspace,
            workspace_shape="flat",
            bundle=parent.bundle,
            tools=parent.tools,
            name=None,
            timeout_seconds=timeout,
            cancel_hooks=_TOOL_CANCEL_HOOKS.get(),
        )
        if not child["ok"]:
            raise ValueError(f"delegate: the child session {child['session_id']}: {child['error']}")
        result: dict[str, Any] = {
            "answer": child["answer"],
            "session_id": child["session_id"],
            "child_root": child["child_root"],
        }
        if model:
            result["via"] = f"different_driver:{model}"
        elif context is not None:
            result["via"] = "context_slice"
        return result

    def _to_standing(name: str, task: str, timeout: float | None) -> dict[str, Any]:
        resolved = session_registry.by_name(name)
        if resolved is None:
            raise ValueError(f"delegate: unknown session name: {name!r}")
        from ..session import UserMessage
        from ..session.vocabulary import USER_MESSAGE

        # The standing session's turn_index and tail seq are read under its turn lock (the
        # builder runs inside turn_sync): read before it, two callers delegating at once got the
        # same turn_index and one could take the other's answer (UI sprint 109, N003).
        snapshot = {"tail_seq": -1}

        def _build(_manifest: Any, record_path: Path) -> Any:
            next_turn_index = 0
            tail_seq = -1
            if record_path.exists():
                for env in api.read_record(record_path):
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
                slash_source=DELEGATE_SLASH_SOURCE,
            )

        on_tool_cancel(_interrupter(session_registry, resolved))
        try:
            _final, root = session_registry.turn_sync(
                resolved, timeout_seconds=timeout, resume_event_builder=_build
            )
        except SessionEndedMidTurn as exc:
            raise ValueError(f"delegate: {SESSION_ENDED_MID_DELEGATE} ({name!r}): {exc}") from exc
        # This turn's answer: the first past the snapshot taken under the lock.
        finals = [
            (seq, text)
            for seq, text in turn_replies(api.read_record(Path(root), resolve_blobs=True))
            if seq > snapshot["tail_seq"]
        ]
        if not finals:
            raise ValueError(
                f"delegate: standing session {name!r} produced no FinalAnswer for this turn "
                f"(tail seq at turn start: {snapshot['tail_seq']})"
            )
        return {
            "answer": finals[0][1],
            "session_id": resolved,
            "child_root": str(root),
            "via": f"standing_session:{name}",
        }

    def _fanout(parent: SessionManifest, spec_raw: Any, timeout: float | None) -> dict[str, Any]:
        if not isinstance(spec_raw, (list, tuple)) or not spec_raw:
            raise ValueError("delegate: children must be a non-empty list of session specs")
        specs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for i, entry in enumerate(spec_raw):
            if not isinstance(entry, Mapping):
                raise ValueError(f"delegate: children[{i}] must be a dict of session spec fields")
            spec = dict(entry)
            name = str(spec.get("name") or f"c{i}")
            if name in seen:
                raise ValueError(
                    f"delegate: children carry duplicate name {name!r}; names must be unique"
                )
            seen.add(name)
            spec["_name"] = name
            specs.append(spec)
        _reserve(len(specs))
        hooks = _TOOL_CANCEL_HOOKS.get()  # executor threads do not inherit context variables

        def _one(spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
            tools_raw = spec.get("tools")
            return spec["_name"], _session_child(
                session_registry,
                parent,
                task=str(spec.get("task", "")),
                driver=str(spec.get("driver") or parent.driver),
                workspace=str(spec.get("workspace") or parent.workspace),
                workspace_shape=str(spec.get("workspace_shape") or "flat"),
                bundle=str(spec["bundle"]) if spec.get("bundle") else parent.bundle,
                tools=tuple(str(t) for t in tools_raw) if tools_raw else parent.tools,
                name=str(spec["session_name"]) if spec.get("session_name") else None,
                timeout_seconds=timeout,
                cancel_hooks=hooks,
            )

        with ThreadPoolExecutor(max_workers=len(specs)) as pool:
            results = dict(pool.map(_one, specs))
        answers = {n: r["answer"] for n, r in results.items() if r["ok"]}
        failed = {
            n: {"error": r["error"], "failure_class": _classify_failure(r["error"])}
            for n, r in results.items()
            if not r["ok"]
        }
        out: dict[str, Any] = {
            "ok": bool(answers),
            "answers": answers,
            "session_ids": {n: r["session_id"] for n, r in results.items()},
            "child_roots": {n: r["child_root"] for n, r in results.items()},
            "via": f"fanout:{len(specs)}",
        }
        if failed:
            out["failed"] = failed
        return out

    return Tool(
        TOOL_NAME_DELEGATE,
        "delegate(task, [model], [child_session_name], [context], [timeout_seconds], [children]) -> "
        "{answer, session_id, child_root}: hand a self-contained subtask to a child session on "
        "your model; it works in its own pane and its answer folds back. model picks another "
        "model; child_session_name routes to a standing session; context hands the child a slice "
        "of your record; children fans out to several sessions at once",
        False,  # runs a real child session
        run,
        # The schema travels with the tool (review C-10); `x-args-passthrough` hands `run` the
        # whole named-args dict (sprint 212).
        {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "the self-contained subtask for the child",
                },
                "model": {
                    "type": "string",
                    "description": "optional model for the child; default: yours",
                },
                "child_session_name": {
                    "type": "string",
                    "description": (
                        "optional standing-session name — routes the task to an existing named "
                        "session instead of a new child"
                    ),
                },
                "context": {
                    "type": "object",
                    "description": (
                        "optional slice of your record to hand the child before its task; "
                        "shape: {parent_seq_range: [int, int], kinds: [str, ...]}"
                    ),
                    "properties": {
                        "parent_seq_range": {"type": "array", "items": {"type": "integer"}},
                        "kinds": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "timeout_seconds": {
                    "type": "number",
                    "description": "optional per-call wall-clock cap (seconds); default none",
                },
                "children": {
                    "type": "array",
                    "description": (
                        "optional fan-out: each entry runs as its own session at once; the result "
                        "holds the answers by name, and the failures apart. When set, the "
                        "single-child fields above are ignored."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "task": {"type": "string", "description": "the child's task"},
                            "driver": {
                                "type": "string",
                                "description": "optional model for this child; default: yours",
                            },
                            "workspace": {
                                "type": "string",
                                "description": "optional workspace path; default: yours",
                            },
                            "workspace_shape": {
                                "type": "string",
                                "description": "flat | worktree; default flat",
                            },
                            "bundle": {
                                "type": "string",
                                "description": "optional guidance bundle; default: yours",
                            },
                            "tools": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "optional tools allow-list; default: yours",
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


__all__ = ["SESSION_ENDED_MID_DELEGATE", "make_delegate", "prefix_context_slice"]

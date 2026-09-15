# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Session registry — the daemon-side name index + manifest catalog (sprint 211).

Piece C Named standing sessions are the
daily-driver's identity: `substrate chat --name reviewer` opens a persistent
record under `~/.substrate/sessions/<session_id>/`, and every later resume
finds it by the same name. The registry:

  - **In-memory** name → session_id + per-session `threading.Lock` map + the
    manifest for every session on disk. (The earlier draft carried an
    `asyncio.Lock` map alongside the threading one; piece-C review finding 3
    collapsed the two — every caller of `turn_sync`, delegate wire and daemon
    POST /turn handler alike, dispatches on a thread, so one primitive covers
    the invariant.)
  - **Persistent** name index at `~/.substrate/sessions/by-name.json`. Atomic
    writes under `fcntl.flock` on the file itself so a second creator with a
    colliding name gets a 409 shape, never a corrupted index.
  - **Per-session manifest** at `~/.substrate/sessions/<session_id>/manifest.json`,
    rewritten on every state change. The record is the source of truth; the
    manifest is a hint the boot scan reads to rebuild the in-memory catalog.
  - **Boot scan** walks `~/.substrate/sessions/*/`, checks each record's status
    via `api.recover_open_segment` (hot segment → `interrupted`) and read_record
    (RunFinalised present → `ended`; otherwise → `parked`), and rewrites the
    manifest status field to match reality.

Canonical home registry (WORKING_AGREEMENT.md) lists:
  - Session manifest: `~/.substrate/sessions/<session_id>/manifest.json`
  - Name → session_id index: `~/.substrate/sessions/by-name.json`
  - Session registry (in-memory): this module.

Everything material rides the record. The manifest is recoverable from the
record's `substrate.RunStarted` payload alone (`runtime.py:_manifest:452-532`);
this module keeps it as a hint so a daemon boot does not need to open every
record's writer just to enumerate what exists.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

# `asyncio` is still imported: `_run_resume_sync` runs Runtime.resume on a fresh
# per-call event loop inside a worker thread. The per-session lock itself is a
# threading.Lock (see the __init__ note), not an asyncio.Lock.

from msgspec import Struct

from substrate import api
from substrate.adapters import DriverParamKey

if TYPE_CHECKING:
    from substrate.api import TopologyBuilder


class SessionStatus(StrEnum):
    """The four SessionManifest.status values. Sprint 070: promoted from
    `Literal["running", ...]` + four STATUS_* string constants (the
    inline-subset-enumeration antipattern) to a proper StrEnum. Members
    still compare `==` with the underlying string; msgspec Struct fields
    typed as `SessionStatus` serialise as string on the wire. Existing
    STATUS_* module constants below stay as aliases for backwards compat
    during the sweep (drop in a follow-up)."""

    RUNNING = "running"
    PARKED = "parked"
    INTERRUPTED = "interrupted"
    ENDED = "ended"


class WorkspaceShape(StrEnum):
    """SessionManifest.workspace_shape. Sprint 070: raw-string field
    values become typed enum members. Three values per the daemon's
    three workspace modes."""

    FLAT = "flat"
    WORKTREE = "worktree"
    ISOLATE = "isolate"


_SESSIONS_BASE_DEFAULT = Path.home() / ".substrate" / "sessions"
_BY_NAME_FILENAME = "by-name.json"
_BY_NAME_LOCK_FILENAME = ".by-name.lock"
_MANIFEST_FILENAME = "manifest.json"


class SessionManifest(Struct, frozen=True):
    """The on-disk hint the boot scan reads to rebuild the in-memory registry.

    Fields match the tech spec `status` is one of `running`
    (a daemon has a live Runtime on the record), `parked` (the record is at
    pause_await_input awaiting the next UserMessage), `interrupted` (the
    record has a torn hot segment — the daemon died mid-turn), `ended` (the
    record has a RunFinalised envelope).
    """

    session_id: str
    name: str | None
    created_at: float
    driver: str
    workspace: str
    workspace_shape: str
    record_root: str
    status: SessionStatus
    bundle: str | None
    seed: str
    # Sprint 217e: tool allow-list. `None` means "no restriction — use full_suite".
    # An empty tuple `()` also means unrestricted; a non-empty tuple filters
    # `full_suite(workspace_path)` down to the named tools before the topology
    # is built. Persists across parks (mutable via PATCH /api/session/<id>).
    tools: tuple[str, ...] | None = None
    # Sprint 223a: role name resolved via the four-layer fallback at
    # `substrate.topologies.session.roles.resolve_role_prompt`. The manifest
    # stores the NAME, not the resolved text — a rename of the on-disk
    # prompt file at layer 1 propagates on the next resume without touching
    # the manifest. Default "default" resolves to the shipped prompt.
    role: str = "default"
    # Sprint 223d: per-turn text prefixed to every UserMessage's
    # assembled_prompt (spec the topology-layer contract). Empty string means no prefix.
    # Mutable via PATCH /api/session/<id> {per_turn}.
    per_turn: str = ""
    # Sprint 225b: composite parent linkage. `None` for standalone
    # sessions. For a child sub-agent in a session composite (e.g.
    # sprint 225c's pair_coding reviewer), holds the parent's session_id.
    # POST /end and DELETE on the parent cascade to every child via
    # list_children(parent_id). The relationship is one level deep — a
    # child of a child is not a supported shape.
    composite_of: str | None = None
    # Sprint 032c (piece-G mechanical translation): per-session driver
    # params. `OllamaResponder.__init__` accepts think/max_tokens/timeout/
    # num_ctx at construction (adapters/models.py:133-165); the daemon's
    # `_daemon_driver_resolver(name, params)` threads this dict into the
    # Responder build. None means "use responder defaults." Absent keys
    # in the dict mean the same. Persisted across parks; mutable via
    # PATCH /api/session/<id> {driver_params}.
    #
    # Recognized keys (validated at set-time): "think" (bool),
    # "max_tokens" (int ≥0; 0 = uncapped), "timeout" (float >0, seconds),
    # "num_ctx" (int ≥1). Unknown keys are 400 at PATCH.
    driver_params: dict[str, Any] | None = None


class NameCollision(Exception):
    """Raised when a create hits an existing name in the by-name.json index.

    Carries the existing session_id so the caller can shape a 409 response.
    """

    def __init__(self, name: str, existing_session_id: str) -> None:
        super().__init__(f"session name {name!r} already taken by {existing_session_id!r}")
        self.name = name
        self.existing_session_id = existing_session_id


class SessionEndedMidTurn(Exception):
    """Raised by `turn_sync` when the target session has already ended (or ended
    between the caller's resolve and the .resume() call). The delegate seam
    (sprint 213b) surfaces this as `ToolResult(ok=False, error="session_ended_mid_delegate")`.
    """


class FreshSessionRequiresUserMessage(Exception):
    """Sprint 217a: raised by `turn_sync` when the session's record is empty
    (no envelopes on disk yet) and the resume event is not a `UserMessage`.
    A fresh session opens via `Runtime.run(topology)` with a `session_open`
    producer emitting the first `UserMessage`; other kinds cannot open a run
    in that shape. `_shutdown_all_sessions` catches this and buckets the
    session as `skipped_fresh`, transitioning the manifest to `"ended"`
    without opening the record.
    """


class TornRecordOnResume(Exception):
    """Sprint 220b: raised by `turn_sync` when a session's record directory
    exists but `api.read_record` raises (RecordGapError, TornFrameError,
    CRCMismatchError, FsyncError, or any IO error). The daemon refuses to
    dispatch either primitive: `Runtime.run` on a directory with existing
    sealed segments would double-head the record; `Runtime.resume` would
    inherit the torn tail. The session is halted in-place — status flips
    to `interrupted`, the SSE stream stays readable, and the manifest
    carries the surfaced error text for the operator. Prior behavior
    (session_registry `_record_has_envelopes` swallowed every exception
    and returned False) silently dispatched `Runtime.run` on a corrupted
    record — reproduced by any process crash mid-turn.
    """

    def __init__(self, session_id: str, record_root: Path, cause: BaseException) -> None:
        super().__init__(
            f"session {session_id!r}: record at {record_root} is torn ({type(cause).__name__}: "
            f"{cause}); refusing to dispatch Runtime.run (would double-head) or Runtime.resume "
            f"(would inherit the torn tail). Fix: quarantine the record and open a new session."
        )
        self.session_id = session_id
        self.record_root = record_root
        self.cause = cause


class TurnHandle:
    """The running turn's event loop, task, and Runtime — populated by
    `_run_resume_sync`, read by `interrupt` to reach the worker thread's
    event loop without holding the per-session lock."""

    __slots__ = ("loop", "task", "runtime")

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.task: asyncio.Task[Any] | None = None
        self.runtime: api.Runtime | None = None


SessionTopologyFactory = Callable[
    ["SessionManifest", Any],  # (manifest, first_turn_user_message | None) → topology
    Callable[["TopologyBuilder"], None],
]


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write `data` to `path` atomically: write to a temp file in the same dir,
    fsync it, then rename. Rename-in-same-fs is atomic on POSIX; a crash mid-write
    leaves `path` at its prior good state or absent, never partially written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(prefix=".tmp.", dir=str(path.parent))
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(data, fp, indent=2, sort_keys=True)
            fp.flush()
            os.fsync(fp.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class SessionRegistry:
    """The daemon's in-memory session catalog + persistent name index.

    Owns three pieces of state:
      - `_by_name`: dict[str, str] mirroring `~/.substrate/sessions/by-name.json`.
      - `_manifests`: dict[str, SessionManifest] keyed by session_id.
      - `_turn_threading_locks`: dict[str, threading.Lock] — one lock per
        session for turn serialization (per product spec §6 "one turn at a
        time per session_id"). Every caller of `turn_sync` — delegate seam
        (tool_loop worker thread) and daemon POST /turn handler
        (ThreadingHTTPServer worker thread) — takes the same lock. The
        earlier `_locks: dict[str, asyncio.Lock]` map is gone (piece-C
        review finding 3).

    Not thread-safe in the general sense; the daemon runs one event loop, and
    the process-level lock lives at `~/.substrate/daemon.pid`. `fcntl.flock`
    on `by-name.json` protects against corruption from ANY writer, including a
    stray script or a second daemon that snuck past the pidfile guard.
    """

    def __init__(
        self,
        base: Path | None = None,
        *,
        session_topology_factory: SessionTopologyFactory | None = None,
        turn_queue_cap: int = 4,
        auto_boot: bool = True,
    ) -> None:
        self._base = Path(base) if base is not None else _SESSIONS_BASE_DEFAULT
        self._by_name: dict[str, str] = {}
        self._manifests: dict[str, SessionManifest] = {}
        # Sprint 216: per-session queued-turn counter for the /turn queue cap.
        # `try_enqueue_turn` increments under `_queue_depth_lock`; `dequeue_turn`
        # decrements after the handler finishes. Depth includes the currently
        # running turn plus every caller waiting on the per-session
        # threading.Lock — a fifth caller against `cap=4` is refused.
        self._turn_queue_cap = int(turn_queue_cap)
        self._queue_depths: dict[str, int] = {}
        self._queue_depth_lock = threading.Lock()
        # Sprint 215b: per-session handle to the running turn's event loop +
        # Runtime, so POST /interrupt can reach cancel_producers across the
        # thread boundary. Populated by turn_sync under the per-session lock;
        # read by interrupt() WITHOUT the lock (intentionally — the interrupt
        # must not block on a turn that holds the lock while running).
        self._running_handles: dict[str, TurnHandle] = {}
        # F14: per-session next turn_index counter, eliminating the O(n)
        # whole-record scan in _session_turn's _build closure. Populated at
        # boot_scan from the record tail; incremented by turn_sync on
        # completion. The counter lives here, not on SessionManifest, to
        # avoid schema growth for a runtime-only optimization.
        self._next_turn_index: dict[str, int] = {}
        # Per-session `threading.Lock` map. Every caller of turn_sync — the delegate
        # seam (sprint 213b, tool_loop worker thread) AND the daemon's POST
        # /api/session/<id>/turn handler (sprint 214a, ThreadingHTTPServer worker
        # thread) — acquires the same lock; no two Runtime.resume calls race the
        # same record's writer.
        #
        # Sprint 214a folded the piece-C review's finding 3: an earlier draft held
        # a second `asyncio.Lock` map for a hypothetical async POST /turn handler.
        # ThreadingHTTPServer dispatches every request on its own thread, so an
        # asyncio.Lock in that path was wrong-primitive dead weight. One lock, one
        # primitive, one invariant.
        self._turn_threading_locks: dict[str, threading.Lock] = {}
        # Sprint 213b: the callable the daemon injects at construction time to
        # rebuild a `session_topology` factory for a given manifest. `turn_sync`
        # invokes it once per call. When None (default), `turn_sync` raises so
        # the registry can be constructed in tests that never exercise the seam.
        self._session_topology_factory: SessionTopologyFactory | None = session_topology_factory
        self._base.mkdir(parents=True, exist_ok=True)
        # Sprint 055: hydrate from disk at construction time. A caller who
        # passes `auto_boot=False` keeps the old shape (empty in-memory
        # catalog until `.boot_scan()` fires). Every production caller
        # (substrate-ui/server.py at daemon start) called boot_scan
        # immediately after constructing, so the auto-boot is behaviourally
        # a no-op there. New callers (tests, CLIs, MCP clients) previously
        # got a silent bug — the registry looked empty even when disk had
        # sessions. `boot_scan` is idempotent; the explicit call the daemon
        # still makes at startup is safe.
        if auto_boot:
            try:
                self.boot_scan()
            except OSError as exc:
                # Boot at construction is best-effort. A permission-denied on
                # the base dir, or a mid-shutdown race, must NOT abort the
                # construction — the caller can still create fresh sessions.
                # Report loudly via warnings so the failure is not silent.
                import warnings

                warnings.warn(
                    f"SessionRegistry(base={self._base!r}): auto-boot scan failed "
                    f"({type(exc).__name__}: {exc}). The in-memory catalog is "
                    "empty; call `.boot_scan()` explicitly once the underlying "
                    "issue is resolved. Pass `auto_boot=False` to suppress this "
                    "path and take manual control of hydration timing.",
                    stacklevel=2,
                )

    # ── boot scan ──────────────────────────────────────────────────────────

    def boot_scan(self) -> list[str]:
        """Rebuild the in-memory registry from disk. Called once at daemon start.

        Reads `by-name.json` under a shared flock (concurrent readers OK). Walks
        every `<session_id>/` under `base` and, for each manifest present,
        classifies status against the record's last envelope: `substrate.RunFinalised`
        → `ended`; `substrate.TerminationMatched(decision="pause-await-input")` →
        `parked`; anything else → `interrupted`.

        Rewrites each manifest whose on-disk status disagrees with reality.
        Returns the list of session directories whose manifests were skipped
        because they could not be parsed — the daemon reports the count on
        stderr so a corrupt manifest does not vanish silently (review finding 12).
        """
        skipped: list[str] = []
        self._by_name = self._read_by_name_index()
        for session_dir in sorted(self._base.iterdir()):
            if not session_dir.is_dir():
                continue
            if session_dir.name == "wt":  # git-worktree subtree; not a session
                continue
            manifest_path = session_dir / _MANIFEST_FILENAME
            if not manifest_path.exists():
                continue
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = _manifest_from_dict(raw)
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                skipped.append(session_dir.name)
                continue
            # `"ended"` is terminal (SessionEnded fired or the daemon flipped
            # a fresh session at shutdown). Never re-derive it: `_scan_record_status`
            # returns `"parked"` for a missing record dir, which would overwrite
            # a fresh-session shutdown that had no record to write to. This was
            # the shape sprint 217a's shutdown path exposed — surfaced by the
            # `test_fresh_session_transitions_to_ended_and_survives_reboot` test.
            if manifest.status == SessionStatus.ENDED:
                true_status = SessionStatus.ENDED
            else:
                true_status = _scan_record_status(Path(manifest.record_root))
            if true_status != manifest.status:
                manifest = _replace(manifest, status=true_status)
                _atomic_write_json(manifest_path, _manifest_to_dict(manifest))
            self._manifests[manifest.session_id] = manifest
            # F14: derive the next turn_index from the record so _session_turn
            # does not need to scan the whole record on every POST /turn.
            self._next_turn_index[manifest.session_id] = _next_turn_index_from_record(
                Path(manifest.record_root)
            )
        # Prune stale by-name entries whose manifests dropped off disk.
        self._by_name = {name: sid for name, sid in self._by_name.items() if sid in self._manifests}
        self._write_by_name_index()
        return skipped

    # ── create / rename ────────────────────────────────────────────────────

    def create(
        self,
        *,
        session_id: str,
        name: str | None,
        driver: str,
        workspace: str,
        workspace_shape: str,
        bundle: str | None,
        seed: str,
        role: str = "default",
        tools: tuple[str, ...] | None = None,
        composite_of: str | None = None,
        created_at: float | None = None,
        driver_params: dict[str, Any] | None = None,
    ) -> SessionManifest:
        """Register a new session. Atomic against by-name.json under `fcntl.flock`.

        If `name` is set and already in the index, raises `NameCollision` with
        the existing session_id. The caller shapes the 409 response.
        """
        if seed:
            import warnings

            warnings.warn(
                "SessionManifest.seed is deprecated. The prompt-composition arc "
                "(sprints 058-067) moved every real prompt source to a "
                "PromptFragment producer; seed has no consumer inside the "
                "topology. Pass empty string; a future sprint drops the field.",
                DeprecationWarning,
                stacklevel=2,
            )
        manifest = SessionManifest(
            session_id=session_id,
            name=name,
            created_at=created_at if created_at is not None else time.time(),
            driver=driver,
            workspace=workspace,
            workspace_shape=workspace_shape,
            record_root=str(self._base / session_id / "record"),
            status=SessionStatus.RUNNING,
            bundle=bundle,
            seed=seed,
            role=role,
            tools=tools,
            composite_of=composite_of,
            driver_params=driver_params,
        )
        # Sprint 223e race fix: bridge finds a session by_name and dispatches
        # a turn immediately after create. Under flock, the by-name.json write
        # is safe, but if `_manifests[session_id] = manifest` lands AFTER the
        # flock releases, a concurrent bridge caller sees the name in the
        # index and calls `turn_sync`, which reads `_manifests.get(session_id)`
        # and raises KeyError before this thread finishes. Do the mkdir +
        # manifest.json + _manifests write INSIDE the flock so the whole
        # create commits atomically from a concurrent reader's perspective.
        session_dir = self._base / session_id
        if name is not None:
            with _flocked(self._base / _BY_NAME_FILENAME) as index:
                if name in index and index[name] != session_id:
                    raise NameCollision(name=name, existing_session_id=index[name])
                index[name] = session_id
                self._by_name = dict(index)
                session_dir.mkdir(parents=True, exist_ok=True)
                _atomic_write_json(session_dir / _MANIFEST_FILENAME, _manifest_to_dict(manifest))
                self._manifests[session_id] = manifest
        else:
            session_dir.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(session_dir / _MANIFEST_FILENAME, _manifest_to_dict(manifest))
            self._manifests[session_id] = manifest
        return manifest

    def set_name(self, session_id: str, name: str) -> SessionManifest:
        """Rename a session. Atomic against by-name.json. Raises `NameCollision`
        if the name is already in use by a different session.

        Red-team finding 4 (2026-08-26): the read-modify-write on
        ``_manifests[session_id]`` must hold the per-session lock so a
        concurrent ``update_status`` (called by ``turn_sync`` on turn
        completion) does not clobber this write or vice-versa.
        """
        if session_id not in self._manifests:
            raise KeyError(f"unknown session_id {session_id!r}")
        threading_lock = self._turn_threading_locks.setdefault(session_id, threading.Lock())
        with threading_lock:
            manifest = self._manifests.get(session_id)
            if manifest is None:
                raise KeyError(f"unknown session_id {session_id!r}")
            with _flocked(self._base / _BY_NAME_FILENAME) as index:
                if name in index and index[name] != session_id:
                    raise NameCollision(name=name, existing_session_id=index[name])
                if manifest.name is not None and manifest.name in index:
                    del index[manifest.name]
                index[name] = session_id
                self._by_name = dict(index)
            updated = _replace(manifest, name=name)
            _atomic_write_json(
                self._base / session_id / _MANIFEST_FILENAME, _manifest_to_dict(updated)
            )
            self._manifests[session_id] = updated
        return updated

    def set_tools(self, session_id: str, tools: tuple[str, ...] | None) -> SessionManifest:
        """Sprint 217e: change the session's tool allow-list. `None` and `()`
        both mean unrestricted; a non-empty tuple filters `full_suite(workspace)`
        down to those names before the topology is built. The next
        `Runtime.resume` reads the new list via `_build_session_topology_from_manifest`;
        the in-flight turn (if any) completes on its prior tool set.

        Holds the per-session lock so a concurrent `update_status` from
        `turn_sync` cannot clobber this write (same pattern as `set_driver`).

        Raises `KeyError` on unknown session_id.
        """
        if session_id not in self._manifests:
            raise KeyError(f"unknown session_id {session_id!r}")
        threading_lock = self._turn_threading_locks.setdefault(session_id, threading.Lock())
        with threading_lock:
            manifest = self._manifests.get(session_id)
            if manifest is None:
                raise KeyError(f"unknown session_id {session_id!r}")
            updated = _replace(manifest, tools=tools)
            _atomic_write_json(
                self._base / session_id / _MANIFEST_FILENAME, _manifest_to_dict(updated)
            )
            self._manifests[session_id] = updated
        return updated

    def set_per_turn(self, session_id: str, per_turn: str) -> SessionManifest:
        """Sprint 223d: change the session's per-turn prefix (spec the topology-layer contract).
        Same lock/write shape as `set_tools`. Empty string clears the prefix.
        The next `Runtime.resume` reads the new value via
        `_build_session_topology_from_manifest`.

        Raises `KeyError` on unknown session_id.
        """
        if session_id not in self._manifests:
            raise KeyError(f"unknown session_id {session_id!r}")
        threading_lock = self._turn_threading_locks.setdefault(session_id, threading.Lock())
        with threading_lock:
            manifest = self._manifests.get(session_id)
            if manifest is None:
                raise KeyError(f"unknown session_id {session_id!r}")
            updated = _replace(manifest, per_turn=per_turn)
            _atomic_write_json(
                self._base / session_id / _MANIFEST_FILENAME, _manifest_to_dict(updated)
            )
            self._manifests[session_id] = updated
        return updated

    def set_driver_params(self, session_id: str, params: dict[str, Any] | None) -> SessionManifest:
        """Change the per-session driver params mid-flight (piece G sprint 032c).

        `params` shape (all optional; unset keys mean "use responder default"):
          - "think"      (bool)             — Ollama thinking mode
          - "max_tokens" (int ≥ 0)          — cap; 0 = uncapped
          - "timeout"    (float > 0.0)      — request timeout, seconds
          - "num_ctx"    (int ≥ 1)          — Ollama context window override

        None clears every override — the resolver builds Responders with
        pure defaults again. An unknown key or wrong type raises
        ValueError (surfaced as 400 at the daemon boundary).

        In-memory catalog and manifest.json update atomically. The next
        `Runtime.resume` builds a fresh Responder via
        `_daemon_driver_resolver(driver, params)` — the cache key changes,
        so a new Responder instance lands. Existing turn-in-flight
        completes on its prior Responder; the next turn sees the new one.

        Same lock discipline as `set_driver` / `set_bundle` (red-team
        finding 4, 2026-08-26).

        Raises `KeyError` on unknown session_id;
        `ValueError` on unknown params key or wrong type.
        """
        if session_id not in self._manifests:
            raise KeyError(f"unknown session_id {session_id!r}")
        if params is not None:
            # Sprint 073: allowed-keys map keyed by DriverParamKey members
            # instead of raw strings. Any drift between the wire key and
            # a downstream check now trips at import time, not at a silent
            # missed-branch. DriverParamKey members compare `==` with str
            # so existing wire-shape passthrough is unchanged.
            allowed: dict[DriverParamKey, type | tuple[type, ...]] = {
                DriverParamKey.THINK: bool,
                DriverParamKey.MAX_TOKENS: int,
                DriverParamKey.TIMEOUT: (int, float),
                DriverParamKey.NUM_CTX: int,
            }
            allowed_names = {k.value for k in allowed}
            unknown = set(params.keys()) - allowed_names
            if unknown:
                raise ValueError(
                    f"driver_params: unknown keys {sorted(unknown)}; "
                    f"allowed: {sorted(allowed_names)}"
                )
            for key_enum, expected in allowed.items():
                key = key_enum.value
                if key not in params:
                    continue
                value = params[key]
                # bool is a subclass of int; guard bool-vs-int mixups first.
                if key_enum is DriverParamKey.THINK and not isinstance(value, bool):
                    raise ValueError(
                        f"driver_params.think must be a bool; got {type(value).__name__}"
                    )
                if key_enum is not DriverParamKey.THINK and isinstance(value, bool):
                    raise ValueError(f"driver_params.{key} must be numeric, not bool")
                if not isinstance(value, expected):
                    exp_name = (
                        expected.__name__
                        if isinstance(expected, type)
                        else "|".join(t.__name__ for t in expected)
                    )
                    raise ValueError(
                        f"driver_params.{key} must be {exp_name}; got {type(value).__name__}"
                    )
                # isinstance above narrowed value; cast to a typed local so
                # mypy --strict tracks the comparison. int/float(value) rejects
                # `object` under call-overload, and the isinstance narrowing
                # gets erased at branch entry — cast is the least-noisy fix.
                if key_enum is DriverParamKey.MAX_TOKENS:
                    v_int = cast(int, value)
                    if v_int < 0:
                        raise ValueError(f"driver_params.max_tokens must be ≥ 0; got {v_int}")
                if key_enum is DriverParamKey.NUM_CTX:
                    v_int = cast(int, value)
                    if v_int < 1:
                        raise ValueError(f"driver_params.num_ctx must be ≥ 1; got {v_int}")
                if key_enum is DriverParamKey.TIMEOUT:
                    v_num = cast(float, value)
                    if v_num <= 0:
                        raise ValueError(f"driver_params.timeout must be > 0; got {v_num}")
        threading_lock = self._turn_threading_locks.setdefault(session_id, threading.Lock())
        with threading_lock:
            manifest = self._manifests.get(session_id)
            if manifest is None:
                raise KeyError(f"unknown session_id {session_id!r}")
            updated = _replace(manifest, driver_params=params)
            _atomic_write_json(
                self._base / session_id / _MANIFEST_FILENAME, _manifest_to_dict(updated)
            )
            self._manifests[session_id] = updated
        return updated

    def set_bundle(self, session_id: str, bundle: str | None) -> SessionManifest:
        """Change the bundle attached to a session mid-flight. In-memory
        catalog and manifest.json both update atomically. The next
        `Runtime.resume` builds `session_topology` with the new bundle's
        assembled seed — mid-turn swaps are not attempted (the in-flight
        turn, if any, completes on its prior seed; the next turn's
        UserMessage.assembled_prompt carries the new seed prefix).

        Sprint 032b (piece-G prereq for sprint 036b's mid-session bundle
        picker): lifts `bundle` from `_NOT_YET` to `_PATCHABLE` in
        `substrate-ui/server.py::_session_patch`. Bundle name is validated
        by attempting `load_bundle(name)`; an unknown bundle raises
        `BundleNotFoundError` (surfaced as 400 at the daemon boundary).
        `None` clears any attached bundle (reverts to the shipped default
        the next turn assembles).

        No `TranscriptCompacted` envelope is written to the record — no
        compaction happens; only the seed shape changes at the next turn.
        Emitting a compaction signal for a non-compaction event would be
        false instrumentation. The UI's `BUNDLE_ATTACHED{session_id,
        bundle, prior_bundle}` (vocab v0.7) is the observable event; the
        record shows the effect at next turn via `UserMessage.assembled_prompt`.

        Same lock discipline as `set_driver` (red-team finding 4, 2026-08-26).

        Raises `KeyError` on unknown session_id;
        `substrate.bundles.BundleNotFoundError` on unknown bundle name.
        """
        if session_id not in self._manifests:
            raise KeyError(f"unknown session_id {session_id!r}")
        if bundle is not None:
            # Validate against the substrate bundle catalog. An unknown name
            # fails here, not silently at next-turn seed assembly.
            from substrate.bundles import load_bundle

            load_bundle(bundle)
        threading_lock = self._turn_threading_locks.setdefault(session_id, threading.Lock())
        with threading_lock:
            manifest = self._manifests.get(session_id)
            if manifest is None:
                raise KeyError(f"unknown session_id {session_id!r}")
            updated = _replace(manifest, bundle=bundle)
            _atomic_write_json(
                self._base / session_id / _MANIFEST_FILENAME, _manifest_to_dict(updated)
            )
            self._manifests[session_id] = updated
        return updated

    def set_driver(self, session_id: str, driver: str) -> SessionManifest:
        """Change the driver for a session. In-memory catalog and manifest.json
        both update atomically. The next `Runtime.resume` builds
        `session_topology` with the new driver — mid-turn swaps are not
        attempted (the in-flight turn, if any, completes on its prior
        driver; the next turn resolves the new driver via
        `_daemon_driver_resolver`).

        Sprint 215c: driver STRING validation is deferred to
        `_daemon_driver_resolver` at next-turn build time. A caller passing
        a string that resolves to `OllamaResponder(model=<bad tag>)` sees
        the failure on the next /turn, not at PATCH time. The daemon-side
        Ollama-tag round-trip is a piece-B follow-up if needed.

        Red-team finding 4 (2026-08-26): holds the per-session lock so a
        concurrent ``update_status`` from ``turn_sync`` does not clobber
        this write or vice-versa.

        Raises `KeyError` on unknown session_id.
        """
        if session_id not in self._manifests:
            raise KeyError(f"unknown session_id {session_id!r}")
        threading_lock = self._turn_threading_locks.setdefault(session_id, threading.Lock())
        with threading_lock:
            manifest = self._manifests.get(session_id)
            if manifest is None:
                raise KeyError(f"unknown session_id {session_id!r}")
            updated = _replace(manifest, driver=driver)
            _atomic_write_json(
                self._base / session_id / _MANIFEST_FILENAME, _manifest_to_dict(updated)
            )
            self._manifests[session_id] = updated
        return updated

    # ── lookups ────────────────────────────────────────────────────────────

    def by_name(self, name: str) -> str | None:
        return self._by_name.get(name)

    def get(self, session_id: str) -> SessionManifest | None:
        return self._manifests.get(session_id)

    def list_all(self) -> list[SessionManifest]:
        return list(self._manifests.values())

    def list_children(self, parent_id: str) -> list[SessionManifest]:
        """Sprint 225b: return every manifest whose composite_of == parent_id.
        Used by the daemon's end/delete cascade. O(n) scan of the in-memory
        catalog — a small n; the daemon holds sessions in the hundreds, not
        millions."""
        return [m for m in self._manifests.values() if m.composite_of == parent_id]

    # ── standing-session turn (delegate path 1 + POST /api/session/<id>/turn) ─

    def turn_sync(
        self,
        session_id: str,
        resume_event: Any = None,
        *,
        timeout_seconds: float = 600.0,
        resume_event_builder: Callable[[SessionManifest, Path], Any] | None = None,
    ) -> tuple[SessionManifest, Path]:
        """Run one turn against a standing session synchronously. Called from
        the delegate seam (sprint 213b) inside tool_loop's worker thread — NOT
        from the daemon's asyncio loop. Returns `(final_manifest, record_root)`.

        Serializes on the per-session `threading.Lock`, so two concurrent parents
        delegating to the same standing session FIFO-queue on this call rather
        than racing the same record's Runtime lock. Rebuilds the session's
        topology via the injected `session_topology_factory` and drives one
        `Runtime.resume` call in a fresh event loop.

        Status transition: a resume that returns `RunResult(status="finalised")`
        writes the manifest to `"ended"` and returns cleanly — the caller
        (delegate) reads the tail FinalAnswer off the record and folds the
        answer back. `/exit` mid-turn is a legitimate finalisation and no
        exception is raised for it.

        Raises `KeyError` on unknown session_id; `SessionEndedMidTurn` when the
        session's status is already `"ended"` at call time (or has transitioned
        to `"ended"` by the time the per-session lock is acquired). Raises
        `RuntimeError` if no `session_topology_factory` was injected at
        construction. Post-review 2026-08-26 finding 5: an earlier docstring
        promised a mid-turn `SessionEndedMidTurn` raise; the code never
        delivered one and the promise is trimmed.
        """
        if self._session_topology_factory is None:
            raise RuntimeError(
                "SessionRegistry.turn_sync: no session_topology_factory was injected at "
                "construction. Daemon (substrate-ui/server.py) supplies one at boot; "
                "tests must pass one to SessionRegistry(...) explicitly."
            )
        manifest = self._manifests.get(session_id)
        if manifest is None:
            raise KeyError(f"unknown session_id {session_id!r}")
        if manifest.status == SessionStatus.ENDED:
            raise SessionEndedMidTurn(
                f"session {session_id!r} has ended (status='ended'); cannot resume"
            )
        threading_lock = self._turn_threading_locks.setdefault(session_id, threading.Lock())
        with threading_lock:
            # Re-check manifest under the lock — an intervening turn may have ended it.
            live_manifest = self._manifests.get(session_id)
            if live_manifest is None or live_manifest.status == SessionStatus.ENDED:
                raise SessionEndedMidTurn(f"session {session_id!r} ended before the turn started")
            record_root = Path(live_manifest.record_root)
            # Sprint 214a: `resume_event_builder` runs UNDER the lock so record-derived
            # state (like next turn_index computed from the reviewer's tail) is atomic
            # with the write. Two concurrent callers thus see two different next-turn
            # values, not the same pre-lock snapshot. When only `resume_event` is
            # given (delegate's existing shape), it is used verbatim — backwards compat.
            if resume_event_builder is not None:
                effective_resume_event = resume_event_builder(live_manifest, record_root)
            else:
                if resume_event is None:
                    raise ValueError("turn_sync: pass either resume_event or resume_event_builder")
                effective_resume_event = resume_event
            # Sprint 217a: compose `Runtime.run` for the first turn on a fresh
            # record and `Runtime.resume` for every turn after. An empty record
            # was the source of finding 16: the previous shape called
            # `Runtime.resume` on a fresh root and `_resume_bootstrap` saw
            # `max_seq == -1`, injected the resume event as the first envelope,
            # and skipped `substrate.RunStarted`. Now the daemon composes the
            # two primitives: `.run()` on empty (with a `session_open` producer
            # that emits the first UserMessage from an initial), `.resume()`
            # otherwise. Neither `Runtime.run` nor `Runtime.resume` changes.
            from substrate.topologies.session import UserMessage

            record_state, torn_cause = _record_state(record_root)
            if record_state == "torn":
                assert torn_cause is not None
                # Halt in place: flip the manifest to "interrupted" so
                # subsequent turns short-circuit instead of retrying the
                # same dispatch and re-crashing on the same torn tail.
                self.update_status(session_id, SessionStatus.INTERRUPTED)
                raise TornRecordOnResume(session_id, record_root, torn_cause)
            is_fresh_record = record_state == "empty"
            if is_fresh_record:
                # Fresh session: the resume_event must be a UserMessage so the
                # `session_open` producer can emit it as the first envelope.
                # SIGTERM shutdown (or any other non-UserMessage first-turn caller)
                # gets a typed refusal; `_shutdown_all_sessions` catches it and
                # buckets under `skipped_fresh`.
                if not isinstance(effective_resume_event, UserMessage):
                    raise FreshSessionRequiresUserMessage(
                        f"session {session_id!r} has no record yet; the first-turn "
                        f"resume event must be a UserMessage (got "
                        f"{type(effective_resume_event).__name__!r})"
                    )
                factory = self._session_topology_factory(live_manifest, effective_resume_event)
            else:
                factory = self._session_topology_factory(live_manifest, None)
            turn_handle = TurnHandle()
            self._running_handles[session_id] = turn_handle
            try:
                if is_fresh_record:
                    result = _run_run_sync(
                        factory,
                        record_root,
                        timeout_seconds=timeout_seconds,
                        handle_out=turn_handle,
                    )
                else:
                    result = _run_resume_sync(
                        factory,
                        record_root,
                        effective_resume_event,
                        timeout_seconds=timeout_seconds,
                        handle_out=turn_handle,
                    )
            finally:
                self._running_handles.pop(session_id, None)
            status_str = getattr(result, "status", "paused")
            if status_str == "finalised":
                new_status: SessionStatus = SessionStatus.ENDED
            elif status_str == "failed":
                new_status = SessionStatus.INTERRUPTED
            else:
                new_status = SessionStatus.PARKED
            updated = self.update_status(session_id, new_status)
            self.advance_turn_index(session_id)
            return updated, record_root

    # ── queue cap ──────────────────────────────────────────────────────────

    def try_enqueue_turn(self, session_id: str) -> tuple[bool, int]:
        """Increment the session's queued-turn depth if it is below the cap.
        Returns `(admitted, depth)`. If `admitted` is False, `depth` equals
        the cap (the caller's would-be position). The caller MUST pair a
        successful admission with `dequeue_turn(session_id)` in a `finally`
        block, or the counter leaks.
        """
        with self._queue_depth_lock:
            depth = self._queue_depths.get(session_id, 0)
            if depth >= self._turn_queue_cap:
                return False, self._turn_queue_cap
            self._queue_depths[session_id] = depth + 1
            return True, depth + 1

    def dequeue_turn(self, session_id: str) -> None:
        with self._queue_depth_lock:
            new_depth = self._queue_depths.get(session_id, 0) - 1
            if new_depth > 0:
                self._queue_depths[session_id] = new_depth
            else:
                self._queue_depths.pop(session_id, None)

    def turn_queue_cap(self) -> int:
        return self._turn_queue_cap

    def next_turn_index(self, session_id: str) -> int:
        """F14: the next turn_index for this session, derived from the
        in-memory counter (no record scan). Returns 0 for unknown sessions."""
        return self._next_turn_index.get(session_id, 0)

    def advance_turn_index(self, session_id: str) -> None:
        """F14: increment the turn counter after a successful turn."""
        self._next_turn_index[session_id] = self._next_turn_index.get(session_id, 0) + 1

    def interrupt(
        self,
        session_id: str,
        *,
        tier: str = "hard",
    ) -> dict[str, Any] | None:
        """Sprint 217d + Phase 8 item 5: cancel a running producer through the
        `Runtime.cancel_producer` substrate primitive. Reaches the worker
        thread's event loop through `_running_handles.loop` and schedules a
        lookup+cancel closure via `call_soon_threadsafe` so the primitive runs
        on the loop it belongs to (the primitive's own thread-safety
        contract).

        Two tiers:

        - `tier="hard"` (default; matches the pre-Phase-8 behavior when
          nothing else can cancel): walks `kind_by_instance` in the order
          `model` then `tool`. Whichever kind has a live producer, that is
          the one cancelled. The tool arm lets a user stop a runaway tool
          call that the model producer cannot reach.
        - `tier="soft"`: does NOT cancel a live tool. If a model producer is
          live, cancels it (same as hard for a model). If a tool is live,
          returns a synthetic ref `{kind: "signal", instance: "soft",
          parent: null}` so the caller knows the tier landed as a signal
          rather than a cancel. The signal envelope
          (`InterruptRequested(tier="soft")`) is recorded by items 6-7 on the
          producer side; this method's job is to say "the request was
          received."

        Returns the cancelled producer's ProducerRef dict when a cancel was
        dispatched, the soft-signal synthetic ref when tier=soft with a live
        tool, or None when no producer is running for this session (parked,
        no handle, runtime not yet live).
        """
        import concurrent.futures

        handle = self._running_handles.get(session_id)
        if handle is None:
            return None
        loop = handle.loop
        runtime = handle.runtime
        if loop is None or runtime is None:
            return None
        if tier not in ("soft", "hard"):
            raise ValueError(f"tier must be 'soft' or 'hard', got {tier!r}")

        fut: concurrent.futures.Future[dict[str, Any] | None] = concurrent.futures.Future()

        def _do_cancel() -> None:
            try:
                st = getattr(runtime, "_st", None)
                if st is None:
                    fut.set_result(None)
                    return
                # Find the live model first — if the model is running, both
                # tiers cancel it (soft stops before the next tool by
                # returning; hard is the same verb at the primitive layer).
                live_model = None
                live_tool = None
                for inst, kind in list(st.kind_by_instance.items()):
                    if kind == "model" and live_model is None:
                        live_model = inst
                    elif kind == "tool" and live_tool is None:
                        live_tool = inst
                caller = f"daemon:interrupt-{tier}"
                if live_model is not None:
                    ref = runtime.cancel_producer(live_model, cause="external", caller=caller)
                    fut.set_result(ref)
                    return
                if live_tool is not None:
                    if tier == "hard":
                        ref = runtime.cancel_producer(live_tool, cause="external", caller=caller)
                        fut.set_result(ref)
                        return
                    # Soft with a live tool (Phase 8 item 7 wiring): inject
                    # InterruptRequested onto the record via the daemon-facing
                    # Runtime.inject_event primitive. The topology's
                    # emit-interrupt-fragment trigger spawns the fragment
                    # producer, which emits a PromptFragment(source=interrupt).
                    # On the next ToolResult boundary,
                    # compose-on-interrupt-tool-result fires the composer
                    # (CONTINUE and WRAP_UP refuse the mirror condition), a
                    # fresh PromptComposed lands, and the model wakes with the
                    # tool result AND the interrupt directive in scope. The
                    # synthetic ref reports "the request was received" so the
                    # client renders "the model will stop after this tool"
                    # instead of "no turn in flight."
                    from .topologies.session import InterruptRequested

                    runtime.inject_event(
                        InterruptRequested(
                            session_id=session_id,
                            tier="soft",
                            source=caller,
                        )
                    )
                    fut.set_result({"kind": "signal", "instance": "soft", "parent": None})
                    return
                fut.set_result(None)
            except Exception as exc:  # noqa: BLE001 — carry to the caller thread
                fut.set_exception(exc)

        try:
            loop.call_soon_threadsafe(_do_cancel)
        except RuntimeError:
            return None
        try:
            return fut.result(timeout=1.0)
        except concurrent.futures.TimeoutError:
            return None

    def has_session_dir(self, session_id: str) -> bool:
        """True iff `<base>/<sid>/` exists on disk. Used to tell a
        deleted-but-once-alive session (session dir present, manifest
        gone — return 410) from a never-existed one (no dir — return
        404). A never-run session's session_dir carries manifest.json
        but no record/ subdir; after DELETE the manifest.json is
        unlinked but the session_dir stays.
        """
        return (self._base / session_id).exists()

    # ── status transitions ────────────────────────────────────────────────

    def update_status(self, session_id: str, status: SessionStatus) -> SessionManifest:
        manifest = self._manifests.get(session_id)
        if manifest is None:
            raise KeyError(f"unknown session_id {session_id!r}")
        updated = _replace(manifest, status=status)
        _atomic_write_json(self._base / session_id / _MANIFEST_FILENAME, _manifest_to_dict(updated))
        self._manifests[session_id] = updated
        return updated

    def delete(self, session_id: str) -> SessionManifest:
        """Remove a session from the registry: manifest file, by-name entry, per-
        session lock. **The record directory stays** — SDD hard rule 12 says the
        audit trail is the work, and the record is the durable evidence of what
        the session did. A user who wants the record dir gone deletes it by hand
        under `~/.substrate/sessions/<session_id>/record/`. Returns the manifest
        that was removed; raises `KeyError` on unknown session_id.

        Piece-B review finding 4: a delete during an in-flight `turn_sync`
        used to race — the turn's tail `update_status` call would find the
        manifest already gone and raise `KeyError` from inside the running
        turn, surfacing to the caller as a generic 500. The fix is to hold
        the per-session `threading.Lock` for the delete, so an in-flight
        turn completes cleanly first. Subsequent turn_sync callers waiting
        on the same lock find the manifest gone under the lock and get
        ``SessionEndedMidTurn`` by the existing under-lock re-check.

        Red-team finding 1 (2026-08-26): the lock acquire is bounded at
        30s. If an in-flight turn is still holding the lock after 30s,
        ``TimeoutError`` propagates to the caller (the server returns 500).
        This prevents an adversary from pinning ThreadingHTTPServer worker
        threads for 600s per DELETE by targeting busy sessions.
        """
        manifest = self._manifests.get(session_id)
        if manifest is None:
            raise KeyError(f"unknown session_id {session_id!r}")
        threading_lock = self._turn_threading_locks.setdefault(session_id, threading.Lock())
        if not threading_lock.acquire(timeout=30.0):
            raise TimeoutError(
                f"delete({session_id!r}): per-session lock not acquired within "
                f"30s (an in-flight turn is still running)"
            )
        try:
            # Re-check under the lock: a concurrent second delete may have
            # already removed the manifest by the time we acquire.
            manifest = self._manifests.get(session_id)
            if manifest is None:
                raise KeyError(f"unknown session_id {session_id!r}")
            # Remove the by-name entry under the flock so a concurrent
            # `set_name` or `create` sees the removal atomically.
            if manifest.name is not None:
                with _flocked(self._base / _BY_NAME_FILENAME) as index:
                    if index.get(manifest.name) == session_id:
                        del index[manifest.name]
                    self._by_name = dict(index)
            # Remove the manifest file. Leave the record dir alone.
            manifest_path = self._base / session_id / _MANIFEST_FILENAME
            try:
                manifest_path.unlink()
            except FileNotFoundError:
                pass  # already gone; idempotent
            # Drop the in-memory catalog + lock. A turn_sync caller still
            # waiting on the lock finds `_manifests.get(...)` returning None
            # under the lock and raises SessionEndedMidTurn — the caller's
            # existing 410 branch handles it.
            self._manifests.pop(session_id, None)
            self._turn_threading_locks.pop(session_id, None)
        finally:
            threading_lock.release()
        return manifest

    # ── private ────────────────────────────────────────────────────────────

    def _read_by_name_index(self) -> dict[str, str]:
        path = self._base / _BY_NAME_FILENAME
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as fp:
                fcntl.flock(fp.fileno(), fcntl.LOCK_SH)
                try:
                    data = json.load(fp)
                finally:
                    fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
        except (OSError, json.JSONDecodeError):
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def _write_by_name_index(self) -> None:
        _atomic_write_json(self._base / _BY_NAME_FILENAME, dict(self._by_name))


# ── helpers ─────────────────────────────────────────────────────────────────


def _record_state(record_root: Path) -> tuple[str, BaseException | None]:
    """Sprint 220b: classify a record directory into three states so the daemon
    dispatches the right primitive (and refuses when neither is safe):

      - `"empty"`   → no directory, or a directory with zero complete envelopes.
                     `turn_sync` composes `Runtime.run(session_topology)` and
                     the `session_open` producer emits the first `UserMessage`.
      - `"has_envelopes"` → at least one complete envelope; `Runtime.resume`.
      - `"torn"`    → `api.read_record` raised. The daemon must refuse both
                     primitives: `.run` would write a fresh `RunStarted` at
                     seq 0 alongside sealed segments (double-head or
                     persistent-bus lock throw); `.resume` would try to read
                     past the torn tail. Returns the exception so the caller
                     surfaces it as `TornRecordOnResume`.

    The previous single-signal `_record_has_envelopes` swallowed every read
    exception into `False`, which routed a torn record into the `.run`
    branch — the crash-mid-turn dispatch hole finding 1 named.
    """
    if not record_root.exists():
        return ("empty", None)
    try:
        has_any = False
        for _ in api.read_record(record_root):
            has_any = True
            break
    except Exception as exc:  # noqa: BLE001 — reclassify below as torn
        return ("torn", exc)
    return ("has_envelopes" if has_any else "empty", None)


def _record_has_envelopes(record_root: Path) -> bool:
    """Back-compat wrapper. `_record_state` is the authoritative call; this
    exists only for older callers that predate the three-state split. New
    call sites must switch to `_record_state` so torn records surface.
    """
    state, _ = _record_state(record_root)
    return state == "has_envelopes"


def _run_run_sync(
    factory: Callable[["TopologyBuilder"], None],
    record_root: Path,
    *,
    timeout_seconds: float,
    handle_out: TurnHandle | None = None,
) -> Any:
    """Sprint 217a: run `Runtime(record_root, persistent=True).run(factory)` on
    a fresh record in a worker thread with its own event loop. The `session_open`
    producer inside the factory emits the first-turn UserMessage; the topology
    fires through to `Park` and pauses on `pause_await_input`. The primitive
    itself is unchanged; the daemon composes it here for turn 1.

    Same shape as `_run_resume_sync` — TurnHandle populated for interrupt,
    timeout raises TimeoutError, kernel exception re-raised — so the interrupt
    seam works on the first turn as it does on every subsequent turn.
    """
    box: dict[str, Any] = {}
    ready = threading.Event()
    done = threading.Event()

    def worker() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            runtime = api.Runtime(record_root, persistent=True)
            task = loop.create_task(runtime.run(factory))
            if handle_out is not None:
                handle_out.loop = loop
                handle_out.task = task
                handle_out.runtime = runtime
            ready.set()
            box["result"] = loop.run_until_complete(task)
        except asyncio.CancelledError:
            box["cancelled"] = True
        except Exception as exc:  # noqa: BLE001 — carried to caller thread
            box["error"] = exc
        finally:
            loop.close()
            done.set()

    threading.Thread(target=worker, daemon=True).start()
    if not done.wait(timeout_seconds):
        ready.wait(1.0)
        if handle_out is not None:
            loop, task = handle_out.loop, handle_out.task
        else:
            loop, task = None, None
        if loop is not None and task is not None:
            loop.call_soon_threadsafe(task.cancel)
            done.wait(10.0)
        raise TimeoutError(
            f"SessionRegistry.turn_sync: run against {record_root} exceeded "
            f"{timeout_seconds}s and was cancelled"
        )
    if box.get("cancelled"):
        raise TimeoutError(f"run against {record_root} was cancelled")
    if "error" in box:
        raise box["error"]
    return box["result"]


def _run_resume_sync(
    factory: Callable[["TopologyBuilder"], None],
    record_root: Path,
    resume_event: Any,
    *,
    timeout_seconds: float,
    handle_out: TurnHandle | None = None,
) -> Any:
    """Run `Runtime(record_root, persistent=True).resume(factory, resume_event)`
    to completion in a worker thread with its own event loop.

    Returns the `RunResult` (has `.status` in `{"paused", "finalised", "failed"}`).
    Raises `TimeoutError` on wall-clock overrun; re-raises the child's exception
    on kernel failure.

    `handle_out`, when provided, is populated with loop/task/runtime once the
    worker's event loop is live — the caller can reach `runtime.cancel_producers`
    via `loop.call_soon_threadsafe` from another thread (sprint 215b interrupt).
    """
    box: dict[str, Any] = {}
    ready = threading.Event()
    done = threading.Event()

    def worker() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            runtime = api.Runtime(record_root, persistent=True)
            task = loop.create_task(runtime.resume(factory, resume_event=resume_event))
            if handle_out is not None:
                handle_out.loop = loop
                handle_out.task = task
                handle_out.runtime = runtime
            ready.set()
            box["result"] = loop.run_until_complete(task)
        except asyncio.CancelledError:
            box["cancelled"] = True
        except Exception as exc:  # noqa: BLE001 — carried to caller thread; NOT BaseException so KeyboardInterrupt / SystemExit propagate to main
            box["error"] = exc
        finally:
            loop.close()
            done.set()

    threading.Thread(target=worker, daemon=True).start()
    if not done.wait(timeout_seconds):
        ready.wait(1.0)
        if handle_out is not None:
            loop, task = handle_out.loop, handle_out.task
        else:
            loop, task = None, None
        if loop is not None and task is not None:
            loop.call_soon_threadsafe(task.cancel)
            done.wait(10.0)
        raise TimeoutError(
            f"SessionRegistry.turn_sync: resume against {record_root} exceeded "
            f"{timeout_seconds}s and was cancelled"
        )
    if box.get("cancelled"):
        raise TimeoutError(f"resume against {record_root} was cancelled")
    if "error" in box:
        raise box["error"]
    return box["result"]


class _FlockedIndex:
    """Context manager: open the by-name index under an exclusive flock, hand
    the caller a mutable dict, write it back atomically on __exit__.

    The flock lives on a STABLE `.by-name.lock` sibling, not on `by-name.json`
    itself. `_atomic_write_json` writes to a tempfile then `os.replace`s it
    over `by-name.json` — the rename swaps inodes, so a flock on the JSON's fd
    is on the OLD inode and the next caller opens the NEW inode with no
    mutual exclusion. Locking a separate file that never gets replaced keeps
    concurrent writers serial. The read of `by-name.json` happens inside the
    critical section, after the flock is held.

    A second daemon (or any writer) trying to take the same exclusive lock
    blocks until this one releases. A crash inside the block leaves
    `by-name.json` at its prior good state (atomic write never partially
    landed) and the flock releases when the file descriptor closes.
    """

    def __init__(self, index_path: Path, lock_path: Path) -> None:
        self._index_path = index_path
        self._lock_path = lock_path
        self._index: dict[str, str] = {}
        self._lock_fp: Any = None

    def __enter__(self) -> dict[str, str]:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        # Touch the lock file if absent, then open for flock. The lock file
        # itself carries no content; only its inode's byte-range lock matters.
        self._lock_fp = self._lock_path.open("a", encoding="utf-8")
        fcntl.flock(self._lock_fp.fileno(), fcntl.LOCK_EX)
        # Under the exclusive lock, read the current index.
        if self._index_path.exists():
            try:
                with self._index_path.open("r", encoding="utf-8") as fp:
                    data = json.load(fp)
                if isinstance(data, dict):
                    self._index = {str(k): str(v) for k, v in data.items()}
            except (OSError, json.JSONDecodeError):
                self._index = {}
        return self._index

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        try:
            if exc is None:
                _atomic_write_json(self._index_path, dict(self._index))
        finally:
            fcntl.flock(self._lock_fp.fileno(), fcntl.LOCK_UN)
            self._lock_fp.close()


def _flocked(index_path: Path) -> _FlockedIndex:
    lock_path = index_path.parent / _BY_NAME_LOCK_FILENAME
    return _FlockedIndex(index_path=index_path, lock_path=lock_path)


def _scan_record_status(record_root: Path) -> SessionStatus:
    """Return the record's true status per §5.

    The boot scan runs while NO Runtime is live on the record — `running`
    never surfaces here. The discriminator is the last envelope:

      - record dir absent → `parked` (session created but never ran)
      - `read_record` raises (gap, torn seal, malformed frames) → `interrupted`
      - last envelope is `substrate.RunFinalised` → `ended`
      - last envelope is `substrate.TerminationMatched` with decision
        `pause-await-input` → `parked` (a clean session-topology pause)
      - anything else → `interrupted` (daemon died before either terminal
        landed; the record's tail is honest but the run is not resumable
        without a specific decision from the operator)

    `api.recover_open_segment` is deliberately NOT called here: it truncates a
    torn tail, which is a write operation the boot scan must not perform.
    """
    if not record_root.exists():
        return SessionStatus.PARKED
    try:
        envelopes = list(api.read_record(record_root))
    except Exception:  # noqa: BLE001 — a corrupt record is a real state, not a crash
        return SessionStatus.INTERRUPTED
    if not envelopes:
        return SessionStatus.INTERRUPTED
    last = envelopes[-1]
    kind = last.get("kind", "")
    if kind == api.RUN_FINALISED:
        return SessionStatus.ENDED
    if kind == api.TERMINATION_MATCHED:
        payload = last.get("payload") or {}
        if (
            isinstance(payload, dict)
            and payload.get("decision") == api.Decision.PAUSE_AWAIT_INPUT.value
        ):
            return SessionStatus.PARKED
    return SessionStatus.INTERRUPTED


def _next_turn_index_from_record(record_root: Path) -> int:
    """Scan the record for the highest UserMessage.turn_index + 1. Used once at
    boot_scan; afterward the in-memory counter is incremented per turn."""
    if not record_root.exists():
        return 0
    highest = -1
    try:
        for env in api.read_record(record_root):
            if env.get("kind") == "UserMessage":
                payload = env.get("payload") or {}
                if isinstance(payload, dict) and "turn_index" in payload:
                    highest = max(highest, int(payload["turn_index"]))
    except Exception:  # noqa: BLE001 — mid-write record or torn tail: an unreadable envelope reads as "no known turn_index"; boot_scan sees the state one step later.
        pass
    return highest + 1 if highest >= 0 else 0


def _manifest_to_dict(m: SessionManifest) -> dict[str, Any]:
    return {
        "session_id": m.session_id,
        "name": m.name,
        "created_at": m.created_at,
        "driver": m.driver,
        "workspace": m.workspace,
        "workspace_shape": m.workspace_shape,
        "record_root": m.record_root,
        "status": m.status,
        "bundle": m.bundle,
        "seed": m.seed,
        # Sprint 217e: tool allow-list serialized as a JSON list; None → absent.
        "tools": list(m.tools) if m.tools is not None else None,
        # Sprint 223a: role name (four-layer resolver reads the prompt fresh).
        "role": m.role,
        # Sprint 223d: per-turn text prefixed to every UserMessage.
        "per_turn": m.per_turn,
        # Sprint 225b: composite parent id (None for standalone sessions).
        "composite_of": m.composite_of,
        # Sprint 032c: per-session driver params (think/max_tokens/timeout/
        # num_ctx). None or an absent key → responder default. Dict of
        # primitives only; JSON-safe by construction.
        "driver_params": dict(m.driver_params) if m.driver_params is not None else None,
    }


_VALID_STATUS: frozenset[str] = frozenset(
    (SessionStatus.RUNNING, SessionStatus.PARKED, SessionStatus.INTERRUPTED, SessionStatus.ENDED)
)


def _manifest_from_dict(d: dict[str, Any]) -> SessionManifest:
    status_raw = str(d["status"])
    if status_raw not in _VALID_STATUS:
        raise ValueError(
            f"manifest status={status_raw!r} not in {sorted(_VALID_STATUS)}; manifest is corrupt"
        )
    tools_raw = d.get("tools")
    tools: tuple[str, ...] | None
    if tools_raw is None:
        tools = None
    elif isinstance(tools_raw, (list, tuple)):
        # JSON round-trip lands a list; in-memory `_replace` passes a tuple.
        tools = tuple(str(t) for t in tools_raw)
    else:
        raise ValueError(f"manifest tools={tools_raw!r} must be a list of strings or absent")
    return SessionManifest(
        session_id=str(d["session_id"]),
        name=d.get("name") if d.get("name") is not None else None,
        created_at=float(d["created_at"]),
        driver=str(d["driver"]),
        workspace=str(d["workspace"]),
        workspace_shape=str(d["workspace_shape"]),
        record_root=str(d["record_root"]),
        status=status_raw,  # type: ignore[arg-type]
        bundle=d.get("bundle") if d.get("bundle") is not None else None,
        seed=str(d["seed"]),
        tools=tools,
        role=str(d.get("role") or "default"),
        per_turn=str(d.get("per_turn") or ""),
        composite_of=d.get("composite_of") if d.get("composite_of") is not None else None,
        driver_params=(dict(d["driver_params"]) if d.get("driver_params") is not None else None),
    )


def _replace(m: SessionManifest, **kwargs: Any) -> SessionManifest:
    """`msgspec.Struct` frozen instances have no built-in replace; build fresh."""
    data = _manifest_to_dict(m)
    data.update(kwargs)
    return _manifest_from_dict(data)


# Sprint 057: public read projections over on-disk registry state. Same
# class as `api.read_record` — pure reads, no side effects. Substrate-ui
# and any other consumer that wants to classify a session's true status
# without opening a Runtime imports these public names; the underscore
# originals stay in place as the primary definitions so every internal
# call site above keeps working unchanged.
def scan_record_status(record_root: Path) -> SessionStatus:
    """Return a record directory's true `SessionStatus` per the boot-scan
    discriminator (§5): parked / interrupted / ended. Pure read — never
    truncates a torn tail. Full contract on `_scan_record_status`."""
    return _scan_record_status(record_root)


def manifest_from_dict(d: dict[str, Any]) -> SessionManifest:
    """Parse an on-disk manifest.json dict into a typed `SessionManifest`.
    Raises `ValueError` on an unknown status or a malformed `tools` field.
    Full contract on `_manifest_from_dict`."""
    return _manifest_from_dict(d)


__all__ = [
    "FreshSessionRequiresUserMessage",
    "NameCollision",
    "SessionEndedMidTurn",
    "SessionManifest",
    "SessionRegistry",
    "SessionStatus",
    "SessionTopologyFactory",
    "manifest_from_dict",
    "scan_record_status",
]

# spec-audit: 2026-09-01

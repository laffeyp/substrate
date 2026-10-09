"""Sprint 211 — atomic-create refuses colliding names, survives concurrent writers.

Two behaviors under test:

  1. A second `create` with the same `name` and a different `session_id` raises
     `NameCollision` carrying the FIRST session's id. The caller shapes the 409
     response `{"error": "name already taken", "existing_session_id": ...}`.
  2. 100 concurrent `create` calls with distinct session_ids AND distinct names
     all succeed. No two share a session_id; no by-name.json entry is dropped
     or duplicated. The `fcntl.flock` on the index survives real contention.

Concurrency runs across process threads (not asyncio), so we exercise the file
lock at the OS level — the guarantee the tech spec §5 makes ("Atomic create:
`fcntl.flock` on `by-name.json` before adding").

"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from substrate.topologies.session_registry import NameCollision, SessionRegistry


def scratch_ws(name: str) -> str:
    """A workspace label inside this run's temp state root (tests/conftest.py)."""
    return os.path.join(os.environ["SUBSTRATE_HOME"], "workspaces", name)


def test_second_create_with_same_name_raises_collision(tmp_path: Path) -> None:
    r = SessionRegistry(base=tmp_path)
    first = r.create(
        session_id="s_first",
        name="reviewer",
        driver="deterministic",
        workspace=scratch_ws("w"),
        workspace_shape="flat",
        bundle=None,
        seed="hi",
    )
    assert first.session_id == "s_first"
    with pytest.raises(NameCollision) as info:
        r.create(
            session_id="s_second",
            name="reviewer",
            driver="deterministic",
            workspace=scratch_ws("w"),
            workspace_shape="flat",
            bundle=None,
            seed="hi",
        )
    err = info.value
    assert err.name == "reviewer"
    assert err.existing_session_id == "s_first"
    # First session's manifest is intact; second was never written.
    assert (tmp_path / "s_first" / "manifest.json").exists()
    assert not (tmp_path / "s_second" / "manifest.json").exists()


def test_idempotent_recreate_with_same_id_and_name_succeeds(tmp_path: Path) -> None:
    """The tech spec §5's collision rule keys on (name → session_id) — a re-create
    with the SAME session_id AND SAME name is idempotent, not a collision.
    Matters for the daemon's own retry paths.
    """
    r = SessionRegistry(base=tmp_path)
    r.create(
        session_id="s_only",
        name="reviewer",
        driver="deterministic",
        workspace=scratch_ws("w"),
        workspace_shape="flat",
        bundle=None,
        seed="hi",
    )
    # No raise; the by-name entry already points at s_only.
    r.create(
        session_id="s_only",
        name="reviewer",
        driver="deterministic",
        workspace=scratch_ws("w2"),  # different workspace; overwrites the manifest
        workspace_shape="flat",
        bundle=None,
        seed="hi",
    )
    assert r.by_name("reviewer") == "s_only"


def test_100_concurrent_creates_never_corrupt_the_index(tmp_path: Path) -> None:
    """Distinct session_ids AND distinct names across 100 threads. Every create
    succeeds; the on-disk by-name.json ends with exactly 100 entries, each
    keyed by the thread's own name → its session_id. No collision, no dropped
    write, no duplicated entry.
    """
    r = SessionRegistry(base=tmp_path)
    errors: list[BaseException] = []

    def _create_one(i: int) -> None:
        try:
            r.create(
                session_id=f"s{i:03d}",
                name=f"name{i:03d}",
                driver="deterministic",
                workspace=scratch_ws(f"w{i}"),
                workspace_shape="flat",
                bundle=None,
                seed="hi",
            )
        except BaseException as exc:  # noqa: BLE001 — a worker thread: any failure is collected and asserted on the main thread
            errors.append(exc)

    threads = [threading.Thread(target=_create_one, args=(i,)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [], f"unexpected errors under concurrent create: {errors[:3]}"
    on_disk = json.loads((tmp_path / "by-name.json").read_text(encoding="utf-8"))
    assert len(on_disk) == 100, f"by-name.json has {len(on_disk)} entries, want 100"
    assert all(on_disk[f"name{i:03d}"] == f"s{i:03d}" for i in range(100))


def test_concurrent_colliders_serialize_and_the_first_wins(tmp_path: Path) -> None:
    """Ten threads race to claim the same name with different session_ids.
    Exactly one create returns cleanly; the other nine raise NameCollision
    naming the winner's session_id (whichever thread landed first).
    """
    r = SessionRegistry(base=tmp_path)
    outcomes: list[tuple[str, str | None, str | None]] = []
    outcomes_lock = threading.Lock()

    def _try_claim(sid: str) -> None:
        try:
            r.create(
                session_id=sid,
                name="reviewer",
                driver="deterministic",
                workspace=scratch_ws("w"),
                workspace_shape="flat",
                bundle=None,
                seed="hi",
            )
            with outcomes_lock:
                outcomes.append((sid, "created", None))
        except NameCollision as exc:
            with outcomes_lock:
                outcomes.append((sid, "collision", exc.existing_session_id))

    threads = [threading.Thread(target=_try_claim, args=(f"s{i}",)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    created = [o for o in outcomes if o[1] == "created"]
    collisions = [o for o in outcomes if o[1] == "collision"]
    assert len(created) == 1
    assert len(collisions) == 9
    winner = created[0][0]
    assert all(c[2] == winner for c in collisions)
    assert r.by_name("reviewer") == winner

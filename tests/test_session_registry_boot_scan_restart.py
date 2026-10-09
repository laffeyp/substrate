"""Sprint 211 — boot scan restores manifests and rewrites stale status fields.

Simulates a daemon restart by constructing a second `SessionRegistry` against
the same base directory. The first registry created several sessions; the
second reads by-name.json + every manifest.json off disk and rewrites the
`status` field of any manifest whose stored status disagrees with the record's
true state per `_scan_record_status`:

  - hot segment torn (daemon died mid-turn) → `interrupted`
  - `substrate.RunFinalised` present → `ended`
  - otherwise (record quiescent, awaiting resume) → `parked`

The three fixtures below build the three record shapes directly on disk —
one via `ci_session_topology` for a real finalised run, one via a synthetic
manifest for a parked session with no record yet, one via a synthetic
manifest paired with a hand-written broken hot segment for interrupted.

"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from substrate import api
from substrate.topologies.session.ci import ci_session_topology
from substrate.topologies.session_registry import (
    SessionManifest,
    SessionRegistry,
    _manifest_to_dict,
    _scan_record_status,
)


def scratch_ws(name: str) -> str:
    """A workspace label inside this run's temp state root (tests/conftest.py)."""
    return os.path.join(os.environ["SUBSTRATE_HOME"], "workspaces", name)


def _write_manifest(base: Path, m: SessionManifest) -> None:
    session_dir = base / m.session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "manifest.json").write_text(
        json.dumps(_manifest_to_dict(m), indent=2, sort_keys=True), encoding="utf-8"
    )


def _mk_manifest(
    session_id: str, name: str | None, status: str, record_root: str
) -> SessionManifest:
    return SessionManifest(
        session_id=session_id,
        name=name,
        created_at=0.0,
        driver="deterministic",
        workspace=scratch_ws("w"),
        workspace_shape="flat",
        record_root=record_root,
        status=status,  # type: ignore[arg-type]
        bundle=None,
        seed="hi",
    )


@pytest.mark.asyncio
async def test_boot_scan_marks_ended_from_finalised_record(tmp_path: Path) -> None:
    """A session whose record has `substrate.RunFinalised` reads as `ended` on
    the boot scan, even if the on-disk manifest says `running` (stale — the
    daemon died between the finalisation and the manifest rewrite).
    """
    session_id = "s_ended"
    session_dir = tmp_path / session_id
    session_dir.mkdir()
    record_root = session_dir / "record"
    await api.Runtime(record_root).run(
        ci_session_topology(turns=("hi", "/exit"), session_id="s_ended_run")
    )
    # Manifest lies about the status — the boot scan corrects it.
    stale = _mk_manifest(session_id, "ended-fixture", "running", str(record_root))
    _write_manifest(tmp_path, stale)

    fresh = SessionRegistry(base=tmp_path)
    fresh.boot_scan()
    got = fresh.get(session_id)
    assert got is not None
    assert got.status == "ended"
    # Rewrite is on disk.
    on_disk = json.loads((tmp_path / session_id / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["status"] == "ended"


def test_boot_scan_marks_parked_when_record_root_is_absent(tmp_path: Path) -> None:
    """A manifest whose `record_root` does not exist is treated as `parked` (a
    fresh session that has not written anything yet). No crash on missing dir.
    """
    session_id = "s_parked"
    stale = _mk_manifest(session_id, "parked-fixture", "running", str(tmp_path / "nonexistent"))
    _write_manifest(tmp_path, stale)

    fresh = SessionRegistry(base=tmp_path)
    fresh.boot_scan()
    got = fresh.get(session_id)
    assert got is not None
    assert got.status == "parked"


def hot_segment(record_root: Path, data: bytes) -> None:
    record_root.mkdir(parents=True)
    (record_root / "events-000001.open.jsonl").write_bytes(data)


def _parked_record_bytes() -> bytes:
    """RunStarted, then the clean pause a session writes at the end of a turn."""
    from substrate.record import framing

    def frame(seq: int, kind: str, payload: dict) -> bytes:
        return framing.frame(
            {
                "kind": kind,
                "payload": payload,
                "producer": None,
                "schema": kind + "@1",
                "seq": seq,
                "t": 0.0,
            }
        )

    return frame(0, api.RUN_STARTED, {}) + frame(
        1, api.TERMINATION_MATCHED, {"decision": api.Decision.PAUSE_AWAIT_INPUT.value}
    )


def test_a_cleanly_parked_record_reads_parked(tmp_path: Path) -> None:
    record_root = tmp_path / "s_parked_whole" / "record"
    hot_segment(record_root, _parked_record_bytes())
    assert _scan_record_status(record_root) == "parked"


def test_boot_scan_marks_interrupted_from_torn_hot_segment(tmp_path: Path) -> None:
    """The same parked record with a frame cut mid-write after it: the daemon died while writing
    the next turn's first envelope. `read_record` skips the cut frame, so without the torn-tail
    check the boot scan read the last whole envelope, a clean pause, and called the session
    parked; the cut message was gone (UI sprint 109, N002). The fixture's whole frames carry
    valid CRCs, so the torn tail is the only thing that differs from the parked case above (lens
    audit F430: the old fixture's fake CRC also produced "interrupted")."""
    session_id = "s_interrupted"
    record_root = tmp_path / session_id / "record"
    hot_segment(
        record_root, _parked_record_bytes() + b'{"crc":"11111111","kind":"UserMessage","payl'
    )
    _write_manifest(
        tmp_path, _mk_manifest(session_id, "interrupted-fixture", "running", str(record_root))
    )

    assert _scan_record_status(record_root) == "interrupted"
    fresh = SessionRegistry(base=tmp_path)
    fresh.boot_scan()
    got = fresh.get(session_id)
    assert got is not None
    assert got.status == "interrupted"


def test_a_complete_frame_with_a_bad_crc_is_interrupted(tmp_path: Path) -> None:
    """A complete frame whose CRC does not match is corruption; boot scan does not resume it."""
    record_root = tmp_path / "s_corrupt" / "record"
    hot_segment(
        record_root,
        b'{"crc":"00000000","kind":"substrate.RunStarted","payload":{},'
        b'"producer":null,"schema":"substrate.RunStarted@1","seq":0,"t":0.0}\n',
    )
    assert _scan_record_status(record_root) == "interrupted"


@pytest.mark.asyncio
async def test_boot_scan_restores_multiple_sessions_across_restart(tmp_path: Path) -> None:
    """One `SessionRegistry` creates three sessions and finalises one; a second
    `SessionRegistry` on the same base reads them all back and returns the right
    status per session. This is the piece-C recovery promise end-to-end.
    """
    first = SessionRegistry(base=tmp_path)
    first.create(
        session_id="s_alive",
        name="alive",
        driver="deterministic",
        workspace=scratch_ws("w"),
        workspace_shape="flat",
        bundle=None,
        seed="hi",
    )
    first.create(
        session_id="s_ended_alt",
        name="ended-alt",
        driver="deterministic",
        workspace=scratch_ws("w"),
        workspace_shape="flat",
        bundle=None,
        seed="hi",
    )
    # Give s_ended_alt a real finalised record so the boot scan reclassifies it.
    ended_record = tmp_path / "s_ended_alt" / "record"
    await api.Runtime(ended_record).run(
        ci_session_topology(turns=("hi", "/exit"), session_id="s_ended_alt_run")
    )

    fresh = SessionRegistry(base=tmp_path)
    fresh.boot_scan()
    ids = {m.session_id: m.status for m in fresh.list_all()}
    assert ids["s_alive"] == "parked"
    assert ids["s_ended_alt"] == "ended"
    # by-name index survived.
    assert fresh.by_name("alive") == "s_alive"
    assert fresh.by_name("ended-alt") == "s_ended_alt"


def test_boot_scan_skips_the_wt_worktree_subdir(tmp_path: Path) -> None:
    """The daemon's git-worktree pattern parks per-session worktrees under
    `~/.substrate/sessions/wt/`. Those are not sessions; the boot scan must
    not treat the wt/ subtree as one. A crash there would prevent daemon
    boot even when the actual session directories are all fine.
    """
    (tmp_path / "wt").mkdir()
    (tmp_path / "wt" / "some-repo-s_xyz").mkdir()  # a worktree
    m = _mk_manifest("s_real", "real-fixture", "running", str(tmp_path / "s_real" / "record"))
    _write_manifest(tmp_path, m)

    fresh = SessionRegistry(base=tmp_path)
    fresh.boot_scan()  # must not raise
    assert {m.session_id for m in fresh.list_all()} == {"s_real"}

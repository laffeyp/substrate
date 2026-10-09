# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Off-bus sidecars — diagnostics + writer stats (technical §3.8, §6.4; F-OBS-6).

The sidecars are NEVER on the bus: they are plain JSONL under `<root>/sidecar/`, keyed by
the `seq` they observed but NEVER sequence-numbered themselves, and the writer's append
cycle does NO sidecar I/O on the hot path. The load-bearing invariant (conformance
check 14, diagnostic invariance): **enabling a sidecar MUST leave the bus log
bit-identical.** This holds by construction here — the sidecar is a separate sink the
runtime feeds *after* a frame is appended (or between cycles), and when a sidecar is
disabled its feed methods are simply never called, so the cycle's bytes are identical
whether or not diagnostics/stats are on.

  - `diagnostics.jsonl` — non-firing predicate evaluations (result, elapsed, observed seq)
    and budget-violation observations (§3.8). Buffered in memory, flushed by a background
    cadence or at fsync boundaries; the cycle never blocks on it.
  - `writer_stats.jsonl` — operator metrics (cycles/sec, queue depths, …; §6.4), sampled
    periodically when `--writer-stats` is enabled.

Sidecar files are read-only-safe for any consumer (a dashboard, `substrate stats`, `tail`)
and are excluded from the record's frame/CRC/replay surface entirely.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Sidecar:
    """A buffered off-bus JSONL sink under `<root>/sidecar/<name>.jsonl`.

    `record()` appends a dict to the in-memory buffer (never touches disk on the hot path);
    `flush()` writes the buffered records and clears the buffer. The runtime flushes off the
    cycle (between cycles / at fsync boundaries / at close). Records are plain JSON objects;
    they carry the observed `seq` but are never themselves sequence-numbered."""

    def __init__(self, root: Path | str, name: str) -> None:
        self._dir = Path(root) / "sidecar"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / f"{name}.jsonl"
        self._buf: list[dict[str, Any]] = []

    @property
    def path(self) -> Path:
        return self._path

    def record(self, entry: dict[str, Any]) -> None:
        """Buffer one off-bus record. Off the hot path: no I/O here."""
        self._buf.append(entry)

    def flush(self) -> None:
        """Append the buffered records to the JSONL file and clear the buffer. Plain text
        append; no fsync coupling to the bus writer (the sidecar is not the record)."""
        if not self._buf:
            return
        lines = b"".join(
            (json.dumps(e, sort_keys=True, separators=(",", ":")) + "\n").encode()
            for e in self._buf
        )
        with open(self._path, "ab") as fh:
            fh.write(lines)
        self._buf.clear()


class DiagnosticSidecar:
    """The §3.8 diagnostic sidecar: non-firing predicate evals + budget-violation
    observations, keyed by observed seq, never sequence-numbered. Off-hot-path (buffered).
    A disabled run holds no instance and never calls these methods, so the bus log is
    bit-identical with diagnostics on or off (conformance check 14)."""

    def __init__(self, root: Path | str) -> None:
        self._sink = Sidecar(root, "diagnostics")

    @property
    def path(self) -> Path:
        return self._sink.path

    def predicate_evaluated(
        self, *, seq: int, predicate_id: str, result: bool, elapsed_us: float
    ) -> None:
        """Record a (typically non-firing) predicate evaluation observed at `seq`."""
        self._sink.record(
            {
                "observed_seq": seq,
                "predicate_id": predicate_id,
                "result": result,
                "elapsed_us": round(elapsed_us, 3),
            }
        )

    def budget_violation(
        self, *, seq: int, predicate_id: str, measured_us: float, count: int
    ) -> None:
        """Record an over-budget predicate observation at `seq` (the kth consecutive)."""
        self._sink.record(
            {
                "observed_seq": seq,
                "predicate_id": predicate_id,
                "kind": "budget_violation",
                "measured_us": round(measured_us, 3),
                "consecutive": count,
            }
        )

    def flush(self) -> None:
        self._sink.flush()


class WriterStatsSidecar:
    """The §6.4 writer-stats sidecar: operator metrics sampled periodically when
    `--writer-stats` is enabled. Off-bus; never sequence-numbered."""

    def __init__(self, root: Path | str) -> None:
        self._sink = Sidecar(root, "writer_stats")

    @property
    def path(self) -> Path:
        return self._sink.path

    def sample(self, metrics: dict[str, Any]) -> None:
        """Record one metrics sample (cycles_per_sec, admission_depth, …, §6.4)."""
        self._sink.record(dict(metrics))

    def flush(self) -> None:
        self._sink.flush()


def read_sidecar(path: Path | str) -> list[dict[str, Any]]:
    """Read an off-bus sidecar JSONL file into a list of records (read-only). Used by
    `substrate stats` and dashboards; returns [] if the file does not exist."""
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    lines = [ln.strip() for ln in p.read_text().splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                break  # the flush is a plain append; a crash mid-write leaves a cut last line
            raise
    return out

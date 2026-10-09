# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Generate committed CI-mode run records for the bundled topologies.

SINGLE SOURCE: the records are generated from the BUNDLED REGISTRY — the exact factories behind
`substrate run --topology <name>` / `substrate demo run <name>` — so `demo replay <name>` (the
committed record) and `demo run <name>` (a live run) always match (review #25 finding A). Add a
topology to `bundled.BUNDLED` and it gets a record here automatically.

Regenerate with `uv run python scripts/gen_topology_records.py`. The wall-clock `t` varies per
generation (excluded from D-8 log-equivalence); the event SEQUENCE and the decision hashes are
stable (the tests assert those, not `t`).
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from substrate.api import Runtime
from substrate.topologies import bundled

TOPOS = Path(__file__).resolve().parent.parent / "src" / "substrate" / "topologies"


def _fresh(name: str) -> Path:
    # bundled.record_path maps a renamed key (pair_coding_chunked) to the directory its committed
    # record lives in; TOPOS / name wrote a stray copy beside it and left the real one stale.
    root = bundled.record_path(name)
    if root.exists():
        shutil.rmtree(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    return root


async def main() -> None:
    names = bundled.names()
    for name in names:
        await Runtime(_fresh(name)).run(bundled.BUNDLED[name]())
    for lock in TOPOS.rglob(".lock"):  # runtime lock markers are not part of the durable record
        lock.unlink()
    print(f"wrote CI-mode records for {len(names)} bundled topologies under {TOPOS}")


if __name__ == "__main__":
    asyncio.run(main())

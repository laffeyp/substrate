# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Substrate — a concurrent streaming dataflow runtime.

You bring computations (Producers) that take typed input and emit a stream of
typed Events; the runtime runs them concurrently, coordinates them through a
single totally-ordered append-only Bus, and creates new Producers dynamically
when Predicates over Views of the log are satisfied (Triggers). All state lives
on the log; the persisted run record is the canonical account of what happened.

Working name "substrate" (B-Q-1 deferred). Public API is re-exported from
`substrate.api`; see the kernel spec (v15), product spec (DRAFT 7), technical
spec (DRAFT 5), and the locked vocabulary at process/signals/0.3.json.
"""

# Derived from the installed distribution's metadata (the dist is `substrate-kernel`; the import name
# stayed `substrate` at the 2026-07-24 rename). A hardcoded "0.0.0" reported the wrong version on a
# project whose thesis is that a run must be attributable (review C-4). Falls back to "0.0.0" only for a
# source tree with no installed metadata at all.
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

try:
    __version__ = _dist_version("substrate-kernel")
except PackageNotFoundError:  # pragma: no cover — not installed (bare source tree)
    __version__ = "0.0.0"

del _dist_version, PackageNotFoundError

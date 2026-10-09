# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The per-user state root, in a leaf module every layer can import.

`substrate.api` re-exports `substrate_home`. It lived in api itself until 2026-10-08, so
`bundles` (which api re-exports) had to import api back to find the root: a cycle.
"""

from __future__ import annotations

import os
from pathlib import Path


def substrate_home() -> Path:
    """The root of substrate's per-user state tree.

    Returns ``Path(os.environ["SUBSTRATE_HOME"])`` when set,
    else ``Path.home() / ".substrate"``.
    """
    raw = os.environ.get("SUBSTRATE_HOME")
    if raw:
        return Path(raw)
    return Path.home() / ".substrate"


__all__ = ["substrate_home"]

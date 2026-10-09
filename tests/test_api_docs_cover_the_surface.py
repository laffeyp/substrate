# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""docs/api.md is generated from `api.__all__`, and the committed page is current.

The generator refuses when its groups do not partition `__all__`, but nothing ran it, so the page
fell 31 names behind and kept 4 that moved to `substrate.app` (found in K251, 2026-10-08).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _generator():
    spec = importlib.util.spec_from_file_location(
        "gen_api_docs", ROOT / "scripts" / "gen_api_docs.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_committed_api_page_is_current() -> None:
    generated = _generator().generate()
    committed = (ROOT / "docs" / "api.md").read_text()
    assert committed == generated, (
        "docs/api.md is stale: run `uv run python scripts/gen_api_docs.py`"
    )

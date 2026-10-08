"""The kernel CLI tests that drive substrate-ui's daemon in-process (UI sprint 106).

Those tests import `server.py` from the substrate-ui checkout beside this repo. Kernel CI checks
out only the kernel, so the import failed there and 21 tests errored at setup on every run. A test
should depend only on what its own repo provides (hermeticity: Winters et al., *Software
Engineering at Google*, ch. 14); where that cannot hold, it skips with the reason (pytest:
skip "tests that depend on an external resource which is not available").
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

UI_ROOT = Path(__file__).resolve().parent.parent.parent / "substrate-ui"


def ui_server_module() -> ModuleType:
    """substrate-ui's `server` module, or a skip when the checkout is not beside this repo."""
    if not (UI_ROOT / "server.py").exists():
        pytest.skip(f"needs the substrate-ui checkout at {UI_ROOT}: this test drives its daemon")
    if str(UI_ROOT) not in sys.path:
        sys.path.insert(0, str(UI_ROOT))
    import server  # type: ignore[import-not-found]

    return server

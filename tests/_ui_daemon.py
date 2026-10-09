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


def ui_daemon(base: Path) -> tuple[object, object]:
    """substrate-ui's App with a session registry under `base`, served on 127.0.0.1:<ephemeral>
    by a started `AppHTTPServer`. Returns `(app, srv)`; the caller shuts `srv` down. The daemon's
    state lives on the App (UI sprint 111), not on the `server` module."""
    import threading

    server = ui_server_module()
    app = server.App()
    app.install_registry(base)
    srv = server.AppHTTPServer(("127.0.0.1", 0), app)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return app, srv

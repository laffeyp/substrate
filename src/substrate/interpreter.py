# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The app's own Python interpreter and the processes it starts (UI sprint 177).

The packaged app starts its server with `PYTHONHOME` set, because the bundled `python3` is a link
into the bundle and cannot find its standard library without it (`electron/main.js`, F10). Every
process the server starts inherited the variable: a session's `bash`, a run's checks, a CLI driver's
own shell. There a user's `python3` (any other interpreter) read the bundle's 3.14 library and died
with "Failed to import encodings module". The server calls `release_python_home` first thing: the
running interpreter has already found its home, and the processes it starts get the user's
environment. A process that runs the app's own interpreter takes its home back with
`own_interpreter_env`. Outside the packaged app `PYTHONHOME` is unset and both do nothing.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

OWN_PYTHONHOME = "SUBSTRATE_PYTHONHOME"


def release_python_home() -> None:
    """Move `PYTHONHOME` out of this process's environment, kept as `SUBSTRATE_PYTHONHOME`."""
    home = os.environ.pop("PYTHONHOME", None)
    if home is not None:
        os.environ[OWN_PYTHONHOME] = home


def own_interpreter_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """`env` (this process's when None) for a process that runs the app's own interpreter: its
    `PYTHONHOME` restored when `release_python_home` moved it."""
    out = dict(os.environ if env is None else env)
    home = out.get(OWN_PYTHONHOME)
    if home and "PYTHONHOME" not in out:
        out["PYTHONHOME"] = home
    return out


__all__ = ["OWN_PYTHONHOME", "own_interpreter_env", "release_python_home"]

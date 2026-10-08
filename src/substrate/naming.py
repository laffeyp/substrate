"""Names that become one path component.

A bundle name or a role name is joined onto a directory (`<bundles_root>/<name>/`,
`<prompts>/<role>.md`). Each must name one entry in that directory: a name with a separator or a
`..` would reach outside it (lens audit F074, F110: `PATCH /api/session {bundle: "../x"}`).
"""

from __future__ import annotations

import re

_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def check_path_component(kind: str, name: str) -> str:
    """Return `name` if it is one safe path component; raise ValueError naming `kind` otherwise.
    Safe: starts with a letter or digit, then letters, digits, `.`, `_`, `-`; never `..`."""
    if not isinstance(name, str) or not _COMPONENT.fullmatch(name) or ".." in name:
        raise ValueError(f"{kind} name {name!r} is not a plain name (letters, digits, . _ -)")
    return name


__all__ = ["check_path_component"]

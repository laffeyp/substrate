# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Container agent — the parsing + edit logic (no Docker, no model)."""

from substrate.assay.swebench_agent import _ACTION, _PATH, _SR, _apply_edit


def test_parse_edit_action():
    reply = "ACTION: edit_file\nPATH: src/a.py\n<<<<<<< SEARCH\nold line\n=======\nnew line\n>>>>>>> REPLACE"
    assert _ACTION.search(reply).group(1).lower() == "edit_file"
    assert _PATH.search(reply).group(1) == "src/a.py"
    sr = _SR.search(reply)
    assert sr.group(1) == "old line" and sr.group(2) == "new line"


def test_parse_read_and_done():
    assert _ACTION.search("ACTION: read_file\nPATH: x.py").group(1).lower() == "read_file"
    assert _ACTION.search("ACTION: done").group(1).lower() == "done"


class _StubWS:
    def __init__(self, content: str) -> None:
        self._c = content
        self.written: str | None = None

    def read_file(self, path: str) -> str:
        return self._c

    def write_file(self, path: str, content: str) -> None:
        self.written = content


def test_apply_edit_applies_and_reports():
    ws = _StubWS("def f():\n    return 1\n")
    note = _apply_edit(ws, "a.py", "    return 1", "    return 2")  # type: ignore[arg-type]
    assert "applied" in note and ws.written == "def f():\n    return 2\n"


def test_apply_edit_reports_missing_search():
    ws = _StubWS("def f():\n    return 1\n")
    assert "not found" in _apply_edit(ws, "a.py", "nonexistent", "x")  # type: ignore[arg-type]
    assert ws.written is None  # nothing written when SEARCH doesn't match

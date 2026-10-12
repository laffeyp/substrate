# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K295: `bash` says when it cut its output.

Before: stdout came back as its first 8,000 bytes and stderr as its last 2,000 characters, with
nothing to say either was cut. A model read 222 lines of a 4,000-line file and answered 222.
"""

from __future__ import annotations

import re
from pathlib import Path

from substrate.topologies.tool_loop.tools import full_suite


def _bash(root: Path, command: str) -> dict[str, object]:
    out = full_suite(root, owner="t295")["bash"].run([command])
    assert isinstance(out, dict)
    return out


def test_long_stdout_is_cut_with_a_marker_naming_the_whole(tmp_path: Path) -> None:
    out = _bash(tmp_path, "seq 1 4000")
    stdout = str(out["stdout"])
    m = re.search(
        r"\[bash: stdout cut to its first 8,000 of ([\d,]+) bytes; the whole output is in (\S+)\.",
        stdout,
    )
    assert m, stdout[-300:]
    total = int(m.group(1).replace(",", ""))
    assert total == len("".join(f"{i}\n" for i in range(1, 4001)))
    assert Path(m.group(2)).read_text().splitlines()[-1] == "4000"


def test_long_stderr_is_cut_with_a_marker(tmp_path: Path) -> None:
    out = _bash(tmp_path, "seq 1 2000 1>&2")
    assert str(out["stderr"]).startswith("[bash: stderr cut to its last 2,000 of ")


def test_short_output_has_no_marker(tmp_path: Path) -> None:
    out = _bash(tmp_path, "echo hi; echo err 1>&2")
    assert out["stdout"] == "hi\n" and "[bash:" not in str(out["stderr"])

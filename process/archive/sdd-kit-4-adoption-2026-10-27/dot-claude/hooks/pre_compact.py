#!/usr/bin/env python3
"""PreCompact hook (sdd-kit-4). Writes the session's handoff from its transcript before a
compaction drops it. No model involved. Never blocks the compaction: always exits 0."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from _common import handoffs_dir, project_root, read_input, session_files

LAST_MESSAGES = 5


def main() -> int:
    data = read_input()
    root = project_root(data)
    session = str(data.get("session_id") or "unknown")
    read, changed, said = session_files(Path(str(data.get("transcript_path") or "")))
    out_dir = handoffs_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    out = out_dir / f"handoff-{stamp}-{session}.md"
    lines = [
        f"# handoff-{stamp}",
        "",
        f"*Written by the PreCompact hook before a {data.get('trigger', 'compact')} compaction. "
        f"Session `{session}`. Transcript: `{data.get('transcript_path', '')}`.*",
        "",
        "## Files read (Read tool), in order",
        "",
        *[f"- `{p}`" for p in read],
        "",
        "## Files edited or written",
        "",
        *[f"- `{p}`" for p in changed],
        "",
        f"## The person's last {LAST_MESSAGES} messages, verbatim",
        "",
    ]
    for text in said[-LAST_MESSAGES:]:
        lines += ["```", text, "```", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

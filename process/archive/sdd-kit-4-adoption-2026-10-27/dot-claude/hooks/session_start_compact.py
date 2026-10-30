#!/usr/bin/env python3
"""SessionStart hook, matcher `compact` (sdd-kit-4). Prints what the agent must re-read after a
compaction: the core corpus's every-session files and the files this session read before it.
Claude Code adds the printed text to the agent's context; it keeps it under 10,000 characters."""

from __future__ import annotations

import re

from _common import every_session_rows, handoffs_dir, project_root, read_input

CAP = 9500


def main() -> int:
    data = read_input()
    root = project_root(data)
    session = str(data.get("session_id") or "unknown")
    lines = [
        "A compaction just happened. Files read before it are no longer read.",
        "Before any write, re-read each file below and name it with its line count in chat.",
        "",
        "Core corpus, every session:",
        *every_session_rows(root),
    ]
    handoffs = sorted(
        p for p in handoffs_dir(root).glob(f"handoff-*-{session}.md") if not p.stem.endswith("-summary")
    )
    if handoffs:
        text = handoffs[-1].read_text(encoding="utf-8")
        section = text.split("## Files read (Read tool), in order", 1)[-1].split("\n## ", 1)[0]
        read = re.findall(r"^- `([^`]+)`", section, flags=re.M)
        lines += ["", f"Files this session read before the compaction ({handoffs[-1].name}):", *read]
    out = "\n".join(lines)
    if len(out) > CAP:
        out = out[:CAP] + "\n[list cut at the hook's limit; the full list is in the handoff file named above]"
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

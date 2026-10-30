#!/usr/bin/env python3
"""PostCompact hook (sdd-kit-4). Saves the compaction's summary beside the handoff the
PreCompact hook wrote for this session, so the summary can be checked against the record."""

from __future__ import annotations

from _common import handoffs_dir, project_root, read_input


def main() -> int:
    data = read_input()
    root = project_root(data)
    session = str(data.get("session_id") or "unknown")
    out_dir = handoffs_dir(root)
    handoffs = sorted(out_dir.glob(f"handoff-*-{session}.md"))
    if handoffs:
        target = handoffs[-1].with_name(handoffs[-1].stem + "-summary.md")
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"summary-{session}.md"
    target.write_text(str(data.get("compact_summary") or ""), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

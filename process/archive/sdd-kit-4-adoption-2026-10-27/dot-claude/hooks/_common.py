"""Shared helpers for the sdd-kit-4 compaction hooks. Standard library only.

The project root is $CLAUDE_PROJECT_DIR when Claude Code sets it, else the hook input's `cwd`.
The project's root CLAUDE.md names its files on its paths line, e.g.
    Working agreement: `process/WORKING_AGREEMENT.md`. ... Handoffs: `process/handoffs/`.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


def read_input() -> dict:
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def project_root(data: dict) -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".").resolve()


def _named_path(root: Path, label: str, default: str) -> Path:
    claude_md = root / "CLAUDE.md"
    if claude_md.is_file():
        m = re.search(label + r":\s*`([^`]+)`", claude_md.read_text(encoding="utf-8"))
        if m:
            return (root / m.group(1)).resolve()
    return (root / default).resolve()


def handoffs_dir(root: Path) -> Path:
    return _named_path(root, "Handoffs", "handoffs")


def working_agreement(root: Path) -> Path:
    return _named_path(root, "Working agreement", "WORKING_AGREEMENT.md")


def every_session_rows(root: Path) -> list[str]:
    """The `every session` rows of the working agreement's ## Core corpus table."""
    wa = working_agreement(root)
    if not wa.is_file():
        return []
    rows, inside = [], False
    for line in wa.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.strip() == "## Core corpus"
            continue
        if inside and line.startswith("|") and "every session" in line:
            rows.append(line.strip())
    return rows


def session_files(transcript: Path) -> tuple[list[str], list[str], list[str]]:
    """(files opened with Read, files edited or written, the person's messages) from a transcript."""
    read, changed, said = [], [], []
    if not transcript.is_file():
        return read, changed, said
    for line in transcript.open(encoding="utf-8"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = rec.get("message") or {}
        content = msg.get("content")
        if rec.get("type") == "assistant" and isinstance(content, list):
            for item in content:
                if item.get("type") != "tool_use":
                    continue
                path = (item.get("input") or {}).get("file_path")
                if not path:
                    continue
                target = read if item.get("name") == "Read" else changed if item.get("name") in ("Edit", "Write") else None
                if target is not None and path not in target:
                    target.append(path)
        elif rec.get("type") == "user":
            if isinstance(content, str) and not content.startswith("<"):
                said.append(content)
            elif isinstance(content, list):
                for item in content:
                    text = item.get("text") if item.get("type") == "text" else None
                    if text and not text.startswith("<"):
                        said.append(text)
    return read, changed, said

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The SEARCH/REPLACE applier — REPAIR's deterministic core (design §4b, KIT_DIARY finding 11).

The one component where a v1 shortcut poisons the MEASUREMENT, not just lowers it: a candidate that
fails to apply for MECHANICAL reasons (ambiguous match, whitespace drift, overlap) confounds "the model
wrote a bad fix" with "the applier dropped a good one". So the contract is pinned and deterministic:

  - SEARCH/REPLACE blocks (Aider/Agentless format), NOT unified diffs (LLMs miscount `@@` lines).
  - Unique-match-or-reject via a TIERED match: (1) exact-byte; (2) if zero, a leading-whitespace-flexible
    line match, accepted ONLY if still UNIQUE; NEVER fuzzy/similarity. Zero/multi at every tier -> reject.
  - File creation: an empty SEARCH block writes a whole new file (path must not already exist).
  - Overlap: all blocks resolve against the ORIGINAL file, spliced in one pass; overlapping spans -> reject.
  - CRLF: the file's real line endings are detected and restored on write.
  - Atomic, all-or-nothing across the whole candidate: every file's every block resolves, or nothing is
    written.
  - Output is `git diff` on the clone, NEVER hand-built hunks -> the `model_patch`.

Deterministic given (candidate text, repo state): its observation contract (#24) is an ordinary unit test.

Block format (markers each on their own line):

    # path: pkg/mod.py
    <<<<<<< SEARCH
    <exact source to find>
    =======
    <replacement>
    >>>>>>> REPLACE
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

_PATH = "# path:"
_SEARCH = "<<<<<<< SEARCH"
_DIVIDER = "======="
_REPLACE = ">>>>>>> REPLACE"


@dataclass(frozen=True)
class ApplyResult:
    """The applier's verdict on one candidate. `applied` True -> `model_patch` is the git diff and
    `creates_file` flags whether any block created a new file. `applied` False -> `error` is the
    structured reason fed back to the correction loop (it maps to Verdict.summary)."""

    applied: bool
    model_patch: str = ""
    creates_file: bool = False
    error: str | None = None


@dataclass(frozen=True)
class _Block:
    search: str
    replace: str


def parse_candidate(text: str) -> dict[str, list[_Block]]:
    """Parse a candidate's response into per-file SEARCH/REPLACE blocks, in document order.

    Raises ValueError on a malformed block (an unterminated or mis-ordered marker triple, or a block
    with no preceding `# path:`)."""
    files: dict[str, list[_Block]] = {}
    lines = text.splitlines()
    path: str | None = None
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith(_PATH):
            path = stripped[len(_PATH) :].strip()
            files.setdefault(path, [])
            i += 1
            continue
        if stripped == _SEARCH:
            if path is None:
                raise ValueError("SEARCH block with no preceding `# path:` header")
            # collect SEARCH body until the divider
            i += 1
            search_lines: list[str] = []
            while i < n and lines[i].strip() != _DIVIDER:
                if lines[i].strip() == _SEARCH or lines[i].strip() == _REPLACE:
                    raise ValueError(f"unterminated SEARCH block for {path!r} (nested marker)")
                search_lines.append(lines[i])
                i += 1
            if i >= n:
                raise ValueError(f"SEARCH block for {path!r} missing `=======` divider")
            # skip the divider, collect REPLACE body until the close marker
            i += 1
            replace_lines: list[str] = []
            while i < n and lines[i].strip() != _REPLACE:
                if lines[i].strip() == _SEARCH or lines[i].strip() == _DIVIDER:
                    raise ValueError(f"malformed REPLACE block for {path!r} (extra marker)")
                replace_lines.append(lines[i])
                i += 1
            if i >= n:
                raise ValueError(f"REPLACE block for {path!r} missing `>>>>>>> REPLACE` close")
            i += 1  # skip the close marker
            search = "\n".join(search_lines)
            replace = "\n".join(replace_lines)
            files[path].append(_Block(search=search, replace=replace))
            continue
        i += 1
    return {p: b for p, b in files.items() if b}


def _leading_ws(s: str) -> str:
    return s[: len(s) - len(s.lstrip())]


def _locate(original: str, search: str) -> tuple[int, int, bool] | str:
    """Return `(start, end, reindent)` of the UNIQUE LINE-ANCHORED occurrence of `search` in `original`,
    or a reason ('not_found' / 'ambiguous'). Every match is WHOLE-LINE (SEARCH/REPLACE blocks are
    whole-line by format) — a mid-line substring is NEVER a match (matching a prefix of a longer line
    silently corrupts its tail: `y = 1` must not match `y = 1234`). Tier 1: exact lines (`reindent=False`).
    Tier 2: leading-whitespace-flexible lines, still-unique (`reindent=True`). Never fuzzy/similarity."""
    o_lines = original.split("\n")
    s_lines = search.split("\n")
    window = len(s_lines)
    if window == 0 or window > len(o_lines):
        return "not_found"

    def span_at(start_ln: int) -> tuple[int, int]:
        # +1 per line for the "\n"; the last-line over-count is absorbed by the slice (end<=len).
        start = sum(len(o_lines[k]) + 1 for k in range(start_ln))
        end = start + sum(len(o_lines[start_ln + k]) + 1 for k in range(window)) - 1
        return (start, end)

    # Tier 1 — exact whole-line match.
    exact = [i for i in range(len(o_lines) - window + 1) if o_lines[i : i + window] == s_lines]
    if len(exact) == 1:
        s, e = span_at(exact[0])
        return (s, e, False)
    if len(exact) > 1:
        return "ambiguous"

    # Tier 2 — leading-whitespace-flexible whole-line match, still-unique-or-reject.
    s_strip = [ln.strip() for ln in s_lines]
    flex = [
        i
        for i in range(len(o_lines) - window + 1)
        if [o_lines[i + k].strip() for k in range(window)] == s_strip
    ]
    if len(flex) == 1:
        s, e = span_at(flex[0])
        return (s, e, True)
    return "ambiguous" if flex else "not_found"


def _reindent(replace: str, search: str, original_region: str) -> str:
    """Re-indent the REPLACE to the file's real indentation (tier-2 restore): shift every replace line by
    the leading-whitespace delta between the matched region's first line and the SEARCH's first line."""
    s_first = next((ln for ln in search.split("\n") if ln.strip()), "")
    o_first = next((ln for ln in original_region.split("\n") if ln.strip()), "")
    s_ind, o_ind = _leading_ws(s_first), _leading_ws(o_first)
    if s_ind == o_ind:
        return replace
    out: list[str] = []
    for ln in replace.split("\n"):
        if not ln.strip():
            out.append(ln)
        elif o_ind.startswith(s_ind):  # file indented MORE: prepend the extra
            out.append(o_ind[len(s_ind) :] + ln)
        elif s_ind.startswith(o_ind) and ln.startswith(
            s_ind[len(o_ind) :]
        ):  # file indented LESS: trim
            out.append(ln[len(s_ind) - len(o_ind) :])
        else:
            out.append(ln)
    return "\n".join(out)


def _resolve_file(
    original: str | None, blocks: list[_Block], relpath: str
) -> tuple[str, bool] | str:
    """Resolve all of one file's blocks. Returns (new_content_lf, creates_file) or a string error.
    `original` is None for a not-yet-existing file. Resolves against the ORIGINAL and splices once."""
    # File creation: empty-SEARCH writes a whole new file.
    if original is None:
        if len(blocks) == 1 and blocks[0].search == "":
            return (blocks[0].replace, True)
        return f"{relpath}: file does not exist (use a single empty-SEARCH block to create it)"
    if any(b.search == "" for b in blocks):
        return f"{relpath}: empty-SEARCH (create) block targets an existing file"

    # Locate every block against the ORIGINAL; collect spans.
    spans: list[tuple[int, int, str]] = []  # (start, end, replacement)
    for idx, b in enumerate(blocks, 1):
        loc = _locate(original, b.search)
        if isinstance(loc, str):
            reason = (
                "SEARCH text not found"
                if loc == "not_found"
                else "SEARCH text matches multiple locations (ambiguous)"
            )
            return f"{relpath} block {idx}: {reason}; add surrounding context to make it unique"
        start, end, reindent = loc
        replacement = _reindent(b.replace, b.search, original[start:end]) if reindent else b.replace
        spans.append((start, end, replacement))

    # Overlap check, then single-pass splice from the original.
    spans.sort(key=lambda t: t[0])
    for j in range(len(spans) - 1):
        if spans[j][1] > spans[j + 1][0]:
            return f"{relpath}: two SEARCH blocks overlap; split into disjoint edits"
    out: list[str] = []
    cursor = 0
    for start, end, replacement in spans:
        out.append(original[cursor:start])
        out.append(replacement)
        cursor = end
    out.append(original[cursor:])
    return ("".join(out), False)


def apply_candidate(text: str, repo_dir: str, *, base_ref: str = "HEAD") -> ApplyResult:
    """Apply a candidate's SEARCH/REPLACE blocks to the git working tree at `repo_dir` (a clone at the
    instance's base_commit), atomically, and return the `git diff` as `model_patch`. All-or-nothing:
    on any block failure, nothing is written and `error` carries the structured reason.

    PRECONDITION (the topology's contract, sprint 5): `repo_dir` is a PRISTINE clone at the instance's
    base_commit and `base_ref` names that commit (the `HEAD` default assumes HEAD==base_commit). A
    correction loop reusing one clone across rounds MUST `git reset --hard base_ref` between candidates,
    else the diff accumulates the prior rounds' edits."""
    import os

    try:
        files = parse_candidate(text)
    except ValueError as exc:
        return ApplyResult(applied=False, error=f"parse failed: {exc}")
    if not files:
        return ApplyResult(applied=False, error="no SEARCH/REPLACE blocks found")

    # Containment: reject any path that escapes the clone (absolute, or via `..`). A model can emit an
    # escaping relative path even non-adversarially; an adversarial one would write outside the tree.
    repo_real = os.path.realpath(repo_dir)
    for relpath in files:
        target = os.path.realpath(os.path.join(repo_dir, relpath))
        if os.path.isabs(relpath) or (
            target != repo_real and not target.startswith(repo_real + os.sep)
        ):
            return ApplyResult(applied=False, error=f"path escapes the repo: {relpath!r}")

    # Resolve EVERY file first (atomic): compute new content for all before writing any.
    resolved: dict[
        str, tuple[str, bool, bool]
    ] = {}  # relpath -> (new_content_lf, creates_file, uses_crlf)
    for relpath, blocks in files.items():
        full = os.path.join(repo_dir, relpath)
        if os.path.exists(full):
            with open(full, "rb") as fh:
                raw = fh.read()
            uses_crlf = b"\r\n" in raw[:4096]
            original: str | None = (
                raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
                if uses_crlf
                else raw.decode("utf-8", errors="replace")
            )
        else:
            original, uses_crlf = None, False
        result = _resolve_file(original, blocks, relpath)
        if isinstance(result, str):
            return ApplyResult(applied=False, error=result)
        new_content, creates = result
        resolved[relpath] = (new_content, creates, uses_crlf)

    # All resolved — write atomically (we already proved every block applies).
    creates_any = False
    for relpath, (new_content, creates, uses_crlf) in resolved.items():
        full = os.path.join(repo_dir, relpath)
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        data = (
            new_content.replace("\n", "\r\n").encode("utf-8")
            if uses_crlf
            else new_content.encode("utf-8")
        )
        with open(full, "wb") as fh:
            fh.write(data)
        creates_any = creates_any or creates

    # model_patch = git diff on the clone (NEVER hand-built). Stage so new files show, diff staged vs base.
    subprocess.run(["git", "-C", repo_dir, "add", "-A"], capture_output=True, check=False)
    diff = subprocess.run(
        ["git", "-C", repo_dir, "diff", "--cached", base_ref],
        capture_output=True,
        text=True,
        check=False,
    )
    # Verdict.passed = applied cleanly AND git-diffs NON-EMPTY (locked vocab). A no-op candidate (or an
    # edit that nets to nothing) would otherwise be submitted as an EMPTY patch = a silent not-resolve.
    if diff.stdout.strip() == "":
        return ApplyResult(applied=False, error="no-op: candidate produced an empty diff")
    return ApplyResult(applied=True, model_patch=diff.stdout, creates_file=creates_any)

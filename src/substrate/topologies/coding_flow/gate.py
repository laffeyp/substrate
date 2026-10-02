# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The deterministic core of the coding-flow topology: parse a candidate's artifacts, write them to
a throwaway sandbox, run the task's GATE command, and return a normalized verdict.

This is the "build-validation" the precursor (prompt-factory) did with a project build — generalized:
the gate is a free-form shell command the task declares (`ruff check . && mypy . && pytest`,
`cargo build && cargo test`, `npm run build`, …). The flow never inspects the code; the gate's exit
code IS the truth. Pure deterministic code — no model anywhere near the validation, by the
heterogeneous-producers rule (truth is a test run, not an LLM's opinion).

The verdict PAYLOAD is NORMALIZED (temp paths and timings stripped) so a fixed candidate + gate yields
a byte-identical VERDICT. That is verdict-stability, not record reproducibility: coding_flow's run as a
whole is NOT replay-deterministic (the gate is a real subprocess — see coding_flow's own docstring),
so only the Verdict payload is byte-stable, not the record.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from msgspec import Struct

# A candidate declares each file's path two ways real coders both emit: as a `# path: X` header on
# the line BEFORE a fenced block, or as the FIRST comment line INSIDE the fence. Handle both — being
# strict about one cost a whole real-model run (every candidate parsed to zero files).
_FENCE = re.compile(r"```[A-Za-z0-9_+.-]*[ \t]*\r?\n(?P<body>.*?)\r?\n```", re.DOTALL)
_PATH = re.compile(r"^\s*(?:#|//|<!--|;|--)?\s*path:\s*(?P<path>[\w./-]+)", re.IGNORECASE)
_TIMING = re.compile(r"\bin \d+\.\d+s\b")  # pytest "= 8 passed in 0.04s ="  -> strip the wall-clock


class GateResult(Struct, frozen=True):
    """The outcome of running the gate on one candidate. `passed` is the exit-code truth; `summary`
    is the normalized gate output (deterministic for a fixed candidate); `returncode` is the raw rc."""

    passed: bool
    returncode: int
    summary: str


def parse_artifacts(text: str) -> dict[str, str]:
    """Extract the path-tagged fenced-block payloads from a drafter's response into {path: content}.
    Accepts a `# path: X` header just before a fence OR a `# path: X` first comment line inside it. A
    response with no recognizable payloads yields an empty dict (the validator treats it as a
    candidate that wrote nothing — it fails the gate honestly, not a crash)."""
    out: dict[str, str] = {}
    pos = 0
    for m in _FENCE.finditer(text):
        body = m.group("body")
        path: str | None = None
        # (a) a `# path: X` header on the line(s) immediately before the fence
        for line in reversed(text[pos : m.start()].rstrip().splitlines()[-2:]):
            header = _PATH.match(line)
            if header:
                path = header.group("path")
                break
        # (b) else the path as the first comment line INSIDE the fence (strip it from the body)
        lines = body.splitlines()
        if path is None and lines and (inner := _PATH.match(lines[0])):
            path = inner.group("path")
            body = "\n".join(lines[1:]).lstrip("\n")
        if path:
            out[path] = body
        pos = m.end()
    return out


# Files an honest candidate has no business emitting — test/lint/build config that can neuter the gate.
_CONFIG_DENY = frozenset(
    {
        "conftest.py",
        "pytest.ini",
        ".pytest.ini",
        "tox.ini",
        "setup.cfg",
        "setup.py",
        "pyproject.toml",
        "ruff.toml",
        ".ruff.toml",
        "mypy.ini",
        ".mypy.ini",
        "pytest_plugins.py",
    }
)


def sanitize_candidate_artifacts(artifacts: dict[str, str]) -> dict[str, str]:
    """Drop config and test files from a CANDIDATE's parsed artifacts before they reach the sandbox.

    The grade-time isolation hole: the gate runs in a config-less sandbox, so a candidate that emits a
    `conftest.py`/`pyproject.toml` whose `addopts = "--co"` makes pytest collect-only and exit 0 — a
    FALSE 'resolved' with no test actually run — or sneaks in its own `test_*.py`, subverts the gate.
    The candidate's job is to emit MODULES; the tests and any config are the harness's, layered on AFTER
    this (fixtures / held-out tests win on collision). Applied at BOTH gates (dev validation and the
    held-out oracle grade), so neither the correction loop nor the score can be gamed by injected
    config. (This does not sandbox candidate code from READING a co-located test file at runtime — that
    residual needs process isolation; tracked separately.)"""
    safe: dict[str, str] = {}
    for path, content in artifacts.items():
        base = Path(path).name.lower()
        if (
            base in _CONFIG_DENY
            or (base.startswith("test_") and base.endswith(".py"))
            or base.endswith("_test.py")
        ):
            continue
        safe[path] = content
    return safe


def _normalize(output: str, sandbox: Path) -> str:
    """Make the gate output reproducible: drop the per-run temp path and wall-clock timings, and cap
    length. Two runs of the same candidate then produce the same summary, so the record is stable."""
    cleaned = output.replace(str(sandbox), "<sandbox>").replace(str(sandbox.resolve()), "<sandbox>")
    cleaned = _TIMING.sub("in <t>s", cleaned)
    cleaned = cleaned.strip()
    return (
        cleaned if len(cleaned) <= 4000 else cleaned[:2000] + "\n…[truncated]…\n" + cleaned[-2000:]
    )


def _gate_env() -> dict[str, str]:
    """The gate's environment: the caller's, with the RUNNING interpreter's scripts directory first
    on PATH, so `ruff`, `mypy` and `python` resolve to the environment substrate itself runs in
    (Twelve-Factor II: dependencies declared and isolated, never whatever the shell's PATH holds).
    Before UI sprint 097, 78 coding-gate tests failed with `mypy: command not found` whenever pytest
    ran from a venv interpreter whose bin was not on the shell's PATH."""
    import os
    import sys
    import sysconfig

    env = dict(os.environ)
    first = [sysconfig.get_path("scripts"), str(Path(sys.executable).parent)]
    env["PATH"] = os.pathsep.join([*dict.fromkeys(first), env.get("PATH", "")])
    return env


def run_gate(artifacts: dict[str, str], gate: str, *, timeout: float = 60.0) -> GateResult:
    """Write `artifacts` into a fresh temp dir, run `gate` there (shell, no network assumed), and
    return the normalized verdict. A timeout or a non-zero exit is a fail, never an exception to the
    caller — a hanging or crashing candidate must not take the run down."""
    if not artifacts:
        return GateResult(
            passed=False, returncode=-1, summary="no artifacts: the candidate wrote no files"
        )
    with tempfile.TemporaryDirectory(prefix="coding_flow_") as d:
        sandbox = Path(d)
        for rel, content in artifacts.items():
            target = (sandbox / rel).resolve()
            try:
                target.relative_to(
                    sandbox.resolve()
                )  # path-traversal guard: a `../` payload escapes
            except ValueError:
                # a candidate wrote a path outside the sandbox -> a FAILED gate, never a crash (an
                # uncaught raise here kills the validator Producer and wedges the whole run).
                return GateResult(
                    passed=False,
                    returncode=-1,
                    summary=f"candidate wrote a path outside the sandbox: {rel!r}",
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        try:
            proc = subprocess.run(
                gate,
                shell=True,
                cwd=sandbox,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=_gate_env(),
            )
        except subprocess.TimeoutExpired:
            return GateResult(
                passed=False, returncode=-1, summary=f"gate timed out after {timeout:g}s"
            )
        if proc.returncode == 127:
            # `command not found`: the gate's TOOL is missing from this environment. That is not
            # the candidate failing; say so, so it is never graded as a bad candidate.
            return GateResult(
                passed=False,
                returncode=127,
                summary="gate tool not installed in this environment: "
                + _normalize(proc.stdout + proc.stderr, sandbox),
            )
        return GateResult(
            passed=proc.returncode == 0,
            returncode=proc.returncode,
            summary=_normalize(proc.stdout + proc.stderr, sandbox),
        )

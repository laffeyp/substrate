# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Capability eval — give the tool-using agent REAL tasks across Ollama model tiers and report how
each model does. The test the usage transcript demanded: write a poem, create a doc, write simple
software. It surfaces real behavior — e.g. a model that REFUSES to write a poem because it thinks it
can only act through tools (the bug this eval helped catch and the prompt fix addresses).

Real-model, slow, non-deterministic → a DIAGNOSTIC script, NOT a CI gate (like the walkthrough tests).

    cd substrate
    uv run python scripts/eval_agent_models.py                                  # default tiers
    uv run python scripts/eval_agent_models.py --models llama3.2:1b,qwen2.5-coder:7b
    uv run python scripts/eval_agent_models.py --models qwen3-coder:480b-cloud --tasks poem
"""

from __future__ import annotations

import argparse
import asyncio
import re
import tempfile
from pathlib import Path

from substrate.adapters import OllamaResponder
from substrate.api import Runtime, read_record
from substrate.topologies.tool_loop import tool_loop_topology
from substrate.topologies.tool_loop.tools import FULL_SUITE

_REFUSAL = re.compile(
    r"can'?t|cannot|unable to|none of the tools|don'?t have a tool|not able to", re.I
)


def _judge_poem(final: str, wd: Path) -> tuple[str, str]:
    snippet = final.replace("\n", " ").strip()[:80]
    if _REFUSAL.search(final):
        return "REFUSED", snippet  # the bug: it won't just GENERATE (thinks it needs a tool)
    return ("PASS" if len(final.split()) >= 8 else "WEAK"), snippet


def _judge_doc(final: str, wd: Path) -> tuple[str, str]:
    f = wd / "README.md"
    if f.exists() and len(f.read_text(encoding="utf-8")) > 20:
        return "PASS", f.read_text(encoding="utf-8")[:60].replace("\n", " ")
    return "FAIL", "(no README.md written)"


def _judge_code(final: str, wd: Path) -> tuple[str, str]:
    f = wd / "add.py"
    if f.exists() and "def add" in f.read_text(encoding="utf-8"):
        return "PASS", f.read_text(encoding="utf-8")[:60].replace("\n", " ")
    return "FAIL", "(no add.py with def add)"


TASKS: dict[str, tuple[str, object]] = {
    "poem": ("Write a short 4-line poem about the ocean. Just write the poem itself.", _judge_poem),
    "doc": (
        "Create a file at {wd}/README.md with a one-paragraph description of a to-do app.",
        _judge_doc,
    ),
    "software": (
        "Create a file at {wd}/add.py with a Python function add(a, b) that returns a + b.",
        _judge_code,
    ),
}


async def _run_one(model: str, template: str, judge) -> tuple[str, int, str]:  # type: ignore[no-untyped-def]
    wd = Path(tempfile.mkdtemp(prefix="eval-"))
    task = template.format(wd=wd)
    await Runtime(wd / "run").run(
        tool_loop_topology(
            model=OllamaResponder(model),
            walkthrough=True,
            deterministic=False,
            tools=FULL_SUITE,
            task=task,
            max_steps=6,
        )
    )
    envs = list(read_record(wd / "run"))
    final = next(
        (str(e["payload"]["text"]) for e in reversed(envs) if e["kind"] == "FinalAnswer"), ""
    )
    calls = sum(1 for e in envs if e["kind"] == "ToolCall")
    verdict, evidence = judge(final, wd)
    return verdict, calls, evidence


async def main(models: list[str], tasks: list[str]) -> None:
    print(f"\n{'MODEL':<26}{'TASK':<10}{'RESULT':<9}{'CALLS':<7}EVIDENCE")
    print("-" * 100)
    for m in models:
        for name in tasks:
            template, judge = TASKS[name]
            try:
                verdict, calls, evidence = await _run_one(m, template, judge)
            except Exception as exc:  # noqa: BLE001 — a model/daemon failure is a row, not a crash
                verdict, calls, evidence = "ERROR", 0, f"{type(exc).__name__}: {exc}"[:60]
            print(f"{m:<26}{name:<10}{verdict:<9}{calls:<7}{evidence}")
    print()


def _parse() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Eval the tool-using agent's capability across Ollama model tiers."
    )
    ap.add_argument(
        "--models",
        default="llama3.2:1b,qwen2.5-coder:7b,qwen3-coder:480b-cloud",
        help="comma-separated Ollama models (small -> big tiers)",
    )
    ap.add_argument(
        "--tasks", default="poem,doc,software", help="comma-separated: " + ",".join(TASKS)
    )
    return ap.parse_args()


if __name__ == "__main__":
    a = _parse()
    asyncio.run(
        main(
            [m.strip() for m in a.models.split(",") if m.strip()],
            [t.strip() for t in a.tasks.split(",") if t.strip() in TASKS],
        )
    )

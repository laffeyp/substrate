#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Run best_of_n_verified with real local models (walkthrough, application-parity W1.2).

Generate N candidates for a task with one model, verify each with an INDEPENDENT judge model
(a different family than the drafter, per finding #42), select the survivor. The loop, the
correction rounds, and the record are best_of_n's; the record is replayable.

    uv run python scripts/run_best_of_n_verified.py \
        --task "Write a haiku about a compiler." \
        --model kimi-k2.6:cloud --verifier-model glm-5.1:cloud --n 3

CI proves the wiring (tests/test_best_of_n_verified.py, deterministic); this is the real-model path.
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from pathlib import Path

from substrate.adapters import OllamaResponder
from substrate.api import RunStatus, Runtime, read_record
from substrate.topologies.applications import best_of_n_verified_topology


async def _run(args: argparse.Namespace) -> int:
    record = Path(args.record) if args.record else Path(tempfile.mkdtemp()) / "best_of_n_verified"
    verifier_model = args.verifier_model or args.model
    print(
        f"task={args.task!r}\ndrafter={args.model}  verifier={verifier_model}  "
        f"n={args.n}  max_rounds={args.max_rounds}\n"
    )
    topo = best_of_n_verified_topology(
        args.task,
        drafter=OllamaResponder(args.model),
        verify=OllamaResponder(verifier_model),  # an independent judge, not the drafter
        n=args.n,
        max_rounds=args.max_rounds,
        deterministic=False,  # real models — not author-deterministic
    )
    result = await Runtime(record).run(topo)

    print(f"status: {result.status}")
    for e in read_record(record):
        k, p = e["kind"], e.get("payload", {})
        if k == "Candidate":
            print(f"  → candidate r{p['round']}/{p['slot']}: {str(p['response'])[:110]}")
        elif k == "Verdict":
            mark = "PASS" if p["passed"] else "FAIL"
            print(f"  ⚖ verdict  r{p['round']}/{p['slot']}: {mark} — {str(p['summary'])[:90]}")
        elif k == "Solved":
            print(f"  ✓ selected r{p['round']}/{p['slot']}")
        elif k == "Exhausted":
            print(f"  ✗ exhausted after {p['rounds']} round(s) — nothing passed")
    print(f"\nfull replayable record: {record}")
    print("view it: uv run python ../substrate-ui/server.py --port 8799  →  http://127.0.0.1:8799/")
    return 0 if result.status == RunStatus.FINALISED else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="generate N candidates, verify each with an independent judge, select the survivor"
    )
    ap.add_argument("--task", required=True, help="the task to solve")
    ap.add_argument(
        "--model", default="kimi-k2.6:cloud", help="the drafter model (generates candidates)"
    )
    ap.add_argument(
        "--verifier-model",
        default=None,
        help="the independent judge model (default: same as --model)",
    )
    ap.add_argument("--n", type=int, default=3, help="candidates per round (default: 3)")
    ap.add_argument(
        "--max-rounds", type=int, default=2, help="correction rounds before giving up (default: 2)"
    )
    ap.add_argument("--record", default=None, help="record root (default: a temp dir)")
    return asyncio.run(_run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())

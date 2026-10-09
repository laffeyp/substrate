#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Run research_sweep over a real document set with real models (walkthrough, application-parity W1.3).

Fan a reader over each document to extract findings for a question, run a completeness critic over
all findings, then synthesize the answer. The record is replayable.

    uv run python scripts/run_research_sweep.py --dir docs/specs/design_spec --glob '*.md' \
        --question "What does the design spec say about error UX?" --model kimi-k2.6:cloud

(F-10: the example targets an in-repo directory that exists on a fresh clone.) CI proves the wiring
(tests/test_research_sweep.py, deterministic); this is the real-model path.
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from pathlib import Path

from substrate.adapters import OllamaResponder
from substrate.api import RunStatus, Runtime, read_record
from substrate.topologies.applications import gather, research_sweep_topology


async def _run(args: argparse.Namespace) -> int:
    paths: list[str | Path]
    if args.dir:
        paths = sorted(str(p) for p in Path(args.dir).glob(args.glob))
    else:
        paths = list(args.paths or [])
    if not paths:
        print("no documents (use --dir <folder> [--glob '*.md'] or --paths a.md b.md)")
        return 1
    documents = gather(paths)
    record = Path(args.record) if args.record else Path(tempfile.mkdtemp()) / "research_sweep"
    print(
        f"question={args.question!r}\ndocuments={[s for s, _ in documents]}  model={args.model}\n"
    )

    model = OllamaResponder(args.model)
    topo = research_sweep_topology(
        args.question,
        documents,
        reader=model,
        critic=model,
        synthesizer=model,
        deterministic=False,
    )
    result = await Runtime(record).run(topo)

    print(f"status: {result.status}")
    for e in read_record(record):
        k, p = e["kind"], e.get("payload", {})
        if k == "Finding":
            print(f"  → {p['source']}: {str(p['note'])[:110]}")
        elif k == "Gaps":
            print(f"  ? gaps: {str(p['note'])[:150]}")
        elif k == "Synthesis":
            print(f"\n  ✓ synthesis:\n{p['text']}")
    print(f"\nfull replayable record: {record}")
    print("view it: uv run python ../substrate-ui/server.py --port 8799  →  http://127.0.0.1:8799/")
    return 0 if result.status == RunStatus.FINALISED else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="fan readers over a document set, critique gaps, synthesize"
    )
    ap.add_argument("--question", required=True, help="the research question")
    ap.add_argument("--dir", default=None, help="a folder of documents to sweep")
    ap.add_argument("--glob", default="*.md", help="glob within --dir (default: *.md)")
    ap.add_argument("--paths", nargs="*", help="explicit document paths (instead of --dir)")
    ap.add_argument(
        "--model", default="kimi-k2.6:cloud", help="the model for reader/critic/synthesizer"
    )
    ap.add_argument("--record", default=None, help="record root (default: a temp dir)")
    return asyncio.run(_run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Run fanout_review against a real repo with real local models (walkthrough, application-parity W1.1).

The review panel over the changed files of a git diff: N role reviewers critique in parallel, a
quorum fires a judge, cancel-all-others stops the lingerers. The record is replayable.

    uv run python scripts/run_fanout_review.py --repo ../substrate-ui --ref HEAD~1 \
        --model kimi-k2.6:cloud --quorum 3

CI proves the wiring (see tests/test_fanout_review.py, deterministic); this is the real-model path.
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from pathlib import Path

from substrate.adapters import OllamaResponder
from substrate.api import RunStatus, Runtime, read_record
from substrate.topologies.applications import changed_files, fanout_review_topology
from substrate.topologies.code_review import DEFAULT_ROLES


async def _run(args: argparse.Namespace) -> int:
    roles = tuple(args.roles) if args.roles else DEFAULT_ROLES
    quorum = min(args.quorum, len(roles))
    record = Path(args.record) if args.record else Path(tempfile.mkdtemp()) / "fanout_review"

    # gather + preview so the operator sees what is being reviewed before models spend time on it
    diff = changed_files(args.repo, args.ref)
    print(
        f"repo={args.repo}  ref={args.ref}  roles={list(roles)}  quorum={quorum}  model={args.model}"
    )
    print(f"diff: {len(diff)} chars\n{diff[:400]}{' …' if len(diff) > 400 else ''}\n")

    responders = {r: OllamaResponder(args.model) for r in roles}
    topo = fanout_review_topology(
        args.repo,
        ref=args.ref,
        responders=responders,
        judge=OllamaResponder(args.model),
        roles=roles,
        quorum=quorum,
        deterministic=False,  # real model — not author-deterministic
    )
    result = await Runtime(record).run(topo)

    print(f"status: {result.status}")
    for e in read_record(record):
        k, p = e["kind"], e.get("payload", {})
        if k == "CritiquePosted":
            print(f"  → {p['role']} (sev {p['severity']}): {p['summary'][:120]}")
        elif k == "VerdictRendered":
            print(
                f"  ✓ verdict: {p['decision']}  (cited {list(p['cited_roles'])}, {p['n_critiques']} critiques)"
            )
        elif k == "substrate.ProducerCancelled":
            print(f"  ✕ cancelled: {(p.get('producer') or {}).get('kind')}")
    print(f"\nfull replayable record: {record}")
    print("view it: uv run python ../substrate-ui/server.py --port 8799  →  http://127.0.0.1:8799/")
    return 0 if result.status == RunStatus.FINALISED else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="review the changed files of a git diff with an N-role panel"
    )
    ap.add_argument("--repo", required=True, help="path to a git repo to review")
    ap.add_argument(
        "--ref", default="HEAD~1", help="diff against this ref (default: HEAD~1 — the last commit)"
    )
    ap.add_argument(
        "--model", default="kimi-k2.6:cloud", help="an Ollama model for every reviewer + the judge"
    )
    ap.add_argument("--roles", nargs="*", help=f"reviewer roles (default: {list(DEFAULT_ROLES)})")
    ap.add_argument(
        "--quorum", type=int, default=3, help="fire the judge at this many critiques (default: 3)"
    )
    ap.add_argument("--record", default=None, help="record root (default: a temp dir)")
    return asyncio.run(_run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())

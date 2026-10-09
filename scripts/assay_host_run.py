# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""First HONEST score: run the host-backend coding step over a SET of real SWE-bench instances spanning
repos, with a real model, no answers handed over, and grade each with the official harness. Reports the
real resolved count (expected low). Env-gated (git + Docker + image pulls + a live model). Slow.

Usage: uv run python scripts/assay_host_run.py [n_instances] [model]
"""

import sys
from collections import defaultdict
from pathlib import Path

from datasets import load_dataset

from substrate.assay.swebench import grade_patch
from substrate.assay.swebench_host import solve_on_host
from substrate.reference._models import OllamaResponder
from substrate.topologies.swebench_solver.firewall import firewall_check

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
MODEL = sys.argv[2] if len(sys.argv) > 2 else "qwen3-coder:480b-cloud"


def _pick_spanning_repos(dataset, n):
    by_repo = defaultdict(list)
    for inst in dataset:
        ok, _ = firewall_check(inst)
        if ok:
            by_repo[inst["repo"]].append(inst)
    picked, repos, i = [], sorted(by_repo), 0
    while len(picked) < n and any(by_repo[r] for r in repos):
        r = repos[i % len(repos)]
        if by_repo[r]:
            picked.append(by_repo[r].pop(0))
        i += 1
    return picked


def main() -> None:
    ds = list(load_dataset("princeton-nlp/SWE-bench_Lite", split="test"))
    chosen = _pick_spanning_repos(ds, N)
    print(
        f"{len(chosen)} instances across {sorted({c['repo'] for c in chosen})} | model={MODEL}",
        flush=True,
    )
    responder = OllamaResponder(MODEL, max_tokens=2048)

    resolved, errors = [], []
    for inst in chosen:
        iid = inst["instance_id"]
        print(f"\n--- {iid} ({inst['repo']}) ---", flush=True)
        try:
            patch = solve_on_host(inst, responder)
        except Exception as exc:  # noqa: BLE001 — a failed solve is data
            print(f"  SOLVE FAILED: {type(exc).__name__}: {str(exc)[:140]}", flush=True)
            errors.append((iid, f"solve: {type(exc).__name__}"))
            continue
        if not patch.strip():
            print("  no patch produced", flush=True)
            continue
        print(f"  patch {len(patch)}b; grading (Docker; slow)...", flush=True)
        try:
            ok = grade_patch(
                iid,
                patch,
                report_root=Path("process/runs/assays/host"),
                dataset_name="princeton-nlp/SWE-bench_Lite",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  GRADE FAILED: {type(exc).__name__}: {str(exc)[:140]}", flush=True)
            errors.append((iid, f"grade: {type(exc).__name__}"))
            continue
        print(f"  resolved={ok}", flush=True)
        if ok:
            resolved.append(iid)

    print("\n==================== HOST-BACKEND SCORE ====================", flush=True)
    print(f"model={MODEL} | instances={len(chosen)} | errors={len(errors)}", flush=True)
    print(f"RESOLVED: {len(resolved)}/{len(chosen)} -> {resolved}", flush=True)
    for iid, why in errors:
        print(f"  err {iid}: {why}", flush=True)


if __name__ == "__main__":
    main()

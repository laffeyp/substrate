# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Run the SWE-bench matrix: host + container backends as Arms over a frozen repo-spanning set, graded by
the official harness, compared with the real assay stats (paired McNemar/bootstrap + power floor). Prints
the leaderboard. Env-gated (Docker + a live model). Slow — each (arm x case) is a real solve + grade.

Usage: uv run python scripts/assay_matrix_run.py [n] [model] [trials]
"""

import asyncio
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from datasets import load_dataset

from substrate.assay.report import build_report
from substrate.assay.run import run_suite
from substrate.assay.suite import BASELINE, FULL
from substrate.assay.swebench_matrix import container_arm, host_arm, swebench_matrix_suite
from substrate.topologies.swebench_solver.firewall import firewall_check

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
MODEL = sys.argv[2] if len(sys.argv) > 2 else "qwen3-coder:480b-cloud"
TRIALS = int(sys.argv[3]) if len(sys.argv) > 3 else 1


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
    print(f"matrix: {len(chosen)} cases x 2 arms x {TRIALS} trials | model={MODEL}", flush=True)

    report_root = Path("process/runs/assays/matrix")
    arms = [
        host_arm("host", BASELINE, model=MODEL),  # control: the simple focused backend
        container_arm("container", FULL, model=MODEL),  # the executing agent backend
    ]
    suite = swebench_matrix_suite(
        chosen,
        arms,
        report_root=str(report_root),
        dataset_name="princeton-nlp/SWE-bench_Lite",
        control_arm="host",
    )
    rundir = Path(tempfile.mkdtemp(prefix="matrix-")) / "run"
    print("running the matrix (each cell = a real solve + official grade; slow)...", flush=True)
    results = asyncio.run(run_suite(suite, rundir, trials=TRIALS))
    report = build_report(suite, results)

    print("\n==================== SWE-BENCH MATRIX LEADERBOARD ====================", flush=True)
    print(
        f"suite={report.suite} v{report.version} | control={report.control_arm} | "
        f"control_check={report.control_check.state}",
        flush=True,
    )
    print(
        f"{'arm':<12} {'role':<9} {'pass':<7} {'rate':<6} {'Δ-vs-ctrl':<10} {'verdict':<13} {'wall_ms':<9}",
        flush=True,
    )
    for a in report.arms:
        delta = f"{a.delta_pass_k:+.2f}" if a.delta_pass_k is not None else "-"
        verdict = a.equivalence or ("control" if a.arm == report.control_arm else "-")
        print(
            f"{a.arm:<12} {a.role:<9} {a.passes}/{a.n_cases:<5} {a.pass_rate:<6.2f} "
            f"{delta:<10} {verdict:<13} {a.elapsed_ms:<9}",
            flush=True,
        )
    print(f"\nnull rule: {report.null_rule}", flush=True)


if __name__ == "__main__":
    main()

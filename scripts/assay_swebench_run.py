# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Run a REAL model over a SET of SWE-bench instances spanning multiple repos — the actual benchmark,
no answers handed over. Reports, honestly: which instances could even be ATTEMPTED (the per-repo setup
must succeed — non-pytest repos like django RAISE today), which RESOLVED, and what broke. This is the
start of running the full SWE-bench, not a cherry-picked smoke; expect breakage on non-flask repos.

Usage: uv run python scripts/assay_swebench_run.py [n_instances] [model]
Env-gated (git + Docker + image pulls + a live model). Slow.
"""

import asyncio
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from datasets import load_dataset

from substrate.assay.run import run_arm_on_case
from substrate.assay.suite import FULL, Arm
from substrate.assay.swebench import swebench_record_oracle
from substrate.assay.swebench_suite import prepare_swebench_case, solver_topology_from_payload
from substrate.reference._models import OllamaResponder
from substrate.topologies.swebench_solver.firewall import firewall_check

N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
MODEL = sys.argv[2] if len(sys.argv) > 2 else "qwen3-coder:480b-cloud"
N_DRAFTS = 2


def _pick_spanning_repos(dataset, n):
    """Pick ~n instances spanning DIFFERENT repos (so the run genuinely hits multiple test setups, not
    one repo's). Firewall-clean only. Round-robin across repos."""
    by_repo = defaultdict(list)
    for inst in dataset:
        ok, _ = firewall_check(inst)
        if ok:
            by_repo[inst["repo"]].append(inst)
    picked, repos = [], sorted(by_repo)
    i = 0
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
        f"chosen {len(chosen)} instances across repos: {sorted({c['repo'] for c in chosen})}",
        flush=True,
    )

    oracle = swebench_record_oracle(
        report_root=Path("process/runs/assays/run"), dataset_name="princeton-nlp/SWE-bench_Lite"
    )
    base_root = Path(tempfile.mkdtemp(prefix="assay-run-"))

    attempted, resolved, skipped = [], [], []
    for inst in chosen:
        iid = inst["instance_id"]
        print(f"\n--- {iid} ({inst['repo']}) ---", flush=True)
        try:
            case = prepare_swebench_case(inst)  # clone + base run (pulls the image)
        except Exception as exc:  # noqa: BLE001 — a repo we can't set up yet is DATA, report it
            print(f"  SKIPPED (setup failed): {type(exc).__name__}: {str(exc)[:160]}", flush=True)
            skipped.append((iid, f"{type(exc).__name__}: {str(exc)[:120]}"))
            continue

        def build(c):  # type: ignore[no-untyped-def]
            responders = [OllamaResponder(MODEL, max_tokens=2048) for _ in range(N_DRAFTS)]
            return solver_topology_from_payload(c.payload, responders, n=N_DRAFTS, max_rounds=2)

        arm = Arm(name="solver", role=FULL, build=build)
        root = base_root / case.case_id
        try:
            res = asyncio.run(run_arm_on_case(arm, case, oracle, root))
        except Exception as exc:  # noqa: BLE001 — a run that blows up is also data
            print(f"  RUN FAILED: {type(exc).__name__}: {str(exc)[:160]}", flush=True)
            skipped.append((iid, f"run: {type(exc).__name__}: {str(exc)[:110]}"))
            continue
        attempted.append(iid)
        if res.result.passed:
            resolved.append(iid)
        print(
            f"  resolved={res.result.passed} | {res.result.detail} | "
            f"calls={res.usage.model_calls} elapsed_ms={res.elapsed_ms}",
            flush=True,
        )

    print("\n==================== REAL RUN RESULT ====================", flush=True)
    print(f"model: {MODEL}  (n_drafts={N_DRAFTS})", flush=True)
    print(
        f"chosen: {len(chosen)} | attempted: {len(attempted)} | could-not-attempt: {len(skipped)}",
        flush=True,
    )
    print(
        f"RESOLVED: {len(resolved)}/{len(attempted)} attempted "
        f"({len(resolved)}/{len(chosen)} of chosen) -> {resolved}",
        flush=True,
    )
    if skipped:
        print("\ncould-not-attempt (the multi-repo work that's NOT done):", flush=True)
        for iid, why in skipped:
            print(f"  {iid}: {why}", flush=True)


if __name__ == "__main__":
    main()

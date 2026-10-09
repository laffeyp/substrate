# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""EXPLORATORY real-MODEL solve of ONE SWE-bench instance through the full topology (review #69 NET: keep
the first real-model solve EXPLORATORY — a single instance, NOT a reported resolve-rate; the power gates +
the exclude-disclosure gate the RATE, not this).

A real Ollama coder model localizes + drafts SEARCH/REPLACE edits; the real DockerTestRunner runs the
firewall-clean per-candidate regression (proximity picker + passed-at-base) and the model's own generated
reproduction test; SELECT reranks; the swebench Docker oracle grades the chosen patch. Banks recall@k (did
localization even contain the gold files — a localization miss is attributable, #61). Real, slow, env-gated
(Docker + the cached image + a live Ollama). Run on the Architect's box, never CI.

Usage: uv run python scripts/solve_instance.py [instance_id] [model]
       (defaults: pallets__flask-4045, qwen2.5-coder:7b)
"""

import asyncio
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

from datasets import load_dataset

from substrate.api import Runtime, read_record
from substrate.assay.swebench import make_prediction, read_resolved, run_swebench
from substrate.reference._models import OllamaResponder
from substrate.topologies.swebench_solver.assemble import (
    swebench_solver_topology_with_test_selection,
)
from substrate.topologies.swebench_solver.firewall import firewall_check
from substrate.topologies.swebench_solver.localize import full_recall_at_k, recall_at_k
from substrate.topologies.swebench_solver.select_docker import (
    DockerTestRunner,
    build_regression_command,
    instance_image,
    repo_test_spec,
)
from substrate.topologies.swebench_solver.select_exec import passed_tests
from substrate.topologies.swebench_solver.select_regression import (
    discover_test_modules,
    make_regression_planner,
)

IID = sys.argv[1] if len(sys.argv) > 1 else "pallets__flask-4045"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "qwen2.5-coder:7b"
N = 2
MAX_ROUNDS = 2


def _added_files(diff: str) -> set[str]:
    return {ln[6:] for ln in diff.splitlines() if ln.startswith("+++ b/") and ln[6:] != "dev/null"}


def _checkout(base_commit: str, repo: str) -> str:
    d = tempfile.mkdtemp(prefix="solve-base-")
    url = f"https://github.com/{repo}"
    print(f"cloning {url} @ {base_commit[:10]} ...", flush=True)
    subprocess.run(["git", "clone", "--quiet", url, d], check=True)
    subprocess.run(["git", "-C", d, "checkout", "--quiet", base_commit], check=True)
    return d


def main() -> None:
    inst = next(
        x
        for x in load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
        if x["instance_id"] == IID
    )

    ok, reason = firewall_check(inst)
    print(f"firewall_check: {ok} — {reason}", flush=True)
    if not ok:
        sys.exit(2)

    base = _checkout(inst["base_commit"], inst["repo"])
    repo_files = subprocess.run(
        ["git", "-C", base, "ls-files"], capture_output=True, text=True
    ).stdout.split()
    repo_tests = discover_test_modules(repo_files)
    exclude = _added_files(inst["test_patch"])
    gold_files = _added_files(inst["patch"])
    print(
        f"repo: {len(repo_files)} files, {len(repo_tests)} test modules; gold touches {sorted(gold_files)}",
        flush=True,
    )

    # the firewall-clean regression: per-candidate planner (proximity subset) + passed_at_base over the FULL
    # eligible set (candidates run subsets; regression_held only checks tests that ran ∩ base-passing).
    spec = repo_test_spec(inst["repo"], inst["version"])
    runner = DockerTestRunner(instance_image(IID), timeout=1800)
    full_reg = build_regression_command(spec, [t for t in repo_tests if t not in exclude])
    print("base run (no patch) for passed-at-base (slow)...", flush=True)
    _, base_out = runner.run("", full_reg)
    base_pass = frozenset(passed_tests(base_out))
    print(f"  passed-at-base: {len(base_pass)} tests", flush=True)
    planner = make_regression_planner(spec, repo_tests, exclude=exclude)

    # a real coder model for every seam (localizer + repro reuse responders[0]; drafters per slot).
    responders = [OllamaResponder(MODEL, max_tokens=2048, num_ctx=32768) for _ in range(N)]

    topo = swebench_solver_topology_with_test_selection(
        responders=responders,
        base_checkout=base,
        issue=inst["problem_statement"],
        repo_skeleton="\n".join(repo_files),
        known_files=set(repo_files),
        runner=runner,
        regression_command=planner,
        passed_at_base=base_pass,
        n=N,
        max_rounds=MAX_ROUNDS,
    )
    rundir = Path(tempfile.mkdtemp(prefix="solve-run-")) / "run"
    print(
        f"\nrunning the solver with {MODEL} (n={N}, real model + real container; slow)...",
        flush=True,
    )
    asyncio.run(Runtime(rundir).run(topo))
    events = list(read_record(rundir))

    # what each phase produced (the record is the observable).
    suspect: list[str] = next(
        (e["payload"]["files"] for e in events if e["kind"] == "SuspectFiles"), []
    )
    applied = [e["payload"] for e in events if e["kind"] == "AppliedPatch"]
    results = [e["payload"] for e in events if e["kind"] == "TestResults"]
    selected = [e["payload"] for e in events if e["kind"] == "SelectedPatch"]
    print(f"\nLOCALIZE suspect files: {suspect}", flush=True)
    print(
        f"  recall@k: {recall_at_k(tuple(suspect), gold_files):.2f}  full_recall@k: {full_recall_at_k(tuple(suspect), gold_files)}",
        flush=True,
    )
    print(f"REPAIR applied patches: {len(applied)}/{N}", flush=True)
    print(
        f"SELECT test results: {[(r['slot'], r['regression_passed'], r['reproduction']) for r in results]}",
        flush=True,
    )
    print(
        f"SELECT chose: {'slot ' + str(selected[0]['slot']) if selected else 'NOTHING (no candidate survived)'}",
        flush=True,
    )

    if not selected:
        print(
            "\n=== no SelectedPatch — nothing to grade (exploratory run, expected for a weak model) ===",
            flush=True,
        )
        sys.exit(0)

    print("\ngrading the chosen patch with the swebench oracle (Docker)...", flush=True)
    pred = make_prediction(IID, selected[0]["model_patch"], model_name="substrate-solver")
    # run_id MUST be unique per (model, patch): the swebench harness caches by run_id+model+instance and
    # SKIPS re-evaluation if that dir exists ("1 instances already run, skipping") -> a constant run_id makes
    # a second run silently REUSE the first run's verdict (caught reading the harness log #154). Hash the
    # patch so distinct patches grade fresh and an identical re-run still caches correctly.
    patch_hash = hashlib.sha1(
        selected[0]["model_patch"].encode(), usedforsecurity=False
    ).hexdigest()[:8]
    run_id = f"solve-{MODEL.split(':')[0].replace('/', '_')}-{patch_hash}"
    rdir = Path("process/runs/smokes/solves") / IID
    run_swebench(
        [pred],
        dataset_name="princeton-nlp/SWE-bench_Lite",
        run_id=run_id,
        instance_ids=[IID],
        report_dir=rdir,
        max_workers=1,
    )
    resolved = read_resolved(rdir, run_id, "substrate-solver", IID)
    print(
        f"\n=== RESOLVED: {resolved} ===  (real model {MODEL}, exploratory, n={N}, run_id={run_id})",
        flush=True,
    )


if __name__ == "__main__":
    main()

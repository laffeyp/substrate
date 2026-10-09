# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""NET #2 (review #69): smoke the REAL regression SEAM end to end on the live flask-4045 image — the seam
the gold-fed solve sidestepped with _PassRunner. This drives the ACTUAL firewall-clean regression command
(proximity picker -> build_regression_command, reusing swebench's own install + test_cmd) through the real
DockerTestRunner, with the gold patch applied, and confirms the picked UNRELATED tests pass (regression
holds) — proving the command + container before the signal is ever trusted to drive selection.

Also runs the per-instance firewall assertion and prints exclude_delta (the harness-assist disclosure).
Real, slow, env-gated (Docker + the cached image). Run on the Architect's box, never in CI.
"""

import subprocess
import sys

from datasets import load_dataset

from substrate.topologies.swebench_solver.firewall import firewall_check
from substrate.topologies.swebench_solver.select_docker import (
    DockerTestRunner,
    instance_image,
    repo_test_spec,
)
from substrate.topologies.swebench_solver.select_exec import passed_tests, regression_held
from substrate.topologies.swebench_solver.select_regression import (
    discover_test_modules,
    exclude_delta,
    make_regression_planner,
    patch_touched_files,
)

IID = "pallets__flask-4045"


def _added_files(diff: str) -> set[str]:
    return {ln[6:] for ln in diff.splitlines() if ln.startswith("+++ b/") and ln[6:] != "dev/null"}


def main() -> None:
    inst = next(
        x
        for x in load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
        if x["instance_id"] == IID
    )
    img = instance_image(IID)

    # 1. per-instance firewall assertion (NET #2 item 2)
    ok, reason = firewall_check(inst)
    print(f"firewall_check: {ok} — {reason}", flush=True)
    if not ok:
        sys.exit(2)

    # 2. discover the repo's OWN test files from the container at base_commit (the checkout, not PASS_TO_PASS)
    print(f"image: {img}\ndiscovering repo test files in-container...", flush=True)
    ls = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            img,
            "bash",
            "-lc",
            "cd /testbed && git ls-files 'tests/**.py' tests/*.py",
        ],
        capture_output=True,
        text=True,
    )
    if ls.returncode != 0:
        print("ls FAILED:\n" + ls.stderr[-1500:], flush=True)
        sys.exit(2)
    # filter to pytest-collectable test MODULES — not fixture/support files (which error on collection).
    repo_tests = discover_test_modules([ln for ln in ls.stdout.splitlines() if ln.strip()])
    print(f"  {len(repo_tests)} repo test modules (e.g. {repo_tests[:3]})", flush=True)

    # 3. build the firewall-clean planner; plan the regression command for the GOLD patch
    spec = repo_test_spec(inst["repo"], inst["version"])
    exclude = _added_files(inst["test_patch"])  # held-out test_patch file paths
    touched = patch_touched_files(inst["patch"])  # gold patch touches src/flask/blueprints.py
    print(f"  gold patch touches: {sorted(touched)}", flush=True)
    print(f"  test_patch files (exclude): {sorted(exclude)}", flush=True)
    print(
        f"  exclude_delta (harness-assist beyond proximity): {exclude_delta(repo_tests, touched, exclude=exclude)}",
        flush=True,
    )

    plan = make_regression_planner(spec, repo_tests, exclude=exclude)
    cmd = plan(inst["patch"])
    picked = cmd.split("pytest -rA ", 1)[1] if "pytest -rA " in cmd else "(none)"
    print(
        f"  regression set (issue-unrelated): {picked[:200]}{'...' if len(picked) > 200 else ''}",
        flush=True,
    )

    # 4. BASE run (no patch) -> the base-passing set. flask has pre-existing base failures (warnings-as-
    # errors), so the signal is "no base-passing test now fails", not "all pass" (#69 NET #2, #149 finding).
    runner = DockerTestRunner(img, timeout=1800)
    print(
        "\nrunning the regression set at BASE (no patch) to get the base-passing set (slow)...",
        flush=True,
    )
    _, base_out = runner.run("", cmd)  # empty patch -> git apply no-op -> base_commit
    base_pass = passed_tests(base_out)
    print(f"  base-passing tests: {len(base_pass)} (of the issue-unrelated set)", flush=True)

    # 5. run the SAME set WITH the gold patch; regression holds iff no base-passing test now fails.
    print("running the SAME regression set WITH the gold patch (slow)...", flush=True)
    _, out = runner.run(inst["patch"], cmd)
    held = regression_held(base_pass, out)
    print(f"\n--- tail ---\n{out[-1200:]}", flush=True)
    print(
        f"\nregression_held = {held}  (no test that passed at base regressed under the correct gold patch)",
        flush=True,
    )
    # the gold patch is correct, so every base-passing test must still pass; a False means the SEAM is
    # broken (env setup, command shape, parsing, or the runner), not the patch.
    sys.exit(0 if held else 3)


if __name__ == "__main__":
    main()

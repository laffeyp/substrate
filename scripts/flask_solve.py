# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""First real solve, gold-fed (controlled): take flask-4045's known fix, reshape it into the find/replace
edits the solver speaks, apply it through our applier on a real flask checkout, and confirm it round-trips.

Stage 1 (this file, run directly): the diff->SEARCH/REPLACE conversion + a real flask checkout + apply,
proving the known fix survives the trip through our applier. Stage 2 (the full pipeline + oracle grade)
builds on a verified stage 1.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from datasets import load_dataset

from substrate.topologies.swebench_solver.applier import apply_candidate

IID = "pallets__flask-4045"
REPO_URL = "https://github.com/pallets/flask"


def diff_to_search_replace(diff: str) -> str:
    """Convert a unified git diff into the solver's SEARCH/REPLACE block format — one block per hunk.
    SEARCH = the hunk's context + removed lines (the original); REPLACE = context + added lines (the new)."""
    lines = diff.splitlines()
    out: list[str] = []
    path: str | None = None
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        if ln.startswith("+++ b/"):
            path = ln[6:].strip()
            i += 1
            continue
        if ln.startswith("@@"):
            i += 1
            search: list[str] = []
            replace: list[str] = []
            while i < n and not lines[i].startswith("@@") and not lines[i].startswith("diff --git"):
                h = lines[i]
                if h.startswith("+"):
                    replace.append(h[1:])
                elif h.startswith("-"):
                    search.append(h[1:])
                elif h.startswith(" "):
                    search.append(h[1:])
                    replace.append(h[1:])
                # "\ No newline at end of file" and blank separators are ignored
                i += 1
            if path and (search or replace):
                out.append(
                    f"# path: {path}\n<<<<<<< SEARCH\n"
                    + "\n".join(search)
                    + "\n=======\n"
                    + "\n".join(replace)
                    + "\n>>>>>>> REPLACE"
                )
            continue
        i += 1
    return "\n".join(out) + "\n"


def _checkout(base_commit: str) -> str:
    d = tempfile.mkdtemp(prefix="flask-base-")
    print(f"cloning {REPO_URL} @ {base_commit[:10]} ...", flush=True)
    subprocess.run(["git", "clone", "--quiet", REPO_URL, d], check=True)
    subprocess.run(["git", "-C", d, "checkout", "--quiet", base_commit], check=True)
    return d


def main() -> None:
    inst = next(
        x
        for x in load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
        if x["instance_id"] == IID
    )
    sr = diff_to_search_replace(inst["patch"])
    print(
        f"known fix touches files: {[ln[8:] for ln in inst['patch'].splitlines() if ln.startswith('+++ b/')]}"
    )
    print(f"converted to {sr.count('<<<<<<< SEARCH')} SEARCH/REPLACE block(s)", flush=True)

    base = _checkout(inst["base_commit"])
    result = apply_candidate(sr, base)
    print(f"\napplied: {result.applied}")
    if not result.applied:
        print(f"ERROR: {result.error}")
        sys.exit(2)
    gold_files = {ln[6:] for ln in inst["patch"].splitlines() if ln.startswith("+++ b/")}

    # normalized-CONTENT equivalence (review #64): file-set match is too weak — it would pass a patch that
    # touches the right file with WRONG/partial content. Compare the actual +/- change bodies (as a set, so
    # git's hunk regrouping doesn't matter) and HALT loudly on any converter mangle BEFORE grading, so a
    # gold-fed run is self-verifying across instances.
    def _changes(d: str) -> list[str]:
        return sorted(
            ln.rstrip()
            for ln in d.splitlines()
            if (ln.startswith("+") or ln.startswith("-")) and not ln.startswith(("+++", "---"))
        )

    if _changes(result.model_patch) != _changes(inst["patch"]):
        print("ERROR: produced patch is NOT content-equivalent to the gold fix (converter mangle)")
        print("  produced:", _changes(result.model_patch)[:6])
        print("  gold:    ", _changes(inst["patch"])[:6])
        sys.exit(2)
    print("produced patch is content-equivalent to the gold fix (self-verified)")

    # === STAGE 2: run the full pipeline with the known fix, then grade with the oracle ===
    import asyncio

    from substrate.api import Runtime, read_record
    from substrate.assay.swebench import make_prediction, read_resolved, run_swebench
    from substrate.topologies.swebench_solver.assemble import (
        swebench_solver_topology_with_test_selection,
    )

    files = (
        subprocess.run(["git", "-C", base, "ls-files"], capture_output=True, text=True)
        .stdout.strip()
        .split("\n")
    )
    skeleton = "\n".join(files)
    known = set(files)
    gold_list = sorted(gold_files)

    class _GoldResponder:
        def respond(self, prompt: str) -> str:
            return ("\n".join(gold_list) + "\n") if "suspect file" in prompt else sr

    class _PassRunner:
        def run(
            self, model_patch: str, test_command: str, extra_files: dict[str, str] | None = None
        ) -> tuple[int, str]:
            return (0, "1 passed in 0.0s")

    topo = swebench_solver_topology_with_test_selection(
        responders=[_GoldResponder()],
        base_checkout=base,
        issue=inst["problem_statement"][:4000],
        repo_skeleton=skeleton,
        known_files=known,
        runner=_PassRunner(),
        regression_command="true",
        n=1,
        max_rounds=1,
    )
    rundir = Path(tempfile.mkdtemp(prefix="solve-")) / "run"
    print("\nrunning the full solver pipeline...", flush=True)
    asyncio.run(Runtime(rundir).run(topo))
    events = list(read_record(rundir))
    selected = [e["payload"] for e in events if e["kind"] == "SelectedPatch"]
    print(
        f"pipeline emitted: SuspectFiles={sum(1 for e in events if e['kind'] == 'SuspectFiles')}, "
        f"AppliedPatch={sum(1 for e in events if e['kind'] == 'AppliedPatch')}, "
        f"SelectedPatch={len(selected)}",
        flush=True,
    )
    if not selected:
        print("ERROR: no SelectedPatch")
        sys.exit(3)

    print("grading the SelectedPatch with the swebench oracle (Docker)...", flush=True)
    pred = make_prediction(IID, selected[0]["model_patch"], model_name="substrate-solver")
    rdir = Path("process/runs/smokes/flask")
    run_swebench(
        [pred],
        dataset_name="princeton-nlp/SWE-bench_Lite",
        run_id="flasksolve",
        instance_ids=[IID],
        report_dir=rdir,
        max_workers=1,
    )
    resolved = read_resolved(rdir, "flasksolve", "substrate-solver", IID)
    print(f"\n=== RESOLVED: {resolved} ===  (the full solver produced a patch the oracle accepts)")


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The SWE-bench Adapter + Suite — wire substrate topologies as Arms over real SWE-bench instances.

The assay harness (suite.py / run.py / report.py / oracle.py) is generic and already proven by the
firewalled coding benchmark (coding.py). This is the SWE-bench analog: a `Case` per instance, an Arm
matrix of topologies, and the record-grading `swebench_record_oracle`. The Adapter does the per-case
setup the session's `scripts/solve_instance.py` did by hand — clone the repo at base_commit, discover the
canonical test modules, build the firewall-clean regression command, and run the base suite ONCE for the
passed-at-base set — and packs PRIMITIVES into `Case.payload` so each Arm's `build(case)` reconstructs the
runner + regression planner without redoing the I/O. Every Arm on a Case consumes the IDENTICAL payload
(the Wave-0-carry discipline); the firewall lives here (the held-out test_patch/FAIL_TO_PASS never enter
the payload — `exclude` carries only test_patch FILE PATHS, used to drop issue-related tests, disclosed).

THE ARM CONTRACT: a topology is a valid SWE-bench Arm iff `build(case)` returns a topology that emits a
`SelectedPatch` carrying its model_patch (what `model_patch_from_record` reads). The pipeline arm built
here (`swebench_solver_arm`) does; other topologies (a tool agent, an ensemble) provide their own arm
builder over the same payload.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NotRequired, TypedDict, cast

from ..topologies.swebench_solver.select_docker import (
    DockerTestRunner,
    build_regression_command,
    instance_image,
    repo_test_spec,
)
from ..topologies.swebench_solver.select_exec import passed_tests
from ..topologies.swebench_solver.select_regression import discover_test_modules
from .suite import ABLATION, BASELINE, FULL, Arm, Case, Suite, Topology
from .swebench import swebench_record_oracle


class PreparedPayload(TypedDict):
    """Sprint 143 — typed shape of a SWE-bench `Case.payload` produced by `prepare_swebench_case`.

    The generic assay `Case.payload` is `dict[str, Any]` by the harness contract; this TypedDict
    types the SWE-bench-specific fields so a caller hand-rolling a payload for
    `solver_topology_from_payload` fails mypy unless every required key is present with the right
    type. No runtime cost — the object at runtime is still a `dict`. The type is the wall that
    keeps future code from opening a second door around `prepare_swebench_case`.
    """

    base_checkout: str
    repo_skeleton: str
    known_files: list[str]
    regression_files: list[str]
    exclude: list[str]
    spec: dict[str, Any]
    passed_at_base: list[str]
    image: str
    issue: str
    # 2026-08-09: when True, the solver SELECT falls back to the whole-run
    # `regression_passed` bool instead of the scoped `regression_held` filter.
    # `prepare_swebench_case(skip_base_pytest=True)` sets this and leaves
    # `passed_at_base` as `[]`. Verified is human-curated to eliminate the
    # flask-class "warnings-as-errors → 133 pre-existing base failures" case
    # (select_exec.py:66-69) — the base-pytest exists as a defense against a
    # class of noise that Verified was built to preclude, so skipping it cuts
    # ~day of prep wall on Verified without changing the honest verdict. On
    # Lite the default stays False; the caller opts in with the confirmatory
    # runner's `SWEBENCH_SKIP_BASE_PYTEST=1`.
    skip_base_pytest: NotRequired[bool]


def safe_case_id(instance_id: str) -> str:
    """A filesystem-safe Case.case_id from a SWE-bench instance_id. The harness forbids `__` in a case_id
    (it is the `{arm}__{case}__t{trial}` run-root separator), but SWE-bench ids contain it
    (`pallets__flask-4045`). Map `__`->`_1776_` (swebench's own TestSpec convention). The REAL instance_id
    stays in `Case.ground_truth` — this is only the path-safe label, never the grade key."""
    return instance_id.replace("__", "_1776_")


def _added_files(diff: str) -> set[str]:
    return {ln[6:] for ln in diff.splitlines() if ln.startswith("+++ b/") and ln[6:] != "dev/null"}


# 2026-08-09 wall-clock reshape (item 3 of the review at
# docs/review/REVIEW-2026-08-09-swebench-runner-shape-and-walltime.md and the mother-clone
# rescue that hit right after re-firing pass 1 with skip_base_pytest ON): the pre-fix `_clone_at`
# ran `git clone https://github.com/{repo}` per instance. Verified spans 500 instances across
# ~12 unique repos; at CONCURRENCY=8 the prep runner regularly grabbed 8 astropy instances
# simultaneously and cloned astropy (~700 MB) 8 times in parallel over one pipe — GitHub throttled
# and the clones fought for bandwidth, so 10 min in the runner had prepped zero cases.
#
# Fix: one bare "mother" clone per repo under `~/.cache/substrate/swe-mothers/<owner__repo>.git`,
# then `git clone --local` per instance (hardlinked objects, essentially instant). Two concurrent
# workers hitting the same missing repo serialize on `fcntl.flock` of a per-repo `.lock` file, so
# a fresh cache never triggers two parallel bare-clones of the same repo. On subsequent runs the
# mother is reused as-is — SWE-bench base_commits are years old, so no `git fetch` is needed for
# cache hits. Cross-process safe (the flock survives a runner restart mid-clone).
_MOTHER_CACHE_ROOT = Path.home() / ".cache" / "substrate" / "swe-mothers"


def _emit_repo_clone_event(kind: str, payload: dict[str, Any]) -> None:
    """Sprint 190 (S5.5): typed events for the B5 GitHub-clone boundary. Prep runs outside
    any substrate topology so the events land on stderr as canonical JSON lines rather than
    on a run's bus. Consumers that grep stderr counts see typed cache-hit vs fetch vs failure
    rates without a log-line-parsing convention. Kind names match vocab v0.3 § G.4."""
    import json
    import sys
    import time

    line = json.dumps(
        {"t": time.time(), "kind": kind, "boundary": "repo_clone", "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    )
    print(line, file=sys.stderr, flush=True)


def _mother_clone(repo: str) -> Path:
    """Bare mother clone for `repo` under `~/.cache/substrate/swe-mothers/`, created on first miss
    under a per-repo `fcntl.flock` so two concurrent workers can't both bare-clone the same missing
    repo. Returns the mother path. Idempotent.

    Sprint 190 (S5.5): emits typed `RepoCloneRequested` / `RepoCloneCached` / `RepoCloned` /
    `RepoCloneFailed` events to stderr per vocab v0.3 § G.4. Runs in the prep phase before any
    substrate topology starts; stderr is the honest emit surface. When the prep phase itself
    becomes a substrate topology later, the same event kinds ride the bus directly."""
    import fcntl
    import time

    _MOTHER_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    safe = repo.replace("/", "__")
    mother = _MOTHER_CACHE_ROOT / f"{safe}.git"
    lock_path = _MOTHER_CACHE_ROOT / f"{safe}.lock"

    started = time.monotonic()
    _emit_repo_clone_event("RepoCloneRequested", {"repo": repo})
    if mother.exists():
        _emit_repo_clone_event(
            "RepoCloneCached",
            {
                "repo": repo,
                "mother_path": str(mother),
                "wall_ms": int((time.monotonic() - started) * 1000),
            },
        )
        return mother

    with open(lock_path, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            if mother.exists():
                # A peer worker fetched under the lock while we waited; treat as cache hit.
                _emit_repo_clone_event(
                    "RepoCloneCached",
                    {
                        "repo": repo,
                        "mother_path": str(mother),
                        "wall_ms": int((time.monotonic() - started) * 1000),
                    },
                )
                return mother
            fetch_started = time.monotonic()
            try:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--bare",
                        "--quiet",
                        f"https://github.com/{repo}",
                        str(mother),
                    ],
                    check=True,
                )
            except subprocess.CalledProcessError as exc:
                _emit_repo_clone_event(
                    "RepoCloneFailed",
                    {
                        "repo": repo,
                        "error": f"git clone --bare failed rc={exc.returncode}",
                        "wall_ms": int((time.monotonic() - started) * 1000),
                    },
                )
                raise
            _emit_repo_clone_event(
                "RepoCloned",
                {
                    "repo": repo,
                    "mother_path": str(mother),
                    "fetch_ms": int((time.monotonic() - fetch_started) * 1000),
                    "wall_ms": int((time.monotonic() - started) * 1000),
                },
            )
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    return mother


def _clone_at(repo: str, base_commit: str) -> str:
    """A per-instance checkout at `base_commit`, cheaply produced from the on-disk mother clone.
    `git clone --local` hardlinks objects — essentially instant even for a 700 MB repo like
    astropy. Origin is removed so the solver's derived clones (`repair_validate_factory` at
    topologies/swebench_solver/repair.py:98 clones this dir again) can't `git fetch` a fix from
    GitHub via origin — the pre-mother `_clone_at` left origin pointing at github.com, a
    pre-existing contamination hole closed here as a side benefit. (The solver still has the
    mother's objects available through the local-clone hardlinks; the container backend at
    swebench_container.py:78-87 does the fuller ref/reflog neuter for the executing-agent path.)"""
    mother = _mother_clone(repo)
    d = tempfile.mkdtemp(prefix="assay-swe-")
    subprocess.run(["git", "clone", "--quiet", "--local", str(mother), d], check=True)
    subprocess.run(["git", "-C", d, "checkout", "--quiet", base_commit], check=True)
    subprocess.run(["git", "-C", d, "remote", "remove", "origin"], capture_output=True, check=False)
    return d


def prepare_swebench_case(
    instance: dict[str, Any],
    *,
    namespace: str = "swebench",
    timeout: int = 1800,
    skip_base_pytest: bool = False,
) -> Case:
    """ENV-GATED (git + Docker). The Adapter's per-case setup: clone at base_commit, discover
    canonical test modules, build the regression command, and optionally run it once at base for
    the passed-at-base set. Returns a `Case` whose `payload` holds PRIMITIVES every Arm
    reconstructs from; `ground_truth` is the instance (the Oracle reads its instance_id).

    2026-08-09 halt-on-error rewrite: no firewall pre-filter. SWE-bench Verified is human-audited
    clean, so a firewall violation on Verified is a data bug in the benchmark and deserves to
    halt the sweep, not silently exclude. Callers using Lite (which does carry leaky instances)
    can call `firewall_check` themselves and skip the leaky ones upstream — that's a benchmark
    choice, not a substrate design.

    2026-08-09 wall-clock reshape: `skip_base_pytest=True` skips the base-repo pytest run — the
    dominant prep bottleneck (astropy/django/sympy: 15-40 min each; 500 instances × 30 min /
    CONCURRENCY=4 ≈ 60h prep). SELECT then falls back to whole-run `regression_passed` at
    select_exec.py:61-76 instead of the scoped `regression_held`. The `passed_at_base` filter
    exists to guard the flask-class "warnings-as-errors → 133 pre-existing base failures" case
    documented at select_exec.py:66-69, which Princeton/OpenAI/Anthropic curated OUT of SWE-bench
    Verified. The choice is stamped in the payload (`skip_base_pytest: True`) and hashed into
    the confirmatory runner's config fingerprint, so the record self-describes the trade.
    """
    base = _clone_at(instance["repo"], instance["base_commit"])
    repo_files = subprocess.run(
        ["git", "-C", base, "ls-files"], capture_output=True, text=True
    ).stdout.split()
    repo_tests = discover_test_modules(repo_files)
    exclude = _added_files(
        instance["test_patch"]
    )  # held-out test_patch file PATHS (firewall-disclosed)
    spec = dict(repo_test_spec(instance["repo"], instance["version"]))

    image = instance_image(instance["instance_id"], namespace=namespace)
    if skip_base_pytest:
        passed_at_base: list[str] = []
    else:
        runner = DockerTestRunner(image, timeout=timeout)
        full_reg = build_regression_command(spec, [t for t in repo_tests if t not in exclude])
        _, base_out = runner.run("", full_reg)  # empty patch -> run on base_commit
        passed_at_base = sorted(passed_tests(base_out))

    payload: PreparedPayload = {
        "base_checkout": base,
        "repo_skeleton": "\n".join(repo_files),
        "known_files": repo_files,
        "regression_files": repo_tests,
        "exclude": sorted(exclude),
        "spec": spec,
        "passed_at_base": passed_at_base,
        "image": image,
        "issue": instance["problem_statement"],
        "skip_base_pytest": skip_base_pytest,
    }
    return Case(
        case_id=safe_case_id(instance["instance_id"]), payload=dict(payload), ground_truth=instance
    )


def solver_topology_from_payload(
    payload: PreparedPayload,
    responders: list[Any],
    *,
    n: int,
    max_rounds: int,
    repro_k: int = 1,
) -> Topology:
    """Sprint 199c (roadmap v2 S7b close): reconstruct the light `swebench_repair_topology`
    for a prepared Case payload — localize + best-of-N repair + emit the first patch that
    applied. The harness grades.

    Pre-Sprint-199c this function built `swebench_solver_topology_with_test_selection` (the
    heavy topology with in-topology `select_exec` + reproduction planner). That path duplicated
    the grader's work in-topology, doubled per-cell Docker minutes, and produced the 517-silent-
    fails shape the 2026-08-10 postmortem records. Sprint 199b retired the matrix-arm opt-in
    (`include_test_selection=True`); Sprint 199c migrates the last live callers (`swebench_solver_arm`
    and `scripts/assay_swebench_run.py`) to the light topology. `repro_k` is preserved in the
    signature for source-compat with pre-migration callers but is ignored — the light topology
    does not run reproductions in-topology; the harness re-runs FAIL_TO_PASS + PASS_TO_PASS.
    """
    from ..topologies.swebench_solver.assemble import swebench_repair_topology

    _ = repro_k  # source-compat with pre-Sprint-199c callers
    return swebench_repair_topology(
        responders=responders,
        base_checkout=str(payload["base_checkout"]),
        issue=str(payload["issue"]),
        repo_skeleton=str(payload["repo_skeleton"]),
        known_files=set(payload["known_files"]),
        n=n,
        max_rounds=max_rounds,
    )


def swebench_solver_arm(
    name: str,
    role: str,
    *,
    models: Sequence[str],
    n: int | None = None,
    max_rounds: int = 2,
    max_tokens: int = 2048,
) -> Arm:
    """A repair Arm over the given producer models. `build(case)` wires the light
    `swebench_repair_topology` from the prepared payload with one rate-limit-wrapped
    Ollama responder per slot. `n` defaults to len(models).

    Sprint 199c (roadmap v2 S7b close): migrated off the heavy
    `swebench_solver_topology_with_test_selection` — the topology's job is producing a
    candidate patch, not grading it. Same wire-shape and Arm contract as Sprint 199b's
    matrix-mode arms; the harness grades.
    """
    slots = n if n is not None else len(models)

    def build(case: Case) -> Topology:
        from .swebench_matrix import _ollama_quota_from_env, _wrap_ollama

        quota = _ollama_quota_from_env()
        responders = [
            _wrap_ollama(models[i % len(models)], quota, max_tokens) for i in range(slots)
        ]
        payload = cast(PreparedPayload, case.payload)
        return solver_topology_from_payload(payload, responders, n=slots, max_rounds=max_rounds)

    return Arm(name=name, role=role, build=build)


def swebench_suite(
    cases: Sequence[Case],
    arms: Sequence[Arm],
    *,
    report_root: Path | str,
    dataset_name: str,
    control_arm: str | None = None,
    name: str = "swebench",
    version: str = "0.1",
    primary_metric: str = "resolved",
    null_rule: str = (
        "the primary endpoint is instances resolved (held-out FAIL_TO_PASS + PASS_TO_PASS all pass, "
        "all-or-nothing). A control Arm must appear on the log; equivalence is claimed only if the paired "
        "delta CI sits inside the pre-registered margin, never from non-significance alone."
    ),
    equivalence_margin: float = 0.1,
    pass_k: int = 1,
) -> Suite:
    """Assemble a SWE-bench Suite: the prepared Cases, the Arm(s), and the record-grading Docker
    Oracle. `report_root` is where the harness writes per-instance grade reports.

    Sprint 201 (best-practice fold): `control_arm` defaulted to `None`. A single-arm Suite (the
    topology-attachment test-drive shape) skips paired-delta framing at the report layer.
    Multi-arm comparative Suites still pass `control_arm` explicitly."""
    return Suite(
        name=name,
        version=version,
        cases=tuple(cases),
        arms=tuple(arms),
        oracle=swebench_record_oracle(report_root=report_root, dataset_name=dataset_name),
        control_arm=control_arm,
        primary_metric=primary_metric,
        null_rule=null_rule,
        equivalence_margin=equivalence_margin,
        pass_k=pass_k,
    )


def _repair_and_grade_topology_from_payload(
    payload: PreparedPayload,
    responders: list[Any],
    *,
    n: int,
    max_rounds: int,
    dataset_name: str,
    model_name: str,
    run_id: str,
    report_dir: Any,
    grade_timeout_seconds: int,
    split: str = "test",
    namespace: str = "swebench",
) -> Topology:
    """Sprint 197 (roadmap v2 S6 consumer): reconstruct `swebench_solve_and_grade_topology` for a
    prepared Case payload. Same Adapter contract as `solver_topology_from_payload`, but the
    topology emits `GradeResult` on the cell's record; the paired `swebench_log_projection_oracle`
    reads it off. `instance_id` comes from the payload's `image` (which encodes it) — the
    payload's `image` is deterministic per instance_id via `instance_image`."""
    from .swebench_solve_and_grade import swebench_solve_and_grade_topology

    # Extract instance_id from the image string (`swebench.eval.<arch>.<instance>.<hash>`).
    # Sprint 197: the payload doesn't carry instance_id directly; it's on the Case's
    # `ground_truth`. Callers pass instance_id explicitly via the Arm's build closure.
    return swebench_solve_and_grade_topology(
        responders=responders,
        base_checkout=str(payload["base_checkout"]),
        issue=str(payload["issue"]),
        repo_skeleton=str(payload["repo_skeleton"]),
        known_files=set(payload["known_files"]),
        instance_id=run_id,  # caller passes instance_id-derived run_id (see arm helper)
        dataset_name=dataset_name,
        model_name=model_name,
        run_id=run_id,
        report_dir=report_dir,
        grade_timeout_seconds=grade_timeout_seconds,
        split=split,
        namespace=namespace,
        n=n,
        max_rounds=max_rounds,
    )


def swebench_solve_and_grade_arm(
    name: str,
    role: str,
    *,
    models: Sequence[str],
    report_root: Path | str,
    dataset_name: str,
    model_name: str = "substrate",
    grade_timeout_seconds: int = 1800,
    n: int | None = None,
    max_rounds: int = 2,
    max_tokens: int = 2048,
    split: str = "test",
    namespace: str = "swebench",
) -> Arm:
    """Sprint 197 (roadmap v2 S6 consumer): an Arm whose `build(case)` returns
    `swebench_solve_and_grade_topology`. Grade emits `GradeResult` on the cell's record;
    paired with `swebench_log_projection_oracle` in `swebench_solve_and_grade_suite`.

    Same responder + rate-limit wiring as `swebench_solver_arm`. `run_id` derives
    from the case's instance_id (via ground_truth) so the harness call inside the grade
    producer uses a deterministic run_id per (arm, case).
    """
    slots = n if n is not None else len(models)

    def build(case: Case) -> Topology:
        from .swebench_matrix import _ollama_quota_from_env, _wrap_ollama

        quota = _ollama_quota_from_env()
        responders = [
            _wrap_ollama(models[i % len(models)], quota, max_tokens) for i in range(slots)
        ]
        payload = cast(PreparedPayload, case.payload)
        # instance_id comes from ground_truth (the raw swebench instance dict); the run_id
        # binds (arm, instance) so parallel grades don't collide on the same report_dir path.
        instance_id = (
            str(case.ground_truth["instance_id"])
            if isinstance(case.ground_truth, Mapping)
            else str(case.ground_truth)
        )
        run_id = f"{name}-{safe_case_id(instance_id)}"
        from .swebench_solve_and_grade import swebench_solve_and_grade_topology

        return swebench_solve_and_grade_topology(
            responders=responders,
            base_checkout=str(payload["base_checkout"]),
            issue=str(payload["issue"]),
            repo_skeleton=str(payload["repo_skeleton"]),
            known_files=set(payload["known_files"]),
            instance_id=instance_id,
            dataset_name=dataset_name,
            model_name=model_name,
            run_id=run_id,
            report_dir=Path(report_root),
            grade_timeout_seconds=grade_timeout_seconds,
            split=split,
            namespace=namespace,
            n=slots,
            max_rounds=max_rounds,
        )

    return Arm(name=name, role=role, build=build)


def swebench_solve_and_grade_suite(
    cases: Sequence[Case],
    arms: Sequence[Arm],
    *,
    control_arm: str | None = None,
    name: str = "swebench",
    version: str = "0.1",
    primary_metric: str = "resolved",
    null_rule: str = (
        "the primary endpoint is instances resolved (held-out FAIL_TO_PASS + PASS_TO_PASS all pass, "
        "all-or-nothing). A control Arm must appear on the log; equivalence is claimed only if the paired "
        "delta CI sits inside the pre-registered margin, never from non-significance alone."
    ),
    equivalence_margin: float = 0.1,
    pass_k: int = 1,
) -> Suite:
    """Sprint 197 (roadmap v2 S6 consumer): assemble a Suite that grades via
    `SwebenchLogProjectionOracle` — reads `GradeResult` off each cell's record instead of
    calling `run_swebench` externally. The arms must build topologies that emit `GradeResult`
    (use `swebench_solve_and_grade_arm` or a hand-wired topology using
    `swebench_solve_and_grade_topology`). No `report_root` param — reports live inside the
    grade producer's run scope; the oracle needs only the record."""
    from .swebench import swebench_log_projection_oracle

    return Suite(
        name=name,
        version=version,
        cases=tuple(cases),
        arms=tuple(arms),
        oracle=swebench_log_projection_oracle(),
        control_arm=control_arm,
        primary_metric=primary_metric,
        null_rule=null_rule,
        equivalence_margin=equivalence_margin,
        pass_k=pass_k,
    )


__all__ = [
    "safe_case_id",
    "prepare_swebench_case",
    "solver_topology_from_payload",
    "swebench_solver_arm",
    "swebench_solve_and_grade_arm",
    "swebench_suite",
    "swebench_solve_and_grade_suite",
    "ABLATION",
    "BASELINE",
    "FULL",
]

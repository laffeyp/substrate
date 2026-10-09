# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The confirmatory SWE-bench runner.

Sprint 199b (roadmap v2 S7b) rewrites the runner around `assay.run.run_suite_with_salvage`
(Sprint 199) — the generic per-cell orchestrator. The pre-Sprint-199b runner reimplemented
concurrency, salvage, per-cell wall-clock, classifier dispatch, and row-write serialization
inline; that inline loop is gone. The runner now owns the SWE-bench-specific pieces
(dataset load, prep + firewall + image pull, cases sidecar, meta.json, resume with
foreign-config guard, model preflight, classifier taxonomy, JSONL row shape, BATCH_GRADE
opt-in) and hands the cell loop to `run_suite_with_salvage(...)`.

Env (all optional; defaults are a smoke slice — the real confirmatory run sets
`SWEBENCH_MODELS`, `SWEBENCH_LIMIT=300`, and `SWEBENCH_TRIALS=3`):

    SWEBENCH_MODELS       comma-sep model ids (default: "llama3.2:1b" — Sprint 160 requires
                          this to be explicitly set; the 1B default reports near-zero on Lite)
    SWEBENCH_N            best-of-N drafters per case (default: 3)
    SWEBENCH_LIMIT        cap instance count (default: 3 — smoke slice; 0 for the full split)
    SWEBENCH_TRIALS       trials per (arm, case) (default: 1)
    SWEBENCH_CONCURRENCY  concurrent cells (default: 8)
    SWEBENCH_ROLE         arm role: baseline | ablation | full (default: "full")
    SWEBENCH_ARM_NAME     arm name written to cells (default: "swebench_solver")
    SWEBENCH_CELLS        cells JSONL path (default: "process/runs/assays/smoke/swebench_cells.jsonl")
    SWEBENCH_SCRATCH      per-cell record roots (default: "process/assay_smoke/records/")
    SWEBENCH_DATASET      HuggingFace dataset (default: "princeton-nlp/SWE-bench_Verified")
    SWEBENCH_SPLIT        dataset split (default: "test")
    SWEBENCH_MARGIN       pre-registered equivalence margin (default: 0.10)
    SWEBENCH_CONTROL      control arm name for delta framing
    SWEBENCH_RUN_TIMEOUT  per-cell wall-clock ceiling in seconds (default: 1800). Sprint 198
                          derives the ACTUAL cell timeout as `min(RUN_TIMEOUT,
                          timeout_for_instance(instance_id))` — sympy cells get 90 min,
                          small repos get 10.
    SWEBENCH_SALVAGE      salvage directory — regrade finished records without model calls
    SWEBENCH_ARMS         "solver" (single arm) | "pass1" (ensemble) | "matrix" (5 arms) |
                          "solve_and_grade" (Sprint 197's log-projection path; the 4 repair
                          arms, container_arm excluded)
    SWEBENCH_ENSEMBLE     comma-sep model ids for the ensemble arm
    SWEBENCH_K            K value for baseline_matched_compute
    SWEBENCH_SKIP_BASE_PYTEST  skip the base-repo pytest step in prepare_swebench_case
                          (default: on for any dataset name containing "Verified")
    SWEBENCH_PREPULL_IMAGES  pre-pull every unique instance image before prep (default: 1)

Usage:

    uv run python scripts/assay_swebench_confirmatory.py            # run/continue
    uv run python scripts/assay_swebench_confirmatory.py report     # rebuild from cells

Env-gated: needs git + Docker + swebench eval images pullable + Ollama live for the listed
models (or a deterministic responder for smoke).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

import msgspec
from datasets import load_dataset

from substrate.adapters.rate_limit import ProviderRateLimited
from substrate.assay.cells import report_from_cells
from substrate.assay.oracle import Verdict
from substrate.assay.preregistration import (
    fingerprint as _fingerprint_shared,
)
from substrate.assay.preregistration import (
    guard as preregistration_guard,
)
from substrate.assay.run import (
    CellOutcome,
    CellSource,
    PerCellBudget,
    UsageTotals,
    run_suite_with_salvage,
)
from substrate.assay.suite import Arm, Case, Suite
from substrate.assay.swebench import (
    DEFAULT_MODEL_NAME,
    REASON_FIREWALL_VIOLATION,
    REASON_HARNESS_ERROR,
    REASON_RATE_LIMITED,
    REASON_TIMED_OUT,
    SwebenchExtractOnlyOracle,
    batch_grade_from_records,
    classify_reason_string,
    timeout_for_instance,
)
from substrate.assay.swebench_errors import SwebenchRunnerError
from substrate.assay.swebench_matrix import (
    container_arm,
    container_solve_and_grade_arm,
    swebench_repair_arm,
)
from substrate.assay.swebench_suite import (
    prepare_swebench_case,
    swebench_solve_and_grade_arm,
    swebench_solve_and_grade_suite,
    swebench_solver_arm,
    swebench_suite,
)
from substrate.topologies.swebench_solver.firewall import FirewallViolation

# ── SWE-bench cell-error taxonomy ─────────────────────────────────────────────
# H-3 (ratified 2026-08-10): runner-side error reasons flow from the shared
# _HARNESS_REASONS closed set at assay/swebench.py. Typed exceptions carry .reason
# directly; the string-repr fallback covers untyped library exceptions.
_ERROR_UNCLASSIFIED = "unclassified_error"


def _reason_from_detail(detail: str) -> str:
    """Pull `reason=<name>` out of a Result.detail line (legacy oracle path)."""
    marker = " reason="
    if marker in detail:
        return detail.rsplit(marker, 1)[1].strip()
    return REASON_HARNESS_ERROR


def _classify_cell_error(exc: BaseException) -> tuple[str, bool]:
    """Classify one cell's exception into (typed_reason, halt_bool). Halt=True halts the
    sweep with the traceback; Halt=False writes an ERROR outcome and continues.

    Design v3 (ratified 2026-08-10) + F4: typed exceptions FIRST — `SwebenchRunnerError`
    subclasses carry `.reason` from the shared `_HARNESS_REASONS` closed set. String-repr
    fallback catches the untyped-exception legacy path (subprocess.CalledProcessError,
    generic OSError, third-party libraries raising RuntimeError)."""
    if isinstance(exc, SwebenchRunnerError):
        return (exc.reason, False)
    if isinstance(exc, ProviderRateLimited):
        return (REASON_RATE_LIMITED, False)
    if isinstance(exc, FirewallViolation):
        return (f"{REASON_FIREWALL_VIOLATION}:{exc.reason}", False)
    if isinstance(exc, TimeoutError | asyncio.TimeoutError):
        return (REASON_TIMED_OUT, False)
    # Sprint 200a: route the string-repr fallback through `classify_reason_string` at
    # `assay/swebench.py` — one source of truth shared with `SwebenchLogProjectionOracle`.
    # `classify_reason_string` returns a `_HARNESS_REASONS` value for docker/git/rate-limit
    # substrings; anything else falls through to REASON_HARNESS_ERROR at the string level.
    # Runner-side we UPGRADE the harness_error fallback to unclassified_error (halt) so an
    # unexpected exception class doesn't get silently absorbed as a flake. subprocess.CalledProcessError
    # (git subprocess errors) always routes as git_error even if its repr doesn't say "git".
    msg = repr(exc).lower()
    if isinstance(exc, subprocess.CalledProcessError):
        # subprocess errors always classify (docker/git present in argv), don't halt.
        return (classify_reason_string(msg), False)
    reason = classify_reason_string(msg)
    if (
        reason == REASON_HARNESS_ERROR
        and "docker" not in msg
        and "container" not in msg
        and "git" not in msg
    ):
        # Genuine unknown — halt so an unfamiliar exception class doesn't get papered over.
        return (_ERROR_UNCLASSIFIED, True)
    return (reason, False)


# ── env parsing ───────────────────────────────────────────────────────────────
MODELS = os.environ.get("SWEBENCH_MODELS", "llama3.2:1b").split(",")
N = int(os.environ.get("SWEBENCH_N", "3"))
LIMIT = int(os.environ.get("SWEBENCH_LIMIT", "3"))
TRIALS = int(os.environ.get("SWEBENCH_TRIALS", "1"))
CONCURRENCY = int(os.environ.get("SWEBENCH_CONCURRENCY", "8"))
ROLE = os.environ.get("SWEBENCH_ROLE", "full")
ARM_NAME = os.environ.get("SWEBENCH_ARM_NAME", "swebench_solver")
CELLS = Path(os.environ.get("SWEBENCH_CELLS", "process/runs/assays/smoke/swebench_cells.jsonl"))
SCRATCH = Path(os.environ.get("SWEBENCH_SCRATCH", "process/runs/assays/smoke/records"))
DATASET = os.environ.get("SWEBENCH_DATASET", "princeton-nlp/SWE-bench_Verified")
SPLIT = os.environ.get("SWEBENCH_SPLIT", "test")
MARGIN = float(os.environ.get("SWEBENCH_MARGIN", "0.10"))
CONTROL = os.environ.get("SWEBENCH_CONTROL", ARM_NAME)
RUN_TIMEOUT = float(os.environ.get("SWEBENCH_RUN_TIMEOUT", "1800"))
SALVAGE = os.environ.get("SWEBENCH_SALVAGE", "")
PREG = os.environ.get("SWEBENCH_PREG", "")
ARMS_MODE = os.environ.get("SWEBENCH_ARMS", "solver")
ENSEMBLE = [m.strip() for m in os.environ.get("SWEBENCH_ENSEMBLE", "").split(",") if m.strip()]
K_CALLS = int(os.environ.get("SWEBENCH_K", "0"))
REPRO_K = int(os.environ.get("SWEBENCH_REPRO_K", "1"))
SKIP_BASE_PYTEST = (
    os.environ.get("SWEBENCH_SKIP_BASE_PYTEST", "1" if "Verified" in DATASET else "0") == "1"
)
BATCH_GRADE = os.environ.get("SWEBENCH_BATCH_GRADE", "0") == "1"
PREPULL_IMAGES = os.environ.get("SWEBENCH_PREPULL_IMAGES", "1") == "1"

_ZERO = UsageTotals(0, 0, 0, 0, False)
_RUN_ID = ""
_CONFIG_FP = ""
_fingerprint = _fingerprint_shared


def _config() -> dict[str, object]:
    return {
        "models": MODELS,
        "n": N,
        "limit": LIMIT,
        "trials": TRIALS,
        "role": ROLE,
        "arm_name": ARM_NAME,
        "dataset": DATASET,
        "split": SPLIT,
        "margin": MARGIN,
        "control_arm": CONTROL,
        "run_timeout": RUN_TIMEOUT,
        "skip_base_pytest": SKIP_BASE_PYTEST,
        "batch_grade": BATCH_GRADE,
        "assay_kind": "swebench",
    }


def _load_rows() -> dict[tuple[str, str, int], dict[str, object]]:
    rows: dict[tuple[str, str, int], dict[str, object]] = {}
    if CELLS.exists():
        for line in CELLS.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                rows[(str(r["arm"]), str(r["case_id"]), int(r["trial"]))] = r
    return rows


def _row(
    arm_name: str,
    role: str,
    case_id: str,
    trial: int,
    verdict: Verdict,
    source: CellSource,
    u: UsageTotals,
    elapsed: int,
    root: str,
    detail: str = "",
    reason: str = "",
    reproduction: str = "",
    recall_at_k: float | None = None,
    full_recall_at_k: bool | None = None,
) -> dict[str, object]:
    measured = source is CellSource.RUN
    return {
        "arm": arm_name,
        "role": role,
        "case_id": case_id,
        "trial": trial,
        "verdict": verdict.value,
        "reason": reason,
        "passed": verdict is Verdict.PASS,
        "source": source.value,
        "detail": detail,
        "elapsed_ms": elapsed if measured else None,
        "root": root,
        "config_fp": _CONFIG_FP,
        "run_id": _RUN_ID,
        "prompt_tokens": u.prompt_tokens if measured else None,
        "completion_tokens": u.completion_tokens if measured else None,
        "inference_ms": u.inference_ms if measured else None,
        "model_calls": u.model_calls if measured else None,
        "estimated": u.estimated,
        "reproduction": reproduction,
        "recall_at_k": recall_at_k,
        "full_recall_at_k": full_recall_at_k,
    }


def _shape_row(outcome: CellOutcome) -> dict[str, object]:
    """Translate a CellOutcome into the SWE-bench cells-JSONL row shape. Sprint 199b
    replaces the pre-fold inline row-write inside `cell()`."""
    arm_name = outcome.arm.name
    role = outcome.arm.role
    case_id = outcome.case.case_id
    trial = outcome.trial
    if outcome.source is CellSource.ERROR:
        # `firewall_violation:<detail>` collapses to REASON_FIREWALL_VIOLATION on the wire;
        # detail carries the specifics.
        exc = outcome.exception
        assert exc is not None
        raw_reason = outcome.exception_reason
        wire_reason = (
            REASON_FIREWALL_VIOLATION
            if raw_reason.startswith(REASON_FIREWALL_VIOLATION)
            else raw_reason
        )
        return _row(
            arm_name,
            role,
            case_id,
            trial,
            Verdict.NO_VERDICT,
            CellSource.ERROR,
            _ZERO,
            0,
            outcome.root,
            detail=f"{raw_reason}: {type(exc).__name__}: {str(exc)[:280]}",
            reason=wire_reason,
            reproduction="",
        )
    assert outcome.result is not None
    reason = outcome.result.reason or (
        ""
        if outcome.result.verdict is not Verdict.NO_VERDICT
        else _reason_from_detail(outcome.result.detail)
    )
    usage = outcome.usage or _ZERO
    return _row(
        arm_name,
        role,
        case_id,
        trial,
        outcome.result.verdict,
        outcome.source,
        usage,
        outcome.elapsed_ms,
        outcome.root,
        detail=outcome.result.detail,
        reason=reason,
        reproduction=outcome.reproduction,
        recall_at_k=outcome.result.recall_at_k,
        full_recall_at_k=outcome.result.full_recall_at_k,
    )


def _write_cases_sidecar(cases: list[tuple[Case, dict[str, object]]]) -> None:
    path = CELLS.parent / f"{CELLS.stem}.cases.json"
    payload = [
        {
            "case_id": case.case_id,
            "instance_id": str(inst["instance_id"]),
            "repo": inst.get("repo"),
            "base_commit": inst.get("base_commit"),
            "version": inst.get("version"),
            "image": case.payload["image"],
            "regression_files": case.payload["regression_files"],
            "exclude": case.payload["exclude"],
            "passed_at_base": case.payload["passed_at_base"],
        }
        for case, inst in cases
    ]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _print_report() -> int:
    if not CELLS.exists():
        print(f"no cells at {CELLS}", flush=True)
        return 64
    report, meta = report_from_cells(CELLS)
    print(
        json.dumps(
            {"report": msgspec.to_builtins(report), "meta": meta},
            indent=2,
            default=str,
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def _build_arms_for_mode() -> tuple[list[Arm], dict[str, dict[str, object]], str]:
    """Build the arm set + per-arm params (fed into pre-reg gate) + control arm name.

    Modes: `solver` (single arm), `pass1` (ensemble only), `matrix` (5 arms via
    swebench_repair_arm + container_arm), `solve_and_grade` (Sprint 197's log-projection
    path — the 4 repair arms only; container_arm excluded because it needs a grade-producer
    fold that hasn't landed).
    """
    strong = MODELS[0]

    if ARMS_MODE == "solver":
        arm = swebench_solver_arm(name=ARM_NAME, role=ROLE, models=MODELS, n=N)
        return [arm], {ARM_NAME: {"models": MODELS, "n": N, "max_rounds": 2}}, CONTROL

    if ARMS_MODE == "pass1":
        if not ENSEMBLE:
            raise SystemExit("SWEBENCH_ARMS=pass1 requires SWEBENCH_ENSEMBLE=<comma-sep models>.")
        ens = swebench_repair_arm(
            "n_drafts_repair_ensemble",
            models=ENSEMBLE,
            n=len(ENSEMBLE),
            max_rounds=2,
            role="full",
        )
        return (
            [ens],
            {"n_drafts_repair_ensemble": {"models": ENSEMBLE, "n": len(ENSEMBLE), "max_rounds": 2}},
            "n_drafts_repair_ensemble",
        )

    if ARMS_MODE in ("matrix", "solve_and_grade"):
        if not ENSEMBLE:
            raise SystemExit(f"SWEBENCH_ARMS={ARMS_MODE} requires SWEBENCH_ENSEMBLE=...")
        if K_CALLS <= 0:
            raise SystemExit(f"SWEBENCH_ARMS={ARMS_MODE} requires SWEBENCH_K=<int>.")
        tool_steps = int(os.environ.get("SWEBENCH_TOOL_STEPS", "8"))

        matrix_spec: list[dict[str, object]] = [
            {
                "name": "single_draft_baseline",
                "role": "baseline",
                "kind": "repair",
                "models": [strong],
                "n": 1,
                "max_rounds": 1,
            },
            {
                "name": "n_drafts_no_correction",
                "role": "ablation",
                "kind": "repair",
                "models": [strong],
                "n": N,
                "max_rounds": 1,
            },
            {
                "name": "n_drafts_repair",
                "role": "full",
                "kind": "repair",
                "models": [strong],
                "n": N,
                "max_rounds": 2,
            },
            {
                "name": "n_drafts_repair_ensemble",
                "role": "full",
                "kind": "repair",
                "models": list(ENSEMBLE),
                "n": len(ENSEMBLE),
                "max_rounds": 2,
            },
            {
                "name": "baseline_matched_compute",
                "role": "baseline",
                "kind": "repair",
                "models": [strong],
                "n": K_CALLS,
                "max_rounds": 1,
            },
        ]
        # Sprint 199d: `container_solve_and_grade_arm` lets the container arm join
        # `solve_and_grade` mode under the log-projection oracle. Pre-Sprint-199d only the
        # record-oracle `matrix` mode carried it.
        matrix_spec.append(
            {
                "name": "tool_loop_container",
                "role": "ablation",
                "kind": "container",
                "models": [strong],
                "max_steps": tool_steps,
            }
        )

        arms: list[Arm] = []
        params: dict[str, dict[str, object]] = {}
        for spec in matrix_spec:
            if spec["kind"] == "repair":
                if ARMS_MODE == "solve_and_grade":
                    arm = swebench_solve_and_grade_arm(
                        str(spec["name"]),
                        role=str(spec["role"]),
                        models=cast("list[str]", spec["models"]),
                        report_root=SCRATCH / "grade",
                        dataset_name=DATASET,
                        n=int(cast(int, spec["n"])),
                        max_rounds=int(cast(int, spec["max_rounds"])),
                    )
                else:
                    arm = swebench_repair_arm(
                        str(spec["name"]),
                        models=cast("list[str]", spec["models"]),
                        n=int(cast(int, spec["n"])),
                        max_rounds=int(cast(int, spec["max_rounds"])),
                        role=str(spec["role"]),
                        repro_k=REPRO_K,
                    )
                params[str(spec["name"])] = {
                    "models": spec["models"],
                    "n": spec["n"],
                    "max_rounds": spec["max_rounds"],
                }
            elif spec["kind"] == "container":
                if ARMS_MODE == "solve_and_grade":
                    arm = container_solve_and_grade_arm(
                        str(spec["name"]),
                        role=str(spec["role"]),
                        model=cast("list[str]", spec["models"])[0],
                        report_root=SCRATCH / "grade",
                        dataset_name=DATASET,
                        max_steps=int(cast(int, spec["max_steps"])),
                    )
                else:
                    arm = container_arm(
                        str(spec["name"]),
                        role=str(spec["role"]),
                        model=cast("list[str]", spec["models"])[0],
                        max_steps=int(cast(int, spec["max_steps"])),
                    )
                params[str(spec["name"])] = {
                    "models": spec["models"],
                    "max_steps": spec["max_steps"],
                }
            else:
                raise SystemExit(f"unknown arm kind {spec['kind']!r}")
            arms.append(arm)

        control = CONTROL if CONTROL != ARM_NAME else "single_draft_baseline"
        return arms, params, control

    raise SystemExit(
        f"SWEBENCH_ARMS={ARMS_MODE!r} unknown — one of solver | pass1 | matrix | solve_and_grade"
    )


def _emit_stderr_event(boundary: str, kind: str, payload: dict[str, Any]) -> None:
    """Boundary event on stderr — used before the substrate topology has a run scope."""
    line = json.dumps(
        {"t": time.time(), "kind": kind, "boundary": boundary, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    )
    print(line, file=sys.stderr, flush=True)


async def _prepull_images(ds: list[dict[str, Any]]) -> None:
    """Pre-pull every unique instance image before the prep sweep so `docker pull` lands
    once per image on registry bandwidth, not per-cell inside DockerTestRunner."""
    from substrate.topologies.swebench_solver.select_docker import instance_image

    unique_images = sorted({instance_image(inst["instance_id"]) for inst in ds})
    print(f"pre-pulling {len(unique_images)} unique instance images...", flush=True)
    pull_sem = asyncio.Semaphore(min(CONCURRENCY, 4))

    async def _pull(image: str) -> str:
        started = time.monotonic()
        _emit_stderr_event("image_pull", "ImageRequested", {"image": image})
        async with pull_sem:
            p = await asyncio.to_thread(
                subprocess.run,
                ["docker", "pull", "--platform", "linux/amd64", image],
                capture_output=True,
                text=True,
                timeout=1800,
            )
        wall_ms = int((time.monotonic() - started) * 1000)
        if p.returncode == 0:
            _emit_stderr_event("image_pull", "ImagePulled", {"image": image, "wall_ms": wall_ms})
        else:
            _emit_stderr_event(
                "image_pull",
                "ImageMissing",
                {
                    "image": image,
                    "wall_ms": wall_ms,
                    "returncode": p.returncode,
                    "stderr_tail": (p.stderr or "")[-400:],
                },
            )
        return f"  {image}: rc={p.returncode}"

    pulls = await asyncio.gather(*(_pull(img) for img in unique_images), return_exceptions=True)
    for pr in pulls:
        print(pr if not isinstance(pr, BaseException) else f"  pull error: {pr!r}", flush=True)


def _preflight_models(models: list[str]) -> None:
    """Ping every declared model; halt at startup if any doesn't respond. A dead model
    produces silent zero-patch rows across every arm — fail loud, not with 1800 fake fails."""
    if not models or os.environ.get("SWEBENCH_SKIP_MODEL_PREFLIGHT", "0") == "1":
        return
    import httpx

    print(f"model pre-flight: pinging {len(models)} declared model(s)...", flush=True)
    dead: list[tuple[str, int | str]] = []
    for m in models:
        try:
            r = httpx.post(
                "http://127.0.0.1:11434/api/chat",
                json={"model": m, "messages": [{"role": "user", "content": "ok"}], "stream": False},
                timeout=30.0,
            )
            if r.status_code != 200:
                dead.append((m, r.status_code))
                print(f"  {m}: HTTP {r.status_code} — DEAD", flush=True)
            else:
                print(f"  {m}: ok", flush=True)
        except httpx.HTTPError as exc:
            dead.append((m, repr(exc)))
            print(f"  {m}: {exc!r} — DEAD", flush=True)
    if dead:
        raise SystemExit(
            f"model pre-flight FAILED: {len(dead)} dead model(s): {dead}. "
            "Set SWEBENCH_SKIP_MODEL_PREFLIGHT=1 to override."
        )


def _interleave_by_repo(ds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic round-robin across repos so 8 concurrent workers pick 8 different
    repos rather than 8 astropy instances back-to-back."""
    from collections import defaultdict

    by_repo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for inst in ds:
        by_repo[str(inst["repo"])].append(inst)
    interleaved: list[dict[str, Any]] = []
    idx = {r: 0 for r in by_repo}
    while any(idx[r] < len(v) for r, v in by_repo.items()):
        for repo in sorted(by_repo):
            i = idx[repo]
            if i < len(by_repo[repo]):
                interleaved.append(by_repo[repo][i])
                idx[repo] = i + 1
    return interleaved


async def _run() -> int:
    global _CONFIG_FP, _RUN_ID
    _RUN_ID = f"run-{int(time.time())}"

    arms, params_by_arm, control = _build_arms_for_mode()
    cfg = _config()
    cfg["arms_mode"] = ARMS_MODE
    cfg["ensemble"] = ENSEMBLE
    cfg["k_calls"] = K_CALLS
    cfg["control_arm"] = control
    if PREG:
        pre = preregistration_guard(PREG, arms, params_by_arm=params_by_arm)
        cfg["preregistration"] = {"path": pre.path, "arms_hash": pre.arms_hash}
        cfg["comparator"] = dict(pre.comparator)
        cfg["graded_rate_floor"] = pre.graded_rate_floor
        print(
            f"pre-registration verified: {pre.path} arms_hash={pre.arms_hash} "
            f"comparator={pre.comparator['source']}={pre.comparator['resolve_rate']} "
            f"graded_rate_floor={pre.graded_rate_floor}",
            flush=True,
        )
    print(
        f"arms_mode={ARMS_MODE} arms=[{', '.join(a.name for a in arms)}] control={control}",
        flush=True,
    )

    _preflight_models(list(MODELS) + [m for m in ENSEMBLE if m not in MODELS])

    _CONFIG_FP = _fingerprint(cfg)
    CELLS.parent.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    done = _load_rows()

    foreign = {str(r.get("config_fp")) for r in done.values() if r.get("config_fp")} - {_CONFIG_FP}
    if foreign:
        raise SystemExit(
            f"{CELLS} holds cells from config(s) {foreign}, current is {_CONFIG_FP}. "
            "Use a fresh SWEBENCH_CELLS (or delete it) — refusing to mix configs."
        )

    (CELLS.parent / f"{CELLS.stem}.meta.json").write_text(
        json.dumps({"config_fp": _CONFIG_FP, "run_id": _RUN_ID, **cfg}, indent=2, sort_keys=True)
    )

    ds = list(load_dataset(DATASET, split=SPLIT))
    instance_ids_env = os.environ.get("SWEBENCH_INSTANCE_IDS", "").strip()
    if instance_ids_env:
        wanted = {s.strip() for s in instance_ids_env.split(",") if s.strip()}
        ds = [inst for inst in ds if str(inst["instance_id"]) in wanted]
    if LIMIT:
        ds = ds[:LIMIT]
    ds = _interleave_by_repo(ds)
    print(f"loaded {len(ds)} instances from {DATASET}:{SPLIT}", flush=True)

    if PREPULL_IMAGES:
        await _prepull_images(ds)

    print(
        f"preparing {len(ds)} cases at CONCURRENCY={CONCURRENCY} "
        f"(skip_base_pytest={SKIP_BASE_PYTEST})...",
        flush=True,
    )
    prep_sem = asyncio.Semaphore(CONCURRENCY)
    prep_progress = {"done": 0}
    prep_lock = asyncio.Lock()

    async def _prep_one(inst: dict[str, Any]) -> tuple[Case, dict[str, object]]:
        async with prep_sem:
            case = await asyncio.to_thread(
                prepare_swebench_case, inst, skip_base_pytest=SKIP_BASE_PYTEST
            )
            async with prep_lock:
                prep_progress["done"] += 1
                if prep_progress["done"] % 20 == 0 or prep_progress["done"] == len(ds):
                    print(f"[{prep_progress['done']}/{len(ds)}] prepared", flush=True)
            return case, inst

    prepped = await asyncio.gather(*(_prep_one(inst) for inst in ds))
    cases: list[tuple[Case, dict[str, object]]] = list(prepped)
    print(f"prepared {len(cases)} cases", flush=True)

    _write_cases_sidecar(cases)

    # Suite construction: `solve_and_grade` uses the log-projection oracle (Sprint 197);
    # every other mode uses the record oracle (external harness call from `run_arm_on_case`).
    case_list = [c for c, _ in cases]
    if ARMS_MODE == "solve_and_grade":
        suite: Suite = swebench_solve_and_grade_suite(
            cases=case_list,
            arms=arms,
            control_arm=control,
            equivalence_margin=MARGIN,
            pass_k=1,
        )
    else:
        suite = swebench_suite(
            cases=case_list,
            arms=arms,
            report_root=str(SCRATCH / "grade"),
            dataset_name=DATASET,
            control_arm=control,
            equivalence_margin=MARGIN,
            pass_k=1,
        )
        if BATCH_GRADE:
            from dataclasses import replace as _dc_replace

            suite = _dc_replace(suite, oracle=SwebenchExtractOnlyOracle())
            print(
                f"BATCH_GRADE=1: oracle deferred; batch grade fires post-sweep, "
                f"max_workers={CONCURRENCY}",
                flush=True,
            )

    def _instance_id(case: Case) -> str:
        if isinstance(case.ground_truth, dict):
            return str(case.ground_truth.get("instance_id", case.case_id))
        return case.case_id

    def _budget_for_cell(_arm: Arm, case: Case) -> PerCellBudget:
        """Sprint 198: per-repo table capped by SWEBENCH_RUN_TIMEOUT."""
        t = min(RUN_TIMEOUT, float(timeout_for_instance(_instance_id(case))))
        return PerCellBudget(time_s=t, reason="per-repo table capped by SWEBENCH_RUN_TIMEOUT")

    total_cells = len(arms) * len(cases) * TRIALS
    todo_count = total_cells - sum(
        1 for a in arms for c, _ in cases for t in range(TRIALS) if (a.name, c.case_id, t) in done
    )
    print(
        f"todo: {todo_count} of {total_cells} cells across {len(arms)} arm(s) "
        f"(already done: {len(done)}; concurrency={CONCURRENCY}, timeout={RUN_TIMEOUT}s, "
        f"salvage={'on' if SALVAGE else 'off'})",
        flush=True,
    )

    started = time.monotonic()
    write_lock = asyncio.Lock()
    progress = {"n": 0}

    async def _append_row(outcome: CellOutcome) -> None:
        row = _shape_row(outcome)
        async with write_lock:
            with CELLS.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
            progress["n"] += 1
            if progress["n"] % 5 == 0 or progress["n"] == todo_count:
                rate = progress["n"] / max(1e-9, time.monotonic() - started)
                eta = (todo_count - progress["n"]) / max(1e-9, rate)
                print(
                    f"  {progress['n']}/{todo_count}  ({rate * 60:.1f}/min, "
                    f"~{eta / 60:.1f} min left)",
                    flush=True,
                )

    def _skip(arm: Arm, case: Case, trial: int) -> bool:
        return (arm.name, case.case_id, trial) in done

    await run_suite_with_salvage(
        suite,
        SCRATCH,
        trials=TRIALS,
        concurrency=CONCURRENCY,
        salvage_dir=Path(SALVAGE) if SALVAGE else None,
        budget_for_cell=_budget_for_cell,
        classify_exception=_classify_cell_error,
        on_outcome=_append_row,
        skip=_skip,
    )

    elapsed = int(time.monotonic() - started)
    print(
        f"\nsweep done: {progress['n']} new cells, {elapsed}s this session, config_fp={_CONFIG_FP}",
        flush=True,
    )

    if BATCH_GRADE:
        print("BATCH_GRADE: reading records + firing one harness call...", flush=True)
        instances_by_case_id = {case.case_id: inst for case, inst in cases}
        grade_start = time.monotonic()
        resolved_by_cell = await asyncio.to_thread(
            batch_grade_from_records,
            SCRATCH,
            instances_by_case_id,
            report_dir=SCRATCH / "grade",
            dataset_name=DATASET,
            model_name=DEFAULT_MODEL_NAME,
            run_id=f"batch-{_RUN_ID}",
            max_workers=CONCURRENCY,
            timeout=int(RUN_TIMEOUT),
        )
        grade_elapsed = int(time.monotonic() - grade_start)
        print(
            f"BATCH_GRADE: graded {len(resolved_by_cell)} cells "
            f"({sum(resolved_by_cell.values())} resolved) in {grade_elapsed}s",
            flush=True,
        )
        updated_rows: list[dict[str, object]] = []
        for line in CELLS.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            cell_name = f"{row['arm']}__{row['case_id']}__t{row['trial']}"
            if cell_name in resolved_by_cell:
                resolved = resolved_by_cell[cell_name]
                v = Verdict.PASS if resolved else Verdict.FAIL
                row["verdict"] = v.value
                row["passed"] = resolved
                row["reason"] = ""
                row["detail"] = f"swebench resolved={resolved} for {row['case_id']} (batch)"
            updated_rows.append(row)
        CELLS.write_text("\n".join(json.dumps(r) for r in updated_rows) + "\n")
        print(f"cells rewritten with batch grades: {CELLS}", flush=True)

    print(f"cells: {CELLS}", flush=True)
    print(
        "run `uv run python scripts/assay_swebench_confirmatory.py report` for the Report",
        flush=True,
    )
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        return _print_report()
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())

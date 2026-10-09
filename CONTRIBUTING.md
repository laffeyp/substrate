# Contributing to Substrate

## Spec corpus

Four documents govern. The code answers to them.

- `docs/specs/kernel_spec/v15.md` — the eight primitives, the append cycle, replay. Read `v16_reconciliation_note.md` alongside.
- `docs/specs/product_spec/draft7.md` — requirements, the 17 conformance checks, the reference topologies.
- `docs/specs/technical_spec/draft5.md` — byte layout, writer cycle, public API.
- `docs/specs/design_spec/draft1.md` — API ergonomics, CLI UX, error UX.

### Amendments

A shipped spec is not edited. Changes land as amendment files next to the base draft; the base stays as the audit trail. Three amendments on file against product draft7:

- `draft7_amendment_A1_replay_3b.md` defers replay Level 3(b) and names the D-8 supplementary-metadata exclusion set.
- `draft7_amendment_A2_nperf1.md` re-baselines the N-PERF-1 throughput floor.
- `draft7_amendment_A3.md` collects the code-vs-spec reconciliations: check-5 wall-clock half, the F-LIFE-2 let-finish/subtree deferral, RunStarted-manifest fidelity, L1-replay scope, and the read-API naming.

## Signal-Driven Development

Built under SDD; the kit is at `../sdd-kit-2/`. Locked signal vocabulary: `process/signals/0.2.json`, additive successor to `0.1.json`. Both stay on disk; `0.1.json` is the v0.1 audit trail. The 0.1 → 0.2 rationale is `process/signals/0.2-rationale.md`.

Implementation roadmap: `process/sprints/PHASE1_PLAN.md`. Per-wave records: `process/BLACKBOARD.md`.

## Gates

The default gate is local: `scripts/ci_local.sh`. It runs the full stack across Python 3.12, 3.13, and 3.14 in isolated envs. `scripts/ci_local_ubuntu.sh` covers the linux cells via Docker.

Hosted GitHub Actions has been unavailable since 2026-07-22 — Actions minutes exhausted. The verification bar cannot depend on a hosted runner. "Gates green" means the local matrix exiting 0, watched to conclusion. The workflow file at `.github/workflows/ci.yml` stays; when Actions returns it is a backstop, not the bar. Its shape is identical to the local matrix: {ubuntu, macOS} × Python {3.12, 3.13, 3.14}.

Every change keeps this green:

```
uv run ruff check          # lint
uv run ruff format --check # format
uv run mypy                # strict type-check
uv run pytest              # tests
uv run lint-imports        # F-API-6: cli imports only substrate.api (import-linter)
uv run substrate conformance --no-perf   # the 17 conformance checks
```

`substrate conformance` is the release gate. CI passes `--no-perf` because check 15 (N-PERF-1, the throughput floor) is hardware-sensitive; on shared runners it is an honest SKIP. Verify the floor on controlled hardware:

```
SUBSTRATE_PERF_GATE=1 uv run pytest tests/test_perf.py
```

or the default `uv run substrate conformance` without `--no-perf`.

`docs/api.md` is generated. Never hand-edit it. Regenerate with `uv run python scripts/gen_api_docs.py` after any change to the public surface (`substrate.api.__all__`) or a public docstring, and commit the result. The committed walkthrough run records at `docs/walkthroughs/records/` regenerate with `uv run python scripts/gen_walkthrough_records.py`.

## Post-1.0 deferrals

Named, not shipped, in v1.0. Each is deferred with cause.

**Replay Level 3(b)** — byte-identical substitution re-execution. Needs a replay-mode writer that replays recorded `t` (amendment A1.1). Levels 1, 2, and 3(a), and D-8 log-equivalence, all ship.

**`let_finish` (F-LIFE-2 recipe) plus the `let-finish` Decision** — the "drain in-flight, then finalise" terminal has no runtime dispatch branch. Shipping the enum value or the recipe would be a silent no-op. Removed for v1.0; deferred until the dispatch and admission-stop mechanism lands. `cancel_all_others`, `quiescence`, `threshold_count`, `all_completed`, `pause_await_input`, `any_of`, and `all_of` all ship.

**`subtree_cancellation`** — needs a sixth decision value plus a scope field. Vocab-blocked.

**A compiled JCS encoder** — the throughput lever beyond the current floor (A2).

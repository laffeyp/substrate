# Sprint 345 — The kernel's lint skips process/

```yaml
---
id: 345
status: closed
closed_at: 2026-11-12
phase: continuing a session (substrate-ui roadmap 2026-11-12-continue-a-session r1, E1)
pass_kind: functional
depends_on: []
plan: ../substrate-ui/process/planning/2026-11-12-continue-a-session/ROADMAP-2026-11-12-continue-a-session-r1.md
---
```

## scope

`pyproject.toml`'s `[tool.ruff] extend-exclude` gains `process`, so ruff's lint and format gates cover the package and its tests and not the planning and evidence scripts under `process/`, as substrate-ui's `ruff.toml` has since its sprint 459. Today the pre-commit hook fails on 8 untracked scripts in `process/planning/substrate-boundary-and-runbook-2026-11-09/evidence-topology-value/` and blocks every commit. One verifiable property: `uv run ruff check .` and `uv run ruff format --check .` exit 0 with those scripts present and unchanged.

## context_files

- `pyproject.toml` (`[tool.ruff]`), `../substrate-ui/ruff.toml`
- `process/WORKING_AGREEMENT.md` (Build and verification commands)

## signal contract

### Emits

No tag.

### Invariants

- Every file under `src/` and `tests/` stays linted and format-checked.
- The scripts under `process/` are not edited.

## artifact contract

### Files modified

- `pyproject.toml`

### Content assertions

- `extend-exclude` lists `process`.

### Command exit codes

- `uv run ruff check .`, `uv run ruff format --check .` return 0; the pre-commit hook passes.

## observation contract

The hook's own run on this sprint's commit, with the untracked scripts present.

## done criteria

Kernel commits pass the hook without touching another session's scripts.

## notes

Grounds: substrate-ui sprint 459 (`ruff.toml` `extend-exclude = ["_deprecated", "process"]`). The kernel already excluded `process/archive`.

## self-review checklist

- [x] Scope is concrete and bounded.
- [x] One file.
- [x] No tag.
- [x] Artifact contract is gradable.
- [x] Observation contract present.

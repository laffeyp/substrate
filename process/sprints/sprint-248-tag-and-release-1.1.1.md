# Sprint 248 — Tag v1.1.1, release to PyPI

```yaml
---
id: 248
status: done
opened_at: 2026-09-29
phase: config-externalization
pass_kind: docs
---
```

## scope

Bump `pyproject.toml` version from `1.1.0` to `1.1.1`. Tag the commit as `v1.1.1`. Build the wheel and publish to PyPI. This unblocks `substrate-ui/scripts/fetch-python-runtime.sh`'s drift guard, which counts commits past the pinned tag on `src/`.

No code changes beyond the version string.

## prerequisites

- sprint 247 (all kernel paths routed through `substrate_home()`)

## context_files

- `pyproject.toml`
- `substrate-ui/scripts/fetch-python-runtime.sh` (to understand the drift guard at lines 54-58)

## signal contract

### Emits

- none

### Consumes

- `pyproject.toml`

### Invariants

- `git rev-list v1.1.1..HEAD -- src/` returns `0` after tagging (drift guard unblocked).
- The wheel on PyPI contains `substrate_home` in `substrate/api.py`.

## artifact contract

### Files modified

- `pyproject.toml` — version field changes from `"1.1.0"` to `"1.1.1"`.

### Content assertions

- `grep 'version = "1.1.1"' pyproject.toml` matches.
- `git tag -l v1.1.1` returns `v1.1.1`.

### Command exit codes

- `uv run python -m pytest tests/` returns 0 (pre-release verification)
- `uv build` returns 0
- `git -C ../substrate rev-list --count v1.1.1..HEAD -- src/` returns `0`

## done criteria

`substrate-kernel==1.1.1` exists on PyPI with `substrate_home()` in its public API. The drift guard in `fetch-python-runtime.sh` passes when `SUBSTRATE_VERSION` is set to `1.1.1`.

## notes

The actual PyPI upload requires credentials. The sprint card documents the steps; the human executes the `uv publish` or `twine upload` command. The Agent prepares the build and verifies the wheel contents.

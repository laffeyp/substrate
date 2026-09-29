# Sprint 246 — `substrate_home()` resolver

```yaml
---
id: 246
status: pending
opened_at: 2026-09-29
phase: config-externalization
pass_kind: architecture
---
```

## scope

Add `substrate_home() -> Path` to `substrate/src/substrate/api.py`. The function returns `Path(os.environ["SUBSTRATE_HOME"])` if the variable is set, else `Path.home() / ".substrate"`. Export it from the `substrate.api` public surface so substrate-ui can import it. This sprint introduces the resolver only — no call sites are rewritten yet (sprint 247 does that).

## prerequisites

- none

## context_files

- `sdd-kit-3/AGENTS.md`
- `BLACKBOARD.md`
- `src/substrate/api.py` (the public surface — preserve accreted exports)
- `process/planning/ROADMAP-2026-09-29-configuration-externalization.md` (in substrate-ui repo)

## signal contract

### Emits

No runtime signals. This is a pure library function with no side effects.

### Consumes

- `src/substrate/api.py`

### Invariants

- All existing `api.py` exports preserved.
- `substrate_home()` returns a `Path`.
- Unset `SUBSTRATE_HOME` returns `Path.home() / ".substrate"`.
- Set `SUBSTRATE_HOME=/foo` returns `Path("/foo")`.

## artifact contract

### Files created

- none

### Files modified

- `src/substrate/api.py` — adds `substrate_home` function and export.

### Content assertions

- `api.py` contains `def substrate_home() -> Path:`.
- `api.py` contains `"substrate_home"` in `__all__` (if `__all__` exists) or exports it at module level.
- `grep -c 'substrate_home' src/substrate/api.py` >= 2 (definition + export).

### Command exit codes

- `uv run python -m pytest tests/` returns 0 (existing suite unbroken)
- `uv run python -c "from substrate.api import substrate_home; import os; os.environ.pop('SUBSTRATE_HOME', None); assert str(substrate_home()).endswith('.substrate')"` returns 0
- `SUBSTRATE_HOME=/tmp/test-sh uv run python -c "from substrate.api import substrate_home; assert str(substrate_home()) == '/tmp/test-sh'"` returns 0

## done criteria

`substrate_home()` importable from `substrate.api`, returns the env var when set, falls back to `~/.substrate`, and does not break the existing test suite.

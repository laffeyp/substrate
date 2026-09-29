# Sprint 247 — Route kernel paths through `substrate_home()`

```yaml
---
id: 247
status: pending
opened_at: 2026-09-29
phase: config-externalization
pass_kind: functional
---
```

## scope

Replace every `Path.home() / ".substrate"` in the kernel with `substrate_home()` from `substrate.api`. Grep counts 10 sites (the response file's 11th, `adapters/models.py:59`, reads config.toml through `transcript.py`'s function and has no direct `Path.home()` call). Each call site changes its root from a hard-coded home-relative path to the resolver. Behavior is unchanged when `SUBSTRATE_HOME` is unset.

## prerequisites

- sprint 246 (`substrate_home()` exists)

## context_files

- `sdd-kit-3/AGENTS.md`
- `src/substrate/api.py` (the resolver)
- `src/substrate/_daemon.py` — line 61
- `src/substrate/bundles.py` — line 55
- `src/substrate/cli.py` — lines 880, 1590, 1785
- `src/substrate/session_registry.py` — line 90
- `src/substrate/topologies/session/roles.py` — line 32
- `src/substrate/topologies/session/transcript.py` — line 112
- `src/substrate/topologies/bundled.py` — line 79
- `src/substrate/topologies/swebench_solver/bundled.py` — line 33

## signal contract

### Emits

No new signals.

### Consumes

- All files listed in `context_files`.

### Invariants

- `grep -rn 'Path.home().*\.substrate' src/substrate/` returns 0 lines after this sprint (every site converted).
- Existing test suite passes with `SUBSTRATE_HOME` unset (identical paths).
- One new test verifies that setting `SUBSTRATE_HOME` changes the root for at least three distinct subsystems (daemon socket, sessions base, config.toml).

## artifact contract

### Files created

- `tests/test_substrate_home_routing.py` — verifies path routing under `SUBSTRATE_HOME`.

### Files modified

- `src/substrate/_daemon.py`
- `src/substrate/bundles.py`
- `src/substrate/cli.py`
- `src/substrate/session_registry.py`
- `src/substrate/topologies/session/roles.py`
- `src/substrate/topologies/session/transcript.py`
- `src/substrate/topologies/bundled.py`
- `src/substrate/topologies/swebench_solver/bundled.py`

### Content assertions

- `grep -rn "Path.home().*\.substrate" src/substrate/` returns empty.
- `grep -rn "substrate_home()" src/substrate/` returns >= 10 lines.
- `tests/test_substrate_home_routing.py` contains at least 3 test functions.

### Command exit codes

- `uv run python -m pytest tests/` returns 0
- `uv run python -m pytest tests/test_substrate_home_routing.py -v` returns 0

## observation contract

### Expected log substrings

- With `SUBSTRATE_HOME=/tmp/sub-test`: daemon socket path contains `/tmp/sub-test/`, sessions base contains `/tmp/sub-test/sessions`, config path contains `/tmp/sub-test/config.toml`.

### Expected runtime signals

- none (library code, no signal emission)

## done criteria

Zero `Path.home() / ".substrate"` literals remain in `src/substrate/`. Every path that was home-relative now routes through `substrate_home()`. Tests pass both with and without `SUBSTRATE_HOME` set.

## notes

The `adapters/models.py:59` reference reads config.toml via `transcript.py`'s `_read_config_context_tokens`, which reads the path from the same function that `cli.py` uses. Verify at execution time whether `models.py` has its own direct reference or goes through `transcript.py`. The response file lists it; the grep may show it's already covered by the `transcript.py` conversion.

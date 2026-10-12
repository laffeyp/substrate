# Sprint 297 — Errors name the value

```yaml
---
id: 297
status: closed
closed_at: 2026-10-12
phase: 1
pass_kind: functional
asked: 2026-10-12 (Architect: "the error must be better … take a look through all our errors like that … it should name the stuff that's wrong")
research: process/planning/RESEARCH-2026-10-12-error-messages.md
context_files:
  - src/substrate/errors.py
  - src/substrate/kernel/runtime.py
  - src/substrate/kernel/sequencer.py
  - src/substrate/kernel/topology.py
  - src/substrate/topologies/session/session_prompt_producer.py
  - src/substrate/topologies/session/skills.py
  - src/substrate/topologies/coding_flow/__init__.py
  - src/substrate/topologies/tool_loop/__init__.py
  - src/substrate/topologies/tool_loop/delegate.py
  - src/substrate/adapters/models.py
design_canon: design spec draft1 §6.1 (where, summary, what's wrong, constraint, fix) and §6.2 (the detail names place, value and rule)
---
```

## scope

Sixteen sites write `repr(exc)` or `{exc!r}` into a record field or a message; `repr` of an `OSError` drops the path (`FileNotFoundError(2, 'No such file or directory')`), and `repr` drops any chained cause. The tool loop and delegate write `TypeName: str(exc)`, which keeps the path and drops the cause.

After:

1. `substrate.errors.describe_error(exc) -> str`: `TypeName: str(exc)`, the class alone when `str` is empty, then `; caused by <describe_error(cause)>` for an explicit `__cause__`, at most three levels. The one home for turning an exception into text.
2. Every site in the research note's table calls it.
3. `CliResponder` checks before it spawns, in `respond` and `astream`: a working folder that is not a directory raises `FileNotFoundError` reading `CliResponder(<name>): working folder <path> does not exist (the session's workspace)`; a program not found on `PATH` raises `FileNotFoundError` reading `CliResponder(<name>): program <argv0> not found on PATH`. Both keep `filename` set.

Old records keep their `repr` strings. `projections/inspect.py`'s class-preserving normalizer reads both forms.

## signal contract

No event kind or payload field changes; the `error` and `detail` strings change form for new records.

## observation contract

- `tests/test_errors_name_the_value_297.py`: `describe_error` on an `OSError` from a real failed `open` names the path; on a chained error names both; on an empty-message error names the class. A producer that raises `FileNotFoundError` on a real path leaves a `ProducerFailed.error` naming that path. `CliResponder` with a missing working folder, and with a missing program, raises the message above. The inspect normalizer maps a new-form string to `<FileNotFoundError>`.
- The UI repo's `test_old_tilde_workspace_159` still passes.

## checks

- New tests red, then green; kernel suite; ruff, mypy --strict, lint-imports.

## result

- **Built.** `substrate.errors.describe_error`; 16 `repr(exc)` / `{exc!r}` sites (runtime ×8, sequencer ×5, topology, session prompt producer, skills, coding_flow) and 4 `TypeName: str(exc)` sites (tool loop, delegate ×3) now call it. `CliResponder._spawnable` checks the working folder and the program before `respond` and both `astream` spawns, and raises `FileNotFoundError(ENOENT, <who and what>, <path>)`:
  - `FileNotFoundError: [Errno 2] CliResponder(claude:opus-4-5): working folder does not exist (the session's workspace): '/Users/x/gone'`
  - `FileNotFoundError: [Errno 2] CliResponder(ghost): program not found on PATH: 'no-such-cli'`
- **Tests** `tests/test_errors_name_the_value_297.py`, 8: red on the old code (the record's `ProducerFailed.error` read `FileNotFoundError(2, 'No such file or directory')` for a real missing path), green after. Kernel suite 1,522 passed, 13 skipped; ruff, mypy --strict (139 files), lint-imports (2 kept) clean.
- **Not changed.** `encoding.py` keeps `raw=repr(exc)` for an undecodable event kind: it is the raw value of a decode, not a message. Old records keep their `repr` strings.
- **Rubber Duck Pass.** No event kind or field moved; `ProducerFailed.error`, `InputBuildFailed.error`, `RunFinalised.kernel_error`, `SessionWarning.detail` and tool `error` strings now read `TypeName: text; caused by ...`, and `projections/inspect.py` still reduces them to `<TypeName>` for comparison.

# Sprint 348 — A CLI driver's prompt goes on standard input

```yaml
---
id: 348
status: closed
closed_at: 2026-11-12
phase: continuing a session (substrate-ui roadmap 2026-11-12-continue-a-session r1, E4)
pass_kind: functional
depends_on: []
plan: ../substrate-ui/process/planning/2026-11-12-continue-a-session/ROADMAP-2026-11-12-continue-a-session-r1.md
---
```

## scope

`CliResponder` passed the prompt as the command's last argument (`src/substrate/adapters/models.py`, `respond`, `astream`, `arespond`). macOS refuses an argument list past `ARG_MAX` (1,048,576 bytes here; measured 2026-11-12: a 0.9 MB argument starts, a 1.1 MB one fails with errno 7). Every prompt now goes on the CLI's standard input, one path for every size (the Architect, 2026-11-12, on a size split: "Is that a best practice?"); the command line keeps the system text's flag. `claude -p` and `cursor-agent -p` read a piped prompt (measured 2026-11-12), and `codex exec` reads its instructions from stdin when none is on the command line (its `--help`). One verifiable property: a 2 MB prompt reaches the CLI whole; the real `claude` answers a prompt sent this way.

## context_files

- `src/substrate/adapters/models.py` (`CliResponder`: `respond`, `astream`, the `stdin=DEVNULL` notes at lines 589, 625, 687)

## signal contract

### Emits

No new kind. The reply and the harness stream events as today.

### Invariants

- The CLI receives the same text as before: the system text through its flag (or heading the prompt without one), the prompt after.

## artifact contract

### Files modified

- `src/substrate/adapters/models.py`

### Files created

- `tests/test_cli_prompt_on_stdin.py`

### Command exit codes

- `uv run pytest tests/test_cli_prompt_on_stdin.py` returns 0.

## observation contract

A stand-in CLI reports what reached it: a 2 MB prompt arrives whole on stdin through `respond`, `arespond` and `astream`. The installed `claude`, through `CliResponder.astream` with Substrate's `claude` flags (less `--dangerously-skip-permissions`, which a one-word reply does not need), answers a prompt sent on stdin.

## done criteria

A CLI driver can take a prompt of any size.

## notes

The consumer is the existing production path: every CLI-driven session's model call.

## self-review checklist

- [x] Scope is concrete and bounded.
- [x] One file.
- [x] No new kind.
- [x] Artifact contract is gradable.
- [x] Observation contract present.

## close

`CliResponder._call(prompt, system)` returns the command line and the standard-input text; `respond` passes it as `input`, `astream` writes it from a task beside the stdout read, `arespond` through `communicate`. The tests that pinned the old command line pin the new one: `tests/test_system_channel_272.py`, `tests/test_reference.py` (its stub reads stdin), and substrate-ui's `tests/test_driver_profile_120.py`.

- `tests/test_cli_prompt_on_stdin.py`: 4 passed (2 MB on stdin through all three calls; a short prompt the same path). Every kernel test using `CliResponder`, with sprints 346 and 347's: 59 passed, 7 skipped (live-driver runs). substrate-ui `test_driver_profile_120.py`: 7 passed, 5 skipped. ruff clean; `mypy --strict` on `models.py` clean.
- Live: the installed `claude` through `CliResponder.astream`, prompt on stdin, replied "osprey" as asked.
- Mutant (the prompt back on the command line): 3 of 4 fail with `OSError: [Errno 7] Argument list too long`.

The card first described a size threshold, short prompts on the command line and long ones on stdin; it changed to one path before the code closed.

Rubber Duck Pass: no kind changes; a session's `PromptComposed` and its reply events read as before. No observations.

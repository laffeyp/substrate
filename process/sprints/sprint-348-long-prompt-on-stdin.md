# Sprint 348 — A CLI prompt past the argument limit goes on standard input

```yaml
---
id: 348
status: pending
phase: continuing a session (substrate-ui roadmap 2026-11-12-continue-a-session r1, E4)
pass_kind: functional
depends_on: []
plan: ../substrate-ui/process/planning/2026-11-12-continue-a-session/ROADMAP-2026-11-12-continue-a-session-r1.md
---
```

## scope

`CliResponder` passes the prompt as the command's last argument (`src/substrate/adapters/models.py`, `respond`, `astream`). macOS refuses an argument list past `ARG_MAX` (1,048,576 bytes here; measured 2026-11-12: a 0.9 MB argument starts, a 1.1 MB one fails with errno 7). A prompt whose bytes pass a set threshold below that limit is written to the CLI's standard input, which is then closed; a shorter prompt goes as now, with stdin at `/dev/null`. One verifiable property: `claude -p` answers a 2 MB prompt sent this way; a 10-byte prompt runs the same command line as before.

## context_files

- `src/substrate/adapters/models.py` (`CliResponder`: `respond`, `astream`, the `stdin=DEVNULL` notes at lines 589, 625, 687)

## signal contract

### Emits

No new kind. The reply and the harness stream events as today.

### Invariants

- Under the threshold, the argv and the stdin handling are byte-identical to today's.

## artifact contract

### Files modified

- `src/substrate/adapters/models.py`

### Files created

- `tests/test_cli_prompt_on_stdin.py`

### Command exit codes

- `uv run pytest tests/test_cli_prompt_on_stdin.py` returns 0.

## observation contract

`claude -p` (the installed CLI) through `CliResponder` with a 2 MB prompt ending in a question about its first line: the reply answers it. The same with a short prompt: the command line is the old one.

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

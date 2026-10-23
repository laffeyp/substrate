# Sprint 270 — A process as a Producer, a topology from a file

```yaml
---
id: 270
status: done
phase: 1
pass_kind: functional
asked: 2026-10-23 (w2m, on branch w2m; w2m BLACKBOARD Decision 2026-10-23 agent-resolved, "How Rust w2m reaches substrate")
---
```

## why

w2m is rewritten in Rust and keeps substrate as its harness (w2m user Decisions 2026-10-21, 2026-10-22, 2026-10-23).
Today a Producer is a Python callable and a topology is a Python function, so a program in another language reaches a
record only through Python code of its own. Substrate already takes one non-Python input, the guest plane's JSONL
trace that an operator ingests. This card gives the harness plane the same: a process that writes events, and a
topology that names it, with no Python on the program's side.

## scope

1. **`substrate.app.process_producer(command, schemas)`** (`substrate/adapters/process.py`; `app`, not `api`: the import layers put adapters above `api`). A Producer that runs `command` (argv), writes its input as
   one JSON line to the process's standard input and closes it, and reads standard output one line at a time. Each line
   is `{"kind": K, "payload": {...}}`; the payload is decoded strictly into the Struct for K and yielded. A line that
   is not JSON, names a kind `schemas` lacks, or fails its Struct ends the Producer as failed, the line's number and
   the decoder's message in the failure. A non-zero exit fails it with the exit status and the last 20 lines of
   standard error. Cancellation terminates the process (SIGTERM, then SIGKILL after 5 s).
2. **`substrate.app.schemas_from_file(path)`.** Builds frozen msgspec Structs, `forbid_unknown_fields`, one per kind
   (class name = kind), from a JSON file: `{"schema_version": n, "kinds": {K: {field: {"type": "str"|"int"|"float"|
   "bool", "optional": bool, "pattern", "min_length", "ge", "le", "enum": [...]}}}}`. The constraints become msgspec
   `Meta` and `Literal`, so a decoded payload is checked as a hand-written Struct is.
3. **`substrate run --file PATH`.** A topology from TOML: `[[producer]]` (kind, command, schemas, deterministic),
   `[[initial]]` (kind, input), `[[trigger]]` (id, on, starts, policy `once` or `per_event`; the started Producer's
   input is the triggering event's payload), `[termination]` (recipe `all_completed`, `quiescence`, `finalise_on`
   with `kind`, or `threshold_count` with `kind` and `n`), `[baseline]` (strings). Paths resolve against the file's
   directory. Static validation is `TopologyBuilder.build`'s, unchanged.

Nothing in the kernel changes: both are built on the public surface (Producer, `producer_kind`, `TopologyBuilder`).

## checks

- A test process emits two kinds; the record holds both, payloads equal, field for field.
- Each malformed line (not JSON, unknown kind, missing field, extra field, bad enum, pattern miss) fails the Producer
  with its line number; a non-zero exit fails it with the status.
- `substrate replay` reproduces a record from a process Producer.
- A topology file and the same topology built in Python give records with the same application events.
- `scripts/ci_local.sh` exits 0.

## result

- `substrate/adapters/process.py` (`process_producer`, `schemas_from_file`, `ProcessFailed`) and `substrate/adapters/topology_file.py` (`topology_from_file`, `TopologyFileError`), exported from `substrate.app`; `run --file`; `docs/process-producer.md`. Nothing in the kernel changed.
- 16 tests (`tests/test_process_producer.py`), with `/bin/sh` and `printf` as the emitting program: two kinds on the record field for field; seven malformed lines (not JSON, unknown kind, missing field, extra field, bad enum, pattern miss, below `ge`) each failing the Producer at line 2 with the line before kept; a non-zero exit failing it with status 3 and the stderr line; the input reaching the process on standard input; Level-2 replay; a topology file and the same topology in Python giving equal application events; `run --file` exiting 0; three bad files refused before a run.
- An optional field left out is null on the record: w2m's hand-written Structs (no `omit_defaults`) record it the same way, so the test was corrected, not the code.
- `scripts/ci_local.sh`: py3.14 PASS; py3.12 and py3.13 FAIL on two tests that fail on the clean HEAD 3c0542ac too, measured 2026-10-23 in a worktree without this card: `test_the_committed_api_page_is_current` (fails under 3.12 there; the page passes only under 3.14) and `test_realmodel_background_bash_103` (a local Ollama model ran `bash_stop` as a shell command: 2 of 3 runs failed on the clean HEAD). Neither touches this card's files. Conformance 15 passed, 0 failed, on all three.
- w2m's first use (its Sprint 125): a Rust binary's SESSION_INIT and SESSION_COMPLETED on a record, Level-2 replay OK, and its planted missing field failed as `ProducerFailed` naming `accepted_count`.

# Changelog

## 1.1.2 — 2026-10-08

Agent work runs until it finishes or the user stops it, and every stop reaches the work.

- **No wall-clock limits on model work.** Turns, delegated runs, Ollama and CLI model calls have
  no default timeout; Ollama's `num_predict` defaults to the context window and a length stop
  raises instead of truncating silently.
- **bash.** A per-call `timeout_s` (default 120, max 600) with a process-group kill;
  `run_in_background`; a command still running at its deadline moves to the background.
  New tools `bash_output`, `bash_stop`, `bash_tasks`. Output goes to files, not pipes. The model
  hears when a background task ends (`BackgroundTaskEnded`).
- **Stops reach the work.** Interrupts stop CLI drivers (process group), delegated children,
  and walking tools; `glob` and `grep` stop at their caps and at the interrupt. Session delete
  interrupts a running turn first; the session setters no longer wait for a running turn.
- **One session registry.** `SessionRegistry` and its types are exported from `substrate.api`.
- **Vocabulary.** `RunStatus` types `RunResult.status` and `RunGraph.status` (a `StrEnum`;
  members still equal their strings). `TaskStatus` for background tasks; kind-name constants in
  `substrate.topologies.tool_loop.kinds`. `substrate.api` adds `RunStatus`, `daemon_client` and
  the four kind names the CLI renders.
- **Renamed:** `tool_loop.delegate._prefix_context_slice` is public as `prefix_context_slice`.
- **Fixes:** `inspect_record` reports a missing record as an error; the `code_review` judge reads
  the model's verdict; the CLI responder reaps its killed child; tests close their sockets and
  run under an empty `HOME` in CI.

## 1.1.1 — 2026-09-29

`substrate_home()` in `substrate.api`: `$SUBSTRATE_HOME` if set, else `~/.substrate`. Every
kernel path routes through it at call time, not import time.

## 1.1.0 — 2026-09-27

Delegate fan-out (a children list with three caps); `ToolProgress` envelopes stream bash
output; `Park` carries a `detail` naming a model failure's cause; `Runtime.inject_event`;
soft and hard interrupt tiers (`InterruptRequested`); tool bodies run in a worker thread so an
interrupt lands during a long call.

## 1.0.1 — 2026-09-03

Re-release with the PolyForm-Noncommercial-1.0.0 license metadata (PEP 639 SPDX expression).
No code changes.

## 1.0.0 — 2026-07-24

First release: the full runtime. The eight primitives, both persistence
modes, replay Levels 1/2/3(a), the read projections (provenance, diff, narration,
graphs), composition, the 17-check conformance suite, bundled topologies with
committed run records, and the model adapters. Level-3(b) byte-identical
re-execution and Windows persistent-bus support are deferred, with rationale in
`docs/specs/` amendments.

## 0.0.1 — 2026-07-24

Name-claim placeholder on PyPI. No runtime.

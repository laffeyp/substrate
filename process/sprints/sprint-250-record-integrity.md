# Sprint 250 — Record integrity and the Claim Check

```yaml
---
id: 250
status: closed
closed_at: 2026-10-08
opened_at: 2026-10-08
pass_kind: remediation
roadmap: substrate-ui/process/planning/ROADMAP-2026-10-08-lens-audit-remediation.md
ledger_rows: 18
---
```

## why

A 2 MB injected event leaves an unreadable record; injected payloads skip the Claim Check; record.close() overwrites the manifest's run_id and ceiling; readers redeem blobs in five places (findings §7).

## sources

- Hohpe and Woolf, *Enterprise Integration Patterns*, Claim Check.
- Fowler, *Event Sourcing*: state is rebuildable from the log.

## scope (ledger rows)

Each row closes as named; a row the sprint cannot close halts the sprint.

| id | close | finding |
|---|---|---|
| F009 | fix | record.py:186-194,202-215,217-221 — _seal_and_roll() and close() call _write_manifest() with the default replay_ceiling="3a"; only the public write_manifest passes the real ceiling. A 3b run's manifest may revert to "… |
| F010 | fix | record.py:38 — imports private `_fsync_dir` from blobstore (cross-module private). |
| F011 | fix | record.py:381 — recover_open_segment reads with hot.read_bytes() (follows symlinks); every other reader uses O_NOFOLLOW per §17. |
| F012 | fix | framing.py:87-95 — json.loads accepts NaN/Infinity; to_canonical_builtins then raises NonCanonicalValueError (a ValueError) outside the try, and recover() catches only TornFrameError/CRCMismatchError → a hostile/corru… |
| F013 | fix | sidecar.py:137-140 — read_sidecar json.loads each line, no torn-last-line handling (flush is a plain append with no fsync). |
| F015 | fix | CONFIRMED runtime.py:318-324 + record.py:217-221 — the finally writes the manifest with the real replay_ceiling and run_id, then record.close() rewrites it with the defaults ("3a", no extras). Every manifest on disk l… |
| F019 | fix | CONFIRMED sequencer.py:185-186 — _Lifecycle payloads (lifecycle frames AND externally injected events: resume_event, inject_event) skip _maybe_offload. Probe (scratchpad/probe_lifecycle.py): a 100 KB resume_event is w… |
| F020 | fix | CONFIRMED sequencer.py:152-163 + runtime.py:404-415 — _emit advances next_seq BEFORE record.append; when append raises (FrameTooLargeError on a >1 MiB injected event), the seq is consumed, the kernel-error RunFinalise… |
| F029 | fix | graph.py:247-276,294,320-323 — `paused` is set by ANY pause TerminationMatched in the record and never cleared by a later resume. A session record pauses every turn, so run_graph reports a live session mid-turn as PAU… |
| F030 | fix | attach.py:35-50 — _sealed_segments/_hot_segment/_segment_index copied from record.py:226-237 (second copy of the segment naming scheme). |
| F031 | fix | replay.py:119-131 — rebuilds the blob path layout (blobs/sha256/xx/hex) by hand and reads the file directly, beside record.resolve_blob_payload / BlobStore.get, which sprint 095 named "the ONE place a stub is redeemed". |
| F034 | fix | ProducerInstance.status (graph.py:52-56,210,294) is a 5-value string set (completed/failed/cancelled/running/interrupted), no enum; consumers compare strings. |
| F035 | fix | graph.py:125 docstring names field `is_root`; the field is `is_initial`. |
| F036 | fix | `_load(record)` (path-or-iterable) is copied in graph.py:62, inspect.py:83, narrate.py:110, replay.py:81 — four copies, two with resolve_blobs handling and two without. |
| F038 | fix | narrate.py:110-113 (and graph/replay _load) read without resolve_blobs; narrate renders payload FIELDS, so an application event over 16 KiB narrates as `$blob=sha256:…, bytes=…` instead of its fields. Sprint 095's rul… |
| F039 | fix | narrate.py:157,159 "__initial__" and :192 "pause-await-input" literals (Decision.PAUSE_AWAIT_INPUT.value exists); narrate.py:69-78 _FAILURE_KINDS "mirrors cli._FAILURE_KINDS" — a declared second copy. |
| F040 | fix | api.py:16-18 — docstring: "FrameTooLargeError cannot reach a caller (oversized payloads are blob-offloaded before framing)". False: injected/lifecycle payloads are never offloaded (probe_lifecycle.py, 2 MB resume_even… |
| F284 | closes with the finding it resolves | l.18 record.py manifest ceiling: confirmed — `_seal_and_roll` (l.194) and `close` (l.221) call `_write_manifest()` with the "3a" default; only runtime.py:320 passes the real ceiling. Same defect as the measured "manif… |

## checks

- A 2 MB resume_event is offloaded; the record reads back whole (probe becomes a test).
- An append failure consumes no seq.
- A closed run's manifest carries run_id and the real replay ceiling.
- One `_load`; narrate/inspect/replay/graph resolve blobs through it.
- `run_graph` reports a resumed session mid-turn as running.
- NaN in a frame cuts recovery instead of crashing it; a torn sidecar line is skipped.

## result

**The Claim Check covers injected events (F019, F020, F040).**
- The sequencer offloads lifecycle payloads too: a `resume_event`, an `inject_event` and the invalid-emission wrapper each pass `_maybe_offload`.
- A 2 MB resume event is now a blob stub in the record; the record reads back whole and the resolved payload equals the input.
- `_emit` advances the seq only after `record.append` returns, so an append that raises leaves no hole.
- The api docstring's claim that FrameTooLargeError cannot reach a caller is now true, and says why.

**The manifest keeps what the run wrote (F009, F015, F284).** The writer loads the manifest's ceiling and extra fields when it opens a root. Roll and close write them back, where they wrote the defaults (`"3a"`, no run_id) over the runtime's manifest.

**One loader, blobs redeemed in one place (F030, F031, F036, F038).**
- `record.load_envelopes` takes a record root or an iterable of envelopes. graph, inspect, narrate and the testing helpers use it; the four `_load` copies are gone. Narrate and the testing helpers pass `resolve_blobs=True`, so a 20 KiB application event narrates as its fields, not `$blob=sha256:…`.
- replay reads blobs through `BlobStore.get`, not a hand-built `blobs/sha256/xx/hex` path.
- `record/live.py` imports the segment helpers rather than copying them.

**Readers (F011, F012, F013).**
- `recover_open_segment` reads without following a symlink.
- A frame holding NaN is cut by recovery, not raised.
- `read_sidecar` skips a torn last line.

**run_graph (F029, F034, F035).**
- A pause is the run's state only while it is the last event, so a resumed session mid-turn reads INCOMPLETE with its live Producer `running`. Before, it read PAUSED, with that Producer `interrupted`.
- `ProducerStatus` (StrEnum) types the five instance statuses.
- The docstring names `is_initial`.

**One copy of each name (F010, F039).**
- `INITIAL_TRIGGER_ID` and `FAILURE_KINDS` live in constants; narrate and the CLI use them.
- The record package's shared helpers are public names (`fsync_dir`, `sealed_segments`, `hot_segment`, `segment_index`); record.py and live.py no longer import another module's private names.

**Found on the way.** The patch's own `_load` removal cut `ProducerNode`, `TriggerEdge`, `RouteEdge` and `TopologyGraph` out of graph.py. The cut ended at the next `def`, not at the next top-level block. Restored from HEAD before any test ran on it.

**Tests.** `tests/test_record_integrity_250.py`, 7 tests. Each fails on HEAD (b04f8b2a) for its own finding:
- the oversized event and the failed append both end in a seq gap;
- the closed manifest has no `run_id`;
- the mid-turn session reads PAUSED;
- NaN raises NonCanonicalValueError;
- the torn sidecar raises JSONDecodeError;
- narration prints the blob stub.

**Gates.** ruff, format, mypy --strict (138 files) and lint-imports (2 contracts) are clean. The kernel suite's deterministic tests (`-m "not realmodel"`): 1,271 passed, 4 skipped, 43 deselected.

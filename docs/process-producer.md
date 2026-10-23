# A process as a Producer, a topology from a file

Sprint 270. A program in any language can run under substrate and put events on a record with no Python of its own.
Substrate runs it as a Producer, checks every event it writes against declared schemas, and records it as if a
Python Producer had yielded it. The Python surface is in `substrate.app` (`process_producer`, `schemas_from_file`,
`topology_from_file`); the command line is `substrate run --file`.

## The line protocol

The process reads its input as one JSON line on standard input, which is then closed (`{}` when the topology gives
none). It writes events to standard output, one JSON object a line:

    {"kind": "SESSION_INIT", "payload": {"vocab_version": "0.9", "profile": "w2m-session-check", ...}}

`kind` names a schema; `payload` is decoded strictly into that schema's Struct, and the Struct is the event on the
record, its class name the event kind. Blank lines are skipped. Standard error is not read as events; its last 20
lines go into the failure when the process exits non-zero.

The Producer fails, and the record holds `substrate.ProducerFailed` with the reason, when a line is not JSON, names a
kind the schemas lack, or fails its Struct (a missing or extra field, a value outside its constraint), the line's
number in the reason; or when the process exits non-zero, with its status. Events before the bad line stay on the
record; nothing after it is read. A cancelled Producer sends the process SIGTERM, then SIGKILL after 5 s.

## The schema file

    {"schema_version": 1,
     "kinds": {"SESSION_COMPLETED": {
         "outcome": {"type": "str", "enum": ["completed", "completed_with_discrepancies", "aborted"]},
         "discrepancy_count": {"type": "int", "ge": 0},
         "elapsed_seconds": {"type": "float"},
         "note": {"type": "str", "optional": true}}}}

Each field has a `type` (`str`, `int`, `float`, `bool`) or an `enum` (a list of allowed values), and optionally
`pattern` (a regular expression), `min_length`, `ge`, `le` (msgspec `Meta`) and `optional`. An optional field the
process leaves out is null on the record, as a Struct field with a `None` default is. Each Struct is frozen and
forbids unknown fields. `schema_version` is the Producer kind's schema version.

## The topology file

    [baseline]                      # strings, recorded in RunStarted's manifest
    harness = "w2m"

    [[producer]]
    kind = "session_events"
    command = ["../target/release/session_events", "--flag"]
    schemas = "schemas/session.json"
    deterministic = false

    [[initial]]
    kind = "session_events"
    input = {profile = "w2m-session-check"}

    [[trigger]]
    id = "judge-on-run"
    on = "EXECUTION_COMPLETED"
    starts = "judge"
    policy = "per_event"            # or "once"; the started Producer's input is the event's payload

    [termination]
    recipe = "all_completed"        # or "quiescence", "finalise_on" with kind, "threshold_count" with kind and n

A command's first element that contains a slash, and `schemas`, resolve against the file's directory, which is also
each process's working directory. The file and every schema file are read before the run opens; an error in either
exits 64 (`[config]`) with no run. `substrate run --file PATH` takes `--root`, `--tail`, `--strict` and the other
`run` options as `--topology` does.

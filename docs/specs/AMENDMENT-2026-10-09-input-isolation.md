# Amendment 2026-10-09 — Producer input: isolation by copy

Ratified by the Architect on 2026-10-09. Sprint K267 (`process/sprints/sprint-267-producer-input-isolated-by-copy.md`) carries the research and the effects. This amendment replaces two rules; the drafts they appear in stay as written.

## F-PROD-3 (product spec draft 7, line 328), as amended

A Producer input MUST be isolated by construction, not by convention. The runtime records the input's canonical bytes, hashes them (D-5), and hands the Producer a fresh value decoded from those same bytes. The Producer therefore runs with exactly what the record holds, and a change it makes to its input reaches no View, staged event or other Producer. The accepted input types are: None, strings, booleans, numbers within the canonical range, lists and tuples, sets and frozensets, mappings with string keys, frozen msgspec Structs and content-hash blob references. The runtime rejects any other type at instantiation with a typed error (`InputTypeError`), recorded as `substrate.InputBuildFailed`.

## Technical spec §8.3 (draft 5, line 632), as amended: Input isolation

When a Trigger fires, or an initial input starts a Producer:

1. A recursive walk checks every node against the accepted types above and raises `InputTypeError` naming the exact path of any other.
2. The input is canonicalized once. Its canonical bytes are recorded (inline, or as a blob above the threshold) and hashed for `input_sha256`.
3. The Producer receives `msgspec.json.decode` of those bytes. A frozen Struct input decodes back into its own type; anything else arrives in the record's JSON shape (objects as dicts, arrays as lists; whole-number floats as integers, as the canonical form writes them).

Execution resources (connections, handles) belong in topology configuration, closed over by Producer factories.

## What this replaces

Sealing: the walk converted dicts to read-only `MappingProxyType` and lists to tuples and handed the Producer that converted value. The record held one form of each input and the Producer another. Code that serialized, printed or type-checked an input diverged from the record; four bugs followed (sprints 049, 052, 053; K261).

## Why

- The record is an event log; anything computed from it must come out the same live and on replay (event sourcing: Martin Fowler, "Event Sourcing"; Greg Young). A Producer's input is such a computation only if it is the recorded form.
- Isolation by private copy is how message-passing systems (the actor model, Erlang) keep receivers from sharing state. It gives the guarantee immutability was meant to give without a second representation.
- Measured on a 74,728-byte input: sealing cost 0.27 ms; the copy costs one decode, 0.05 ms, of bytes the kernel already builds to hash.

# Sprint 267 — A Producer's input is its own copy of the recorded input

```yaml
---
id: 267
status: closed
opened_at: 2026-10-09
closed_at: 2026-10-09
phase: 1
pass_kind: architecture
roadmap: substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md
decided: 2026-10-09 (Architect ratified isolation by copy over sealing)
---
```

## why

Every Producer input exists in two forms. The kernel records and hashes the input's canonical form (plain JSON objects and arrays). The Producer receives `seal(input)`: dicts turned into read-only `MappingProxyType`, lists into tuples. Code that turns an input into text or JSON, or checks its type, sees the second form while the record holds the first. The kernel itself works around the split: `kernel/sequencer.py:420-425` hashes the pre-seal value because msgspec cannot encode a sealed one.

The split has caused four bugs, each fixed where it surfaced:

| When | Where | What broke |
|---|---|---|
| Sprint 049 | `substrate_tools.py` | `isinstance(…, dict)` false on a sealed mapping |
| Sprint 052 | `substrate_tools.py:134` | `run_topology`'s `inputs` failed the same check; fixed with a top-level `dict(...)` |
| Sprint 053 | `delegate.py:678` | the check failed and the tool "silently dropped every kwarg past `task`"; fixed with a top-level `dict(...)` |
| K261 (2026-10-09) | session prompt builder | tool arguments printed as `mappingproxy({...})`; a real model copied that text into its next tool calls |

The `dict(...)` fixes unwrap one level, so nested values stay sealed. Separately, 110 places in producer code check `hasattr(inp, "get")` or the input's type before reading it: a Producer cannot trust the shape it is handed.

## research

### What the spec requires

- Product spec F-PROD-3 (`docs/specs/product_spec/draft7.md:328`): "Input immutability MUST be enforced by construction, not convention". Inputs are frozen Structs, tuples, frozensets, primitives and blob references; any other type is rejected with a typed error.
- Technical spec §8.3 (`docs/specs/technical_spec/draft5.md:632`): the input is sealed by a recursive walk that accepts those types and raises `InputTypeError` on anything else. Dicts and lists are not on the list.
- `record/sealing.py` converts dicts and lists instead of rejecting them, calling it a "reconciliation" with the ergonomic dict inputs of the design examples, and asks for a spec flow-back ("technical §8.3 should list immutable-sealed dict/list"). The flow-back never landed; the specs still describe a rule the kernel does not implement.

### What the rule is for

Immutability is the means. The goals are:

1. What a Producer runs with equals what the record says it ran with (D-5: `input_sha256` over the recorded input).
2. A Producer cannot change kernel state (views, staged events, another Producer's input) through its input.

### The established design

The record is an event log and views are projections of it. Event sourcing's rule (Martin Fowler, "Event Sourcing", martinfowler.com/eaaDev/EventSourcing.html; Greg Young's CQRS and event-sourcing writing; both practitioner sources) is that state derived from the log is a pure function of the events, so a projection built live equals the same projection rebuilt by replaying the log. Anything that consumes event data — a Producer's input, the model's prompt — must see the events in their recorded form, or live and replay diverge.

Goal 2 is the isolation property of message-passing systems (the actor model; Erlang processes): a receiver gets its own copy of a message, decoded from its serialized form, so no state is shared. Isolation by copy delivers goal 2 without changing the value's types.

### The design

When a Trigger fires (and when an initial input starts a Producer), the kernel already builds the input's canonical bytes to hash it. This sprint:

1. builds the canonical bytes once;
2. hashes those bytes for `input_sha256` and records them (inline or as a blob, as today);
3. decodes the same bytes into a fresh value and hands that to the Producer.

Goal 1 holds by construction: the Producer's input is the recorded bytes, decoded. Goal 2 holds by construction: the value is a private copy, so a Producer that changes it touches nothing else. The validation stays: a value with no canonical form (raw bytes, handles, objects, integers beyond 2⁵³, non-string keys) is still rejected, now as `InputTypeError` from the canonical check, before any Producer starts.

### Measured cost (2026-10-09, one 74,728-byte input, mean of 200)

| Step | Today | After |
|---|---|---|
| `seal()` | 0.27 ms | removed |
| canonical bytes for the hash | already paid | already paid, once |
| decode for the Producer | — | 0.05 ms |

## effects

### First-order (what a Producer receives)

- **Types.** Dicts and lists, not `MappingProxyType` and tuples. Checked: every `isinstance(…, tuple)` in topology code also accepts lists (`delegate.py:347`, `:410`; `parent_context_producer.py:132`; `applications/registry.py:114`; `session_registry.py:1549`). No producer hashes, puts in a set, or compares against a tuple anything taken from its input.
- **Numbers.** Canonical JSON writes whole floats as integers: `2.0` becomes `2`, `-0.0` becomes `0`. The record and every replay already hold these values; only live Producers saw the float. A Producer that checks `isinstance(x, float)` on an input value would change behavior; none was found.
- **Structs and blob references.** No Trigger or initial passes a Struct or a `BlobRef` as input (initials use `None` or dicts; `BlobRef` is built only by the kernel's offload path and replay). A Struct input would arrive as a dict; the card adds a registration check so a builder that returns one is caught.
- **Mutation.** A Producer may now change its own input. Nothing else can observe it.

### Second-order

- **Record and replay.** Unchanged on disk. D-5 becomes stronger: the hash, the recorded input and the Producer's input come from one byte string, not from a pre-seal value and a separately sealed copy.
- **CI records.** The recorded bytes are unchanged, so the committed CI records should not move. Any that do mark a value the old path recorded differently from what it handed the Producer — a finding, not noise.
- **K261's `unseal()`.** Becomes unnecessary and is removed; the prompt builder sees plain values because its input is plain.
- **The two `dict(...)` fixes** (`substrate_tools.py:134`, `delegate.py:678`) become no-ops and are removed.
- **The 110 defensive input checks** become dead weight. They stay working; removing them is follow-up cleanup, not this sprint.
- **Views passed to predicates** (`TriggerContext.views`, `sequencer.py:350-357`) stay read-only. That is a separate guard (a predicate must not change the kernel's own views) and not an input.
- **Public promises.** `docs/api.md:1006-1007` (`InputTypeError`: "immutability is enforced by construction"), `docs/tutorial.md:56` ("frozen=True … keeps Producer inputs immutable") and `docs/adding-a-topology.md:65` ("sealed input") describe sealing; they change to isolation by copy.
- **Tests that pin sealing.** `tests/test_sealing.py` asserts `MappingProxyType` and tuples; it is rewritten to pin isolation (a Producer's change to its input is invisible to the view and to a second Producer) and rejection (bytes, objects, large integers, non-string keys). `tests/test_agency.py` builds `MappingProxyType` fixtures for its own scorer; unaffected.

### Found while measuring: K261 records the whole history every model step

K261 put the session's full turn history into the model step's input, and every input is recorded. Each step re-records everything before it: 300 bytes at step 1, 5,879 bytes at step 11 of a seven-turn run (`TriggerFired.resolved_input`), so the record grows with the square of session length. That is a K261 defect, not an effect of this sprint, and K261 fixes it before it closes: the model step's input carries only what the window keeps, which is bounded by the driver's context.

## scope

- `kernel/sequencer.py` and `kernel/runtime.py`: build canonical bytes once; hash and record them; hand the Producer `msgspec.json.decode(bytes)`.
- `record/sealing.py`: `seal()` retires from the input path; the canonical check is the validation. `unseal()` (K261) is removed.
- `substrate_tools.py:134`, `delegate.py:678`: drop the `dict(...)` fixes.
- Docs: `docs/api.md`, `docs/tutorial.md`, `docs/adding-a-topology.md`.
- Spec amendment: `docs/specs/AMENDMENT-2026-10-09-input-isolation.md` (new file; the drafts stay as written) restating F-PROD-3 and §8.3 as isolation by copy.

## prerequisites

- none. K261 resumes on top of this sprint.

## context_files

- `sdd-kit-2/AGENTS.md`
- `substrate/src/substrate/kernel/sequencer.py`, `kernel/runtime.py`, `record/sealing.py`, `encoding.py`
- `substrate/docs/specs/product_spec/draft7.md` (F-PROD-3), `docs/specs/technical_spec/draft5.md` (§8.3)

## signal contract

### Emits

No new kind. `substrate.TriggerFired` and `substrate.InputBuildFailed` keep their payloads.

### Invariants

- The recorded `resolved_input` / `input_blob` and `input_sha256` are byte-identical to today's for the same input.
- A Producer's input equals `msgspec.json.decode` of the recorded input bytes.
- An input with no canonical form never starts a Producer; it records `InputBuildFailed`.

## artifact contract

### Files modified

- `substrate/src/substrate/kernel/sequencer.py`, `kernel/runtime.py`, `record/sealing.py`
- `substrate/src/substrate/topologies/tool_loop/substrate_tools.py`, `topologies/tool_loop/delegate.py`
- `substrate/docs/api.md`, `docs/tutorial.md`, `docs/adding-a-topology.md`
- `substrate/tests/test_sealing.py` (rewritten for isolation)

### Files created

- `substrate/docs/specs/AMENDMENT-2026-10-09-input-isolation.md`
- `substrate/tests/test_input_isolation_267.py`

### Command exit codes

- `uv run python -m pytest tests/test_input_isolation_267.py` returns 0, and non-zero before the change.
- Kernel suite, ruff, format, mypy --strict, lint-imports return 0; committed CI records unchanged.

## observation contract

### Before running anything: predicted breaks

Written before the suite runs; a failure not on this list is a misunderstanding to explain, not a test to adjust.

- `tests/test_sealing.py`: its `MappingProxyType` and tuple assertions (rewritten in this sprint).
- Any test asserting an input value is a tuple or a float where canonical JSON gives a list or an int. Search before the run: `isinstance(..., tuple)` and `== (` on Producer inputs in tests.
- No CI record should change.

### Driving steps

- The isolation test: a Producer mutates its input; a View and a second Producer started from the same Trigger see the recorded value.
- The equality test: for a session turn with tool calls, every Producer's input equals the decode of its `TriggerFired` input on the record.
- The rejection test: bytes, an object, an integer of 2⁵³ + 1 and a non-string key each record `InputBuildFailed` and start no Producer.
- A live session on the installed Substrate.app runs a tool turn on Ollama and a turn on `claude`.

## done criteria

Every Producer receives a private copy of exactly what the record holds as its input, and no code anywhere needs to know that inputs were ever sealed.

## result

- `kernel/sequencer.py` `_producer_input`: checks the input's types, builds its canonical bytes once, records them (inline or blob) and hashes them, and hands the Producer `msgspec.json.decode` of the same bytes (a frozen Struct decodes to its own type). `kernel/runtime.py` (initial inputs) uses the same path. `record/sealing.py` is deleted; `record/inputs.py` `check_input` keeps the accepted-type rules as validation only. The predicted test run caught why it is needed: `msgspec.to_builtins` turns bytes, datetimes, UUIDs and Decimals into strings without complaint, which would have widened what an input may be.
- Red before: `test_input_isolation_267` failed with the Producer receiving `mappingproxy({'items': ('a', 'b'), ...})`. Green after: plain private copies equal to the record; a Producer's change reaches neither a View nor another Producer; a frozen Struct arrives as its own type; bytes, objects, 2**53+1 and non-string keys still record InputBuildFailed and start nothing. `test_input_check_267` replaces `test_sealing.py`.
- K261's `unseal()` and `_plain()` were removed; K261's tool-turn test now asserts no real prompt contains `mappingproxy`.
- `substrate_tools.py:134` and `delegate.py:678`: comments corrected. The `isinstance(..., Mapping)` checks and `dict(...)` copies were kept, not removed as scoped: both stay correct for plain dicts.
- Docs: the source docstrings (`errors.py` InputTypeError, `protocols.py`, `kernel/composition.py`) changed and `docs/api.md` was regenerated from them; `docs/tutorial.md` and `docs/adding-a-topology.md` edited. `docs/specs/AMENDMENT-2026-10-09-input-isolation.md` restates F-PROD-3 and §8.3.
- Prediction vs result (kernel suite, 1,329 passed, 4 failed): three failures were predicted and are K261's or pre-existing (`grep`, compaction, `background_bash_103`). One was not: the committed `natural_conversation` CI record diverged at seq 39. Cause: `conversation.py:135` writes `{cg}` from its input into the speaker's prompt; sealed, its lists printed as tuples (`('x',)`), unlike the record (`['x']`). The prediction "no CI record moves" was wrong; the card's rule ("a record that moves marks a value handed over in another form") classified it. The record was regenerated.
- Gates: ruff, format, mypy --strict (135 files), lint-imports clean.

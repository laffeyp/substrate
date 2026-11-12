# Substrate refactor: step-by-step plan for each domain

2026-11-09. Turns the code described in `RESEARCH-2026-11-09-substrate-design-and-boundary-r3.md` into the standard implementation that paper ends with. Every step uses a published technique under its published name.

## The procedure

Refactoring is a series of small changes, each of which leaves behaviour the same and the tests passing. Six named techniques organize the work. The rest of the steps are moves from Martin Fowler's catalog.

| Technique | Source | Used here for |
|---|---|---|
| Characterization test | Michael Feathers: a test that documents "your system's actual behavior" | Pinning behaviour before a change where no test does |
| Golden Master (also Approval or Snapshot testing) | Secondary summaries of Feathers | The 18 committed records: capture full output, diff against it |
| Branch by Abstraction | Fowler: "making a large-scale change to a software system in gradual way" | Replacing the builder, the model interface and the record reader |
| Strangler Fig | Fowler: "a gradual approach to legacy modernization" | Moving topologies to the new form one at a time |
| Parallel Change | Fowler: expand, migrate, contract | Changing a signature that has many callers |
| Mikado Method | "a process for surfacing hard-to-see dependencies in a codebase" | Finding the order of moves that untangles the import cycles |

Three rules hold for every step:

- A step changes structure only. A fault found during a step is written down and fixed in its own change.
- Each step runs the tests for the code it touched. The full gate, `scripts/ci_local.sh`, runs at the end of each domain.
- A step that fails to go through is reverted and split into smaller steps. The Mikado Method records what the failure showed had to happen first.

Callers inside this repository change in the same step as the thing they call, so no step leaves a compatibility layer behind. Parallel Change's middle phase lasts only while a signature's callers are being moved within one domain.

Domains are in dependency order: each one needs the ones before it.

## 1. Safety net

| Step | Technique | What changes | Done when |
|---|---|---|---|
| 1.1 | Golden Master | Confirm `test_committed_record_is_current` covers all 18 committed records and compares them byte for byte | The test fails when one payload field in one record is altered by hand |
| 1.2 | Characterization test | Add one test per session path the committed records do not reach: resume, interrupt, change of settings, MCP call, language measurement | Each test passes on today's code and records its event sequence |
| 1.3 | Characterization test | Add tests of the kernel's failure paths that write directly to the record: a View raising, a kernel error, a stuck quiescent run, an at-rest append | Each asserts the exact frames written |
| 1.4 | Extract Function, Replace Inline Code with Function Call | Create `tests/support/` and move the session driver `_turn` (11 copies), scripted responders (at least 10), `_require_model` (13) and `_open` (6) into it | No test file defines those helpers |

## 2. Specifications

The product spec's first principle is that a disagreement between code and spec is resolved in the spec first, and specs change by addition. These amendments are written before the code moves.

| Step | What changes | Done when |
|---|---|---|
| 2.1 | Amendment: a topology is an immutable value built from typed declarations, replacing the definition of a topology as a function of a builder, in the product and design specs | The amendment file exists and names the sentences it replaces |
| 2.2 | Amendment: every name on the record is derived from the code | Same |
| 2.3 | Amendment: there are nine pieces, with the run record counted; the kernel, product and design specs and `docs/README` are corrected | A search for "eight primitives" and "eight words" finds only superseded text |
| 2.4 | Amendment: the typed `Record` read surface returns, reversing the amendment that dropped it | Same as 2.1 |

## 3. The typed pieces

New types are added beside the old ones first, and the old ones go when their last user moves.

| Step | Technique | What changes | Done when |
|---|---|---|---|
| 3.1 | Replace Primitive with Object | `NewType`s for `TriggerId`, `ProducerKind`, `InstanceId`, `ContentHash`, `CallId` | Lifecycle Structs below use them |
| 3.2 | Encapsulate Record | One frozen Struct per lifecycle event, 12 of them, with `omit_defaults` so absent keys stay absent | Each Struct encodes to the same JSON as today's dict for the same fields, by test |
| 3.3 | Replace Primitive with Object | `Body[In, Out]` and `Producer[In, Out]`; `View[T]`; `Predicate[E]`; `Trigger[E, In]`; `Route[E, S]`; `Slot[T]`, in new kernel modules | `mypy --strict` accepts a typed async generator as a `Body` |
| 3.4 | Encapsulate Record, Move Function | `Topology` and `Fragment` as frozen values whose constructors run every static check, including the checks now in the `validate` CLI command | A malformed topology raises at construction, by test |
| 3.5 | Move Function | `Topology.manifest()` produces a `TopologyManifest` Struct; `Runtime._manifest` calls it | `RunStarted` bytes are unchanged for a builder-defined topology |

## 4. The kernel and the Bus

| Step | Technique | What changes | Done when |
|---|---|---|---|
| 4.1 | Replace Inline Code with Function Call | One function builds and appends an envelope; `_emit`, `_view_failure`, `_try_record_kernel_error`, `_fail_stuck_quiescent` call it | One place in the kernel assigns `next_seq` |
| 4.2 | Replace Inline Code with Function Call, Encapsulate Record | Each lifecycle event is constructed from its Struct at its emit site | No dict literal for a lifecycle payload remains in the kernel |
| 4.3 | Move Function | `AppendCycle` is renamed `Bus`, in `bus.py`; `_submit_emission` and `_writer_loop` move into it | `Runtime` holds no admission logic |
| 4.4 | Extract Class | `ProducerSupervisor` takes `_flush_scheduled`, `_producer_task`, `cancel_producer`, budgets; it exposes `live_instances()` | Tests and the session registry call `live_instances()` and no test reads `runtime._st` |
| 4.5 | Move Field, then Inline Class | Each `RunState` field moves to the class that decides it; `RunState` is removed | `runstate.py` is gone |
| 4.6 | Separate Query from Modifier, Move Field | `FiringPolicy.admit` both decides and mutates. `Once`, `PerKey` become frozen declarations; the Bus holds the fired set and seen keys per run. Views become factories in the declaration | One `Topology` value runs twice and fires its judge both times, by test |
| 4.7 | Substitute Algorithm | The three linear scans in the cycle become lookups in the subscription index the specification names, built in the `Topology` constructor | The perf floor test still passes and record output is unchanged |
| 4.8 | Move Function | Locking, recovery and the writer move into `kernel/log/`; `encoding.py` moves into `kernel/`; `append_at_rest` becomes a `Record` method sharing the envelope constructor | Import contract: `kernel` imports nothing outside itself except the standard library, msgspec, rfc8785 and ulid |
| 4.9 | Move Function | `views.py`, the recipes from `policies.py` and `composition.py` move out to `substrate.views`, `.termination`, `.composition` | Import contract: those modules import only the kernel's public names |

## 5. Constructing topologies

This is Branch by Abstraction. `Runtime.run` already accepts any `Callable[[TopologyBuilder], None]`, so that callable is the abstraction, and the rewrite of the ensemble topology showed a `Topology` value can satisfy it through `__call__`.

| Step | Technique | What changes | Done when |
|---|---|---|---|
| 5.1 | Branch by Abstraction | `Topology.__call__(b)` translates the value into builder calls | The ensemble rewrite passes, as it does in `evidence-topology-value/` |
| 5.2 | Strangler Fig | Convert topologies one at a time, smallest first: the reference topologies, then `debate`, `adversarial_pair`, `pair_coding`, `prisoners_dilemma`, `game_of_life`, `intel_asymmetry`, `natural_conversation`, `recursive_decomposition`, `code_review`, `code_evolution`, `best_of_n`, `coding_flow`, `swebench_solver`, `tool_loop`, `session` | Each conversion: its record regenerates, and its events match the old record once old names are mapped to derived ones |
| 5.3 | Inline Function | Within each conversion, a `*_factory` that only returns `lambda: body` is inlined; a Producer that carries configuration becomes a frozen callable | `grep "return lambda: _"` finds nothing in that topology |
| 5.4 | Replace Primitive with Object | Within each conversion, input dicts become typed Struct inputs and `hasattr(inp, "get")` goes | Count of that idiom falls to zero at the end of the domain |
| 5.5 | Parallel Change, contract phase | `Runtime` takes `Topology` directly and builds its index from it; `__call__`, `TopologyBuilder` and `Registration` are removed | Neither name exists in `src/` |
| 5.6 | Remove Dead Code | `_RecordingBuilder` test doubles and `assert callable(topo)` give way to assertions on the value | Neither appears in `tests/` |

## 6. Names and references

Most of this happens inside the Strangler Fig conversions. These steps finish it.

| Step | Technique | What changes | Done when |
|---|---|---|---|
| 6.1 | Replace Magic Literal | A literal that remains in two layers, such as `/exit`, moves to one leaf module below both | Its pinning test is removed |
| 6.2 | Remove Dead Code | `session/vocabulary.py`'s kind, trigger-id and producer-kind constants and their frozensets | The module holds only enums, payload parts and prompt text |
| 6.3 | Remove Dead Code | `test_kind_constants_match_structs_107`, `test_trigger_names_264`, `test_session_vocabulary_constants`, `scripts/check_status_literals.sh` | They are gone and the gate passes |
| 6.4 | Replace Primitive with Object | Where a value is validated into a `StrEnum` and then stored raw, store the enum: `applications/registry.py`, `SessionManifest.workspace_shape` | `mypy --strict` passes with the enum type on the field |

## 7. Types at the boundaries

| Step | Technique | What changes | Done when |
|---|---|---|---|
| 7.1 | Parallel Change, Introduce Parameter Object | `Tool` takes one Struct class for its arguments. Expand: accept a Struct or a list. Migrate each tool. Contract: remove the list path, `_named_to_positional`, `x-args-passthrough`, `_TOOL_SCHEMAS` | Every tool's schema comes from `msgspec.json.schema` |
| 7.2 | Replace Type Code with Subclasses | Tagged tuples become Struct unions, read with `match`: `parse_tool_call`, `_decide`, `_resolve`; `SafeCanonical`; `ReplayResult` | No function returns a tuple whose first element is a tag |
| 7.3 | Replace Error Code with Exception | A tool that both returns `{"ok": False}` and raises settles on raising | Tools have one failure path |
| 7.4 | Encapsulate Record | `ErrorInfo` Struct, with `reason` from a closed enum, built where an exception is caught | `_error_sentinel` and `classify_reason_string` are removed |
| 7.5 | Encapsulate Record | The stderr JSON events become declared events on the record or entries in the sidecar | No `_emit_*_event` writes JSON to stderr |
| 7.6 | Encapsulate Record | `NamedTuple` records become frozen Structs or frozen dataclasses by the paper's rule | No `NamedTuple` in `src/` |

## 8. The model interface

Branch by Abstraction again: the new `Responder` is the abstraction, and each adapter is a supplier.

| Step | Technique | What changes | Done when |
|---|---|---|---|
| 8.1 | Branch by Abstraction | `Responder.respond(request) -> Reply`, `StreamingResponder`, `ToolCallingResponder` as `runtime_checkable` Protocols ([PEP 544](https://peps.python.org/pep-0544/)) | The Protocols exist with one adapter behind them |
| 8.2 | Replace Conditional with Polymorphism | Move `DeterministicResponder`, `OllamaResponder`, `CliResponder` and the Decorators onto them. `call_responder`'s branches become each adapter's own `respond` | `call_responder` and `call_responder_metered` are removed |
| 8.3 | Parameterize Function | `respond`, `arespond`, `respond_metered`, `arespond_metered` collapse into one method | Each adapter has one `respond` |
| 8.4 | Replace Conditional with Polymorphism | `getattr(responder, ...)` probes and `type(responder).__name__` become `isinstance` on a Protocol | A search for those probes finds none |
| 8.5 | Substitute Algorithm | CI stand-ins inside `instruments/` and `tool_loop`'s modes move behind `ScriptedResponder`; `walkthrough: bool` goes (Remove Flag Argument) | Production bodies have one path |

## 9. Session

| Step | Technique | What changes | Done when |
|---|---|---|---|
| 9.1 | Introduce Parameter Object | `SessionConfig` replaces `session_topology`'s 31 parameters; `start_build`'s 13 become fields of it (Preserve Whole Object) | `session_topology` and `start_build` each take one `SessionConfig` |
| 9.2 | Extract Function | Each predicate conjunction becomes a named function | No multi-line lambda among the Triggers |
| 9.3 | Combine Functions into Transform | Define `TurnState`, `Phase` and a pure `advance(state, event)`, as a View beside the existing ones | A table test covers every transition; the View agrees with the old predicates on all session records, by test |
| 9.4 | Substitute Algorithm | Each Trigger's predicate reads the phase | No Trigger reads `user_turns` or `returned_turns` directly |
| 9.5 | Extract Function | The four copies of the model-start input become one function | One definition remains |
| 9.6 | Extract Class, Move Function | `session_registry.py` becomes `session/service.py`, split into manifest store, name index and turn dispatcher | Manifest storage, the name index and turn dispatch are separate classes |
| 9.7 | Combine Functions into Class | `turn_replies`, `slice_kind_matches` and `turn_pairings` become `SessionRecord.turns()` | One definition of a turn |
| 9.8 | Move Function | `context_windows`, `mcp_channel` and `agency` move to `models/`, `tools/` and `assay/` | Each sits with its peers |

## 10. Ambient state

| Step | Technique | What changes | Done when |
|---|---|---|---|
| 10.1 | Replace Query with Parameter, Introduce Parameter Object | `ToolContext` passed to `Tool.run`, replacing `_BASH_PROGRESS_CTX`, `_TOOL_CANCEL_HOOKS` and tools' use of `_CURRENT_RUNTIME` | Those ContextVars are removed |
| 10.2 | Encapsulate Variable, then Move Field | The two `TABLE`s, `_CHANNELS` and `_context_cache` are encapsulated, then moved to the session service | No module-level mutable table remains in `session` or `tools` |
| 10.3 | Move Field | Rate-limit semaphores move onto the limiter; `_reset_semaphores_for_tests` goes | That function is removed |
| 10.4 | Replace Query with Parameter | `_ACTIVE_RUNTIMES_BY_RECORD_ROOT` lookups use the handle the session service holds; `_REGISTRY` becomes a value passed to the CLI | Both are removed |

## 11. Composition

| Step | Technique | What changes | Done when |
|---|---|---|---|
| 11.1 | Change Function Declaration | `best_of_n_correction(b, ...)` returns a `Fragment` | It takes no builder |
| 11.2 | Remove Flag Argument, Parameterize Function | `seed_on`, `draft_input_extra`, the `termination` argument go; callers connect Fragments | Those parameters are gone |
| 11.3 | Replace Inline Code with Function Call | `coding_flow` and `fanout_review` use the Fragment; `compose_run` returns one | No topology retypes the four-Producer loop |
| 11.4 | Remove Dead Code | The retired 270-line topology in `assemble.py` and placeholder terminations | They are gone |
| 11.5 | Extract Class | `Join` in `substrate.joins`; the fan-in predicates in `best_of_n`, `coding_flow`, `code_review`, `assemble` use it (Replace Inline Code with Function Call) | One definition of a fan-in |
| 11.6 | Move Field | The export map becomes a field of an `Embedded` declaration, keyed by Struct class; `__substrate_export_map__` goes | That attribute is gone |
| 11.7 | Decorator pattern (Gamma et al.) | `on_failure` wraps a body; each `try`/`except` in a Producer body that swallows exceptions moves to it | Per-body broad excepts in topologies are gone |

## 12. The read side

| Step | Technique | What changes | Done when |
|---|---|---|---|
| 12.1 | Combine Functions into Class | `Record` holds the path, parsed frames and index; the nine free functions in `record.py` and the `projections/` queries become methods | `load_envelopes` and `record: Any` are gone |
| 12.2 | Split Phase | The reader separates from the writer: reader becomes `substrate.record`, writer stays in `kernel/log/` | `record.py` holds no writer |
| 12.3 | Replace Primitive with Object | `Record.events()` yields typed Events with lifecycle payloads as Structs | Projections hold no `isinstance(ref, dict)` |
| 12.4 | Remove Flag Argument | Blobs resolve by default and lazily; integrity readers call a separate raw method | `resolve_blobs` is gone |
| 12.5 | Encapsulate Record | `Record.topology()` decodes the same `TopologyManifest` the writer encodes; `TopologyGraph` becomes that type | Writer and reader share one Struct |
| 12.6 | Remove Dead Code | The output caps and comments written for a stub payload reaching Triggers are reviewed against what they do today | Each cap that stays has a stated reason |

## 13. Module organization

| Step | Technique | What changes | Done when |
|---|---|---|---|
| 13.1 | Mikado Method | Draw the graph of what must move before the `session`, `tool_loop`, `session_registry`, `runs` cycle can break | The graph is written down with its leaves first |
| 13.2 | Move Function | Tool identity into `tools/`; `delegate` into `session/`; `RunSpec` into `session/` | `tools` imports nothing from `session` |
| 13.3 | Replace Query with Parameter | The session service takes end-of-session callbacks; it no longer imports `runs.hold` or `tool_loop.background` | Those local imports are gone |
| 13.4 | Move Function | Non-topologies leave `topologies/`, and records-only directories move to test data | `topologies/` holds packages of topologies and `_shared/` |
| 13.5 | Move Function | Root modules move to the layer that uses them: `bundles`, `naming`, `home`, `templates` to `session/`; `interpreter`, `_daemon` to `cli/` | The package root holds only `__init__`, `__main__`, and the listed standard modules and packages |
| 13.6 | Remove Middle Man | `api.py` and `app.py` go. `substrate/__init__.py` exports the nine pieces, `Topology` and `Runtime`; callers import named public modules | Neither file exists |
| 13.7 | Move Function, Extract Function | `cli.py` becomes `cli/` with one module per command group | No CLI module exceeds one command group |
| 13.8 | Replace Conditional with Polymorphism | `_slash_route`'s `if` chain becomes a table of command objects | The chain is gone |
| 13.9 | Move Function | Function-local imports move to module level as each cycle goes | Count of function-local imports used to break a cycle is zero; the import contract extends inside `session`, `tools` and `topologies` |
| 13.10 | Move Function | Tests move to mirror the package and take behaviour names | No test file name ends in a sprint number |

## 14. Code style

Last, because earlier domains delete most of what it would touch.

| Step | Technique | What changes | Done when |
|---|---|---|---|
| 14.1 | Inline Variable | Aliases such as `_TRIGGER_FIRED = TRIGGER_FIRED` and `import os as _os` | A search finds none |
| 14.2 | Remove Dead Code | In-repo compatibility: `_record_has_envelopes`, `reference/_models.py`, `_ = repro_k`, `has_session_prompt` | They are gone |
| 14.3 | Substitute Algorithm | Tests asserting on source text become assertions on behaviour, or move to the import contract | No test reads a source file except the import-contract tests |
| 14.4 | No catalog entry; plain deletion | Sprint, ticket, review and `§` references are removed from comments and docstrings; a requirement stays named in words where a line implements it | A search for sprint and ticket numbers in `src/` finds none |

## Sources

Fowler, *Refactoring*, online catalog: [refactoring.com/catalog](https://refactoring.com/catalog/); every step name above that is not listed below comes from it, checked against that page. [Strangler Fig](https://martinfowler.com/bliki/StranglerFigApplication.html), [Branch by Abstraction](https://martinfowler.com/bliki/BranchByAbstraction.html), [Parallel Change](https://martinfowler.com/bliki/ParallelChange.html): Fowler's site. [Characterization testing](https://michaelfeathers.silvrback.com/characterization-testing): Feathers's own article. [Mikado Method](https://mikadomethod.info/): the authors' site, which gives the definition quoted and leaves the steps to the book. Golden Master: known here from [a secondary summary of Feathers](https://understandlegacycode.com/blog/key-points-of-working-effectively-with-legacy-code/); the book itself was not read. Decorator: Gamma et al., *Design Patterns*, cited from general knowledge of the book.

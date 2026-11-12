# The design of the Substrate code, measured against the design of its ideas

Second version, 2026-11-09. Replaces `RESEARCH-2026-11-09-substrate-design-and-boundary.md`, now in `superseded/` in this folder. `RESEARCH-2026-11-09-boundary-and-runbook-prep.md` stands unchanged.

Subject: the architecture, design patterns, code patterns and code style of the `substrate` package.

## The finding

The specifications define Substrate as a small set of named things. Each has a shape, invariants and a place in a six-step append cycle. The package holds types for four of those things. The rest exist as method calls, dictionaries, strings and closures, and a reader has to reconstruct them from their uses.

One decision produces most of the distance between the ideas and the code: **a topology is a procedure that mutates a builder, when the model describes a value.** Because a topology is a procedure, a Trigger cannot be held, a Producer's input cannot be typed, an edge can only be a string, two topologies cannot be composed without colliding, and the only way to ask a topology what it contains is to run it or to hand it a fake builder. The code then spends its effort compensating: 685 lines of string constants, tests that keep those strings equal to class names, 111 repetitions of `inp.get(...) if hasattr(inp, "get")`, and two test doubles of `TopologyBuilder`.

The better pattern is an immutable, validated, exported `Topology` value built from typed declarations. To check that it works, the ensemble topology that ships with Substrate was rewritten in this design, in a throwaway copy made for this paper. In that topology several models answer one question and a judge picks the best answer once three are in. The rewrite passes `mypy --strict`, turns five kinds of wiring mistake into type errors, runs on the existing `Runtime` without a kernel change, and produces the same events as the original. The part titled "How a topology is constructed" gives the method and its limits.

The rest of the paper takes one software-engineering concept at a time: the concept, the general pattern in this code, the instances, then whether a better pattern exists and which one to use. It ends with the standard implementation those answers add up to.

## Basis

Read in full: all 159 Python modules in `src/substrate` (39,769 lines), all 240 test files, all 39 scripts, the current specifications with their amendments, the 15 superseded spec drafts, `substrate_v14_kernel.py`, `proof/substrate_proof.py`, and the documents under `docs/`. Not read: `process/`, which holds 10 GB of run records and 35 MB of archive, apart from the parts of `BLACKBOARD.md` and `WORKING_AGREEMENT.md` cited here.

Counts come from the working tree on 2026-11-09. External sources are of three kinds and are labelled where used. Papers and first-party language references are primary. Framework documentation is vendor documentation: reliable for what the API is, and silent on whether the design is good. John Ousterhout's *A Philosophy of Software Design* was not read; its terms are taken from its [author page](https://web.stanford.edu/~ouster/cgi-bin/book.php), a [chapter-by-chapter reader's notes](https://dev.to/danlebrero/book-notes-a-philosophy-of-software-design-cna), and his [published exchange with Robert Martin](https://github.com/johnousterhout/aposd-vs-clean-code).

## Correspondence between the model and the code

**The concept.** In domain-driven design, the ubiquitous language is a rigorous, model-based vocabulary that the code itself uses ([Fowler's summary of Evans](https://martinfowler.com/bliki/UbiquitousLanguage.html)). The test is mechanical: take a word from the model and find the thing in the code that carries that name and has that shape.

**The pattern here.** The vocabulary is enforced in prose, log fields and CLI output. It is largely absent from the type system.

| Spec word | Shape in the specifications | Where it is in the code | Status |
|---|---|---|---|
| Producer | typed input to async stream of typed events | `protocols.Producer`, `__call__(input: Any) -> AsyncIterable[Event]` | Exists. Input is `Any`; declares `Event` where bodies yield payload Structs |
| Event | typed, sequenced record | `types.Event` | Exists. Readers receive dicts instead |
| Bus | admission queue, log, single writer | No class. `RunState.inbox`, `credits`, `control`, `next_seq`, `in_cycle`, plus `RecordWriter`, `AppendCycle`, `Runtime._submit_emission` | Absent as a thing |
| View | incremental projection; the design spec writes `View[T]` | `protocols.View`, `value() -> Any` | Exists, untyped |
| Predicate | cheap gate with a taxonomy of five forms; the design spec lists a library and `AnyOf`/`AllOf`/`Not` | `Callable[[TriggerContext], bool]`, a lambda at each site | No name, no library |
| Trigger | `(predicate, producer_factory, firing_policy, input_builder)` | `TriggerReg` in `kernel/topology.py`, unexported | Named for registration |
| Route | `(source_predicate, target_input_slot, transform)` | `RouteReg`, same file, unexported | Named for registration |
| TerminationPolicy | callback with recipes | `kernel/policies.TerminationPolicy` | Exists |
| Topology | "the arrangement" | `Callable[[TopologyBuilder], None]`, named as an alias only in `assay/suite.py` | A function signature |
| Run record | "the artifact the whole product is organized around" | `Iterator[dict[str, Any]]` | A path and a dict stream |

The specification's own executable statement of the design reads the opposite way. `docs/specs/kernel_spec/substrate_v14_kernel.py` is 248 lines including its checks. It has `@dataclass class Trigger`, `@dataclass class Route`, and `class Kernel` whose `_cycle` method is the six numbered steps. A reader finds all of them by name. The production package holds the same ideas across `kernel/`, `record/`, `constants.py` and `types.py`.

This is why following references in an editor explains nothing. Following `b.trigger` lands on a method that appends a `TriggerReg` to a list. Following `"adjudicator"` goes nowhere, because it is a string. `ctx.views["candidates"]` is a dictionary lookup that returns `Any`. The connections that make up a topology live in string equality, and editors do not navigate string equality.

The documents disagree on how many primitives there are. The kernel and product specs say eight, with Event in and Topology out. The design spec says eight, with Topology in and Event out. The README says "nine fundamental ideas" and the tutorial "nine pieces", counting the run record. `docs/README` says eight. `docs/cradle-x-substrate` holds a proposal that says nine and a paper of the same date that says eight. `docs/design/ui-design-handoff.md` says "exactly eight words" and lists nine. When the set has no representation in code, nothing forces one answer.

The generated API reference shows the same gap. Its "Primitives & protocols" group holds `Producer`, `ProducerFactory`, `Responder` (whose docstring says "NOT a kernel primitive"), `View`, five standard views, the firing policies, the cooldowns and `TerminationPolicy`. It has no entry for Bus, Predicate, Trigger or Route.

Authors already expect the missing names. `test_fewer_producers_263` annotates a return as `api.Registration`, and `test_run_suite_with_salvage` annotates one as `api.Topology`. Neither name exists on `api`. The annotations survive only because `from __future__ import annotations` never resolves them.

**Is there a better pattern?** Yes, and it needs no invention: one exported class per primitive, carrying the specification's word. Bus becomes a class that owns admission, the append cycle and the log. Trigger and Route become public declarations. Predicate becomes a named generic Protocol with the combinators the design spec already listed. The count is nine: Producer, Event, Bus, View, Predicate, Trigger, Route, TerminationPolicy and the run record, as the README has it. The Bus is one of them. Topology is a named value made from the nine. The kernel spec, product spec, design spec and `docs/README` say eight; they are marked here to be corrected later and have not been changed.

## How a topology is constructed

**The concept.** The Builder pattern separates the construction of a complex object from its representation, and the last step returns the product ([summary](https://en.wikipedia.org/wiki/Builder_pattern)). The product is the point. Three other graph-building systems show the shape. They are cited as examples of the pattern only; none is proposed for use, and the recommended design needs nothing beyond Python and msgspec, which Substrate already uses. Kafka Streams: `StreamsBuilder.build()` "Returns the Topology that represents the specified processing logic" ([vendor documentation](https://kafka.apache.org/39/javadoc/org/apache/kafka/streams/StreamsBuilder.html)). LangGraph requires the same step: "You must compile the graph before you invoke or stream it," and "Compilation checks the graph structure" ([vendor documentation](https://docs.langchain.com/oss/python/langgraph/graph-api)). Akka Streams describes its built graphs as "immutable, thread-safe, and freely shareable" ([vendor documentation](https://doc.akka.io/libraries/akka-core/current/stream/stream-graphs.html)).

**The pattern here.** A topology author writes a function that returns a function that calls methods on a builder it was handed. The ensemble topology, trimmed:

```python
def ensemble_topology(question, *, members, adjudicator, quorum=3, ...) -> Callable[[api.TopologyBuilder], None]:
    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind("adjudicator", schemas=[Verdict], schema_version=1,
                        factory=_adjudicator_factory(question, adjudicator),
                        deterministic=deterministic)
        b.view("candidates", api.KindBuffer("Candidate"))
        b.trigger(
            "adjudicate",
            subscription=api.Subscription(kinds=frozenset({"Candidate"})),
            predicate=lambda ctx: len(ctx.views["candidates"].value()) >= quorum,
            starts="adjudicator",
            input_builder=lambda ctx: {"candidates": list(ctx.views["candidates"].value())},
            policy=api.Once(),
        )
    return topo
```

The shape is a Builder with the useful half removed. `TopologyBuilder.build()` exists and returns a `Registration`, so a product does exist. It fails the role of a product in five ways.

The author never sees it. `Runtime` calls `builder = TopologyBuilder(); topology(builder); reg = builder.build()` internally, and `api` does not export `Registration`, `TriggerReg`, `RouteReg` or `ProducerKindReg`.

It is mutable. `Registration` is a plain `@dataclass` of dicts and lists. The docstring on `build()` says "Freeze and statically validate"; the method runs two name checks and returns the same mutable object.

Its validation is in the wrong layer. The check for a subscription naming a kind nobody emits, and the check for a missing termination policy, live in the `validate` command in `cli.py`. A run started through `Runtime` does not get them. A rule about whether a topology is well formed belongs to the constructor of a topology.

Every builder method returns `None`, across 268 call sites in 34 builder functions. No Trigger or Producer can be held, passed, compared or tested. Connections are therefore strings by necessity.

Nothing can ask a topology what it contains. The repo's workarounds are the evidence: two separate `_RecordingBuilder` test doubles, the first documented as "Used to inspect what a topology declares without wiring the real substrate runtime", the second of which reads a policy's display name (`"GradeResult" in b.termination_str`); `assert callable(topo)` as the assertion on built topologies in at least four tests; `b._reg.producer_kinds` reached in three files. In `assay/preregistration.py` the docstring states that arm parameters "live in Arm.build's closure and cannot be extracted reflectively", so a parallel `params_by_arm` restates them, and a review later found that the preregistration fingerprint hashed only each arm's name and role, so a changed parameter passed unnoticed.

The project's stated direction needs the value. The kernel spec foresees a "typed Topology specification" emitted as events and `AddTrigger`-style self-modification. `docs/design/substrate-as-a-tool.md` translates a spec dict into builder calls, in code kept outside this package. The cockpit design has agents declaring topologies, the proposal itself being an event, and spans of real runs promoted to reusable topologies. A callable cannot be proposed, recorded, diffed or promoted.

The value already exists on the read side. `projections/graph.py` defines frozen `ProducerNode`, `TriggerEdge`, `RouteEdge` and `TopologyGraph`, and tests read them as `by_kind["judge"].is_initial`, `adj.starts == "judge"`, `adj.on == ("CritiquePosted",)`. They are reconstructed from the `RunStarted` manifest after a run, and that manifest is itself built as nested dicts in `Runtime._manifest` with no type shared between writer and reader. The topology value exists at the end of the pipeline where it is least useful.

The origin is in the design spec. Its alternatives section compared decorators against builder methods, and rejected decorators for import-order problems. It compared the builder against incremental `Runtime.add_producer`. A first-class topology value never appeared on the list. "Topologies are functions of the builder; that's the contract," and the product spec made it a requirement: "A topology is a factory function receiving a `TopologyBuilder`."

**Is there a better pattern?** Seven candidates, weighed against what Substrate topologies actually do: they have cycles (judge back to drafter), predicates and input mappings on every edge, and member counts known only at construction.

| Candidate | What it fixes | What it costs | Verdict |
|---|---|---|---|
| Today's procedure over a builder | Nothing further | Everything above | Replace |
| Builder that returns a public frozen value, with handles returned from each call (the Kafka and Akka shape) | Product held; references become objects | Keeps a mutable object around for a job Python keyword arguments already do | Workable; second choice |
| Frozen value constructed directly from typed declarations | Product held, typed edges, validation in the constructor, value equality, composition | Conditional parts are written as ordinary list-building before the constructor call | **Recommended** |
| Decorators on a local object (`@t.producer`, `@t.trigger`) | Reads well for small fixed topologies; avoids the import-order objection the spec raised, which applied to global decorators | Still mutation; a Trigger has two callables, so one decorator picks one awkwardly; loops over N members read badly | Optional sugar over the value, at most |
| Class-body declaration using `__set_name__` | Removes name strings: the [Python reference](https://docs.python.org/3/reference/datamodel.html) guarantees the hook is "called at the time the owning class" is created | A class body is fixed at definition, and the ensemble topology has a member count known only at call time; 31-parameter parametrization has nowhere to go | Rejected as the primary form |
| Pipe or fluent operators | Terse for straight pipelines | An operator has two operands, and an edge here has a predicate, an input mapping and a firing policy; cycles do not fit a pipeline | Rejected |
| Data-only topology (YAML or JSON) | Fully serializable | Kernel non-goal ("Topology is host-language code"); the kernel spec keeps Predicates as host-language callables, and the product spec's prototype measured that as affordable | Rejected; the value's structure serializes anyway |

A direct constructor beats the fixed-up Builder for a language reason. Builder exists largely because of languages without keyword arguments and immutable record syntax. Python has both, and a local list handles the conditional case.

The recommended form, for the wiring shown above:

```python
def ensemble(question, *, members, judge, quorum=3) -> Topology:
    ms = tuple(member(n, question, r, True) for n, r in members.items())
    adj = adjudicator(question, judge, True)              # Producer[Adjudicate, Verdict]
    candidates = kind_buffer("candidates", Candidate)     # View[tuple[Candidate, ...]]
    return Topology(
        producers=(*ms, adj),
        views=(candidates,),
        triggers=(
            Trigger("adjudicate", on=Candidate, start=adj,
                    when=lambda c: len(c[candidates]) >= quorum,
                    input=lambda c: Adjudicate(c[candidates]),
                    policy=api.Once()),
        ),
        initial=tuple(Initial(m, None) for m in ms),
        termination=api.any_of(api.cancel_all_others(completed(adj)), api.all_completed()),
    )
```

`Trigger[E, In]` ties three things together in the type system: the event it fires on, the input its mapping returns, and the input the started Producer accepts. Cycles cost nothing, because Producers do not refer to Triggers. Only Triggers refer to Producers.

**The test.** Whether this design can carry a real topology is a question the code can answer, so the ensemble topology was rewritten in it, in a throwaway copy outside the package. The original ships in `substrate.reference`: several model Producers answer one question, and once three answers are in, a judge Producer picks one. The rewrite is 166 lines of scratch code: 111 for the declaration types and the code that connects them to today's builder, 55 for the topology itself. Nothing in `src/` changed. The files are kept in `evidence-topology-value/` in this folder. `Topology` defines `__call__(self, b)`, which translates the value into calls on today's `TopologyBuilder`, so `Runtime.run(value)` accepts it unchanged.

- `mypy --strict` (2.1.0) passes on the declaration types and on the rewritten topology. Two `type: ignore` comments remain, both in the code that connects to today's builder: one for a dynamically built `tuple[of, ...]`, one because the kernel's current `Producer` Protocol rejects a typed body.
- Five deliberate wiring errors are rejected statically: an input mapping returning the wrong type for the started Producer; a predicate reading a misspelled event field (mypy suggests the right one); a View value used as the wrong type; a body yielding a kind its Producer does not declare; a Trigger starting a Producer with a different input type. A Producer emitting two kinds infers `Producer[None, A | B]`.
- On the real `Runtime` with deterministic responders, the original and the rewrite each finalise with 27 events. Excluding `t` and `crc`, and normalizing instance ULIDs (which differ on every run), non-`RunStarted` events show zero differences. `RunStarted` differs only in `fingerprint.qualname` for the six Producers, which records the name of the callable.
- The constructor refuses a Trigger that starts an undeclared Producer before any run exists, and assignment to the value raises `FrozenInstanceError`.

Limits of the test. It covers the ensemble topology alone, without its slow-member option; `session_topology` was not converted. The rewrite decodes on each predicate call. `msgspec.convert` measured 0.08 µs for one event, and 0.47, 3.6 and 31.5 µs for a tuple of 1, 100 and 1,000 items, against a 100 µs Predicate budget. Per-call decoding of a long buffer is therefore the wrong implementation, and a typed View must hold decoded Structs, decoded once per event.

The test also corrects a comment copied across the repo. The ensemble topology's source explains `_Factory = Callable[[], Any]` by saying "an async-generator function's static type does not structurally match the Producer Protocol". The test's `Body[In, Out]` Protocol accepts async generators under `--strict`. The current Protocol fails because it declares `AsyncIterable[Event]` while bodies yield payload Structs, and because its parameter can be passed by keyword, so a body whose parameter is called `inp` does not match. The escape to `Any`, redeclared in 27 modules, follows from how the Protocol is written and from no limit of mypy.

## Names and references

**The concept.** Primitive obsession is using a string or number where the domain has a concept. The specific form here is reference by identifier: one thing points at another by repeating its name.

**The pattern here.** Every connection in a topology is a string that must equal another string. `api.Subscription(kinds=frozenset({"Candidate"}))` appears 67 times beside `class Candidate`. `starts="adjudicator"` must equal a `producer_kind` argument. `ctx.views["candidates"]` (43 sites) must equal a `b.view` argument, and `staged["failure"]` must equal a Route's slot.

The project saw the cost and built management for it. `session/vocabulary.py` is 685 lines, with `SESSION_STARTED = "SessionStarted"` beside `class SessionStarted` in another file, 21 trigger-id constants and 12 producer-kind constants. Adding one event kind means a constant, a frozenset entry, an `__all__` entry, a Struct and a schema-list entry. `docs/design/string-literal-discipline.md` catalogues 14 antipatterns and prescribes "one constant, one test locks them equal". `scripts/check_status_literals.sh` greps source for literals.

Then tests hold the copies together. `test_kind_constants_match_structs_107` says constants live in leaf modules "so any module can import them without a cycle; that leaves them as strings, so this test is what keeps each one equal to the struct". `test_trigger_names_264` runs a regex over source lines. `test_session_kinds_is_exactly_the_session_structs` walks `vars(session)` for Struct classes and compares them to `SESSION_KINDS`, which proves the constant is derivable. `test_slash_command_exit_matches_session_end_on_exit_sentinel` pins a literal duplicated across the CLI layer boundary.

The discipline document never asks whether the reference needs to be a string. The builder already derives the kind from the class (`schema_map[s.__name__] = ...`), so the string is computed in one direction and retyped by hand in the other.

**Is there a better pattern?** Three options, and each has a proper place.

Constants with a locking test are what exists. They contain the risk and keep the cost.

Closed enumerations (`StrEnum`) are right for values that really are closed: `RunStatus`, `Decision`, `RunFailureReason`. They stay.

Reference by object is right for the connections inside a topology. Another project, the data-pipeline tool Dagster, does this and is cited as an example only: its `deps=[daily_sales]` passes the asset object ([vendor documentation](https://dagster.io/docs/guides/build/assets/defining-assets)). In the test rewrite of the ensemble topology, described under "How a topology is constructed", `on=Candidate`, `start=adj` and `c[candidates]` are checked by the type checker and navigable in an editor. The string survives only on the wire, derived once from the class, which keeps `schema` values and committed records the same. `session/vocabulary.py`'s constant tables, the kind-matching tests and the grep gate then have nothing to protect.

Where a layer rule forces a literal into two files, as with the CLI's `/exit`, the answer is one leaf vocabulary module below both layers.

## Types at the boundaries

**The concept.** A boundary is where untyped data enters typed code. The project's own document states the rule correctly: the "first function that touches an external string maps it to a typed value", and "Downstream code sees only typed values".

**The pattern here.** The rule is applied at the emission boundary and almost nowhere else. A Producer's output is a declared Struct and is validated. Its input is `Any`. `.get("` occurs 809 times, `ctx.event.payload[` 86 times, and `hasattr(inp, "get")` 111 times, the last defending against a non-dict input that cannot arrive. Each edge converts Struct to dict by hand in the `input_builder` and dict back to fields by hand in the body, untyped on both sides. Typed inputs already work: the input-isolation amendment decodes a Struct input to its own type, and `test_input_isolation` proves it. Topologies do not use them.

The kernel's own events are the least typed in the system. Applications must declare frozen Structs; the 12 lifecycle kinds are string constants with payloads built as dict literals at each site, and the envelope literal is built at five sites. Every consumer then re-parses: `isinstance(ref, dict) and isinstance(ref.get("instance"), str)` recurs through `projections/`, and `producer_kind_from_lifecycle_payload` exists because the payload is a dict. A test needs four lines to say "when adj completes":

```python
lambda c: c.event is not None and getattr(c.event, "kind", "") == "substrate.ProducerCompleted"
    and isinstance(getattr(c.event, "payload", None), dict)
    and c.event.payload.get("producer", {}).get("kind") == "adj"
```

Tool arguments are the sharpest case. A tool's shape is restated in five places: name constants, `TOOL_NAMES`, suite keys, `_TOOL_SCHEMAS`, and the description string. Arguments arrive as a positional `list[Any]`, so a call reads `T._bash(tmp_path, owner, ["sleep 1; echo built", None, True])`. Named arguments from the model are mapped to positions and unmapped again inside the tool. An `x-args-passthrough` schema flag opts out of that round trip, and at least ten tools use it. `edit` coerces the string `"false"` by hand. Three documents since mid-2026 name per-tool Struct schemas as the next step.

Results and errors have no consistent form. Tagged tuples: `parse_tool_call` returns `("tool", ...)` or `("answer", ...)`, and `_decide` returns `("evolve" | "spawn" | "exhaust", payload)`. Flag bags: `SafeCanonical` is `ok` plus seven optional fields, and `ReplayResult` carries optional fields per level. One tool both returns `{"ok": False, "error": ...}` and raises `ValueError`. Exceptions lose their type at the record boundary and get parsed back: `_error_sentinel` normalizes reprs by regex and `classify_reason_string("CalledProcessError(125,...)")` substring-matches them. `applications/registry.py` validates into a `StrEnum` and then stores the raw `str`. Three record idioms sit side by side (Struct, frozen dataclass, `NamedTuple`), and a second event channel of JSON on stderr carries its own vocabulary outside the bus.

**Is there a better pattern?** For payloads and inputs, `TypedDict` would give static checking with no runtime decode, and the product spec's benchmark already chose msgspec over Pydantic, at 3.7 times the decode-and-validate rate. Struct is the right answer and is already the project's decoder.

For tools, one Struct per tool gives everything from one declaration. Verified against msgspec 0.21.1: `msgspec.json.schema(T)` produces the JSON Schema, and `msgspec.convert({"flag": "false"}, T, strict=False)` produces `flag=False`, with a path-bearing `ValidationError` under strict mode. The five restatements, the passthrough flag, the positional round trip and the hand coercion go away.

For results, tagged Struct unions with `match`. For errors, one `ErrorInfo` Struct (`type`, `message`, `reason`) recorded at the point of capture, so nothing is parsed back from text. For records, one rule: anything that crosses the record is a frozen Struct, in-process configuration is a frozen dataclass, and `NamedTuple` retires.

## Depth and information hiding

**The concept.** Parnas decomposed systems by the design decisions each module hides ([1972](https://wstomv.win.tue.nl/edu/2ip30/references/criteria_for_modularization.pdf)). Ousterhout's terms sharpen this: a deep module has a small interface over a large implementation, information leakage is one decision visible in several modules, pass-through layers add interface with no function, and complexity should be pulled downward, away from callers.

**The pattern here.** Interfaces are wide or missing at exactly the points the model says should be narrow.

*The Bus has no module.* The specification's central object is spread over a `RunState` of per-run mutable fields, whose docstring says "extracted from the Runtime God-class" and "only their HOME changed". `Runtime` and `AppendCycle` both reach into it, `Runtime` reaches into `AppendCycle` privates such as `_cyc._maybe_offload`, and `session_registry` reaches `runtime._st.kind_by_instance`. `runtime._st` is read in at least five tests because no public way lists live instances. The extraction moved state without hiding a decision.

*The blob threshold leaks to authors.* Claim Check is the right pattern, and `record/blobstore.py` implements it well. But a payload's shape depends on its byte size: past 16 KiB, `ctx.event.payload` becomes `{"$blob": ...}`. So `tool_loop` caps output at 12k, `localize_elements` caps its list, `_step(ctx)` defaults on a missing key, and `test_a_huge_tool_output_cannot_wedge_the_loop` records a 341 KB `glob` result taking `step` out of the frame. Readers remember a `resolve_blobs=True` flag. A storage decision is visible in topology code in at least four places.

*The model interface is too small, so callers go around it.* `Responder` declares one method. The code actually uses `respond`, `arespond`, `respond_metered`, `arespond_metered`, `achat_tools`, `achat_tools_metered`, `astream`, `stream_format`, `system_channel`, `command`, `context_tokens`, `name` and `_model`, found by `getattr`. `resolve_driver_context` tests `type(responder).__name__ == "DeterministicResponder"`. Every wrapper branches on which of four method combinations is present.

*Parameters pass through layers.* `start_build` takes 13 parameters and relays them into `session_topology`'s 31. `_session_started_factory` takes 17 to forward into one Struct. `swebench_solve_and_grade_topology` takes 17, retyped by each arm factory. In all, 37 functions take eight or more parameters.

**Is there a better pattern?** For the Bus, a single class with a narrow surface (`submit`, the cycle, read access) that owns admission, sequence, control queue and log, with `RunState` dissolved into it. The kernel spec's three-part description (admission queue, log, Views) gives the internal decomposition.

For blobs, resolve inside the kernel before any author callback sees the payload, so offload is invisible above the log. Lazy resolution keeps the hot path cheap.

For `Responder`, the alternatives are one wide Protocol, which forces every stand-in to implement everything, or several narrow ones. Interface segregation with `runtime_checkable` Protocols ([PEP 544](https://peps.python.org/pep-0544/)) fits: one async `Responder.respond(request) -> Reply` where `Reply` always carries usage, plus `StreamingResponder` and `ToolCallingResponder`, tested with `isinstance`. The sync and metered duplicates disappear into one method. Sync callers get one adapter at the edge.

For long parameter lists, a frozen `SessionConfig` Struct passed whole. It also becomes the thing that preregistration and comparison can hash.

## Is the kernel a kernel

**The concept.** A kernel is defined by a minimality test. Liedtke: "a concept is tolerated inside the kernel only if moving it outside the kernel, i.e. permitting competing implementations, would prevent the implementation of the system's required functionality" ([SOSP 1995](https://cgi.cse.unsw.edu.au/~cs9242/22/papers/Liedtke_95.pdf)). The companion idea is the separation of mechanism from policy.

**The pattern here.** The word has four meanings in the project. In `substrate_v14_kernel.py` it means the minimal executable semantics. In the technical spec it means the whole runtime including record framing ("~80 lines of code in the kernel"). In the code it means one folder of 2,864 lines. In the product spec's package-name decision it is a free name on PyPI, `substrate-kernel`, because `substrate` was taken.

Against Liedtke's test the folder fails in both directions. It contains things that could be outside with no privileges: `views.py` implements the public `View` Protocol, `policies.py`'s recipes are callbacks over a public Decision, `composition.py` is a Producer that runs a Runtime, and `topology.py` holds a global name registry the CLI uses. It leaves out things the cycle cannot run without: `record/` (the log itself) and `encoding.py`. `runtime.py`, at 1,149 lines, combines run lifecycle, locking, recovery, manifest construction, Producer supervision, budget enforcement, the writer loop, termination, cancellation, injection, a process-wide registry of active runtimes and a ContextVar. A record operation with pause semantics, `append_at_rest`, is a module function beside them.

The boundary of the product is similarly blurred. The product spec says "The product is the runtime, not a topology catalogue" and places reference topologies in `examples/`. Runtime-proper modules are 6,392 lines, 16% of the package; topologies are 18,674 lines, 47%, including a 5,341-line session harness, in the same import namespace.

The concept is sound. TerminationPolicy as an open callback with recipes on top is a textbook split of mechanism and policy, and the 248-line kernel shows the true minimum is small.

**Is there a better pattern?** Three options for the word. Drop it and say `core`; keep the folder and redefine it in docs; or make the folder satisfy the definition. The third is best, because every specification already uses the word. `kernel/` holds the types of the primitives, the Bus and append cycle, the log, encoding and the supervisor, and it passes Liedtke's test. Standard Views, termination recipes, firing conveniences, joins and composition move out and import only the public kernel surface. An import contract enforces it, which makes the claim "nothing above the kernel is privileged" checkable.

## Module organization and dependency direction

**The concept.** "Architectures should tell readers about the system, not about the frameworks" ([Martin](https://blog.cleancoder.com/uncle-bob/2011/09/30/Screaming-Architecture.html)). A layout should reveal the layers, and dependencies should run one way.

**The pattern here.** The package root has 26 entries with no signal of tier. Core definitions (`constants`, `encoding`, `errors`, `types`, `protocols`) sit beside two facades (`api`, `app`), application support (`bundles`, `home`, `naming`, `interpreter`, `_daemon`, an HTTP client for a daemon outside this package), authoring tools (`templates`, `testing`) and the CLI. The real tiers are written in exactly two places, neither in the tree: a `layers` contract in `pyproject.toml`, and a `GROUPS` dict in `scripts/gen_api_docs.py`. That contract is good practice; the note beside it records that before 2026-10-08 topologies and assay imported each other. It orders the top-level units and stops there.

`topologies/` has 29 entries. Fifteen are topology packages. Seven are something else: `session_registry.py` (a 1,799-line daemon service doing manifest persistence, locking, turn dispatch, queues and boot scan), `workspace.py` (a git utility), `bundled.py` (a registry), `conversation.py` (a shared engine), `instruments/`, `runs/` and `applications/`, which itself mixes topologies, a session opener and a TOML parser. Seven more are directories that hold only committed records.

Inside that folder the dependencies form cycles: `session`, `tool_loop`, `session_registry` and `runs` all reach each other. `session.vocabulary` imports tool names from `tool_loop.tools`, `tool_loop.delegate` imports `session_registry`, and `session_registry` imports `session`. 201 function-local imports and a block of seven `# noqa: E402` imports at the bottom of `session/__init__.py` hold it together. `home.py` exists as a module so that `bundles` need not import `api`.

*The flat `api.py`.* A Facade offers a simpler interface over a subsystem. `api.py` is 267 lines exporting 119 names from 21 modules, simpler than nothing; it flattens the surface and adds no function, which makes it a pass-through in Ousterhout's sense. Its comments divide `__all__` into informal groups, and `gen_api_docs.py` has to re-create them as 16 hand-written sections to document it. `import substrate` yields only `__version__`. A second facade, `app`, was added so a CLI rule could be met; the test comment records that the CLI earlier reached topologies through `importlib.import_module` "with a comment saying it did so to pass this contract". The product spec specified a small surface: primitives, `Runtime`, standard Views, standard policies, conformance helpers.

`cli.py` is 1,914 lines: run, tail, inspect, narrate, language, handoff, replay, validate, stats, conformance, resume, demo, score, a chat REPL, daemon spawn, a bundle wizard, an installer, a config loader, an SSE parser and a 170-line slash-command router. A bare `substrate` opens the chat. Tests are 240 flat files, 90 named by sprint number, so the tests of prompt building are spread over six files told apart only by sprint numbers.

**Is there a better pattern?** Package by layer gives clear dependency rules and scatters features. Package by feature keeps features together and hides layers. The hybrid fits this system: layers at the top of the package, features inside the layers that hold many of them (one package per topology, one per benchmark). The public surface is the same layout: a curated root exporting the primitives and `Runtime`, with public modules `substrate.views`, `.termination`, `.record`, `.replay`, `.errors` and `.testing`. A flat facade with better comments leaves the problem. Importing from internals directly exposes every private module. Grouping by namespace gives readers the groups the docs script already had to invent.

Whether the upper layers become a separate distribution is a packaging step that an enforced import direction makes cheap, and it can come later.

## Composition and reuse

**The concept.** Parts should combine by a stated interface, with their internals unable to collide, and each rule should have one home.

**The pattern here.** Reuse is done by calling a function that mutates a shared builder. `best_of_n_correction(b, ...)` registers fixed kinds (`seeder`, `drafter`, `validator`, `judge`) and a fixed view name, so two calls on one builder collide. `fanout_review` decorates a topology by calling `inner(b)`. `compose_run(b, spec, own_record)` is a third form. Because a composed fragment has already set termination, callers overwrite it: `session/ci.py` calls `_ci_base()(b)` and then `b.termination(...)`, with a comment saying "Overwrite"; `swebench_solve_and_grade` does the same; `assemble.py` passes `termination=api.quiescence()` as a placeholder that never fires. `coding_flow` and the retired solver topology retype the same four Producers and three Triggers.

The one sound composition mechanism is `embedded_substrate(_inner_topo, exports={"Tick": OuterTick})`, which has a boundary and a typed export map. Its export map, though, travels as an attribute on a callable, and the builder calls the factory at registration to fish it out.

Fan-in has no concept. Six topologies write barriers as predicate arithmetic over view lengths; `repro_base_validate.py` warns that omitting one emission "would deadlock the barrier". Failure policy is written by hand in each Producer body, with 57 `# noqa: BLE001` sites and bodies that differ on whether to swallow.

Copying fills the gaps: `_Factory` in 27 modules, `_git` in 4, a `_turn` driver in 11 test files, scripted responders in 10 or more, `_require_model` in 13. `test_session_registry_consolidated_099` records a real case of a copied module and its original drifting apart.

**Is there a better pattern?** Two other graph systems show the idea and are cited as examples only. Akka's partial graphs "return the set of yet to be connected ports" ([vendor documentation](https://doc.akka.io/libraries/akka-core/current/stream/stream-graphs.html)), and LangGraph keeps subgraph state "under a namespace of the parent thread". Applied here: a `Fragment` is a value with Producers, Views and Triggers and no termination, so the overwrite problem cannot occur. `Topology` is a complete fragment plus termination and initials. `fragment.namespaced("repair")` prefixes kinds, and with no prefix given names are unchanged, which keeps existing records stable.

Two composition forms then have clear criteria. Same-bus merge when the parent's predicates read the child's events. `embedded_substrate` when only exports should cross, since it has its own writer and log. Both are needed, and the export map becomes a field of the declaration.

Join belongs in the standard library as a named View and predicate pair (`Join(on=Verdict, key=..., count=n)`). The specification treats progress gating as a pattern and not a primitive, and a library helper honours that. Failure policy becomes a Decorator over a Producer body (`RateLimitedResponder` is already this pattern for models), declared on the Producer.

The recorded rule that new session-like topologies start as a literal copy of `session/` is a separate, standing decision about how those are authored. The fragments above replace the builder-mutation sites listed here.

## Control flow, closures and long functions

**The concept.** State that governs behaviour should be nameable. A closure is an object with no name for its fields, which is a fine trade for small things.

**The pattern here.** `session_topology` has 31 parameters and 717 lines, of which the nested `topo` is 507. Its 22 Trigger registrations implement a state machine (turn open, prompt, model step, tool, language, return, end) with no state type. A state exists only as a conjunction such as `_producer_kind_from_ref(ctx) == PRODUCER_KIND_SESSION_PROMPT and int(ctx.views["user_turns"].value()) > 0 and _turn_open(ctx) and _skill_of(_turn_message(ctx)) is None`, and the machine has to be reconstructed by reading all 22. The same model-start input dict is written at four Triggers.

Producer configuration is captured by closure inside a factory inside a function: `_return_factory() -> Callable[[], Any]` defines `_return` and returns `lambda: _return`, three levels to yield one event. There are 70 `*_factory` definitions. The design spec chose this ("Producer state, if any, lives in closures over the factory"), and the same closures are why `Arm.build` cannot be identified.

Modes hide inside bodies. The `tool_loop` model body is one generator of 110 lines with five modes. CI stand-ins live inside production Producers in `instruments/`, even though `Responder` exists to be that seam. Dispatch on a kind string is written as `if`/`elif` chains (`_render_turns`, `_inspect_record_impl`, `_slash_route`). In the package, 137 functions exceed 50 lines and 35 exceed 100.

**Is there a better pattern?** For the session machine, the options are a state-machine library (against the one-runtime-dependency policy, and it would hold state off the log), classes in the State pattern (runtime objects holding state, again off the log), or a reducer View: a View whose `update` folds events into a frozen `TurnState` with a closed `Phase` enum. The reducer View is the right one because it is the specification's own idea: all state lives on the log and Views are its projections. Predicates become `phase_is(Phase.MODEL_DONE)`, and the machine fits on one page.

For configuration, closures remain acceptable for small things. Where identity matters a frozen callable object is better: a dataclass whose fields are the configuration and whose `__call__` is the body. It is canonicalizable, so preregistration can hash an arm directly and `params_by_arm` goes away.

For modes, Strategy behind the `Responder` seam, with deterministic stand-ins only behind it. For kind dispatch, `match` over the tagged union.

## Ambient state

**The concept.** A dependency passed as a parameter is visible in the signature. One reached through a global is visible only on reading the body.

**The pattern here.** Process-wide state includes `_REGISTRY`, two different module-level `TABLE`s, `_CHANNELS`, `_semaphores`, `_context_cache` and `_ACTIVE_RUNTIMES_BY_RECORD_ROOT`. ContextVars serve as hidden parameters: `_CURRENT_RUNTIME` so a tool can find its runtime, `_BASH_PROGRESS_CTX` (named for one tool, used by all, and read by `runs/hold` to find a call id), and `_TOOL_CANCEL_HOOKS`. Tests show the cost: `hold.TABLE = table` inside `try`/`finally`, `_reset_semaphores_for_tests()` in a production module, `patch.object(session_mod.api, "any_of", ...)`, and a thread setting `_TOOL_CANCEL_HOOKS` by hand.

**Is there a better pattern?** A dependency-injection framework would add machinery and a dependency for a problem a parameter solves. The plain answer: `Tool.run(args, ctx: ToolContext)`, where `ToolContext` carries the runtime handle, progress callback and cancel hooks, and one host object owns the tables. Topology registries become values passed to the CLI. A ContextVar remains the right tool only for something that truly is per-task and read deep in foreign call stacks, and nothing listed here is that.

## The read side

**The concept.** A log is the write model, and readers need a read model built on it. A reader should not have to know the storage format.

**The pattern here.** Reading the record is nine free functions over a path in `record.py`, each returning `dict[str, Any]`, and `projections/` functions that take `record: Any`, meaning a path or an iterable. Each projection re-derives lifecycle meaning with `.get`. "Turn" is computed separately in `turn_replies`, `slice_kind_matches` and `turn_pairings`. Four launcher scripts have `if k == "ToolCall"` print ladders. A test is named for reading a payload that is sometimes a dict and sometimes a `mappingproxy`, which are two runtime shapes of one concept.

The technical spec defined `load_record -> RunRecord`. A later amendment to the product spec relaxed it to the shipped `read_record` over dicts, itself naming the "stringly-typed read surface" and deferring a typed object. The spec moved to match what got built. Meanwhile `Event.from_envelope` exists and the typed reader is one `map` away.

`record/` also keeps writing and reading in one 623-line module, and `record/inputs.py` validates Producer inputs, which is not a record concern.

**Is there a better pattern?** A `Record` object: `Record.open(path)`, `.events()` yielding typed `Event`s with lifecycle payloads as Structs and blobs resolved, `.topology()` returning the same structure the `Topology` value serializes to, and the inspection queries as methods. A domain subclass, `SessionRecord.turns()`, gives "turn" one definition. A dict iterator can remain underneath for tooling. Writer and reader then share one schema for the manifest, which closes the gap between `Runtime._manifest` and `graph.py`.

## Code style

**The concept.** A comment should say what the code cannot. History belongs to version control and the project's log.

**The pattern here.** Comments carry 553 references to sprint or ticket numbers, 110 review or audit references and 492 `§` marks. Docstrings narrate how things came to be ("Sprint 065: ... deleted", "F2 fix (review 2026-08-08)", "Deferred to sprint 064"). Blocks of twenty comment lines sit over three lines of logic. A reader of `runtime.py` gets the case history before the behaviour.

Compatibility layers are kept for callers that are all in this repository: `_ = repro_k  # kept in signature for source-compat`, a retired 270-line topology still in `assemble.py`, `_record_has_envelopes` "Back-compat wrapper", and `reference/_models.py` re-exporting adapters. Residue from past changes stays: `_TRIGGER_FIRED = TRIGGER_FIRED` aliases in four files, `import os as _os` when `os` is imported at the top, `from .vocabulary import (X as _KIND_X,)` aliases of aliases.

Tests assert on source text: `"except BaseException" not in src`, `text.count("turn_replies(") == 2`, a regex over docstrings. They reach private state because the public surface offers no equivalent, and helpers are copied because `tests/` has no support module.

**Is there a better pattern?** A comment keeps a requirement ID only where the line implements a contract, such as the rule that an invalid emission is recorded and numbered, and says why when the reason is not visible. Sprint and review history stays in git and `BLACKBOARD.md`, where it already is. No compatibility layer exists for in-repo callers, because a change updates them. Tests mirror the package and are named for behaviour, with a `tests/support` module holding the session driver and the scripted responders. A value-based surface removes most reasons to scan source or reach private fields.

## The standard already exists in parts of the package

This is evidence about what the rewrite should imitate, and that it is within reach of how this project writes.

`record/` has small modules with one job each: `framing`, `blobstore`, `locking`, `sidecar`, `live`. Its tests read as a specification. `language/` is pure functions over frozen dataclasses, one module per concept, each measure documented with its published definition and cross-checked against `river`, `lexicalrichness`, `powerlaw`, `nolds` and `cmudict`. `assay` has real domain classes: `Suite` and `Arm` validate in `__post_init__`, `Case("a", {}, "20")` reads as a declaration, `Oracle` is a Protocol with two Strategies, and `Result` is frozen with a derived `.passed`. `swebench_solver` is organized by phase, with `select_patch(applied, results)` pure over Structs. `RateLimitedResponder` is a true Decorator. `any_of` and `all_of` over `TerminationPolicy` are a Composite with walkable structure. `conversation.Instrument` is a declaration record.

Each of these is what a typed value with a small interface looks like here, and each sits next to code that has the opposite shape. `Suite.__post_init__` already does for an experiment what `Topology.__post_init__` should do for a topology.

## The standard best-practices implementation

The specifications are kept. The semantics of the append cycle, the record format, replay levels and the vocabulary are what the code is meant to express, and the rewrite preserves them. The preservation contract is concrete: the conformance suite, the 18 committed records, and the behaviour tests. Replacing factory closures moves `fingerprint.qualname` in `RunStarted`, as the test rewrite showed, so those records regenerate; any other difference is a failure. The specification changes are the product spec's list of the public API and its definition of a topology as a function of a builder, the design spec's "functions of the builder", the amendment that dropped `RunRecord`, and the count of primitives, which the kernel, product and design specs give as eight and which becomes nine.

The package reads top to bottom as the architecture:

```
src/substrate/
  __init__.py      Producer Event View Predicate Trigger Route TerminationPolicy
                   Topology Fragment Initial Record Runtime Bus and their direct types
  kernel/          passes the minimality test; imports nothing above itself
    event.py       Event, ProducerRef, one typed Struct per lifecycle event
    producer.py    Producer[In, Out], Body[In, Out]
    view.py        View[T]
    predicate.py   Predicate[E], and, or, not
    trigger.py     Trigger[E, In], firing policies, cooldowns
    route.py       Route[E, S]
    termination.py TerminationPolicy, Decision
    topology.py    frozen Fragment and Topology; every static check in the constructor
    bus.py         Bus: admission, append cycle, control queue, sequence
    runtime.py     Runtime: run, resume, Producer supervision, budgets
    encoding.py    RFC 8785
    log/           framing, segments, blobstore, locking, sidecar, attach
  views.py         standard Views, typed, holding decoded Structs
  termination.py   recipes
  joins.py         Join and the fan-in helpers
  composition.py   namespacing, embedded_substrate
  record.py        Record, the typed read model; inspection queries as methods
  replay.py        replay levels
  errors.py        one hierarchy, ErrorInfo
  testing.py       assert_event and friends, shared stand-ins
  models/          Responder and capability Protocols, Ollama, CLI, deterministic, Decorators
  tools/           Tool[Args], ToolContext, the tool suite, one Struct per tool
  session/         events, TurnState reducer View, topology, prompts, SessionRecord,
                   SessionService (now session_registry), delegate
  topologies/      one package per topology; _shared/ for the conversation engine
                   and the best-of-N fragment; committed records under tests/records
  language/        as now
  assay/           as now, with swebench under it and a generic Case[P]
  conformance/
  cli/             one module per command group; imports the public surface only
```

Dependencies run one way, enforced by import contracts inside `topologies`, `session` and `tools` as well as across the top level: `kernel`, then `views`, `termination`, `joins`, `composition`, `record`, `replay`, then `models`, `tools`, `session`, `topologies`, `assay`, `cli`. Function-local imports for cycle-breaking do not exist.

Each primitive is a named, exported, generic type. A topology is an immutable value validated at construction, built from declarations that refer to each other by object, with the kind strings derived from classes and present only on the wire. Producer inputs and every lifecycle event are frozen Structs. Blobs are invisible above the log. The Bus is one class. `Record` is the one way to read, sharing its schema with what the writer records. Composition is a function over values with namespaces and a clear boundary between merge and embed. Fan-in is a named library concept. Failure policy is a declared Decorator. Session state is a reducer View with a closed phase enum. Tools take one Struct and one context object. Module-level mutable state is gone. Comments state what the code cannot, and tests are named for behaviour with a shared support module.

Because `Topology` can lower onto the current builder, as the test rewrite showed, topologies can move one at a time while the runtime stays in place, and the builder can retire last.

A reader of that package who clicks `Trigger` lands on the class the specification defines.

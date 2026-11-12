# Substrate code design review

Third version, 2026-11-09. Replaces `RESEARCH-2026-11-09-substrate-design-and-boundary-r2.md`, now in `superseded/` in this folder.

Subject: the architecture, design patterns, code patterns and code style of the `substrate` package.

## Main finding

The specifications define Substrate as nine named pieces. Each has a shape, invariants and a place in a six-step append cycle. The package holds types for four of those pieces. The rest exist as method calls, dictionaries, strings and closures, and a reader has to reconstruct them from their uses.

One decision produces most of the distance between the ideas and the code: **a topology is a procedure that mutates a builder, when the model describes a declaration.** Because a topology is a procedure, a Trigger cannot be held, a Producer's input cannot be typed, every connection and every name can only be a string, two topologies cannot be combined without colliding, and the only way to ask a topology what it contains is to run it or to hand it a fake builder. The code compensates with 685 lines of string constants, tests that keep those strings equal to class names, 111 repetitions of `inp.get(...) if hasattr(inp, "get")`, and two test doubles of `TopologyBuilder`.

The better design is a frozen, validated, exported `Topology` declaration built from typed parts. To check that it works, the ensemble topology that ships with Substrate was rewritten in this design, in a throwaway copy made for this paper. In that topology several models answer one question and a judge picks the best answer once three are in. The rewrite passes `mypy --strict`, turns four kinds of wiring mistake into type errors, runs on the existing `Runtime` without a kernel change, and produces the same events as the original, with every name derived from the code. "Topology construction" gives the method and its limits.

Each part below takes one software-engineering concept and each pattern the code uses under it. A pattern's entry says what is there, how it works, what replaces it, why that beats the alternatives, and which published refactoring technique gets there. The exact steps for a part are written from the code when that part is done.

## Sources and scope

Read in full: all 159 Python modules in `src/substrate` (39,769 lines), all 240 test files, all 39 scripts, the current specifications with their amendments, the 15 superseded spec drafts, `substrate_v14_kernel.py`, `proof/substrate_proof.py`, and the documents under `docs/`. Not read: `process/`, which holds 10 GB of run records and 35 MB of archive, apart from the parts of `BLACKBOARD.md` and `WORKING_AGREEMENT.md` cited here. The kernel, the record writer, the public API modules, `best_of_n`, the graph and inspection projections, and the session wiring were re-read while writing this version.

Counts come from the working tree on 2026-11-09. External sources are of three kinds and are labelled where used. Papers and first-party language references are primary. Framework documentation is vendor documentation: reliable for what an API is, and silent on whether the design is good. Other projects are cited only as examples of a pattern; none is proposed for use. John Ousterhout's *A Philosophy of Software Design* was not read; its terms are taken from its [author page](https://web.stanford.edu/~ouster/cgi-bin/book.php), a [chapter-by-chapter reader's notes](https://dev.to/danlebrero/book-notes-a-philosophy-of-software-design-cna), and his [published exchange with Robert Martin](https://github.com/johnousterhout/aposd-vs-clean-code).

## Refactoring method

Refactoring is a series of small changes, each leaving behaviour the same and the tests passing. A fault found during a change is written down and fixed in its own change. The techniques named under each pattern are published ones.

| Technique | What it is, from its source | Source |
|---|---|---|
| Moves such as Extract Class, Move Function, Replace Primitive with Object | The online catalog; every move named in this paper is listed there | [Fowler, *Refactoring*](https://refactoring.com/catalog/) |
| Characterization test | A test that documents "your system's actual behavior" | [Feathers](https://michaelfeathers.silvrback.com/characterization-testing) |
| Golden Master | Capture full output once and diff against it; here the 18 committed records | Known from [a secondary summary of Feathers](https://understandlegacycode.com/blog/key-points-of-working-effectively-with-legacy-code/); the book was not read |
| Branch by Abstraction | "making a large-scale change to a software system in gradual way" | [Fowler](https://martinfowler.com/bliki/BranchByAbstraction.html) |
| Strangler Fig | "a gradual approach to legacy modernization" | [Fowler](https://martinfowler.com/bliki/StranglerFigApplication.html) |
| Parallel Change | Expand, migrate, contract | [Fowler](https://martinfowler.com/bliki/ParallelChange.html) |
| Mikado Method | "a process for surfacing hard-to-see dependencies in a codebase" | [Authors' site](https://mikadomethod.info/), which leaves the steps to the book |

The Golden Master here compares by equivalence, not bytes: ULIDs differ on every run, and `test_committed_record_is_current` uses `first_divergence`. A renaming conversion needs a comparator that takes a committed old-to-new name map, compares every frame after the mapping, and reports all differences. A record regenerates only after that comparison is clean.

Standing project rules bind the work. A new primitive names its production consumer, and tests do not count. The canonical-home registry in `WORKING_AGREEMENT.md` changes with every move. The Length and Tone controls stay in the session vocabulary.

Four changes alter what a reader sees, so each is stated and lands by itself: derived names on non-session records, blobs resolving by default in `Record.events()`, a typed error for an unsupported schema version, and the initial-Producers field in the manifest.

The parts depend on each other in this order: the safety net of Characterization tests and the Golden Master records; the specification amendments; the typed pieces; the kernel; the construction of topologies, which carries most of the changes to names and boundary types with it; the model interface; session; ambient state; composition; the read side; module organization; and code style last, because earlier parts delete most of what it would touch.

## Model-to-code correspondence

In domain-driven design, the ubiquitous language is "a common, rigorous language between developers and users", "based on the Domain Model used in the software" ([Fowler's summary of Evans](https://martinfowler.com/bliki/UbiquitousLanguage.html)). The test is mechanical: take a word from the model and find the thing in the code that carries that name and has that shape. The project enforces its vocabulary in prose, log fields and CLI output, and much less in types.

### Types for the nine pieces

| Piece | Shape in the specifications | Where it is in the code | Status |
|---|---|---|---|
| Producer | typed input to async stream of typed events | `protocols.Producer`, `__call__(input: Any) -> AsyncIterable[Event]` | Exists. Input is `Any`; declares `Event` where bodies yield payload Structs |
| Event | typed, sequenced record | `types.Event` | Exists. Readers receive dicts instead |
| Bus | admission queue, log, single writer | No class. Spread over `RunState`, `RecordWriter`, `AppendCycle` and `Runtime` | Absent |
| View | incremental projection; the design spec writes `View[T]` | `protocols.View`, `value() -> Any` | Exists, untyped |
| Predicate | cheap gate with a taxonomy of five forms; the design spec lists a library and `AnyOf`/`AllOf`/`Not` | `Callable[[TriggerContext], bool]`, a lambda at each site | No name, no library |
| Trigger | `(predicate, producer_factory, firing_policy, input_builder)` | `TriggerReg` in `kernel/topology.py`, unexported | Named for registration |
| Route | `(source_predicate, target_input_slot, transform)` | `RouteReg`, same file, unexported | Named for registration |
| TerminationPolicy | callback with recipes | `kernel/policies.TerminationPolicy` | Exists |
| Run record | "the artifact the whole product is organized around" | `Iterator[dict[str, Any]]` | A path and a dict stream |
| Topology, the arrangement made from the nine | "the arrangement" | `Callable[[TopologyBuilder], None]`, named as an alias only in `assay/suite.py` | A function signature |

The specification's executable version has these names. `docs/specs/kernel_spec/substrate_v14_kernel.py` is 248 lines including its checks, with `@dataclass class Trigger`, `@dataclass class Route`, and `class Kernel` whose `_cycle` method is the six numbered steps. A reader finds all of them by name.

Following references in an editor explains nothing in the production code. Following `b.trigger` lands on a method that appends a `TriggerReg` to a list. Following `"adjudicator"` goes nowhere, because it is a string. `ctx.views["candidates"]` is a dictionary lookup that returns `Any`. The connections that make up a topology live in string equality, and editors do not navigate string equality.

The replacement is one exported class per piece, carrying the specification's word: `Producer[In, Out]`, `Event`, `Bus`, `View[T]`, `Predicate[E]`, `Trigger[E, In]`, `Route[E, S]`, `TerminationPolicy`, `Record`. Authors already expect these names. `test_fewer_producers_263` annotates a return as `api.Registration` and `test_run_suite_with_salvage` annotates one as `api.Topology`. Neither exists on `api`; the annotations survive only because `from __future__ import annotations` never resolves them. The generated API reference has no entry for Bus, Predicate, Trigger or Route, and its "Primitives & protocols" group includes `Responder`, whose own docstring says "NOT a kernel primitive".

Exporting `TriggerReg` and `RouteReg` as they are would be the smallest step. It fails because they hold strings and `Any` and can only be produced by the builder.

**Refactoring.** Replace Primitive with Object and Encapsulate Record from Fowler's catalog. The code moves through three forms: today's `TriggerReg` and `RouteReg`, holding strings and `Any`; typed declarations added beside them, which translate into the old records so nothing above changes; and the old records removed when the last topology has moved. Bus and `Record` get their own treatment below. Exports move to the package root when each type is finished.

### Number of pieces

The kernel and product specs say eight, with Event in and Topology out. The design spec says eight, with Topology in and Event out. The README says "nine fundamental ideas" and the tutorial "nine pieces", counting the run record. `docs/README` says eight. `docs/cradle-x-substrate` holds a proposal that says nine and a paper of the same date that says eight. `docs/design/ui-design-handoff.md` says "exactly eight words" and lists nine. When the set has no representation in code, nothing forces one answer.

The count is nine: Producer, Event, Bus, View, Predicate, Trigger, Route, TerminationPolicy and the run record, as the README has it. The Bus is one of them. Topology is a named object made from the nine. The kernel spec, product spec, design spec and `docs/README` say eight; they are marked here to be revised in new drafts and have not been changed.

**Refactoring.** The project's own rule applies: specifications change first and by addition. New drafts of the kernel, product and design specs state the count, with the prior drafts preserved, and `docs/README` is corrected.

### Predicates

The specification defines five forms of Predicate and the design spec names a small library. The code has lambdas. A test needs four lines to say "when adj completes":

```python
lambda c: c.event is not None and getattr(c.event, "kind", "") == "substrate.ProducerCompleted"
    and isinstance(getattr(c.event, "payload", None), dict)
    and c.event.payload.get("producer", {}).get("kind") == "adj"
```

`Predicate[E]` is a Protocol, and a standard module supplies `completed(adj)`, `count_at_least(view, n)`, `event_where(...)` and combinators for and, or and not. The specification keeps Predicates as host-language callables, and its prototype measured that as affordable, so a plain lambda stays legal; the library covers the common forms. A closed predicate language would let the runtime reason about cost, but the product spec rejected it on those measurements.

**Refactoring.** Extract Function, then Replace Inline Code with Function Call. Each lambda first becomes a named function where it stands. Named functions that recur move to a standard module, and call sites use them. Combinators arrive last, once enough named Predicates exist to combine.

## Topology construction

The Builder pattern separates the construction of a complex object from its representation, and the last step returns the product ([summary](https://en.wikipedia.org/wiki/Builder_pattern)). Three other graph-building systems show the shape. They are cited as examples of the pattern only; none is proposed for use, and the recommended design needs nothing beyond Python and msgspec, which Substrate already uses. Kafka Streams: `StreamsBuilder.build()` "Returns the Topology that represents the specified processing logic" ([vendor documentation](https://kafka.apache.org/39/javadoc/org/apache/kafka/streams/StreamsBuilder.html)). LangGraph: "You must compile the graph before you invoke or stream it," and "Compilation checks the graph structure" ([vendor documentation](https://docs.langchain.com/oss/python/langgraph/graph-api)). Akka Streams describes its built graphs as "immutable, thread-safe, and freely shareable" ([vendor documentation](https://doc.akka.io/libraries/akka-core/current/stream/stream-graphs.html)).

### Builder function replaced by a frozen declaration

A topology author writes a function that returns a function that calls methods on a builder it was handed. The ensemble topology, trimmed:

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

Every registration method returns `None`, across 264 call sites, so no Trigger or Producer can be held, passed, compared or tested. Connections are strings by necessity.

The origin is in the design spec. Its alternatives section compared decorators against builder methods and compared the builder against incremental `Runtime.add_producer`. A first-class topology object never appeared on the list. "Topologies are functions of the builder; that's the contract," and the product spec made it a requirement: "A topology is a factory function receiving a `TopologyBuilder`."

Seven forms were weighed against what Substrate topologies actually do: they have cycles (judge back to drafter), predicates and input mappings on every edge, and member counts known only at construction.

| Form | What it fixes | What it costs | Verdict |
|---|---|---|---|
| Today's procedure over a builder | Nothing further | Everything in this part | Replace |
| Builder that returns a public frozen object, with handles returned from each call (Akka's shape; Kafka's `build()` returns a `Topology` that still has public `add` methods) | Product held; references become objects | Keeps a mutable object around for a job Python keyword arguments already do | Workable; second choice |
| Frozen declaration constructed directly from typed parts | Product held, typed edges, validation in the constructor, composition | Conditional parts are written as ordinary list-building before the constructor call | **Use this** |
| Decorators on a local object (`@t.producer`, `@t.trigger`) | Reads well for small fixed topologies; avoids the import-order objection the spec raised, which applied to global decorators | Still mutation; a Trigger has two callables, so one decorator picks one awkwardly; loops over N members read badly | Optional sugar over the declaration, at most |
| Class-body declaration using `__set_name__` | Derives names from attribute names: the [Python reference](https://docs.python.org/3/reference/datamodel.html) guarantees the hook is "called at the time the owning class" is created | A class body is fixed at definition, and the ensemble topology has a member count known only at call time; 31-parameter parametrization has nowhere to go | Rejected as the primary form |
| Pipe or fluent operators | Terse for straight pipelines | An operator has two operands, and an edge here has a predicate, an input mapping and a firing policy; cycles do not fit a pipeline | Rejected |
| Data-only topology (YAML or JSON) | Fully serializable | The kernel spec says "Topology is host-language code" and keeps Predicates as host-language callables, and the product spec's prototype measured that as affordable | Rejected; the declaration's structure serializes anyway |

A direct constructor beats the Builder here because Python has keyword arguments and frozen records, and a local list handles the conditional case.

The same wiring as a frozen declaration:

```python
def ensemble(question, *, members, judge, quorum=3) -> Topology:
    ms = tuple(member(n, question, r) for n, r in members.items())
    adj = adjudicator(question, judge)                    # Producer[Adjudicate, Verdict]
    candidates = kind_buffer(Candidate)                   # View[tuple[Candidate, ...]]
    return Topology(
        producers=(*ms, adj),
        views=(candidates,),
        triggers=(
            Trigger(on=Candidate, start=adj,
                    when=lambda c: len(c[candidates]) >= quorum,
                    input=lambda c: Adjudicate(c[candidates]),
                    policy=Once()),
        ),
        initial=tuple(Initial(m, None) for m in ms),
        termination=any_of(cancel_all_others(completed(adj)), all_completed()),
    )
```

No name in that example is typed by the author. Inside `member` and `adjudicator`, a Producer is declared from its body: `Producer(answer, emits=(Candidate,), key=name)` and `Producer(adjudicate, emits=(Verdict,))`. "Names and references" gives the rule.

`Trigger[E, In]` ties three things together in the type system: the event it fires on, the input its mapping returns, and the input the started Producer accepts. Cycles cost nothing, because Producers do not refer to Triggers. Only Triggers refer to Producers.

**Refactoring.** Branch by Abstraction, Strangler Fig and Parallel Change. `Runtime.run` already accepts any `Callable[[TopologyBuilder], None]`, so that callable is the abstraction. The forms are: a `Topology` that translates itself into builder calls; topologies converted one at a time, smallest first and `session` last, each record regenerating as its Golden Master; `Runtime` accepting a `Topology` directly as the expand phase of Parallel Change; and the builder and the translation removed as the contract phase.

### `Registration`

`TopologyBuilder.build()` exists and returns a `Registration`, so a product does exist. The author never sees it: `Runtime._drive` calls `builder = TopologyBuilder(); topology(builder); reg = builder.build()` internally, and `api` exports neither `Registration` nor `TriggerReg`, `RouteReg` or `ProducerKindReg`. `Registration` is a plain `@dataclass` of dicts and lists. The docstring on `build()` says "Freeze and statically validate"; the method runs two name checks and returns the same mutable object.

`Topology` replaces it as the one product, frozen and exported. `Runtime.run(topology)` takes it directly.

**Refactoring.** Encapsulate Record, then Inline Class. `Topology` takes over the fields of `Registration` as a frozen object. `Runtime` reads it. `Registration` goes when nothing builds one.

### Topology validation

The check for a subscription naming a kind nobody emits lives in the `validate` command in `cli.py`, beside a printed note about a missing termination policy. A run started through `Runtime` does not get them. A rule about whether a topology is well formed belongs to the constructor of a topology, as `Suite.__post_init__` already does for a benchmark. `validate` then constructs the declaration and reports the error. A missing termination stays what it is today, a note with a quiescence default, and the constructor does not refuse it. Moving the checks into `build()` would also work, but `build()` is only reached by the runtime and by those who know to call it.

**Refactoring.** Move Function. The checks in the `validate` command move into the `Topology` constructor, with Characterization tests pinning what `validate` reports today. The command then constructs the declaration and prints the error.

### Inspecting a topology

The repository's workarounds are the evidence: two separate `_RecordingBuilder` test doubles, the first documented as "Used to inspect what a topology declares without wiring the real substrate runtime", the second of which reads a policy's display name (`"GradeResult" in b.termination_str`); `assert callable(topo)` as the assertion on built topologies in at least four tests; `b._reg.producer_kinds` reached in three files. In `assay/preregistration.py` the docstring states that arm parameters "live in Arm.build's closure and cannot be extracted reflectively", so a parallel `params_by_arm` restates them, and a review later found that the preregistration fingerprint hashed only each arm's name and role, so a changed parameter passed unnoticed.

The project's stated direction needs the declaration. The kernel spec foresees a "typed Topology specification" emitted as events and `AddTrigger`-style self-modification. `docs/design/substrate-as-a-tool.md` translates a spec dict into builder calls, in code kept outside this package. The cockpit design has agents declaring topologies, the proposal itself being an event, and spans of real runs promoted to reusable topologies. A callable cannot be proposed, recorded, diffed or promoted as a structure. A declaration's structure can. The callables inside it remain code, and a parameter a predicate captures is visible only when it is declared, through the frozen callable objects under "Producer factories and closures" or a parameter field recorded in the manifest. Fingerprints use canonical bytes, because Python salts `str` hashes across processes. Two calls with the same arguments do not compare equal, since each holds new callables.

The structure already exists on the read side, as `TopologyGraph`, described under "Reading the record". It sits at the end of the pipeline, where it is least useful.

**Refactoring.** Follows from the declaration. Substitute Algorithm in the tests, which assert on its fields, and Remove Dead Code for `_RecordingBuilder` and for `params_by_arm` once an arm can be hashed.

### The `Producer` Protocol

```python
class Producer(Protocol):
    def __call__(self, input: Any) -> AsyncIterable[Event]: ...
```

The ensemble topology explains its `_Factory = Callable[[], Any]` by saying "an async-generator function's static type does not structurally match the Producer Protocol". That comment sits in the reference topologies, and the escape to `Any` is assigned in 26 modules. The stated cause is wrong. An async generator matches a Protocol with no trouble: the test below used `Body[In, Out]` and it passes under `--strict`. The current Protocol fails for two other reasons. It declares `AsyncIterable[Event]` while bodies yield payload Structs, which the Bus wraps into Events. And its parameter can be passed by keyword, so a body whose parameter is called `inp` does not match.

```python
class Body[In, Out](Protocol):
    def __call__(self, input: In, /) -> AsyncIterator[Out]: ...

class ContextBody[In, Out](Protocol):
    def __call__(self, input: In, run: RunContext, /) -> AsyncIterator[Out]: ...
```

`Producer` accepts either. The second form is for a body that needs the run itself, as "ContextVars" describes.

**Refactoring.** Change Function Declaration by Parallel Change. `Body[In, Out]` is added beside `Producer`, typed bodies adopt it during the topology conversions, and the old Protocol and every local `_Factory` alias go at the end.

### Other builder declarations

The example above shows one Trigger and one View. The frozen declaration has to carry all of this.

| Today | In the declaration |
|---|---|
| A kind that arrives from outside: `InterruptRequested` and `SessionEndRequested` written by the daemon, `UserMessage` as a resume event, `OperatorOverride` | `Topology(external=(InterruptRequested, ...))`, Struct classes. The constructor checks each Trigger's `on` against emitted plus external. A Fragment is not checked; only the whole `Topology` is |
| `Park`, which no code emits and old records hold | Declared external |
| A lifecycle kind | Each lifecycle Struct names its reserved wire kind, one function maps class to wire kind for the subscription, the emitter and the reader, and the constructor exempts the reserved namespace |
| A Trigger on several kinds (seven today) | `on=(ProducerCompleted, ProducerFailed)`, with `E` their union |
| `ctx.event.seq` | `c.event` is the typed payload; `c.seq` and `c.producer` are the envelope's fields |
| `b.route` | `Route(on=..., into=failure, transform=...)` in `Topology(routes=...)` |
| `b.instrument` | A function that returns a Fragment holding a Producer, a PerEvent Trigger named as the Producer is, and an optional Route |
| `b.baseline` | `Topology(baseline=...)`, a Struct |
| `Budget`, `author_version`, `schema_version` | Fields of `Producer`; bumping `schema_version` remains the evolution mechanism |
| Cooldowns | A field of `Trigger` |
| State a body keeps across firings, such as `prev_write` in `tool_loop` | `Producer(state=...)`, a factory called once per run |
| A complete topology extended by another | `Topology.as_fragment()` |

**Refactoring.** Each row is added to the typed pieces before the first topology that needs it converts.

### Test rewrite of the ensemble topology

The ensemble topology was rewritten in this design, in a throwaway copy outside the package, to find out whether the design can carry a real topology. The original ships in `substrate.reference`: several model Producers answer one question, and once three answers are in, a judge Producer picks one. The rewrite is 197 lines of scratch code: 142 for the declaration types and the code that connects them to today's builder, 55 for the topology itself. No Producer, View or Trigger in it has a name typed by its author. Nothing in `src/` changed. The files are kept in `evidence-topology-value/` in this folder. `Topology` defines `__call__(self, b)`, which translates the declaration into calls on today's `TopologyBuilder`, so `Runtime.run(topology)` accepts it unchanged.

- `mypy --strict` (2.1.0) passes on the declaration types and on the rewritten topology. Two `type: ignore` comments remain, both in the code that connects to today's builder: one for a dynamically built `tuple[of, ...]`, one because the kernel's current `Producer` Protocol rejects a typed body.
- Four deliberate wiring mistakes are rejected statically: an input mapping returning the wrong type for the started Producer; a predicate reading a misspelled event field (mypy suggests the right one); a View value used as the wrong type; a Trigger starting a Producer with a different input type. A fifth, a body yielding a kind its Producer does not declare, is rejected only when the Producer carries an explicit type annotation; without one the type widens to `Struct`, and the writer still records the event as invalid at run time. A constructor check that compares the body's return annotation with `emits` closes it. A Producer emitting two kinds infers `Producer[None, A | B]`.
- On the real `Runtime` with deterministic responders, the original and the rewrite each finalise with 27 events. Excluding `t`, `crc` and `RunFinalised.run_id`, normalizing instance ULIDs (which differ on every run), and mapping each old name to its derived name (`adjudicator` to `adjudicate`, `member-m0` to `answer-m0`), the events after `RunStarted` show zero differences. `RunStarted` differs in the derived names and in `fingerprint.qualname`.
- The constructor refuses a Trigger that starts an undeclared Producer before any run exists, refuses two Triggers that derive the same name, and raises `FrozenInstanceError` on assignment.

Limits of the test. It covers the ensemble topology alone: one Trigger, one View, no Route, no lifecycle subscription and no composition, without its slow-member option. `session_topology` was not converted.

The rewrite decodes on each predicate call. `msgspec.convert` measured 0.08 µs for one event, and 0.47, 3.6 and 31.5 µs for a tuple of 1, 100 and 1,000 items, against a 100 µs Predicate budget. Per-call decoding of a long buffer is therefore the wrong implementation, and a typed View must hold decoded Structs, decoded once per event.

The rewrite also cannot run twice as written. Running one declaration a second time finalised but fired the judge zero times, because `Once` keeps its `_fired` flag on itself and the Trigger holds that object. The fix, given under "The kernel", is that declarations hold no run state and the Bus keeps it.

## Names and references

Primitive obsession is using a string or number where the domain has a concept. The specific form here is reference by identifier: one thing points at another by repeating its name.

### References between declarations

Every connection in a topology is a string that must equal another string. `api.Subscription(kinds=frozenset({...}))` appears 67 times beside the Struct classes it names. `starts="adjudicator"` must equal a `producer_kind` argument. `ctx.views["..."]` (42 sites) must equal a `b.view` argument, and `staged["failure"]` must equal a Route's slot. A typo fails at run time, or silently never fires.

The replacement passes the object: `on=Candidate`, `start=adj`, `c[candidates]`. In the test rewrite of the ensemble topology, described under "Topology construction", those are checked by the type checker and navigable in an editor. Another project, the data-pipeline tool Dagster, does this and is cited as an example only: its `deps=[daily_sales]` passes the asset object ([vendor documentation](https://dagster.io/docs/guides/build/assets/defining-assets)).

The builder already derives an event's kind from its class (`schema_map[s.__name__] = ...`), and code retypes that string by hand everywhere else. A string appears only on the wire, written by the runtime.

**Refactoring.** Replace Primitive with Object, carried out inside each Strangler Fig conversion. A string copy of a name becomes a reference to the one object: the Struct class, the Producer declaration, the View handle or the Slot.

### Names on the record

The same fault covers each declaration. Every `b.producer_kind("adjudicator", ...)`, `b.view("candidates", ...)`, `b.trigger("adjudicate", ...)` and Route slot is a string an author invents and the record then depends on. Each is a typed-in identifier for something the code already identifies.

| Thing | Name comes from |
|---|---|
| Event kind | the Struct's class |
| Producer kind | the body function, with any leading underscore dropped: `Producer(adjudicate, emits=(Verdict,))` gives `adjudicate` |
| N copies of one Producer | the body function plus real data: `Producer(answer, emits=(Candidate,), key=name)` gives `answer-m0` |
| View | the View's type and what it reads: `kind_buffer(Candidate)`; two equal declarations are one View |
| Trigger | what it starts and its event, in the ratified form `<what it starts>-on-<event>`: `Trigger(on=Candidate, start=adj, ...)` gives `adjudicate-on-candidate` |
| Two Triggers on the same event and Producer | the name of each `when` function; the constructor refuses two that derive the same name |
| Route | its slot and its event, as `<slot>-on-<event>`; an instrument's Route keeps today's `<producer>-stage` form |
| Route slot | a typed slot object: `failure = Slot(FailureReason)`, read as `c[failure]`, which is `FailureReason \| None` because a slot can be empty |
| Fragment namespace | a closed enum member passed at the call: `repair.namespaced(Part.REPAIR)` |

The session's `model-on-tool-result` and `model-wrap-up-on-tool-result` show the two-Triggers case: both fire on `ToolResult` and start the model, and named functions `more_steps_allowed` and `step_limit_reached` tell them apart. The strings on the record are computed once, from these objects, by the runtime.

A name on the record is a public contract, so renaming a private function must not change it silently. Derivation is the default. Where a name is part of a contract, a member of a closed `StrEnum` pins it: `Producer(respond, emits=(Answer,), name=SessionProducer.MODEL)`. That is a typed reference to one definition, with no string literal at the declaration, and the test rewrite's `pinned_name.py` passes `mypy --strict`. The session's Producer kinds, Trigger ids and View names are pinned this way, and any Slot can be, as are the conformance suite's and any others a test or reader relies on, so they keep the names `process/signals/session-vocabulary.md` ratified. Two roles that share one body, such as the two `validate` functions in `swebench_solver`, and Triggers built in a loop use `name=` or `key=`. Derived forms are kebab-case, as the design spec requires of names. A View or Slot name that changes is mapped by the comparison under "Refactoring method". Other topologies' records regenerate with their derived names.

**Refactoring.** No catalog refactoring fits, because the recorded name changes where it is derived, so this is a stated change to the record and not a pure refactoring. A name argument gives way to a computed property or an enum member, and Change Function Declaration removes the string parameter. The constructor gains the check that two declarations do not resolve to one name. A record regenerates only after the comparison under "Refactoring method" is clean.

### String constants and their tests

`session/vocabulary.py` is 685 lines, with `SESSION_STARTED = "SessionStarted"` beside `class SessionStarted` in another file, 21 trigger-id constants and 12 producer-kind constants. Adding one event kind means a constant, a frozenset entry, an `__all__` entry, a Struct and a schema-list entry. `docs/design/string-literal-discipline.md` catalogues 14 antipatterns and prescribes "one constant, one test locks them equal". `scripts/check_status_literals.sh` greps source for literals.

Tests then hold the copies together. `test_kind_constants_match_structs_107` says constants live in leaf modules "so any module can import them without a cycle; that leaves them as strings, so this test is what keeps each one equal to the struct". `test_trigger_names_264` runs a regex over source lines. `test_session_kinds_is_exactly_the_session_structs` walks `vars(session)` for Struct classes and compares them to `SESSION_KINDS`, which proves the constant is derivable.

The discipline document never asks whether the reference needs to be a string. Once connections are objects and names are derived, the event-kind constant tables, the matching tests and the grep gate have nothing to protect, and they go. The session's 12 Producer-kind and 21 Trigger-id constants become the closed enums that pin those names. Generating the constants from the classes would remove the drift and keep a second name for everything.

**Refactoring.** Remove Dead Code, last. The event-kind constants, their frozensets, the matching tests and the grep gate go once the conversions leave them unused.

### Enumerations

`RunStatus`, `Decision`, `RunFailureReason` and `InvalidReason` are `StrEnum`s, and they are right: the values are a closed set and do not name a class. They stay. The same treatment should extend to the places that validate into an enum and then store the raw string, such as `applications/registry.py` and `SessionManifest.workspace_shape`.

**Refactoring.** Replace Primitive with Object, only at the places that validate into an enum and then store the raw string.

### Literals shared across layers

`test_slash_command_exit_matches_session_end_on_exit_sentinel` pins `/exit` because the CLI may not import topologies, so the literal lives in both. A leaf vocabulary module below both layers holds it once. The test exists only because the dependency rule had no place to put a shared word.

**Refactoring.** Replace Magic Literal, then Move Function: one constant in a leaf module below both layers.

## Types at boundaries

A boundary is where untyped data enters typed code. The project's own document states the rule correctly: the "first function that touches an external string maps it to a typed value", and "Downstream code sees only typed values". The rule is applied at the emission boundary and almost nowhere else.

### Producer inputs

A Producer's output is a declared Struct, validated by the writer. Its input is `Any`. `.get("` occurs 809 times in the package, `ctx.event.payload[` 86 times, and `hasattr(inp, "get")` 111 times, the last defending against a non-dict input that cannot arrive. Each edge converts by hand, untyped on both sides:

```python
# best_of_n: the Trigger's input builder
input_builder=lambda ctx: {"round": int(ctx.event.payload["round"]),
                           "slot": int(ctx.event.payload["slot"]),
                           "response": ctx.event.payload["response"]}
# the Producer's body, another file
rnd = int(inp.get("round", 1)) if hasattr(inp, "get") else 1
```

Typed inputs already work. `AppendCycle._producer_input` decodes a Struct input back to its own type, and `test_input_isolation` proves it. Topologies do not use it.

The replacement declares each Producer's input as a frozen Struct, and `Trigger[E, In]` makes the mapping from event to input a checked function. `TypedDict` would give static checking with no decoding at run time, and the product spec's benchmark already chose msgspec over Pydantic, at 3.7 times the decode-and-validate rate. Struct is already the project's decoder and needs no new dependency. Recorded input bytes stay the same, because a Struct with the same field names encodes to the same JSON.

**Refactoring.** Replace Primitive with Object and Introduce Parameter Object, inside each topology's conversion. The input builder first returns a Struct with the same fields as today's dict, so the recorded bytes stay the same. The body then reads fields from the Struct. The `hasattr` guards go last.

### Lifecycle events

Applications must declare frozen Structs. The 12 lifecycle kinds are string constants whose payloads are dict literals built at each site. Consumers then re-parse them: `isinstance(ref, dict) and isinstance(ref.get("instance"), str)` recurs through `projections/`, `StartedCompletedCounts.update` checks `isinstance(event.payload, dict)`, and `producer_kind_from_lifecycle_payload` exists only because the payload is a dictionary.

```python
class TriggerFired(Struct, frozen=True, omit_defaults=True):
    trigger_id: TriggerId
    firing_key: CanonicalValue
    factory: ProducerKind
    instance: InstanceId
    input_sha256: ContentHash
    resolved_input: CanonicalValue | UnsetType = UNSET
    input_blob: BlobRef | None = None
```

One Struct per lifecycle event gives the writer a checked constructor and the readers a typed decode. `msgspec.UNSET` keeps an absent key absent while a `None` still encodes as `null`, as the record has it today; `omit_defaults` alone would drop `"resolved_input":null`. Declaring them as `TypedDict`s would document the shape and leave every reader's checks in place.

**Refactoring.** Encapsulate Record and Replace Inline Code with Function Call. Each lifecycle event gets a Struct, and a Characterization test shows it encodes to the same JSON as today's dict. Emit sites construct the Struct. Readers move to the typed form under "Reading the record".

### Tool arguments

`Tool` is a `NamedTuple` whose `run` takes `list[Any]`. A tool's shape is stated in five places: name constants, `TOOL_NAMES`, suite keys, `_TOOL_SCHEMAS` and the description string. A call reads `T._bash(tmp_path, owner, ["sleep 1; echo built", None, True])`. Named arguments from the model are mapped to positions by `_named_to_positional`, with `None` filling gaps, and unmapped again inside the tool as `a[1] if len(a) > 1 else None`. Tools that need named arguments set an `x-args-passthrough` flag to opt out of the round trip; eight do. `edit` coerces the string `"false"` by hand. Three documents since mid-2026 name per-tool Struct schemas as the next step.

```python
class ReadFile(Struct, frozen=True):
    """Read a file, line-numbered."""
    path: str
    offset: Annotated[int, Meta(ge=1)] = 1
    limit: Annotated[int, Meta(ge=1)] | None = None

read_file = Tool(ReadFile, run=_read_file, deterministic=True)
```

One declaration gives the name, the description, the JSON Schema and the decoder. Checked against msgspec 0.21.1: `msgspec.json.schema(T)` produces the schema, and `msgspec.convert({"flag": "false"}, T, strict=False)` produces `flag=False`, with a path-bearing `ValidationError` in strict mode. The five restatements, the passthrough flag and the hand coercion go away. Keeping the positional list and generating the schema from it would fix only one of the five.

**Refactoring.** Parallel Change with Introduce Parameter Object. Expand: `Tool` accepts an argument Struct or the old list. Migrate each tool. Contract: remove the list path, `_named_to_positional`, the passthrough flag and `_TOOL_SCHEMAS`.

### Results and errors

`parse_tool_call` returns `("tool", ...)` or `("answer", ...)`. `_decide` returns `("evolve" | "spawn" | "exhaust", payload)`. `SafeCanonical` is `ok` plus seven optional fields, and `_resolve` returns a five-tuple. One tool both returns `{"ok": False, "error": ...}` and raises `ValueError`.

Exceptions lose their type at the record boundary and are then parsed back from text: `_error_sentinel` extracts a class name by regex, and `classify_reason_string("CalledProcessError(125,...)")` substring-matches reprs.

A tagged union of Structs replaces each tuple, and `match` reads it. One `ErrorInfo` Struct (`type`, `message`, and `reason` from a closed enum), built where the exception is caught, is what the record stores, so nothing is parsed back from text. Result-type libraries exist for this and would add a dependency for what a small union of Structs already does.

**Refactoring.** Replace Type Code with Subclasses for tagged tuples and flag bags, read with `match`. Replace Error Code with Exception for a tool with two failure paths. Encapsulate Record for `ErrorInfo`, built where the exception is caught, after which the text parsers go by Remove Dead Code.

### Record types and the stderr event channel

Struct, frozen dataclass and `NamedTuple` sit side by side with no rule. The rule: anything that crosses the record is a frozen Struct, in-process configuration is a frozen dataclass, and `NamedTuple` retires. A second event channel of JSON on stderr, with a `boundary` key, carries container and harness events in its own vocabulary outside the bus, and is tested by parsing captured output. Those events belong on the record as declared events, or in the existing off-bus sidecar when they must not affect sequence numbers.

**Refactoring.** Encapsulate Record brings the records under the rule. The stderr events move by Substitute Algorithm to declared events or to the sidecar.

## Depth and information hiding

Parnas decomposed systems by the design decisions each module hides ([1972](https://wstomv.win.tue.nl/edu/2ip30/references/criteria_for_modularization.pdf)). Ousterhout's terms sharpen this: a deep module has a small interface over a large implementation, pass-through layers add interface with no function, and complexity should be pulled downward, away from callers. The largest case in this code, the missing Bus, is under "The kernel".

### The `Responder` interface

`Responder` declares one method, `respond(prompt) -> str`. The code actually uses `respond`, `arespond`, `respond_metered`, `arespond_metered`, `achat_tools`, `achat_tools_metered`, `astream`, `stream_format`, `system_channel`, `command`, `context_tokens`, `name` and `_model`, found by `getattr` at each call site. `call_responder` branches on `system_channel`, then on `arespond`, then on `isinstance(responder, DeterministicResponder)`, then falls back to a thread. `call_responder_metered` repeats the walk for metered calls and reads the private `_model`. `resolve_driver_context` tests `type(responder).__name__ == "DeterministicResponder"`. `EnsembleResponder` branches on which of four method combinations is present.

The Protocol states one method, so every caller probes for the rest.

```python
class Responder(Protocol):
    async def respond(self, request: ModelRequest) -> Reply: ...     # Reply always carries usage

class StreamingResponder(Responder, Protocol):
    def stream(self, request: ModelRequest) -> AsyncIterator[StreamItem]: ...

class ToolCallingResponder(Responder, Protocol):
    async def call_tools(self, request: ModelRequest, tools: ...) -> ToolReply: ...
```

One wide Protocol would force every stand-in to implement everything. Narrow Protocols ([PEP 544](https://peps.python.org/pep-0544/)) state the capabilities once. Python's `runtime_checkable` check looks only at the presence of attributes, ignoring signatures, so it cannot tell a sync method from an async one. Each adapter therefore declares its capabilities at construction, and `isinstance` only narrows types. System text is a field of `ModelRequest`. The sync and metered duplicates disappear into one method, and a blocking implementation is wrapped once at the edge.

The deterministic stand-in's special path exists to keep CI records byte-identical by completing without yielding. That requirement belongs inside the stand-in's own `respond`.

**Refactoring.** Branch by Abstraction, with the new Protocols as the abstraction and each adapter as a supplier. Change Function Declaration merges the plain and metered methods into one that always returns usage. Replace Conditional with Polymorphism turns the branches in `call_responder` into each adapter's own `respond`, and the `getattr` probes into capabilities the adapter declares. Decorators move last.

### Long parameter lists

`start_build` takes 13 parameters and relays them into `session_topology`'s 31. `_session_started_factory` takes 17 to forward into one Struct. `swebench_solve_and_grade_topology` takes 17, retyped by each arm factory. In all, 37 functions take eight or more. `session_topology`'s own comment says four of its parameters "are placeholders on the daemon's call-site contract". Tests restate the same keyword arguments in 15 files.

A frozen `SessionConfig` passed whole removes the relaying, gives the tests one builder for it, and is hashable, which preregistration needs. Grouping into several smaller configs comes after that, where natural clusters appear: driver, workspace, prompt. `**kwargs` forwarding would shorten the signatures and lose every check.

**Refactoring.** Introduce Parameter Object, then Preserve Whole Object as each layer stops unpacking it. Clusters split out afterward by Extract Class.

## The kernel

No. `src/substrate/kernel/` fails all three meanings of the word. One kernel property, a single path to the log, is real.

What the folder holds is a run engine: an in-process event log with one writer and a rule evaluator attached, running on one asyncio event loop, next to a small library of Views and termination recipes.

### How a run works

`Runtime` is single-use, and everything starts in its `_drive` method.

1. `_drive` calls `builder = TopologyBuilder(); topology(builder); reg = builder.build()`. It takes the lock if the run is persistent, recovers any torn tail on the record, and opens a `RecordWriter`. It then creates a `RunState`, publishes itself in a process-global dictionary keyed by record path, sets a ContextVar to itself, and creates an `AppendCycle`.
2. `_bootstrap` runs the cycle on `RunStarted`, which becomes sequence 0. For each initial Producer it records a `TriggerFired` and adds the Producer to `RunState.scheduled`.
3. `_flush_scheduled` turns each scheduled Producer into an `asyncio` task running `_producer_task`. That task posts `ProducerStarted` to the inbox, calls the factory to get the body, and iterates `async for obj in start(inp)`. Each yielded object goes to `_submit_emission`, which acquires a credit from a semaphore and puts an `_Emission` on the inbox. The inbox itself is an unbounded `asyncio.Queue`; the semaphore is the bound the specification calls the admission queue. Lifecycle messages skip the semaphore, so a full queue cannot block the writer's own bookkeeping.
4. `_writer_loop` waits on the inbox with a 10 ms timeout. When the timeout expires and nothing is running or queued, the run is quiescent and the TerminationPolicy is asked what to do. When work arrives, the loop drains everything ready into a batch and, for each item, releases its credit, calls `AppendCycle.cycle`, starts any newly scheduled Producers, and consults the TerminationPolicy.
5. `AppendCycle.cycle` runs six steps with no `await` between them, so no Producer can run during a cycle:
   - **Validate.** `_resolve` checks that the object is a Struct whose class name the Producer declared, canonicalizes it, and writes it to the blob store if it exceeds 16 KiB. A failure becomes a `ProducerEmittedInvalidEvent` that continues through the cycle.
   - **Number and append.** `_emit` assigns the next sequence number, builds the envelope, and passes it to `RecordWriter.append`, which frames it with a CRC, writes it and applies the fsync policy.
   - **Update Views.** A loop over every View calls `update` on those whose subscription matches.
   - **Stage Routes.** A loop over every Route writes matching transforms into `RunState.staged`.
   - **Evaluate Triggers.** A loop over every Trigger runs its predicate under a time budget, applies the cooldown and firing policy, runs the input builder, canonicalizes the input, queues a `TriggerFired`, and schedules the Producer.
   - **Drain control.** The cycle calls itself on each queued control event, in order.
6. When the TerminationPolicy returns finalise, the writer appends `TerminationMatched` and `RunFinalised`. The `finally` block in `_drive` cancels the tasks, writes the manifest, closes the record, releases the lock and removes the runtime from the global dictionary.

### The kernel against three definitions

| Meaning of kernel | Test | Result here |
|---|---|---|
| A protection boundary, as in an operating system | Untrusted code cannot touch kernel state or stop the kernel | **No.** Producers are arbitrary Python in the same process and on the same event loop. Predicates and Views run inside the cycle. The technical specification says plainly that there is no sandbox. A Predicate that blocks holds the writer and every Producer until it returns, and a Producer that blocks the loop does the same. `MappingProxyType(self._reg.views)` makes the dictionary read-only, but its values are the live View objects, so a Predicate can call `update` |
| Minimality: Liedtke's test, "a concept is tolerated inside the µ-kernel only if moving it outside the kernel, i.e. permitting competing implementations, would prevent the implementation of the system's required functionality" ([SOSP 1995](https://cgi.cse.unsw.edu.au/~cs9242/22/papers/Liedtke_95.pdf)) | Everything in the folder must be there, and everything that must be there is in the folder | **No.** His test asks what may stay inside. `views.py` imports only `constants` and `types`. `policies.py` imports nothing from Substrate at all. Both could live outside with no privilege. By extension of his test, `kernel/` also leaves out what it needs: it imports `record/` and `encoding`, without which no cycle can run |
| The small core everything else builds on | The core is small and separate | **True of the idea, false of the folder.** `substrate_v14_kernel.py` states the cycle in 248 lines including its checks. The folder's 2,864 lines mix that core with library code and `runtime.py`'s many jobs |

The word also means four different things in the project. In `substrate_v14_kernel.py` it is the minimal executable semantics. In the technical specification it is the whole runtime including record framing ("~80 lines of code in the kernel"). In the code it is one folder. In the product specification's package-name decision it is a name that was free on PyPI, `substrate-kernel`, because `substrate` was taken.

One property of a kernel is real: every event reaches the log through one writer, is validated there, and gets its number there. No Producer holds a reference to the record. The technical specification states it as "exactly one append path". The code has one writer at a time but six places that build an envelope and write it. `_emit` is the normal one. `_view_failure`, `_try_record_kernel_error` and `_fail_stuck_quiescent` each build a dictionary literal and call the record directly, each advancing `next_seq` by hand. `append_at_rest` builds two more outside any run, under the lock.

The product specification says "The product is the runtime, not a topology catalogue". Runtime-proper modules are 6,392 lines, 16% of the package. Topologies are 18,674 lines, 47%, including a 5,341-line session harness in the same import namespace.

### The Bus

The Bus is the specification's central object. In the code, admission is `RunState.inbox` plus `RunState.credits`, sequencing is `RunState.next_seq` and `in_cycle`, the control queue is `RunState.control`, the log is `RecordWriter`, submission is `Runtime._submit_emission`, and the cycle is `AppendCycle`. `AppendCycle` lives in `sequencer.py`. A reader looking for the Bus finds no file, class or function with that name.

Replace them with one `Bus` class that owns admission, the control queue, the sequence counter, the cycle and the log:

```python
class Bus:
    async def submit(self, producer: ProducerRef, payload: Struct) -> None: ...   # takes a credit
    def post(self, event: LifecycleEvent) -> None: ...                            # skips the credit
    def run_cycle(self, pending: Pending) -> Event: ...                           # the six steps
```

A Bus that merely forwards to `RunState` would add a layer and hide nothing, so the fields move into it and `RunState` stops existing. Keeping `AppendCycle` and renaming it `Bus` is the cheaper option, and it fails because submission and admission would stay in `Runtime`. The specification's three-part description (admission queue, log, Views) gives the internal division.

**Refactoring.** Combine Functions into Class and Move Function. `AppendCycle` is the seed. Admission and `_submit_emission` move into it, then the writer loop, then the renamed class takes its fields from `RunState`.

### `RunState`

`RunState` holds about two dozen mutable fields that `Runtime` and `AppendCycle` both read and write. Its docstring says "extracted from the Runtime God-class" and "only their HOME changed", which is accurate: the extraction moved the fields and hid no decision. `Runtime` also calls `self._cyc._producer_input` and `self._cyc._maybe_offload`, private methods of the object it delegates to, and `session_registry` reads `runtime._st.kind_by_instance`.

Each field should belong to the class that makes decisions about it: `next_seq`, `control`, `staged`, `counts` and quarantine state to `Bus`; `tasks`, the three `*_by_instance` maps and `cancel_reasons` to a `ProducerSupervisor`; `phase` and the final event to `Runtime`. The supervisor exposes `live_instances()`, which is what five tests and the session registry currently reach into private state to get. Splitting the bag into smaller dataclasses would keep the sharing and multiply the names. Moving the fields to their deciders removes the sharing.

**Refactoring.** Move Field, one field at a time, each to the class that decides it, then Inline Class. Hide Delegate replaces outside reads of `_st` with queries on the owner, such as `live_instances()` and a phase query.

### `Runtime`

`runtime.py` is 1,149 lines covering run lifecycle, locking, recovery, manifest construction, Producer supervision, wall-clock and event-count budgets, the writer loop, termination, cancellation, event injection, a process-wide registry of active runtimes, and a ContextVar. `append_at_rest`, a record operation that knows what a pause looks like, is a module function beside them.

Each job moves:

| Job today in `runtime.py` | Moves to |
|---|---|
| Producer tasks, budgets, cancellation | `ProducerSupervisor` |
| Writer loop | `Bus` |
| Manifest construction | `Topology` supplies its section of the manifest, and `Runtime` writes the whole with `run_id`, `name`, `baseline` and `config`; one type reads it back |
| Recovery, locking | the log package |
| `append_at_rest` | `Record` |
| Global runtime map, ContextVar | removed; callers hold the `Runtime` they started |

`Runtime` then wires a Topology, a Bus, a supervisor and a log together and returns a `RunResult`.

**Refactoring.** Extract Class for the `ProducerSupervisor`, and Move Function for the other jobs in the table. `Runtime` shrinks as each job leaves and keeps its public methods throughout.

### Envelope construction

Every write site builds the same dictionary. Three of them advance `next_seq` by hand. One `Bus._append(kind, payload, producer)` builds the envelope, assigns the number and writes, and the failure paths call it too. That makes "exactly one append path" true of the code. `append_at_rest` becomes the one case that runs without a Bus, and it should be written as a `Record` method that shares the same envelope constructor.

**Refactoring.** Replace Inline Code with Function Call. The failure paths differ today in when they advance the sequence and in which run fields they set, so Characterization tests pin those frames and results first.

### Run state in firing policies and Views

`Once` stores `_fired` on itself, `PerKey` stores `_seen`, and every View stores its accumulated values. Those objects live in `Registration`. This works today only because a topology is a function: each run calls it and gets new objects. The technical specification places firing state with the writer, on the grounds that it can be rebuilt from the record.

A topology that is a reusable declaration cannot hold run state. The declaration must say which policy applies and the Bus must keep the state per run: `Once()` becomes a frozen description, and the Bus holds a `fired` set keyed by Trigger. A View declaration carries a factory, as the test rewrite's `View.make` does. Copying the policy objects at the start of each run would also work and would leave state in objects that a reader has to know were copied. Firing state stays fresh per run and per resume, as it is today. The technical specification describes rebuilding it from the record, keyed on `trigger_id`; that difference between code and spec is logged and closed in its own change.

**Refactoring.** Separate Query from Modifier, because `admit` both decides and changes state, then Move Field, which takes the fired flag and seen keys to the Bus. Views in the declaration become factories, one per run. A test runs one declaration twice.

### Subscription dispatch

The cycle loops over all Views, all Routes and all Triggers and calls `subscription.matches` on each. The technical specification defines a subscription index built once at registration, a pair of dictionaries by kind and by Producer, so that the cost per event follows the number of matches and not the number registered. With a frozen Topology the index is computed once in its constructor, and the cycle reads it. A cache inside `matches` would save little and would still visit every subscriber.

**Refactoring.** Substitute Algorithm. The index is built in the `Topology` constructor and the three loops read it. The performance floor test and the Golden Master records guard it.

### Library code in the kernel

`views.py`, the recipes in `policies.py`, `composition.py` and the name registry in `topology.py` use only public interfaces. They move out to `substrate.views`, `substrate.termination` and `substrate.composition`, as do the Predicate combinators and `log/attach`, which never writes. `record/`, `encoding.py`, `errors.py` and `constants.py` move in. Private kernel code moves to `_internal` modules, and an import contract forbids the standard library from importing them; import-linter's contracts work on modules, not names. That gives "nothing above the kernel is privileged" a check that fails when it stops being true.

Three choices were open for the word itself: drop it for `core`, keep the folder and redefine the word in the docs, or make the folder satisfy the definition. The third is right because every specification already uses the word, and it costs only the moves above.

**Refactoring.** Move Function in both directions, with the import contract added as each module settles.

### Protection boundary

Giving Producers real isolation would mean running them in subprocesses or containers, and Predicates would then have to cross a process boundary inside a cycle that must not await. The specifications chose in-process execution, so the kernel should not claim protection it lacks. Two small gaps can close. Author callbacks should receive decoded values through typed handles and never the View object, so a Predicate cannot call `update`. And the docs should state the guarantee that exists: one writer, one numbering, validation at the boundary, inside one trusted process.

**Refactoring.** Encapsulate Collection: author callbacks receive decoded values through typed handles, and the mapping of live View objects stops being visible. The docs change to state the guarantee.

## Module organization and dependency direction

"Your architectures should tell readers about the system, not about the frameworks you used in your system" ([Martin](https://blog.cleancoder.com/uncle-bob/2011/09/30/Screaming-Architecture.html)). Martin's own argument puts use cases at the top level; the layered tree below has its own grounds, the kernel's independence from its applications. Dependencies should run one way, so that a reader can understand a lower layer without knowing what sits above it.

### Package root

`src/substrate/` holds core definitions (`constants`, `encoding`, `errors`, `types`, `protocols`) beside two facades (`api`, `app`), application support (`bundles`, `home`, `naming`, `interpreter`), an HTTP client for a daemon outside this package (`_daemon`), authoring tools (`templates`, `testing`), the CLI, and packages (`kernel`, `record`, `projections`, `adapters`, `reference`, `conformance`, `language`, `assay`, `topologies`). A file's position says nothing about its rank.

The real rank is written down in exactly two places, neither of them in the tree: a `layers` contract in `pyproject.toml` with eleven levels, and a `GROUPS` dictionary in `scripts/gen_api_docs.py`. The contract is good practice, and the note beside it records that before 2026-10-08 topologies and assay imported each other.

The replacement makes the tree state the layers: `kernel/`, then the standard-library modules (`views`, `termination`, `joins`, `composition`, `record`, `replay`), then `models/`, `tools/`, `session/`, `topologies/`, `assay/`, `cli/`. Application support moves into the layer that uses it: `bundles`, `naming` and `templates` into `session/`, `interpreter` and `_daemon` into `cli/`.

Two organizing rules compete. Packaging by layer gives clear dependency rules and scatters a feature across folders. Packaging by feature keeps a feature together and hides the layers. The hybrid fits this system: layers at the top, because the kernel's independence from its applications is the design's main claim, and features inside the layers that hold many of them, with one package per topology and one per benchmark.

**Refactoring.** Move Function, one module at a time, in the order the import contract allows. The contract changes with the tree.

### Contents of `topologies/`

`topologies/` has 29 entries. Fifteen are topology packages. Seven more are directories that hold only committed records and no code: `best_of_n_verified`, `daily`, `fanout_review`, `game_of_life_glider`, `natural_conversation_bare`, `research_sweep`, `swebench_repair`. The other seven are something else:

| Entry | What it is | Where it belongs |
|---|---|---|
| `session_registry.py`, 1,799 lines | A daemon service: manifest persistence, a name index, locks, turn dispatch, queues, a boot scan | `session/service.py` |
| `workspace.py` | A git utility | `session/` |
| `bundled.py` | The registry of named topologies | `topologies/__init__.py` |
| `conversation.py` | An engine several topologies share | `topologies/_shared/` |
| `instruments/` | Side Producers shared by conversation topologies | `topologies/_shared/` |
| `runs/` | Build, review and hold operations on sessions | `session/runs/` |
| `applications/`, a name the project ratified | Three topologies, a session opener and a TOML parser | The folder stays and holds the three topologies; the opener and the parser move to `session/` |

The records-only directories move together under `topologies/_records/`, because `substrate demo replay` reads them through `bundled.record_path` and `test_committed_record_is_current` checks them. A `_shared` folder is a small concession to the rule, and the alternative of a top-level `engines/` package would put a layer between `topologies/` and its own helpers.

**Refactoring.** Move Function for the modules and the committed records, with `bundled.record_path` and their test updated to the new path.

### Import cycles

Of the 188 imports inside functions, 103 are in `topologies/`. Some are harmless habit, such as `import json` in a body. Many exist only because two packages depend on each other: `session/__init__.py` ends with seven imports marked `# noqa: E402`. A function-local import turns a module-load error into a run-time surprise, and it hides the dependency from the import contract.

The cycle has four causes:

| Cause | Cure |
|---|---|
| `session/vocabulary.py` imports tool-name constants from `tool_loop.tools`, while `tool_loop` is supposed to sit below `session` | Tool identity moves into `tools/`, which knows nothing of sessions, and `session` imports it one way |
| `tool_loop/delegate.py` imports `session_registry` and `session.vocabulary`, because the delegate tool starts a child session | `delegate` is a session operation; it moves to `session/` |
| `session/__init__.py` imports `compose_run` and `first_message` from `runs.run` inside functions and `RunSpec` under `TYPE_CHECKING`, while `runs` imports `session` | `RunSpec`, a plain record, moves to `session/`. `session_topology` accepts a finished fragment instead of knowing how to compose a run |
| `session_registry` imports `runs.hold` and `tool_loop.background` inside functions to clean up when a session ends | The service takes a list of end-of-session callbacks, registered by whoever owns the table |

The existing `layers` contract then extends inside `session`, `tools` and `topologies`. Keeping the local imports and adding a lint for them would record the problem without fixing it. `home.py` exists as a separate module only so `bundles` need not import `api`; it stops being needed when `bundles` moves.

**Refactoring.** Mikado Method to find the order: attempt a move, note what breaks, revert, and do the prerequisites first. Move Function for the four causes in the table. The session service takes end-of-session callbacks in place of importing their owners. Function-local imports move to module level as each cycle goes, and the contract extends inward.

### `api.py`

A Facade offers a simpler interface over a subsystem. `api.py` exports 119 names from 21 modules with no grouping in the namespace, so it is the same surface, flattened. Lifecycle constants sit beside exceptions, fsync policies and bundle loaders. Its comments divide `__all__` into informal groups, `gen_api_docs.py` re-creates those groups as 16 hand-written sections to document it, and `import substrate` yields only `__version__`. The product specification asked for something much smaller: the primitives, `Runtime`, standard Views, standard policies and the conformance helpers.

The replacement has two levels. `substrate` exports the nine pieces, `Topology` and `Runtime`, the words a reader expects to import:

```python
from substrate import Producer, Trigger, Route, View, Topology, Runtime
from substrate.views import KindBuffer
from substrate.termination import any_of, all_completed
from substrate.record import Record
```

Everything else lives in a named public module: `substrate.views`, `.termination`, `.joins`, `.composition`, `.record`, `.replay`, `.errors`, `.testing`. A better-commented flat file would leave one namespace of 119 names. Importing directly from internal modules would expose every private module as public surface. Named modules give readers the groups the documentation script already had to invent, and the docs script then reads the modules and needs no hand-written list.

**Refactoring.** Remove Middle Man. Named public modules appear first, callers move to them, and `api.py` goes when nothing imports it.

### `app.py`

`app.py` was added so the CLI could reach applications while importing only "public" modules. Its docstring says the kernel's facade used to depend on the applications above it, which was a real fault, and a test comment records that the CLI earlier reached topologies through `importlib.import_module` "with a comment saying it did so to pass this contract". The second facade met the letter of the rule. It exports a mix: session classes, tool-kind strings, language catalogs, a template renderer, an interpreter fix for a packaged app.

The replacement is that `session`, `topologies` and `assay` each define `__all__`, and the CLI imports those packages by name. The import contract then says what is true: the CLI may depend on any public layer. The original goal, that the CLI uses nothing private, holds because private code lives in separate `_internal` modules, which an import contract can forbid; import-linter's contracts work on modules and have no notion of public names.

**Refactoring.** Remove Middle Man, the same way. Each layer declares `__all__`, the CLI imports it, and the import contract is rewritten to match.

### `cli.py`

One file holds 58 functions covering run, tail, inspect, narrate, language, handoff, replay, validate, stats, conformance, resume, demo, score, a chat REPL, daemon spawn, a bundle wizard, an installer, a config loader, an SSE parser and a 170-line slash-command router. A bare `substrate` opens the chat, so the runtime's default verb is an application.

The replacement is a `cli/` package with one module per command group: `cli/run.py`, `cli/inspect.py`, `cli/session.py`, `cli/bundle.py`. Splitting alone would only spread the same code around, so the logic also moves to the layer it belongs to: `validate`'s checks go into the `Topology` constructor, the SSE parser and daemon client go beside each other, and slash commands become a table of command objects instead of a chain of `if` statements.

**Refactoring.** Extract Function and Move Function, command group by command group. Replace Conditional with Polymorphism turns the slash router into a table of command objects.

### Test layout

A test named `test_fewer_producers_263` records when it was written. The tests of prompt building are spread over six files told apart only by sprint numbers. Helpers are copied because `tests/` has no support module: `_turn` in 15 files, scripted responders in at least 10, `_require_model` in 9.

The replacement mirrors the package (`tests/kernel/`, `tests/session/`, `tests/topologies/`), names each file for the behaviour under test, and adds `tests/support/` for the session driver and the scripted responders. Sprint numbers stay in git, which already has them. Renaming the files in place without moving helpers would fix the names and keep the duplication.

**Refactoring.** Extract Function and Replace Inline Code with Function Call for the shared helpers first. Then Move Function for the files into a tree that mirrors the package, section by section as the code they test moves.

## Composition and reuse

Parts should combine through a stated interface, in a way that keeps one part's names from colliding with another's, and each rule should have one home.

### Reuse through a shared builder

`best_of_n_correction(b, ...)` registers four Producer kinds with fixed names (`seeder`, `drafter`, `validator`, `judge`), a View named `verdicts`, four Triggers and a termination policy on whatever builder it receives. Called twice on one builder, the second call silently replaces the first's Producers, because `producer_kinds` is a dictionary, and appends duplicate Triggers. Parameters accumulate to bend it: `seed_on`, `draft_input_extra`, `termination`, `validator_schemas`, `judge_schemas`.

`fanout_review` decorates a topology by calling `inner(b)` and then registering more. `compose_run(b, spec, own_record=...)` is a third form of the same thing.

The replacement is a `Fragment`, a frozen declaration with Producers, Views and Triggers but no termination and no initial Producers. `Topology` is a Fragment plus those two:

```python
repair = best_of_n(n=3, max_rounds=2, draft=drafter, validate=validator)     # Fragment
solver = Topology.of(localize, repair.namespaced(Part.REPAIR), select,
                     initial=[Initial(localizer, case)],
                     termination=finalise_on(SelectedPatch))
```

Two other graph systems show the idea and are cited as examples only. Akka's partial graphs "return the set of yet to be connected ports" and LangGraph keeps subgraph state "under a namespace of the parent thread" (both vendor documentation: [Akka](https://doc.akka.io/libraries/akka-core/current/stream/stream-graphs.html), [LangGraph](https://docs.langchain.com/oss/python/langgraph/graph-api)). `namespaced(Part.REPAIR)` prefixes kinds and View names with the value of a closed enum member, since a declaration cannot know which function built it. A complete `Topology` that another topology extends, as `fanout_review` and `session/ci.py` do today, becomes a Fragment through `as_fragment()`, which drops its initials and termination for the caller to set.

The recorded rule that new session-like topologies start as a literal copy of `session/` is a separate, standing decision about how those are authored. The BLACKBOARD also records that the driven end of a turn is composed onto the one session topology. Fragments replace the builder-mutation sites listed here.

**Refactoring.** Change Function Declaration: a function that takes `b` becomes a function that returns a Fragment. For a while the Fragment also translates itself onto a builder, as `Topology` does, so callers can move one at a time by Strangler Fig. `namespaced()` comes when two parts first need it.

### Termination in composed parts

`b.termination` assigns one field, so the last caller wins. `session/ci.py` calls `_ci_base()(b)` and then `b.termination(...)`, with the comment "Overwrite session_topology's pause_await_input termination". `swebench_solve_and_grade` does the same with an eight-line comment. `assemble.py` passes `termination=api.quiescence()` to `best_of_n_correction` as a placeholder that never fires, so the argument can be overwritten later.

A Fragment has no termination field, so this cannot happen. Raising an error on a second `b.termination` call would catch the accident and leave the fragment-setting-termination shape in place.

**Refactoring.** Move Statements to Callers. The `termination` argument and each overwrite move to the code that builds the whole Topology, and Remove Dead Code takes out the placeholders.

### Same-bus merge and embedding

`embedded_substrate(_inner_topo, exports={"Tick": OuterTick})` is the one composition mechanism with a real boundary: the inner run has its own writer, log and root, and only mapped kinds cross. The solver's design document intended repair to be nested this way, and it was built by builder mutation instead.

Neither form replaces the other. A same-bus merge is right when the parent's Predicates must read the child's events, as the solver's select step reads every candidate from the repair loop. Embedding is right when only exports should cross, because the inner run is a sealed unit with its own record. Merge a Fragment by default, and embed when the parent needs only the result.

`embedded_substrate` itself needs one change. Its export map travels as `start.__substrate_export_map__`, an attribute on a callable, and `producer_kind` calls the factory at registration to fish it out with `getattr`. In this design the export map is a field of an `Embedded` Producer declaration, keyed by Struct class (`exports={Tick: OuterTick}`), and the manifest reads it directly. The required `inner_root` key, read from an untyped input dictionary, becomes a field of a typed input Struct.

**Refactoring.** Move Field for the export map, from an attribute on a callable to the declaration. Replace Primitive with Object for the `inner_root` key.

### Fan-in

A round finishes when all N verdicts are in, and that is written by hand in each topology that needs it:

```python
predicate=lambda ctx: len(_round_verdicts(ctx, int(ctx.event.payload["round"]))) >= n
```

`best_of_n`, `coding_flow`, `code_review` and `swebench_solver/assemble.py` each spell a variant, and `repro_base_validate.py` warns that omitting one emission "would deadlock the barrier". The specification treats progress gating as a pattern and not a primitive, so the kernel should stay as it is. The standard library should have a join:

```python
round_done = Join(on=Verdict, key=lambda v: v.round, count=n)
Trigger(on=Verdict, start=judge, when=round_done.complete,
        input=lambda c: JudgeInput(c.event.round, c[round_done]))
```

`Join` is a View plus a predicate, built on public interfaces. A primitive would widen the kernel for something the existing pieces can express, and that is the reason the specification gave for leaving it out.

**Refactoring.** Extract Function for each arithmetic check, Extract Class for `Join`, then Replace Inline Code with Function Call at the sites listed.

### Failure handling in Producers

57 sites are marked `# noqa: BLE001`. Some Producers swallow exceptions and emit an empty result, others let them propagate, and the choice has reversed over time: the solver's rewrite removed the swallowing from its own bodies, and application topologies kept it. What a failed Producer means is a property of the topology, and it is buried inside bodies.

A Decorator over a Producer body declares it, in the same way `RateLimitedResponder` already wraps a Responder:

```python
drafter = Producer(on_failure(draft, emit=Candidate.failed), emits=(Candidate, ModelUsage))
```

The kernel's behaviour stays the same: an unhandled exception becomes `ProducerFailed`, and the decorator is only for a Producer that must keep the round going. A runtime-level retry option would hide a decision from the record, which the specification rejects.

**Refactoring.** The Decorator pattern (Gamma et al.). Extract Function takes each body's `try`/`except` out, and the Decorator holds it. A Characterization test pins each Producer's failure behaviour first, because the bodies differ today.

### Duplicated helpers

`_Factory` is redeclared in 26 modules, even though `ProducerFactory` exists for that purpose, and it disappears with typed Producers. `_git` is written four times and belongs in one module. `coding_flow` and the retired solver topology retype the Producers and Triggers of `best_of_n_correction`, and the Fragment gives them one home. `test_session_registry_consolidated_099` records a real case of a copied module and its original drifting apart until they behaved differently.

**Refactoring.** Replace Inline Code with Function Call against one home for each helper, and Inline Variable for the `_Factory` aliases.

## Control flow, closures and long functions

State that governs behaviour should have a name. A closure holds state with no name for its fields, which suits small things and hides large ones.

### Session state machine

`session_topology` has 31 parameters and 717 lines, of which the nested `topo` function is 507. Its 19 `b.trigger` calls and one `b.instrument` call implement a state machine: turn open, session prompt, skill fragment, model step, tool, language measurement, return, end. No state type exists. A state exists only as a conjunction spread over Triggers:

```python
predicate=lambda ctx: (
    _producer_kind_from_ref(ctx) == PRODUCER_KIND_SESSION_PROMPT
    and int(ctx.views["user_turns"].value()) > 0
    and _turn_open(ctx)
    and _skill_of(_turn_message(ctx)) is None
),
```

The machine has to be reconstructed by reading all 20 predicates and holding them in mind. `_turn_open` is itself defined later in the same function and reached by late binding. The same model-start input dictionary is written at three Triggers.

Three replacements are possible. A state-machine library holds state off the log. Classes in the State pattern are runtime objects, again off the log. A reducer View is the specification's own idea, since all state lives on the log and Views are its projections:

```python
class TurnState(Struct, frozen=True):
    phase: Phase
    turn_index: int
    step: int

def advance(state: TurnState, event: Event) -> TurnState: ...   # pure; one place

Trigger(on=(ProducerCompleted, ProducerFailed), start=model,
        when=phase_is(Phase.READY_FOR_MODEL), input=model_input)
```

`advance` is a pure function, so the whole machine can be tested as a table without running a topology, and it fits on one page. Naming each conjunction as a helper would be a cheap improvement, and it would still leave the transitions scattered.

**Refactoring.** Extract Function names each conjunction. Extract Function builds `advance` as a pure function, and a View calls it beside the existing Triggers. Characterization tests over session records show the View and the predicates agree. Substitute Algorithm then moves each Trigger onto the phase.

### Producer factories and closures

`_return_factory() -> Callable[[], Any]` defines `_return` and returns `lambda: _return`, three levels to yield one event. There are 70 `*_factory` definitions. The design spec chose this ("Producer state, if any, lives in closures over the factory"). The same closures are why `Arm.build` cannot be identified, and why the manifest's fingerprint for most Producers reads `_candidate_factory.<locals>.<lambda>`.

The design spec gives configuration captured at registration as the factory's reason. Almost no Producer needs a fresh factory per instance, because state lives on the log. A stateless Producer is the async generator itself, passed directly. Where configuration matters and identity must be visible, a frozen dataclass whose fields are the configuration and whose `__call__` is the body can be hashed and canonicalized, so preregistration can hash an arm directly and `params_by_arm` goes away. Small closures with nothing to identify can stay.

**Refactoring.** Inline Function removes a factory that only returns its body. Replace Function with Command turns a closure whose configuration matters into a frozen callable object.

### Modes inside Producer bodies

The `tool_loop` model body is a 110-line generator with several modes: walkthrough with native tools, walkthrough with text, script, and a default calculator. CI stand-ins live inside production Producers in `instruments/`, deriving results from a hash while discarding the model's reply, even though `Responder` exists to be that seam.

Strategy behind the `Responder` boundary replaces them. A script is a `ScriptedResponder`, the calculator demo is a `ScriptedResponder` with two calls, and production bodies have one path. A `walkthrough: bool` parameter to a topology then has nothing to switch.

**Refactoring.** Replace Conditional with Polymorphism moves each mode behind a Responder. Remove Flag Argument takes out `walkthrough`.

### Dispatch on kind strings

`_render_turns` is a 60-line `if`/`elif` over kind strings with `isinstance(payload, Mapping)` guards. `_inspect_record_impl` is 160 lines on a format string, and `_slash_route` is 170. With a closed union of Structs, `match` reads the same and the type checker can say when a case is missing. A registry of handlers suits the open-ended case, such as slash commands; `match` suits the closed one.

**Refactoring.** Replace Type Code with Subclasses for the closed sets, read with `match`. Replace Conditional with Polymorphism for the open ones.

### Long functions

137 functions exceed 50 lines and 35 exceed 100. Most long ones are long because they hold the wiring or dispatch already covered above, and they shrink when those change. A line limit applied first would cut them along arbitrary seams.

**Refactoring.** Extract Function, last, on whatever is still long after the other changes.

## Ambient state

A dependency passed as a parameter is visible in the signature. One reached through a global is visible only on reading the body.

### ContextVars

`_CURRENT_RUNTIME` lets a tool find its runtime. `_BASH_PROGRESS_CTX`, named for one tool, is used by every tool and read by `runs/hold` to find a call id. `_TOOL_CANCEL_HOOKS` carries cancellation. The tool producer sets the last two by hand around each call, and a test sets one by hand in a thread.

```python
class ToolContext(Struct):
    runtime: RuntimeHandle
    call_id: CallId
    report_progress: Callable[[str], None]
    on_cancel: Callable[[Callable[[], None]], None]

def run(args: ReadFile, ctx: ToolContext) -> str: ...
```

A dependency-injection framework would add machinery and a dependency for what a parameter does. A ContextVar is the right tool only for something per-task that must be read deep inside code that cannot take a parameter, and nothing listed here is that: Substrate writes both ends of every one of these calls. A Producer body that needs its own record path, as the session's model step does, is a `ContextBody`, which takes a `RunContext` from the runtime as its second parameter; the path is never recorded, because a recorded path would tie the record's bytes to where it sits.

**Refactoring.** Replace Query with Parameter and Introduce Parameter Object. `Tool.run` gains the context object by Parallel Change, each tool moves over, and the ContextVars go.

### Process-wide tables

`_REGISTRY`, two different module-level `TABLE`s, `_CHANNELS`, `_semaphores`, `_context_cache` and `_ACTIVE_RUNTIMES_BY_RECORD_ROOT` are all process-wide. Tests show the cost: `hold.TABLE = table` inside `try`/`finally`, `_reset_semaphores_for_tests()` in a production module, `patch.object(session_mod.api, "any_of", ...)`.

The session service owns the tables that are about sessions and hands them to what needs them. Topology registries become values passed to the CLI. `_ACTIVE_RUNTIMES_BY_RECORD_ROOT` exists so a daemon can reach a child's runtime for an interrupt; the session service that started the child already holds its handle. A rate limiter's semaphores belong to the limiter object.

**Refactoring.** Encapsulate Variable first, so every use goes through one function. Move Field onto the owning object. Replace Query with Parameter where a caller reached the table directly.

## Reading the record

A log is the write model. Readers need a read model built on it, and should not have to know the storage format.

### Record reader functions

`record.py` exposes `read_record`, `read_range`, `read_first_envelope`, `read_last_envelope`, `has_torn_tail`, `recover_open_segment`, `recover_and_read`, `resolve_blob_payload` and `load_envelopes`. Each re-derives the path and returns dictionaries. Every function in `projections/` takes `record: Any`, meaning a path or an iterable, and calls `load_envelopes` first. A caller who wants the provenance of one Producer and then the graph reads the record twice.

The technical specification defined `load_record -> RunRecord`. A later amendment to the product spec relaxed it to the shipped `read_record` over dicts, naming the "stringly-typed read surface" and deferring a typed object. The specification moved to match what got built.

```python
record = Record.open(path)
record.topology()                 # the same type the writer serialized
record.explain(instance)          # was explain_producer(path, instance)
for event in record.events(): ...  # typed Events, lifecycle payloads as Structs
```

`Record` caches its parsed frames, so several questions cost one read. A dict iterator stays available for tooling that wants the bytes as written. A thin wrapper around the same free functions would change only the spelling. This object owns the loaded frames, the index of firings and the blob resolver.

Writing and reading also separate. `record.py` is 623 lines holding `RecordWriter`, fsync policies and all the readers. The writer moves into the kernel's log package and the reader becomes the public `substrate.record`. `record/inputs.py` validates Producer inputs, which is not a record concern, and moves to the Bus.

**Refactoring.** Combine Functions into Class, with Branch by Abstraction so projections can move one at a time. Extract Class separates the reader from the writer.

### Lifecycle parsing in projections

`_firing_index` and `_started_index` in `inspect.py` and `fired`, `started`, `ended` in `graph.py` each loop over envelopes checking `env.get("kind")` and then `isinstance(ref, dict) and isinstance(ref.get("instance"), str)`. `Event.from_envelope` already exists and gets halfway. With one typed Struct per lifecycle event, `record.events()` gives `TriggerFired` objects, and the defensive checks disappear because the decoder has already enforced the shape.

Tolerant parsing was reasonable when the shape was undocumented. A record's shape is pinned by the schema it carries. A frame whose schema version the reader does not support raises a typed error naming the kind and version, as the product spec requires, and older session shapes keep reading through Struct defaults.

**Refactoring.** Replace Primitive with Object as each projection adopts typed events. Remove Dead Code takes out the checks.

### Topology manifest

`Runtime._manifest` builds the topology description as nested dictionaries. `topology_graph` reads them back with `str(t.get("id", "?"))` fallbacks into frozen `ProducerNode`, `TriggerEdge`, `RouteEdge` and `TopologyGraph` Structs. Those Structs are the topology's read model, and they read as the write model should. The writer and reader share no type, so nothing checks that they agree.

One schema serves both: `Topology` supplies a `TopologyManifest` Struct, `Runtime` writes it with the run's own fields, and `Record.topology()` decodes it. `TopologyGraph` is then that same Struct. Initial Producers, which the manifest omits today and `topology_graph` has to infer from `__initial__` firings, become a field, which is a stated addition to the record.

**Refactoring.** Encapsulate Record: one manifest Struct. The writer encodes it and the reader decodes it, and the comparison shows the manifest is equivalent.

### Turn reconstruction

`turn_replies` in `vocabulary.py`, `slice_kind_matches` in `context_slice.py` and `turn_pairings` in the language code each decide what a turn is by folding over dictionaries. A launcher script has an `if k == "ToolCall"` print ladder. A test is named for reading a payload that is sometimes a dict and sometimes a `mappingproxy`.

`SessionRecord(Record)` adds `.turns()`, returning typed `Turn` objects, and every reader uses it. A shared helper function would also remove the duplication; the class is better because a session's old-format readers then have one place to live.

**Refactoring.** Combine Functions into Class on `SessionRecord`, with Substitute Algorithm at each of the three call sites.

### Blob resolution

`_maybe_offload` implements Claim Check. It writes a payload over 16 KiB to the blob store ahead of the frame, the record holds a `{"$blob": ...}` stub, and the live cycle keeps the full payload, so Views, Routes and Triggers always see real fields.

The readers do not get the same treatment. `read_record` returns the stub unless the caller remembers `resolve_blobs=True`, and `load_envelopes` has the same flag, so every reader chooses. `Record.events()` resolves by default and lazily, with a separate raw path for integrity checks that want the bytes as written. `read_record` keeps today's behaviour while callers move.

Several comments still describe a problem the cycle has fixed. `tool_loop` and `localize_elements` cap their output "under the 16 KiB blob-offload threshold" because an offloaded payload once reached Triggers as a stub. Live Triggers now receive the full payload. Those caps should be judged again on what they are still for, and the comments should go.

**Refactoring.** Remove Flag Argument, with a separate raw method for integrity readers. Remove Dead Code for the comments, after each output cap is judged on what it still does.

## Code style

A comment should say what the code cannot. History belongs to version control and the project's log.

### History in comments

250 comments name a `Sprint N` or `Knnn` ticket, and comments hold 187 `§` marks. Counting docstrings as well, there are about 550 and 480. Docstrings narrate how things came to be ("Sprint 065: ... deleted", "F2 fix (review 2026-08-08)", "Deferred to sprint 064"). Blocks of twenty comment lines sit over three lines of logic. A reader of `runtime.py` gets the case history before the behaviour.

A comment keeps a requirement reference only where the line implements a contract, such as the rule that an invalid emission is recorded and numbered, and says why when the reason is not visible. Sprint and review history stays in git and `BLACKBOARD.md`, where it already is. `language/` shows the register: each measure's docstring states its published definition.

**Refactoring.** No catalog entry fits. It is plain deletion, done last, because earlier sections delete most of these comments along with their code.

### Compatibility code

`_ = repro_k  # kept in signature for source-compat`, a retired 270-line topology still in `assemble.py`, `_record_has_envelopes` "Back-compat wrapper", and `reference/_models.py` re-exporting adapters all serve callers that live in this repository. A change updates its callers in the same commit, so none of these has a purpose. Only the record format and the published package's public names need compatibility.

**Refactoring.** Remove Dead Code and Inline Function, with callers changed in the same commit.

### Leftover aliases and dead conditionals

`_TRIGGER_FIRED = TRIGGER_FIRED` aliases appear in three files. `import os as _os` sits in functions when `os` is imported at the top. `from .vocabulary import (X as _KIND_X,)` makes aliases of aliases. `has_session_prompt = True` is followed by `if has_session_prompt:`.

**Refactoring.** Inline Variable and Remove Dead Code.

### Tests on source text

`"except BaseException" not in src`, `text.count("turn_replies(") == 2` and a regex over docstrings test the words in a file. They exist because the public surface offered no way to ask the real question, and they break on a rename. With a declaration-based surface and typed reads, most become ordinary assertions. A rule about source that must hold, such as a layer boundary, belongs in the import contract or a lint.

**Refactoring.** Substitute Algorithm: each becomes an assertion on behaviour, or moves to the import contract when it is a rule about layers.

## Existing code to imitate

`record/` has small modules with one job each: `framing`, `blobstore`, `locking`, `sidecar`, `live`. Its tests read as a specification. `language/` is pure functions over frozen dataclasses, one module per concept, each measure documented with its published definition and cross-checked against `river`, `lexicalrichness`, `powerlaw`, `nolds` and `cmudict`. `assay` has real domain classes: `Suite` and `Arm` validate in `__post_init__`, `Oracle` is a Protocol with several Strategies, and `Result` is frozen with a derived `.passed`. `swebench_solver` is organized by phase, with `select_patch(applied, results)` pure over Structs. `RateLimitedResponder` is a true Decorator. `any_of` and `all_of` over `TerminationPolicy` are a Composite with walkable structure. `conversation.Instrument` is a declaration record. Firing policies and cooldowns are closed unions, and `AppendCycle.cycle` matches the specification's six steps line for line.

`Suite.__post_init__` already does for a benchmark what `Topology.__post_init__` should do for a topology.

## The standard implementation

The specifications are kept. The semantics of the append cycle, the record format, replay levels and the vocabulary are what the code is meant to express, and the rewrite preserves them. The preservation contract is concrete: the conformance suite and the behaviour tests pass, and the 18 committed records regenerate from the new code with the same events apart from derived names, `fingerprint.qualname` and the new initial-Producers manifest field. The specification changes are the Trigger tuple with `producer_factory`, per-instance factories and `start(input)`, the product spec's list of the public API, its definition of a topology as a function of a builder, its subscription by Producer id, the free inspection functions, the design spec's "functions of the builder" and "the builder methods *are* the vocabulary", the rule that the CLI imports only `substrate.api`, the amendment that dropped `RunRecord`, and the count of primitives, which the kernel, product and design specs give as eight and which becomes nine. New drafts carry them, with the prior ones preserved, and the vocabulary changes go through typed proposals and a version bump.

The package layout:

```
src/substrate/
  __init__.py      Producer Event Bus View Predicate Trigger Route TerminationPolicy
                   Record Topology Fragment Initial Runtime
  kernel/          passes the minimality test; imports nothing above itself
    event.py       Event, ProducerRef, one typed Struct per lifecycle event
    producer.py    Producer[In, Out], Body[In, Out]
    view.py        View[T]
    predicate.py   Predicate[E]
    trigger.py     Trigger[E, In], frozen firing-policy and cooldown declarations
    route.py       Route[E, S]
    termination.py TerminationPolicy, Decision
    topology.py    frozen Fragment and Topology; every static check in the constructor;
                   the subscription index; the manifest
    bus.py         Bus: admission, sequence, control queue, the append cycle, firing state
    supervisor.py  ProducerSupervisor: tasks, budgets, cancellation, live_instances()
    runtime.py     Runtime: wires the above, run, resume, RunResult
    encoding.py    RFC 8785
    errors.py      one hierarchy, ErrorInfo
    constants.py   defaults and enums
    log/           writer, framing, segments, blobstore, locking, sidecar
  views.py         standard Views, typed, holding decoded Structs
  termination.py   recipes
  predicates.py    completed, count_at_least, the common forms and the combinators
  joins.py         Join and the fan-in helpers
  composition.py   namespacing, embedded_substrate
  record.py        Record, the typed read model; inspection queries as methods; attach
  replay.py        replay levels
  testing.py       assert_event and friends, shared stand-ins
  models/          Responder and capability Protocols, Ollama, CLI, deterministic, Decorators
  tools/           Tool[Args], ToolContext, the tool suite, one Struct per tool
  session/         events, TurnState reducer View, topology, prompts, SessionRecord, SessionConfig,
                   service (now session_registry), delegate, runs/, bundles, workspace
  topologies/      one package per topology; _shared/ for the conversation engine,
                   instruments and the best-of-N fragment
  language/        as now
  assay/           as now, with swebench under it and a generic Case[P]
  conformance/
  cli/             one module per command group; imports public modules only
```

Dependencies run one way, enforced by import contracts inside `session`, `tools` and `topologies` as well as across the top level: `kernel`, then the standard modules, then `models`, `tools`, `session`, `topologies`, `assay`, `cli`. Function-local imports for cycle-breaking do not exist.

Each of the nine pieces is a named, exported type. A topology is a frozen declaration validated at construction, built from declarations that refer to each other by object, with every name derived from the code or pinned by a closed enum, and strings only on the wire. Run state lives in the Bus, or in a per-run factory on a Producer, so one Topology can run many times. Producer inputs and every lifecycle event are frozen Structs. The Bus is one class with one append path. `Record` is the one way to read, sharing its schema with what the writer records. Composition is a function over declarations with namespaces and a stated rule for merge versus embed. Fan-in is a named library concept. Failure policy is a declared Decorator. Session state is a reducer View with a closed phase enum. Tools take one Struct and one context object. Module-level mutable state is gone. Comments state what the code cannot, and tests are named for behaviour with a shared support module.

Because a `Topology` can translate itself into calls on the current builder, as the test rewrite showed, topologies can move one at a time while the runtime stays in place, and the builder can retire last.


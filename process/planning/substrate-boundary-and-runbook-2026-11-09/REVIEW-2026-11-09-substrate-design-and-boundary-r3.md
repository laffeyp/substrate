# Review — the Substrate design paper (r3) and the refactor sequence

*2026-11-09. Reviews `RESEARCH-2026-11-09-substrate-design-and-boundary-r3.md`, `SEQUENCE-2026-11-09-substrate-refactor.md` and `evidence-topology-value/` in this folder, against published practice, the current specifications, the SDD kit and the code. "Research line 171" and "Sequence line 15" are lines of those two documents. Code is substrate at `0301beca` and substrate-ui at `9266de0`. The substrate working tree differs from `0301beca` only in `process/BLACKBOARD.md` and this folder. Nothing under `superseded/` was read.*

*Read in full by the reviewer: both documents, the seven evidence scripts, and `kernel/runtime.py`, `sequencer.py`, `topology.py`, `triggers.py`, `runstate.py`. The other modules, tests, specs and substrate-ui were covered by AST and grep sweeps and by five subagents, whose main findings were re-checked at the cited lines. Not re-checked by the reviewer: the fit of the catalog refactorings in finding 31, and the Flink, DBOS, Restate, protobuf and `runtime_checkable` quotations, which rest on a subagent's reading of those pages. The evidence scripts were re-run. No test suite or harness was run.*

---

## Result

The paper's diagnosis holds, and a typed, frozen topology declaration is the right direction. The re-run gave what the paper reports: 27 events each, zero differences after `RunStarted`, and `mypy --strict` passing. The six hand-built envelopes, the Bus spread across objects and the live View leak are accurately described. About 155 of about 180 checked claims about the code held, and 14 claims about substrate-ui held, including that a converted topology stays callable by `server.py`.

The sequence cannot run as written. Findings 1 to 4 stop `session_topology` being constructed in the design as specified. Finding 15 means the Golden Master cannot check any conversion that renames something, which is nearly all of them. Finding 11 is the one decision that goes further than any source read: every name derived from code, with no override.

Findings 1 to 16 should be corrected before stage 3 starts, because stage 3 moves the prototype into the package.

---

## Decisions that fail as written

### 1. Kinds that arrive from outside are refused

`tv.py:100` raises when no Producer emits a Trigger's kind, and Research line 171 moves that check into the constructor. The design has no way to declare an injected kind. Running the check over all 18 bundled topologies refuses `session` and `daily`, on `InterruptRequested`, `SessionEndRequested` and `Park`. `session/__init__.py:1717` states that the daemon writes the first two. `UserMessage` arrives as a resume event and is emitted only under `if first_turn_user_message`. `OperatorOverride` in `reference/r2_pipeline.py:297` is the same case.

Six more sites subscribe to a kind emitted only by a composed part (`runs/run.py:100`, `session/ci.py:123`, `swebench_solve_and_grade.py:91`, `assemble.py:364,385`, `best_of_n/__init__.py:154`). A merge resolves those.

Correction: `Topology` gains a declared field for external kinds, typed as Struct classes, and the constructor checks `on` against emitted plus external. A Fragment is not checked; only the whole `Topology` is. `Park` has no emitter anywhere and needs its own line: declare it external, or log it as a stale subscription.

### 2. Lifecycle Triggers do not match

Eleven sites subscribe to lifecycle kinds. Seven are in `session/__init__.py` (1373, 1428, 1443, 1465, 1551, 1578, 1593), and the `b.instrument` at 1218 on `RunStarted` is the only start of `session_started`. `tv.py:93-101` has no lifecycle exemption. Research line 294 gives each lifecycle event a Struct and states no mapping from class to wire. `on.__name__` yields `ProducerCompleted`, and the wire kind is `substrate.ProducerCompleted` (`constants.py:63`), so `tv.py:114` would subscribe to a kind that never occurs.

Correction: the class-to-wire mapping is one function, used by the subscription, the emitter and the record reader. The constructor exempts the reserved namespace, as `validate` does today.

### 3. `on` takes one class and seven Triggers take several

7 of 73 Triggers subscribe to several kinds. Five are `{ProducerCompleted, ProducerFailed}` (`session/__init__.py:1373,1428,1443,1465,1551`). `assemble.py:635` is a deliberate last-arriver join. The example at Research line 701, `Trigger(on=ProducerCompleted, start=model, ...)`, drops the failure path of the Trigger it replaces.

Correction: `on` accepts a tuple of classes and `E` is their union. The example at line 701 changes to match.

### 4. `Ctx.event` drops the envelope

`tv.py:48` returns only the decoded payload. Four sites read `ctx.event.seq` (`pair_coding/__init__.py:137`, `session/__init__.py:1133,1357,1547`).

Correction: `Ctx` exposes the payload and the envelope fields separately, typed.

### 5. Two roles sharing one body derive one name

Two Producers in `swebench_solver/assemble.py` have bodies named `validate` (`repair.py:88`, `repro_base_validate.py:73`), registered today as `validator` and `repro_base_validate`. `conformance.py:344,347` registers `counter` and `noop` on one `_counter`. Both derive one kind, and the constructor raises. Research line 238 defines `key=` only for N copies. `conformance_perf.py:83` builds five identical Triggers per kind in a loop, and `Trigger` has no `key`.

Correction: finding 11's override covers both, or `key=` is defined for roles and added to `Trigger`.

### 6. Declarations the design does not have

The example at Research lines 137 to 152 and `tv.py` have no form for:

- Routes. `Slot` appears once, at Research line 242. `Topology` has no `routes=` field and no rule gives a `route_id`, which `sequencer.py:370` records. All six reads of `staged` use `.get` and tolerate an empty slot, so `c[failure]` needs `T | None` or a default.
- `b.instrument`, which expands to a Producer, a PerEvent Trigger with its id equal to the kind, and an optional `{name}-stage` Route (`kernel/topology.py:309-335`).
- `b.baseline`, `Budget`, `author_version`, cooldowns and `schema_version`. `tv.py:107` hard-codes 1, while `docs/schema-evolution.md` makes bumping it the evolution mechanism. `WORKING_AGREEMENT.md:183` says every Producer declares a `Budget`.

Research line 210 gives the test's limits as the slow-member option and the session. The test had one Trigger, one View, no Route, no lifecycle subscription and no composition.

Correction: the paper states the declaration for each of these before stage 3, and line 210 states the real limits.

### 7. Composition of whole topologies has no form

A Fragment has no initial Producers and no termination (Research line 599). Three sites apply a complete topology and then add to it: `fanout_review.py:140`, `swebench_solve_and_grade.py:74`, `session/ci.py:114`, which also replaces the termination at `:135`. No step from a `Topology` to a Fragment is stated. `namespaced()` prefixes with "the name of the function that built the Fragment" (Research line 608), and a value has no way to know that function unless it is passed in or read from the stack.

Correction: state the conversion, and pass the namespace explicitly at the `namespaced()` call.

### 8. Run state and ambient state the paper does not list

Research line 473 moves run state out of firing policies and Views. `tool_loop/__init__.py:317` holds `prev_write` in a factory's closure, built once per run by today's topology function. Built at value construction, it carries across runs and breaks stage 4's finish condition at Sequence line 63.

Research line 755 says nothing listed needs a ContextVar, and the table at line 457 removes it. `session/__init__.py:983` reads `api.current_record_root()` inside a Producer body, on purpose: `runtime.py:156-158` explains that a recorded path would make the record's bytes depend on location. `Body` at Research line 196 takes one input, so that body has nowhere to get the path.

Correction: the Producer declaration carries a per-run state factory for the first case, and `Body` gains a run-context parameter, or the ContextVar stays for this one read and the paper says so.

### 9. The value does not have value equality, and it still hides parameters

Research line 126 credits the form with "value equality". Run with the rewrite: two `ensemble(...)` calls with the same arguments compare unequal and hash differently, because each holds a new lambda. `quorum=3` and `quorum=9` produce the same Trigger id, and the number sits only inside the lambda. That is the preregistration fault at Research line 177, where a changed parameter passed unnoticed. `hash()` also cannot fingerprint across processes, since Python salts `str` hashes.

Research line 179 says a callable "cannot be proposed, recorded, diffed or promoted". The value holds callables too, so the same limit applies to it beyond its structure.

Correction: drop the equality claim. State that parameters captured by a predicate or body are visible only when declared, through the frozen callable objects at Research line 713 or a parameter field recorded in the manifest. Fingerprints use canonical bytes. Line 179 claims the structure only.

### 10. One of the five rejected mistakes is rejected only with an annotation

Research line 206 lists "a body yielding a kind its Producer does not declare" as rejected. `negative.py:27` carries an explicit `Producer[Adjudicate, Verdict]` annotation. Without it, `Producer(bad, (V,))` passes `--strict` and infers `Producer[None, Struct]`. A body yielding `V | W` with `emits=(V,)` also passes. The value design's own examples leave these unannotated. `_resolve` still records the event as invalid at run time.

Correction: the paper says four are rejected unconditionally and the fifth only with an annotated Producer, or the constructor compares the body's return annotation with `emits`.

### 11. Deriving every name, with no override, goes beyond the sources

Research lines 230 to 247 derive every wire name from code and remove the name arguments. 52 of 87 registrations change name. After this, renaming a private function changes what the record says, which is not a behaviour-preserving change. Research line 247's refactoring name hides this: see finding 31.

Sources on names held in a durable log or a resumable run, all vendor documentation:

- LangGraph: "If you omit a node name, LangGraph uses the function name", and "Do not rename or remove a node the thread is about to enter. On resume, LangGraph looks up that node by name, and a missing name fails the run."
- Temporal defaults to the function name and allows an explicit one: "Changing an Activity's registered name while Executions are in flight leaves those Executions scheduling the old name. Register both names until the in-flight Executions drain, or use a versioning guard."
- DBOS and msgspec derive by default, with an override.
- Restate: "removing or renaming them is not" allowed.
- Kafka Streams and Flink warn about names generated from position or structure, a different derivation. Kafka's page also says "It's a good practice to name your processing nodes when using the DSL."

No source read endorses derivation with no override. The derived forms also conflict with two project rules. `docs/specs/design_spec/draft1.md:355` requires kebab-case names "convertible to filenames", against `answer[m0]` and `Candidate->adjudicate`. K264 (`BLACKBOARD.md:809`) fixes session Triggers as `<what it starts>-on-<event>`, ratified in `process/signals/session-vocabulary.md`.

Correction: derive by default and keep an explicit `name=` on Producer, Trigger, View and Slot. The constructor check for two equal names stays. Session wire names stay as they are, set by `name=` or by a derivation that yields the K264 form. That also closes findings 16 and 17 for the session.

### 12. The lifecycle Struct changes the bytes

Research line 309 says `omit_defaults` "keeps optional keys absent, as the record has them today". Records hold `"resolved_input":null` (`docs/walkthroughs/records/r1`, seq 1), and `_producer_input` writes it for a `None` input. The Struct at Research line 299 drops that key, so the finish condition at Sequence line 53 fails for every initial Producer.

Correction: use `msgspec.UNSET`. Tested: `resolved_input: Any | None | UnsetType = UNSET` encodes `null` when set to `None` and omits the key when unset.

### 13. The manifest cannot be a method of `Topology` alone

Research line 454 and the target tree at line 881 give the manifest to `Topology`. `Runtime._manifest` also records `run_id`, `name`, `baseline`, and `config` with fsync, admission and budget. `baseline` has no field on `Topology`, and the rest belong to the run. Research line 802 adds an initial-Producers field, which contradicts "the same events apart from derived names and `fingerprint.qualname`" at Research lines 207 and 864.

Correction: `Topology` supplies its section and `Runtime` writes the whole. The preservation contract names the added field.

### 14. Resume does not rebuild firing state today

Research line 473 says keeping the state in the Bus "makes replay and resume rebuild it in one place". `_resume_bootstrap` restores Views, counts and the sequence, and no firing state, cooldown counters or staged Routes. Today every resume gets fresh policy objects, so `Once` re-arms. Rebuilding is what `docs/specs/technical_spec/draft5.md:689-692` describes, keyed on `trigger_id`. It would be a change of behaviour inside a refactor, and under changed Trigger ids an old record would never match.

Correction: the refactor keeps today's behaviour, fresh per run and per resume. The gap between code and spec is logged and fixed in its own change.

---

## The sequence

### 15. The Golden Master cannot check a renaming conversion

Sequence line 29 says to confirm the 18 records are "compared byte for byte". They are not, and cannot be, since ULIDs differ per run. `test_committed_record_is_current` uses `first_divergence`, which compares kind plus a normalized payload hash (`projections/inspect.py:217-225,279-322`). It leaves out `t`, `run_id`, `instance`, the envelope's `producer` and `schema`, and producer `instance` and `parent`. It keeps `trigger_id`, `factory` and `producer.kind`.

Every renaming conversion therefore diverges at index 0, on `RunStarted`, and the function stops at the first difference. Regenerating with `scripts/gen_topology_records.py` overwrites the baseline in the same change as the code. The finish condition at Sequence line 82, "the same events apart from derived names and `fingerprint.qualname`", has no tool behind it except the string replacements in `compare.py`, written for one topology. Approval-testing practice keeps the value in reviewing the difference and scrubbing what varies (ApprovalTests documentation).

Correction: stage 1 builds a comparator that takes a committed old-to-new name map, compares every frame after the mapping, and reports all differences. A record regenerates only after that comparison is clean. Stage 1's wording says equivalence, not bytes.

### 16. Two claims about names are false

Sequence line 15 says the session's Producer kinds keep their names, with `run_tool` the one rename.

| Kind | Body | Derived |
|---|---|---|
| `interrupt_fragment` | `_interrupt` (`session/interrupt_fragment_producer.py:45`) | `interrupt` |
| `driver_stepper` | `_stepper` (`session/ci.py:54`) | `stepper` |
| `tool` in `tool_loop` | `run_tool` | `run_tool` |

`tv.py:27-28` does not strip the underscore, so the prototype yields `_return`.

The same line says substrate-ui only displays Trigger ids. These read them:

- `web/app/derive/structure.ts:49` tags instruments with `t.id === t.starts`. Derived ids lose the tag with no error.
- `harness/shakeout/structure_lists_producers.ts:92-95` asserts the `-on-` form.
- `tests/test_server.py:75,84` assert `"adjudicate"`, and `:82` asserts `reviewer-security`.

In substrate, `conformance.py:162,214,612` compare literal ids, and Research line 864 names the conformance suite as the preservation contract.

Correction: finding 11's override, or the sequence lists these sites and the conformance change.

### 17. Behaviour changes inside work defined as behaviour-preserving

Research line 25 says each change leaves behaviour the same, and the standing rule is that a refactor carries UI, text and logic over exactly. These change it:

- Trigger ids in what the transcript and stream show (Sequence line 80).
- Blobs resolving by default (Research line 818, Sequence line 128), against today's stub.
- A frame that fails to decode raises (Research line 794). `docs/specs/product_spec/draft7.md:475` requires a typed error naming the unsupported kind and version, and K260 (`BLACKBOARD.md:831`) reads old session records.
- A missing termination is a printed note with exit 0 in `validate` (`cli.py:659`). Research line 171 lists it among the checks moving to the constructor, which would make it a refusal.

Correction: each goes to its own change, or the paper marks it as a stated behaviour change with its reason.

### 18. Order and content of the stages

- Stage 3 promises "the nine pieces as named types" (Sequence line 49). `Bus` arrives at stage 4 and `Record` at stage 10.
- Sequence line 9 says each import path changes once. Stage 4 moves `record/` and composition (line 59), and stages 10 and 9 reshape them. Research line 786 splits `record.py` afterward. 28 test files import `substrate.record`, `substrate.encoding` or `substrate.kernel`, and at least 9 `src/` modules above the kernel import `record` or `encoding`, so "touches nothing above the kernel" at line 57 is false. substrate-ui is unaffected.
- Sequence line 116 says Fragments exist from stage 5, and line 49 adds them at stage 3.
- Stage 11's reason (line 136) fails: nothing in stage 10 uses the builder. The real dependency runs the other way. Stage 10's manifest Struct, built by `Topology.manifest()`, needs a `Runtime` that holds the value, and that arrives at stage 11.
- Public names break at stages 6, 8 and 11, and Sequence line 148 assigns 2.0.0 to stage 12. SemVer requires the major bump for any incompatible change to the public API. The sequence should state that nothing is released from stage 6 to stage 12, or move the bump.

Correction: move `record/` and composition at stage 12, or restate the rule. State the manifest's source at stage 10 as `Registration`, moving to the value at stage 11.

### 19. substrate-ui lists are incomplete

- Stage 7 (Sequence line 100) misses `scripts/gen_kinds.py:56`, which is build command 3, and `harness/shakeout/fixtures/write_session_shapes.py:120`. `session_errors.py` only re-exports a delegate constant.
- Stage 7's split affects `SessionRegistry(` on 20 lines in 16 files and two private reads (`test_server_session_queue_cap.py:120,122`, `test_session_registry_first_turn_uses_run.py:37`).
- Stage 8 (line 110) omits `run_hold.TABLE`, used at `server.py:1016,1037,3835,3845,3849`. Its home, `topologies/runs/hold.py:308`, is outside the finish condition's "`session` or `tools`".
- Stage 10 (line 130) names 56 uses of `api.read_record`; the count is 51. `narration_summary`, `trace_ancestry`, `explain_producer` and `read_last_envelope` are unlisted.
- Stage 11 (line 140): `gen_kinds.py:70-76` also reads `reg.triggers` and `reg.views`. "TopologyBuilder" remains in `web/app/state/studio.ts:131` and `gen_kinds.py:9`, so the finish condition fails.
- Stage 12 (line 152): Python inside TS strings (`handoff_live.ts:53,58`, `topologies_live.ts:127`) and `fetch-python-runtime.sh:203` are invisible to an import contract.

### 20. The installed app is insulated in code and not in data

Sequence line 13 covers the code. Each turn rebuilds the topology from the manifest and resumes the existing record (`session_registry.py:918-920`). `_resume_bootstrap` checks neither manifest nor names. After an upgrade, a session parked by old code continues under new code. Stage 5's fixture tests this once, at one point in the sequence.

Correction: the parked-record fixture runs at every later stage that changes the session.

### 21. Stage 2 cannot finish as written and amends too little

The finish condition at Sequence line 43 fails after the named corrections. `docs/tutorial.md:220`, `docs/design/ui-design-handoff.md:80,273`, `docs/cradle-x-substrate/three-way-intersection.md:17,33,54,186,218` and `docs/swebench/swebench-solver-design.md:72` still match. The search also misses "Eight." at `kernel_spec/v15.md:292` and "eight-word" at `cli.py:10` and `projections/inspect.py:9`. "Corrected" (Research line 74, Sequence line 39) contradicts the convention of new drafts with the prior preserved.

The target design also contradicts current spec text that neither document amends:

- The Trigger tuple with `producer_factory` (`v15.md:370`, `product_spec/draft7.md:368`).
- Per-instance factories (`design_spec/draft1.md:390`), and `start(input)`.
- `Callable[[TopologyBuilder], None]` (`technical_spec/draft5.md:872`) and "the builder methods *are* the vocabulary" (`design_spec/draft1.md:351`).
- Kebab-case names and `schema_version`, as in findings 6 and 11.
- `substrate.cli` importing only `substrate.api` (`technical_spec/draft5.md:890`).
- F-OBS-3's free functions becoming methods.
- Subscription by "event kinds and/or ProducerIds" (`product_spec/draft7.md:356`).

---

## Code organization

### 22. The target kernel fails the paper's own tests

Stage 4 finishes when "the kernel imports nothing above itself". `kernel/` imports `errors`, `constants`, `types`, `protocols`, `encoding` and `record`. The tree at Research line 894 leaves `errors.py` outside, though `ErrorInfo` goes on the record and the writer raises `FsyncError`.

Research line 410 evicts `views.py` because it could live outside. By that test, the combinators in `kernel/predicate.py` (line 876) and `log/attach` (line 886) go too. `record/live.py` states it never opens a file for writing and never signals the writer. Line 872 says the target "passes the minimality test".

Correction: `errors` and `constants` move into the kernel, and the combinators and `attach` move out.

### 23. Facts the moves depend on

- Research line 527 says `test_committed_record_is_current` is the records directories' only reason to exist. `substrate demo replay` reads them through `bundled.record_path` (`cli.py:838-846`), so moving them to test data breaks that command.
- Research line 525 dissolves `applications/`, which `BLACKBOARD.md:312` records as an Architect-ratified name. The paper does not cite it.
- The cycle table at Research line 541 says `RunSpec` is imported inside functions. It is under a module-level `TYPE_CHECKING` block (`session/__init__.py:98-99`). `compose_run` and `first_message` are the function-local imports.

---

## SDD discipline

### 24. No vocabulary work in the sequence

Hard rule 2 sends vocabulary changes through a typed proposal and a version bump. Neither document mentions `process/signals`. `current.json` defines Trigger by its tuple with `producer_factory` (line 49), Topology as "One of the eight named primitives" (line 94) and the eight-word list (line 913). It also names `RunRecord`, `load_record`, `input_builder`, `api.append_at_rest` and the `trigger_id` values, and has no entry for Fragment, Initial, Body or Join. `session-vocabulary.md:375-379` ratifies Trigger ids that Sequence line 15 changes.

Correction: stage 2 includes the vocabulary proposals and the bump.

### 25. Decisions the paper did not read

Research line 19 records that `process/` was read only in part. These recorded rules go uncited:

- `WORKING_AGREEMENT.md:203-208`: a new primitive names a production consumer, and "Tests do not count". Stage 3 adds types "unused by production paths" (Sequence line 49), and the consumer arrives at stage 5, so stage 3's cards must name it.
- `WORKING_AGREEMENT.md:55-125`: the canonical-home registry (hard rule 7) moves at stages 4 and 12 with no update named.
- `WORKING_AGREEMENT.md:72`: `api.py` is the CLI's only import surface, and stage 12 removes it.
- `WORKING_AGREEMENT.md:116`: the Length and Tone controls live in `session/vocabulary.py`, and stage 11 retires "constant tables" without placing them.
- `BLACKBOARD.md:284`: the driven end of a turn is composed onto the one session topology. Research line 610 cites only the copy rule.

---

## Sources and published practice

### 26. `runtime_checkable` is the same probe

Research line 368 replaces `getattr` probes with `isinstance` against `runtime_checkable` Protocols. The Python documentation says such a check looks only at "the presence of the required methods or attributes, not their type signatures or types", that runtime checkability is not inherited, and that since 3.12 the check uses `inspect.getattr_static()`. An `isinstance` check cannot tell a sync `respond` from an async one, each narrower Protocol needs its own decorator, and a wrapper that forwards through `__getattr__` would likely fail (inferred, untested).

Correction: decide capabilities once at construction, on the adapter, and keep `isinstance` for narrowing.

### 27. An import contract cannot state "public names only"

Research lines 485 and 569 and Sequence line 152 rely on import contracts to forbid non-public names. import-linter's contract types (Forbidden, Protected, Layers, Independence, Acyclic siblings) work on modules, and its documentation page never mentions `__all__` or public names.

Correction: public and private code live in separate modules, or the rule is a custom contract.

### 28. Quotations

- Liedtke wrote "inside the µ-kernel" (Research line 410 drops "µ-"). His test runs one way, so "in both directions" is the paper's extension.
- Martin wrote "Your architectures should tell readers about the system, not about the frameworks you used in your system." Research line 499 alters it unmarked. His argument is that the top level should show the use cases, and Research line 509 puts layers at the top. The layered tree has its own grounds; the quotation does not supply them.
- Fowler's page on Ubiquitous Language never says "that the code itself uses" (Research line 41). It says the language is "based on the Domain Model used in the software".

### 29. Kafka is not the shape claimed

Research line 125 calls a public frozen value "the Kafka and Akka shape". Kafka's `Topology` has public `addSource`, `addProcessor`, `addSink` and `addStateStore`, and its documentation does not call it immutable. Akka holds.

### 30. Attributions to the specs

- "One-dependency policy" (Research line 691) is misattributed. `technical_spec/draft5.md:1005` says the list is short "not because of policy", and only `design_spec/draft1.md:143` says one. The rejection of a state-machine library stands on the off-log state alone.
- "So each instance can have fresh state" (Research line 713): `design_spec/draft1.md:371` gives configuration captured at registration as the reason.
- "Measured its cost" (Research line 493): the measurements in the product spec are of Predicate budget, not of in-process execution.

### 31. Refactoring names

All 35 names exist in Fowler's catalog. Eight uses do not fit its sketches. The one that matters is Replace Derived Variable with Query (Research line 247). That refactoring swaps a stored value for an equal computed one. Here the value changes, `adjudicator` to `adjudicate`. The others are Split Phase for reader and writer, Combine Functions into Transform for a fold over events, Replace Query with Parameter for the end-of-session callbacks, Remove Flag Argument for the `termination` placeholder, Parameterize Function, Change Value to Reference and Replace Constructor with Factory Function.

---

## Terminology

### 32. "Value"

The paper's central word is "value" (Research lines 13, 94, 126). Fowler's Value Object is "equal due to the value of their properties", and finding 9 shows this object is not. "Frozen declaration" says what it is. The word "kernel" is examined properly at Research lines 405 to 417, and "Claim Check", "Decorator", "Composite", "Strangler Fig" and "Characterization test" are used in their established senses. "Golden Master" fits only once finding 15 is corrected, since the test compares an equivalence relation and not output text.

---

## Facts

### 33. Counts

| Research line | Claim | Code shows |
|---|---|---|
| 222 | `frozenset({"Candidate"})` 67 times | 4. The 67 is every kind |
| 222 | `ctx.views["candidates"]` 43 sites | 2. 42 is any key |
| 533 | 201 function-local imports, 112 in `topologies/` | 188 and 103. Nested functions were counted twice |
| 192 | The "structurally match" comment copied into 27 modules | 2. `_Factory` is assigned in 26 |
| 830 | 553 and 492 in comments | Counts over whole-file text; 223 and 187 in comment tokens |
| 315 | `x-args-passthrough`, at least ten tools | 8 |
| 353 | Every wrapper, such as `RateLimitedResponder`, branches on four combinations | One `getattr`; `EnsembleResponder` covers four |
| 376 | Same 12 keywords in six files | 15 files |
| 583 | `_turn` 11 files, `_require_model` 13 | 15 and 9 |
| 689 | One input dictionary at four Triggers | 3 |
| 808 | Four launcher scripts | 1 |
| 844 | `_TRIGGER_FIRED` in four files | 3 |
| 858 | `Oracle` has two Strategies | 5 classes |
| 116 | 268 call sites in 34 functions | 264 in 35 by AST. "Every builder method returns `None`" excepts `build()` |

Sequence line 9: substrate-ui's `tests/` holds 71 Python files and `server.py` uses 25 paths. Research line 19's 240 test files holds with 237 named `test_*.py`.

### 34. The evidence scripts

`twice.py:13` counts firings with `trigger_id == "adjudicate"`, an id the rewrite never produces, so it prints 0 for both runs. The Verdict counts of 1 then 0 are what support Research line 214. `compare.py:61` also drops `run_id` from `RunFinalised`, which Research line 207 does not list.

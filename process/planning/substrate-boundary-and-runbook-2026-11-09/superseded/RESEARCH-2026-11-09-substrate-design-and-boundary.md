# Substrate: the design of the code, and the boundary with substrate-ui

*2026-11-09. Research paper on what is in `substrate/` and `substrate-ui/` and how far the code falls short of the concepts it implements. It corrects `RESEARCH-2026-11-09-boundary-and-runbook-prep.md` in this folder, which ruled the boundary correct; the numbers that note got wrong are listed under "Corrections to the earlier note". The order of work, set by the Architect on 2026-11-09: this paper first, then the runbook, the file moves and a full rewrite or refactor. No source file changed in the making of this paper. The probes ran from the session scratchpad against the repo's virtual environment.*

---

## The finding

The system works and is in daily use. The code does not express the design. The specification defines eight primitives, the README nine, the working agreement a different eight. Four have a type in the code. The other concepts are a callable signature retyped at each use, a registration record the public surface does not export, or a behaviour spread over four objects. The `kernel/` folder is neither the minimum the runtime needs nor all of it. `substrate.api` is 119 names in one namespace, and the words of the design are mostly not among them. A topology is checked for two things at build time, so a misspelled event kind produces a run that finishes cleanly and silently does the wrong thing.

The repo split runs in the right direction but is drawn in the wrong place. A standing-session service exists, with no name and no home, split between the two repos.

The Architect's charge is that the code is trash and the concepts are rigorous. The evidence supports the charge for everything around the append cycle: types, packaging, topology checking, session assembly, the public surface. The append cycle itself, the canonical-byte handling and the failure recording at user-code seams are sound in substance. A rewrite has good logic to keep and a poor structure to replace.

---

## The primitives

Three documents list them, and the lists differ. `docs/specs/kernel_spec/v15.md` says "Eight": Producer, Event, Bus, View, Predicate, Trigger, Route, TerminationPolicy. `README.md` says "nine fundamental ideas" and adds the run record. `process/WORKING_AGREEMENT.md` names eight words, dropping Event and adding Topology. Ten concepts in all, none listed the same way twice.

An AST walk of `src/substrate/` found this.

| Concept | What the code has | Where |
|---|---|---|
| Producer | `Protocol` with `__call__(self, input: Any) -> AsyncIterable[Event]` | `protocols.py:24` |
| Event | frozen `Struct` | `types.py:45` |
| View | `Protocol`; `value()` returns `Any` | `protocols.py:61` |
| TerminationPolicy | a class that wraps a callable and a name | `kernel/policies.py:47` |
| Bus | no type. `AppendCycle`, `RunState`, `RecordWriter` and `Runtime._writer_loop` share it. The word survives in `BusLockedError` | `kernel/sequencer.py`, `kernel/runstate.py`, `record/record.py`, `kernel/runtime.py` |
| Predicate | no type. `Callable[[TriggerContext], bool]`, written out twice | `kernel/topology.py:92`, `:238` |
| Trigger | no public type. `TriggerReg`, absent from `substrate.api` | `kernel/topology.py:89` |
| Route | no public type. `RouteReg`, absent from `substrate.api` | `kernel/topology.py:100` |
| Topology | no type. `Callable[[TopologyBuilder], None]`, written out at 7 sites; the one alias is in `assay/suite.py:43` | `kernel/runtime.py:202`, `kernel/topology.py:382` |
| Run record | no type. `read_record` yields `dict[str, Any]` | `record/record.py:416` |

The Architect's statement that the primitives do not exist anywhere is exact for six of ten, and three of the remaining four are thinner than their names.

The Producer protocol states something false. It declares a stream of `Event`, but `AppendCycle._resolve` takes the kind from `type(obj).__name__` and requires a declared `Struct`. A probe that yielded a real `api.Event` got `substrate.ProducerEmittedInvalidEvent` on the record and a run status of `finalised`. The tutorial says Producers yield "typed Events — msgspec `Struct`s", so "Event" means the authored payload in the documentation and the stored envelope in the code. `mypy` cannot catch this, because 15 Producer signatures in `topologies/` are annotated `AsyncIterator[Any]`. `Any` appears 22 times in `kernel/runtime.py`, 20 in `kernel/sequencer.py` and 14 in `kernel/topology.py`. Strict `mypy` passes because the connections between primitives are typed `Any`.

The spec's other terms have drifted too. It requires "a typed `ProducerId` with kind metadata, not free strings"; `_Emission.producer` is `dict[str, Any]` and is read as `ref["kind"]`. It defines a Trigger with a `producer_factory`; `TriggerReg.starts` is a string. It defines a Route with a `source_predicate`; `RouteReg` has a `Subscription`. The quarantine payload at `kernel/sequencer.py:500` writes `predicate_id` and `trigger_id` with the same value, since a Predicate has no identity of its own.

Stored and in-memory forms are also separate by hand. The envelope is a dict literal at `kernel/sequencer.py:148` and again at `:328`, and `Event.from_envelope` rebuilds the type from `.get` calls with defaults.

---

## Whether the kernel is a kernel

The term has a settled meaning. Liedtke's minimality test (SOSP 1995, read here through a UNSW lecture slide that quotes it): "a concept is tolerated inside the µ-kernel only if moving it outside the kernel, i.e. permitting competing implementations, would prevent the implementation of the system's required functionality." The separation of mechanism from policy goes back to Brinch Hansen's RC 4000 and to Levin et al. on Hydra (1975; citation seen, paper not read).

`kernel/` fails the test in both directions. It contains what could move out: `views.py` (132 lines of standard Views), the recipes in `policies.py`, the firing policies in `triggers.py`, and `composition.py` (243 lines). The spec itself says of the recipes that "the contract is the callback, not the recipe set." It omits what the runtime cannot work without: `record/` (1,278 lines), `encoding.py`, `types.py`, `protocols.py`. `protocols.py` also holds `Responder`, whose docstring says it is "NOT a kernel concept".

The name stretches further at the package level. The distribution is `substrate-kernel`, and it ships 39,769 lines. The modules that make up the runtime proper (`kernel`, `record`, `projections`, `encoding`, `api`, `constants`, `errors`, `home`, `naming`, `protocols`, `testing`, `types`) total 6,392 lines, 16 percent. `topologies/` is 18,674 lines, 47 percent, of which the interactive session is 5,341.

Application needs have also reached down. `Runtime` keeps a process-wide map, `_ACTIVE_RUNTIMES_BY_RECORD_ROOT`, so that "a cross-thread daemon call can find it", and a comment in `__init__` names `SessionRegistry.interrupt`. The runtime knows about the session service above it.

---

## `substrate.api`

`api.py` is 267 lines of imports and an `__all__` of 119 names drawn from 21 modules, in one namespace. A single re-export file is ordinary Python and not a defect in itself. Three things are.

It adds no abstraction. Ousterhout's "Different Layer, Different Abstraction" names adjacent layers with similar abstractions as a red flag. `api` is the module tree with the dots removed. Trigger cooldowns (`Logical`, `WallClock`) sit beside record repair (`recover_open_segment`, `has_torn_tail`), 17 constants, 10 error classes and fsync policies (`Always`, `Interval`, `NoFsync`), with no grouping.

It omits the vocabulary. A reader who opens the public surface finds `TopologyBuilder` and `TriggerContext` and finds no Bus, Predicate, Trigger, Route, Topology or Record.

It is not the boundary it claims to be. Its docstring says "Everything else is private." `substrate-ui/server.py` imports from 25 distinct `substrate` modules. The test that polices this, `test_ui_imports_only_sanctioned_substrate_surfaces`, compares only the first two segments of a module path and sanctions `substrate.api`, `.app`, `.adapters`, `.topologies` and `.assay`, which is 26,751 lines, 67 percent of the package. It passes, and it permits `substrate.topologies.session.model_class`.

---

## The topology is not checked

The module docstring of `kernel/topology.py` says "Registration is frozen when the factory returns" and that static checks are caught at build time. `build()` is nine lines and checks two things: every `Trigger.starts` names a Producer kind, and every initial names one. It freezes nothing. Probes on 2026-11-09:

| Probe | Result |
|---|---|
| A Trigger subscribes to `"Itme"` where the Producer emits `Item` | `build()` passes; the run ends `finalised`; the Trigger never fires and nothing on the record says so |
| `producer_kind("a", ...)` registered twice | accepted; the second replaces the first with no error |
| `build()` result mutated with `.clear()` | the change reaches the builder; the next `build()` returns the emptied set |

The first row matters most. `ProducerKindReg.schemas` already knows every kind each Producer may emit, and `Subscription.kinds` is never compared with it. `topologies/` constructs `Subscription(` at 62 sites, each one a string a typo can break. A runtime whose stated product is a provable record accepts this silently at the point where checking costs almost nothing. The spec's statement that "Divergence is the topology author's problem" covers runaway firing, and a Trigger that can never fire is a different case.

---

## The execution engine

The six-step `AppendCycle.cycle` at `kernel/sequencer.py:100` reads as the specification does. A Producer's input is recorded, hashed and copied from one canonical byte string (`_producer_input`). Disk and memory payloads are distinct by design. Failures in user code become recorded events and never crash the writer. `TerminationPolicy` composes and can be walked with `leaves()`. This logic is worth carrying into a rewrite.

Around it:

**A cascade limit nobody chose.** Step 6 drains the control queue by recursion (`kernel/sequencer.py:127`), and each nested call drains the rest of the queue, so depth grows with queue length. A probe with 900 Triggers on one event finalised. With 1,100 Triggers the run failed at 982 `TriggerFired` events: `RecursionError: maximum recursion depth exceeded`, reason `kernel_error`. The spec promises unbounded topology depth. This is a limit on one cascade's width, set by Python's stack and stated nowhere. A loop would remove it and keep the FIFO order.

**A known bug's twin.** The comment at `sequencer.py:157` records that advancing `next_seq` before the append left a gap that made a whole record unreadable (lens audit F020), and `_emit` was fixed. `_view_failure` at `:318` still advances first, and so does the kernel-error path at `runtime.py:438`. Both are terminal paths, so the exposure is small. The two exist because the frame-writing code exists three times.

**Runtime as a holder of state.** The sequencer's own docstring says it was "Extracted from the Runtime God-class." `Runtime` still has 19 instance attributes, 9 of them first set outside `__init__`, and `_drive` is 150 lines covering lock, recovery, sidecars, run state, writer loop, cancellation, manifest and context reset. Its `finally` block catches `NameError` at `runtime.py:390` to guard a local that may never have been bound.

**Dead code.** `AppendCycle._resolved_input_fields` at `sequencer.py:279` has no caller in `src/` or `tests/`.

---

## The rest of the package

Measured across 1,341 functions, 137 run past 50 lines and 35 past 100. Length alone proves nothing: in the published exchange with Robert Martin, Ousterhout keeps a 65-line method whole, and judges a split by whether a reader must read one part to understand another. By that test the worst case is `session_topology`, at 717 lines, whose nested `topo` is 507 and nested `_model_factory` 280, closures over shared locals. This paper measured that function by AST and did not read it in full. `cli.py` is 1,914 lines in one file.

Source comments carry the project's history where the design should be: 553 references to sprint or K numbers, 110 to review or audit findings, 492 `§` citations. A reader of `kernel/topology.py` learns that `Budget` was "Additive kernel primitive (Sprint 164, amended Sprint 166...)". The BLACKBOARD and git already hold this.

Package names follow mechanism. `reference/` (1,025 lines) re-exports `adapters/` for back-compatibility. `topologies/` holds things that are not topologies: `session_registry.py`, `workspace.py`, `runs/`, `applications/registry`. `substrate.app` is a second flat facade, added on 2026-10-08 when the first had come to depend on the applications above it.

An abandoned session recorded on the BLACKBOARD on 2026-11-09 listed similar findings. Checked against the code: `session/__init__.py` is 1,785 lines and `_drive` 150, as it said. `api` holds 119 names, where it said 124. `build()` checks two reference kinds, where it said "1 of 4 invariants".

---

## The boundary

The thinking was that substrate-ui is the window and substrate is where things run.

**Sources.** Ousterhout's book text was not read. Its edition history comes from his Stanford page, chapter and section titles from reader notes and a table of contents, and direct quotations from his public exchange with Martin. Section 9.4 is "Separate general-purpose and special-purpose code" and section 6.6 is "Push specialization upwards (and downwards!)". Parnas 1972 was read by OCR of a scan: the criterion is to begin with "difficult design decisions or design decisions which are likely to change. Each module is then designed to hide" such a decision. Fowler's "Separated Presentation" gives the rule and the test: "The presentation is able to call the domain but not vice-versa", and imagine "writing a command line interface for the same application"; code that the second presentation would duplicate belongs in the domain.

**What holds.** Python imports run one way: `substrate` imports nothing from `substrate-ui`. Kernel internals stay hidden. Kind names reach the window through generated files (`scripts/gen_kinds.py`), and a search found none retyped in `web/` outside tests. `general-purpose below, special-purpose above` is also what `substrate`'s internal layers do, and `lint-imports` holds them.

**What does not.** `server.py` is 5,462 lines, and it is not a window. Sorted by function name:

| Purpose | Lines |
|---|---|
| Session service: open, turn, end, interrupt, patch, resume, shutdown | 2,040 |
| HTTP and process plumbing | 1,274 |
| Record reads and projections | 603 |
| Workspace files, worktrees, recents | 547 |
| Model roster and CLI sign-in | 479 |
| Topology launch | 408 |

The window proper is `web/` (11,060 lines, generated files and tests excluded) and `electron/` (1,416). `_build_session_topology_from_manifest` decides what a session is: it assembles eleven tools by name plus `skill`, sets `max_turns=200` and `turn_max_steps=24`, and passes at least 15 keyword arguments to `session_topology`. `_session_turn` computes the turn's context slice, skill routing and attachments inside an HTTP handler. Ousterhout's "Pull Complexity Downwards" and the section on specialization both put these decisions in a layer below the presentation.

Fowler's test has already been run, by accident. Substrate has a command line, and it is the second presentation. `substrate chat` reaches sessions through `substrate-ui/server.py`:

```
[config] daemon not running and [daemon] server_path is empty in …/.substrate/config.toml — set it to the absolute path of substrate-ui/server.py, or start the daemon manually.
```

That command, run with an isolated home and no daemon, exited 64. `server.py` is not in the package on PyPI, so `substrate chat`, `substrate daemon` and `substrate session` from a plain `pip install` have nothing to start. The reverse paths exist as well:

- The `run_topology` tool in `topologies/tool_loop/substrate_tools.py` calls `daemon_client`, which calls HTTP on `server.py`, which runs `Runtime`. The call leaves substrate and comes back.
- `tests/_ui_daemon.py` imports `server.py` from the sibling checkout, and 4 test files use it. Without the sibling they skip.
- `_daemon.py` and `server.py` are two ends of one HTTP protocol, in two repos, with no shared schema. The two have drifted: `cli.py:1261` and `:1290` tell the user `/api/applications` and `/api/topology/<name>/run` are "not yet shipped", and `server.py:2872` has served them since sprint 225a.

The line has also been moving. `SessionRegistry` began in `substrate-ui` and moved to the kernel on 2026-10-01. `workspace.py` moved on 2026-10-13 (K315). `substrate-ui`'s recorded scope still reads "through `substrate.api` ONLY" and "a lens, never a controller of run semantics", followed by a note that the app has since taken on opening and driving sessions.

**Verdict.** Three layers exist and the repo split acknowledges two. The kernel and topologies are one; the window is another; between them sits a standing-session service with a registry, a wire protocol, session assembly, a model roster and workspace management. Half of it is in `substrate` and half in `server.py`. The window-and-engine idea is right, and the code has not carried it out. Under Parnas's criterion the design decision "what a session is and how it is hosted" is hidden in no module. The earlier note's verdict that the boundary is correct looked at import direction only.

---

## The repo as a project

Measured against the two guides and `sdd-kit-3`:

| Item | State in `substrate/` |
|---|---|
| Runbook | None. |
| `process/BLACKBOARD.md` | The kit has required one stream, newest last, since 2026-10-29. This file still has eight sections and a "Single writer per section" header. The kit's decision search finds 6 entries; the `## Decisions` section holds 22 more. `substrate-ui`'s same search finds 120. |
| `process/planning/` | 81 flat files and one folder, no index. `substrate-ui` has 25 folders and a `README.md` with status per piece of work. |
| Sprint cards | 259 entries, highest 340. The BLACKBOARD records K341 to K344 as built, with no cards. |
| `process/WORKING_AGREEMENT.md` | Says Apache-2.0 where `LICENSE` and `pyproject.toml` say PolyForm Noncommercial; vocabulary 0.3 where `current.json` points to 0.4; session vocabulary v0.8 where the file says v0.18; halt conditions from sdd-kit-2; "The Architect runs these" where kit 3 has the agent run the build. |
| `CONTRIBUTING.md` | Cites `../sdd-kit-2/` and `0.2.json`. |
| Dangling citations | `process/RESEARCH.md` (the file is `process/planning/RESEARCH.md`); `docs/review/` (now in the workspace `docs/`). |
| Git | `process/runs/` is 18,340 of 19,414 tracked files and 10 GB on disk; `.git` is 1.1 GB. History begins 2026-09-29, though the BLACKBOARD begins in June. |
| Deleted work | The BLACKBOARD records nine review drafts deleted on 2026-11-09. The kit forbids deleting files. |

`substrate-ui` is further along, as the Architect said, and it has aged. `RUNBOOK-2026-10-29-project-r6.md` names `electron/main.js` and `web/reveal_component.ts`, and neither exists now: Electron main moved to TypeScript and the window to React. Its last end-to-end run was 2026-10-27, and 104 commits have landed since 2026-10-29. `README.md` still says React comes from a CDN. The guide's second rule, that every path exists, fails on the model the substrate runbook would follow.

Versioning between the two is by path. The app builds its kernel from `../substrate` HEAD (`scripts/fetch-python-runtime.sh`) and records the commit, and a PyPI release gates nothing in it. `substrate-kernel` 1.1.2 is a public version, and its largest consumer ignores it.

---

## What a standard implementation is

**Each primitive is a named type, exported under its own name.** PEP 544 protocols may be generic and PEP 695 gives the syntax on the project's 3.12 floor, so `Producer[I, E]`, `View[T]` and `type Predicate = ...` cost nothing. `Trigger` and `Route` are public frozen values. The authored payload and the stored `Envelope[T]` are two named types with one conversion. The Bus is one class owning `append` and read access, with `AppendCycle`'s steps inside it.

**A Topology is an immutable value.** The Builder pattern's `build()` returns a finished product. Validation there rejects duplicates and checks every subscribed kind, starter, slot and View against the declared schemas. Kinds become references to `Struct` classes where a topology has the class in hand.

**One writer, one frame path.** A single function creates envelopes and advances the sequence. The control queue drains in a loop.

**The package states its layers.** A core of primitives, Bus, runtime, record and encoding, under Liedtke's test, named for what it is. A library of standard Views, policies and firing rules, built on the core with no privileges. Topologies above that. A session service, holding the registry, the session assembly now in `server.py`, the workspace logic and a typed wire protocol, with one schema used by client and server. `cli` and the window are two presentations of that service, and substrate-ui contains the window and its process launcher.

**The public surface is grouped.** The package root exports the primitives. `substrate.views`, `.termination`, `.record`, `.replay` and `.errors` carry the rest. A runtime-level import rule replaces the two-segment test.

**Comments say what the code cannot.** Sprint numbers stay in git and the BLACKBOARD.

**What a rewrite carries over unchanged.** The specs' semantics; the on-disk record format and the 18 committed records; the 17 conformance checks; the 1,711 collected tests, or a stated successor to each. Technique 43 of `sdd-kit-3/TECHNIQUES.md` defines a refactor by the same contract outcomes before and after. Struct class names and fields are part of the record: `RunStarted` hashes event schemas, and K344 regenerated 2 of 18 bundled records for one added field. The probes above are behaviour too, so each one changed by the rewrite is a recorded change to the spec or vocabulary.

---

## Corrections to the earlier note

| The note says | Measured |
|---|---|
| "The boundary is correct" | Import direction is correct; the service layer is split across both repos |
| "Substrate has no knowledge of substrate-ui" | `cli.py` launches `substrate-ui/server.py`; `tests/_ui_daemon.py` imports it; `_daemon.py` is its client |
| `api` re-exports 73 names | 119 |
| 145 Python files across 13 subpackages | 159 files; 10 subpackages and 16 top-level modules |
| Session topology ~3,500 lines | 5,341 |
| `tools/sync-substrate-vocab.ts` runs at build time | Exists only in `_deprecated/classic-tree/` |
| 340+ sprint cards | 259 entries, highest number 340 |
| BLACKBOARD has 1,344+ entries | 1,350 lines |

## Not checked

`session/__init__.py`, `cli.py` and most of `server.py` were measured and sampled, not read whole. `kernel/`'s `runtime.py` was read from line 150 to 439, `sequencer.py`, `topology.py` and `policies.py` whole. The line counts for `server.py` come from sorting functions by name and are approximate at the edges. The Ousterhout book text was not consulted; a claim needing a page reference needs the book.

## Sources

- J. Ousterhout, *A Philosophy of Software Design*, 2nd ed., 2021. [Author's page](https://web.stanford.edu/~ouster/cgi-bin/book.php). [Reader notes used for chapter titles and short quotations](https://dev.to/danlebrero/book-notes-a-philosophy-of-software-design-cna).
- J. Ousterhout and R. Martin, [aposd-vs-clean-code](https://github.com/johnousterhout/aposd-vs-clean-code), 2024–25. First 100,000 characters read.
- D. Parnas, "On the criteria to be used in decomposing systems into modules", *CACM* 15(12), 1972. [Scan](https://wstomv.win.tue.nl/edu/2ip30/references/criteria_for_modularization.pdf), final pages OCR'd.
- M. Fowler, [Separated Presentation](https://martinfowler.com/eaaDev/SeparatedPresentation.html); [Presentation Domain Data Layering](https://martinfowler.com/bliki/PresentationDomainDataLayering.html).
- J. Liedtke, "On µ-Kernel Construction", SOSP 1995. [Paper](https://cgi.cse.unsw.edu.au/~cs9242/22/papers/Liedtke_95.pdf); quotation taken from [UNSW lecture slides](https://cgi.cse.unsw.edu.au/~cs9242/25/lectures/01a-intro.pdf).
- [PEP 544](https://peps.python.org/pep-0544/), [PEP 695](https://peps.python.org/pep-0695/).
- `sdd-kit-3/` in full, excluding `_prior-2026-10-29/` and `example/` as the substrate-ui runbook directs. `docs/runbook-guide-2026-10-30/GUIDE-2026-11-04-runbook-r2.md`. `docs/document-organization-guide-2026-10-30/GUIDE-2026-10-30-reorganizing-files-and-folders-r3.md`.

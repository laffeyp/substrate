# Substrate refactor sequence and its effect on substrate-ui

2026-11-09. The order of work that turns the code described in `RESEARCH-2026-11-09-substrate-design-and-boundary-r3.md` into the standard implementation that paper ends with. The paper holds the patterns, techniques and forms for each part. This document holds the order, the reason for it, and what each stage does to substrate-ui. The exact plan for a stage is written when that stage starts, from the code.

## Running the refactor alongside substrate-ui work

The refactor can run while substrate-ui work continues. It needs one preparatory change in substrate-ui and a branch for each stage. One long branch for the whole refactor will not work.

### Current activity in the two repositories

substrate-ui is mid-feature. Sprints 389 to 391 are building the code editor, its working tree holds 51 changed files, and it took 91 commits since 2026-11-01. A recorded decision halts the project after Phase 1 of the code editor, until the design team finishes its SDD process.

substrate-ui's work also changes substrate. Attachments arrived as a pair on 2026-11-08: K344 in substrate and sprint 388 in substrate-ui. In the four weeks to 2026-11-09, 54 commits changed substrate's `src/`, and the files they touched most are the ones the refactor rewrites: `topologies/session` 65 times, `runs` 48, `tool_loop` 15, `session_registry.py` 11.

### Branching options

| Approach | What happens | Verdict |
|---|---|---|
| One branch for all 13 stages, merged at the end | Substrate's `main` keeps taking session changes while the branch rewrites the same files. Fowler: "The problem with big merges is not so much the work involved with them, it's the uncertainty of that work" | Rejected |
| All stages directly on `main` with substrate-ui's imports changing as they go | Six stages break substrate-ui's imports while its work is in progress | Rejected |
| One short branch per stage, merged to `main` when its checks pass, with substrate-ui behind one import module | Each merge is small. Substrate's `main` always works with substrate-ui | **Use this** |

Each stage branch lives in a git worktree, so the `../substrate` checkout that substrate-ui's development uses stays on `main`. To check a stage against substrate-ui, a matching pair of worktrees sits side by side in one parent folder. `../substrate` then resolves to the stage branch, and the paths hardcoded in `package.json`, `.githooks/pre-commit`, `server.py` and the harnesses work unchanged. A stage branch merges `main` into itself before it lands, which picks up any additive session change that substrate-ui's work has added.

### The import boundary in substrate-ui

substrate-ui's non-test code imports about 120 names from 29 substrate module paths, spread over eight files, and its tests import 104 names from 13 paths. That spread is why a substrate move reaches substrate-ui.

The Anti-Corruption Layer pattern, from Eric Evans, puts "a facade or adapter layer between different subsystems" ([Microsoft's description](https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer), vendor documentation), so that communication on one side "always uses the data model and architecture" of that side. Here the layer is one module, `substrate_boundary.py`, at substrate-ui's root. It is the only Python file that imports substrate, and an import contract in substrate-ui enforces that. Python held in strings also imports substrate, in `harness/shakeout/handoff_live.ts`, `harness/shakeout/topologies_live.ts` and `scripts/fetch-python-runtime.sh`; no import contract reads strings, so those three files are listed and change at stage 12. Every other file imports from the boundary module, under today's names.

```python
# substrate_boundary.py, at stage 0
from substrate.topologies.session import UserMessage, FileWritten, session_topology

# the same file, after stages 7 and 12
from substrate.session import UserMessage, FileWritten, SessionConfig, build_session

def session_topology(**settings):
    return build_session(SessionConfig(**settings))
```

`server.py`'s call and its keyword arguments stay as they are. A person working on the editor sees one rule: import substrate names from `substrate_boundary`. When a refactor stage renames something, that file changes and nothing else in substrate-ui does. Editor work does not touch that file, so the two never conflict.

### Contract test in substrate

A consumer-driven contract "represents the mandatory set of exportable elements required to support consumer expectations" ([article on Fowler's site](https://martinfowler.com/articles/consumerDrivenContracts.html)). Substrate gains a test that imports every name `substrate_boundary.py` uses, from a list committed in substrate. A stage that would break substrate-ui then fails substrate's own gate, on the stage branch, before anyone in substrate-ui sees it.

### Stages substrate-ui never sees

Stages 1, 2, 3, 4, 9 and 13 change nothing substrate-ui imports. Stage 5 changes names only in what the stream shows for non-session topologies. These merge to `main` as they pass.

### Stages that change the boundary module

Stages 6, 7, 8, 10, 11 and 12 change names substrate-ui imports. Each lands as a pair of commits: the substrate change and the `substrate_boundary.py` change, tested together in the worktree pair and merged together. Substrate's `main` and substrate-ui's `main` are never out of step.

### What substrate-ui needs by the end

| Change | Stage | Where it lands |
|---|---|---|
| Every import path | 12 | `substrate_boundary.py` |
| `session_topology` keyword arguments become `SessionConfig` | 7 | A function in `substrate_boundary.py` that keeps today's signature |
| `SessionRegistry` split into three classes | 7 | None: `SessionService` keeps the 23 methods `server.py` calls, and the boundary module exports it under the old name |
| Tool suites | 8 | None for `full_suite`, `make_delegate`, `make_skill_tool` and the `substrate_tools` makers, which `server.py` passes through without calling `Tool` |
| `background.TABLE` and `run_hold.TABLE` | 8 | `substrate_boundary.py` exposes the owned objects |
| Responders | 6 | Constructors unchanged; `context_tokens()` stays on `OllamaResponder`; test doubles of a Responder change |
| `read_record` and the inspection functions | 10 | Dict readers stay available through the boundary module, so substrate-ui's `read_record` calls stay as they are |
| `gen_kinds.py`, `demo_topologies.py`, `gen_demo_records.py`, the shakeout fixture | 7 and 11 | Those four files, which define or inspect topologies |
| Python in strings in `harness/shakeout/handoff_live.ts` and `topologies_live.ts`, and in `scripts/fetch-python-runtime.sh` | 12 | Those files |
| The import allow-list at `tests/test_server.py:357` | 12 | That test |
| Front end | 11 | One string: `web/app/state/studio.ts:131` tells the user a spec "builds through the real TopologyBuilder", a class stage 11 removes. Event kinds and session names stay the same, so the generated `.gen.ts` files do not change |

Moving substrate-ui onto typed `Record` events and calling `SessionConfig` directly are later, separate work that substrate-ui can take up whenever it wants. The refactor does not depend on them.

### Timing of the session stages

Stage 5's last step and stage 7 rewrite the session while substrate-ui's work adds to it. Additive changes merge cleanly into a short branch. The halt after Phase 1 of the code editor is the natural time to run stages 7 and 12, the two largest, because no substrate-ui work will be adding to the session then.

## Ordering constraints

### New forms before conversions

Topologies cannot convert until typed declarations exist, and a `Topology` declaration cannot be reused across runs until run state has left the declarations and moved into the Bus.

### substrate-ui's imports of substrate internals

Eight of its non-test Python files and 47 of its 71 test files import substrate. `server.py` alone uses 25 internal module paths, among them `substrate.topologies.session`, `substrate.topologies.tool_loop.delegate`, `substrate.topologies.applications.*`, `substrate.adapters.models` and `substrate.assay.cells`. Module moves therefore come after the code being moved has reached its final shape, so each import path changes once.

### Changes across both repositories

substrate-ui's development commands run with `uv run --project ../substrate`, so a change to substrate reaches it at once. A stage that changes a name substrate-ui imports lands in both repositories together, and from stage 0 on the substrate-ui side of that change is `substrate_boundary.py`.

### The installed app

`scripts/fetch-python-runtime.sh` builds a substrate wheel from `../substrate` and bundles it into the app. The installed app keeps its own copy until a new build is installed, so work in progress cannot break it.

### Names on old records and in sessions

Every record carries its own manifest. The session's Producer kinds, Trigger ids and View names are pinned by closed enums to the names the session vocabulary ratified, so a parked session continues under the same names, and the transcript and `harness/shakeout/structure_lists_producers.ts` see what they see today. Other topologies derive their names. Where substrate-ui or the conformance suite reads a name, either the name is pinned or the reader changes in the same conversion.

### Parked sessions across an upgrade

Each turn rebuilds the topology and resumes the existing record, so a session parked by old code continues under new code once a new build is installed. A session record parked by today's code is kept as a fixture from stage 1, and it runs at every stage that changes the session.

### Releases

Substrate is published at 1.1.2, with `substrate.api` as its public surface. Public names also break at stages 6, 8 and 11, so nothing is released from stage 6 until stage 12, which is version 2.0.0.

## Checks at each stage

Every stage ends with substrate's `scripts/ci_local.sh`. A stage that changes substrate-ui also ends with commands 1 to 7 of the build table in `substrate-ui/RUNBOOK-2026-10-29-project-r6.md`: ruff check, ruff format, `gen_kinds.py --check`, `npm run build`, `npm run test:unit`, `harness/vm_smoke.ts`, `npm run test:py`. Stages 5, 7 and 12 also run commands 8 to 16, which build the packaged app and run its smoke, shakeout, lifecycle, transcript, tasks and resume harnesses.

## Stages

### 0. Import boundary in substrate-ui

**Reason.** Every later stage that changes an import needs one place to change it.

**Work.** `substrate_boundary.py` is created at substrate-ui's root, exporting every substrate name substrate-ui uses. The eight non-test files and 47 test files import from it. An import contract forbids importing substrate in any other Python file. The Python held in strings in `handoff_live.ts`, `topologies_live.ts` and `fetch-python-runtime.sh` stays outside the contract and is recorded with the list of names. Substrate gains the contract test and its list of names.

**substrate-ui.** Import lines change in those 55 files, and no other line does.

**Done when.** substrate-ui's commands 1 to 7 pass, and the import contract and the contract test both pass.

### 1. Safety net

**Reason.** Later stages claim to preserve behaviour, and these tests check the claim.

**Work.** Golden Master: the 18 committed records are compared by equivalence through `first_divergence`, because ULIDs differ on every run. A comparator is added that takes a committed old-to-new name map, compares every frame after the mapping and reports all differences, so a renaming conversion can be checked before its record regenerates. Characterization tests for the session paths those records do not reach (resume, interrupt, change of settings, MCP call, language measurement) and for the kernel's failure paths that write frames directly. A session record parked by today's code is kept as a fixture. Shared test helpers move to `tests/support/`.

**substrate-ui.** No change. Its build-table commands 1 to 7 are recorded as the starting state.

**Done when.** Altering one payload field in one committed record makes the comparator report it, and each new Characterization test passes on today's code.

### 2. Specification amendments

**Reason.** The product spec requires a disagreement between code and spec to be resolved in the spec first.

**Work.** New spec drafts, with the prior ones preserved: a topology is a frozen declaration; names are derived from the code or pinned by closed enums; there are nine pieces; the typed `Record` read surface returns. They also amend the text the design contradicts: the Trigger tuple with `producer_factory`, per-instance factories and `start(input)`, the builder as the vocabulary, subscription by Producer id, the free inspection functions, and the rule that the CLI imports only `substrate.api`. The vocabulary changes go through typed proposals in `process/signals/proposals.json` and a version bump: Topology's and Trigger's definitions, `RunRecord`, the nine pieces, and new entries for Fragment, Initial, Body and Join.

**substrate-ui.** No change.

**Done when.** The new drafts and the bumped vocabulary exist, and `docs/README`, `docs/tutorial.md`, `docs/design/ui-design-handoff.md`, `docs/swebench/swebench-solver-design.md`, `cli.py` and `projections/inspect.py` say nine. Older documents whose subject is a past design stay as written.

### 3. Typed pieces

**Reason.** Everything after this stage moves onto these types.

**Work.** Added beside the old code: Producer, View, Predicate, Trigger and Route as named generic types, `Topology` and `Fragment` with every form the builder has today, one Struct per lifecycle event, and the identifier types. The Bus arrives at stage 4 and `Record` at stage 10. Each sprint card names stage 5's first conversion as the production consumer, as the working agreement requires. `Topology` translates itself onto today's builder. This is the ensemble rewrite in `evidence-topology-value/`, moved into the package.

**substrate-ui.** No change.

**Done when.** The ensemble topology runs through the new declaration in a test, and a lifecycle Struct encodes to the same JSON as today's dict for every kind.

### 4. Kernel and Bus

**Reason.** A topology cannot be a reusable declaration until run state leaves it. This stage must precede the conversions, and above the kernel it changes only the runtime's private readers.

**Work.** One append path. `AppendCycle` becomes `Bus` and takes admission and the writer loop. `ProducerSupervisor` is extracted. `RunState` dissolves into its owners. Firing state moves to the Bus. The subscription index replaces the scans. Files stay where they are: the moves in and out of the kernel happen at stage 12, so each import path changes once. Firing state stays fresh per run and per resume, as it is today.

**substrate-ui.** No code change. It reads no private runtime state. `session_registry.py`, `tool_loop/__init__.py` and `runs/hold.py` in substrate change from `_st` and `_loop` to public queries, and tests that read `_st` use `live_instances()`.

**Done when.** One `Topology` runs twice with the same result, the parked-session fixture resumes, and the perf floor test passes.

### 5. Topology conversion

**Reason.** The types and the Bus now exist. Strangler Fig: the builder and the declaration run side by side until the last topology has moved.

**Work, in order.** Each conversion uses typed inputs and object references, with names derived from the code.

1. The three reference topologies, which have the most tests and the least depending on them.
2. `conversation.py` and `instruments/`, then what is built on them: `debate`, `natural_conversation`, `prisoners_dilemma`, `intel_asymmetry`.
3. Independent topologies: `adversarial_pair`, `pair_coding`, `game_of_life`, `recursive_decomposition`.
4. `code_review`, then `fanout_review`, which composes it.
5. `best_of_n` as a Fragment, then its users: `coding_flow`, `code_evolution`, `best_of_n_verified`, `research_sweep`, `swebench_solver`.
6. `assay`'s arms and the conformance topologies.
7. `tool_loop`, because `session` imports its tool Producer.
8. `session` and its CI driver, last, as the largest and the one in daily use.

**substrate-ui.** `gen_demo_records.py` and `demo_topologies.py` regenerate or convert when the topologies they use do. Non-session Trigger and Producer names change in what the stream shows. `tests/test_server.py` asserts `adjudicate` and `reviewer-security`, so those topologies pin the names or the test changes with the conversion. `web/app/derive/structure.ts` tags instruments by `t.id === t.starts`, and the instrument declaration keeps that true. `server.py`'s imports of these topologies keep working, because each still has a function of the same name at the same path until stage 12. A converted topology's return value is callable by the old `Runtime.run` path, so `server.py`'s run calls are unchanged.

**Done when.** Every topology in `bundled.py` is a `Topology`, each committed record has passed the comparator and regenerated with the same events apart from derived names and `fingerprint.qualname`, and the session record parked by the old code, kept as a fixture in stage 1, resumes under the converted topology in a test.

### 6. Model interface

**Reason.** It is independent of stages 3 to 5 in its code, but stage 7 needs a single `respond` so session's model step can be simplified once.

**Work.** Branch by Abstraction: `Responder` and the capability Protocols, each adapter moved behind them, `call_responder` removed, CI stand-ins moved behind `ScriptedResponder`.

**substrate-ui.** `substrate_boundary.py` changes in the same pair of commits, along with any test double that implements a Responder.

**Done when.** No `getattr` probe of a Responder remains in either repository.

### 7. Session

**Reason.** The session has converted, its tools have converted, and the model interface is settled.

**Work.** `SessionConfig` replaces the 31 parameters. `TurnState` and `advance` become a View, and Triggers read the phase. `session_registry.py` is split into manifest store, name index and turn dispatcher, in place. `SessionRecord.turns()` becomes the one definition of a turn.

**substrate-ui.** `substrate_boundary.py` keeps `session_topology`'s signature and exports `SessionService` under the old name, so `server.py`, `scripts/gen_kinds.py`, the shakeout fixture and the 20 lines that construct `SessionRegistry` stay as they are. Two private reads change, in `test_server_session_queue_cap.py` and `test_session_registry_first_turn_uses_run.py`.

**Done when.** Both repositories' checks pass, the packaged app's harnesses pass, and the parked-session fixture resumes.

### 8. Tools and ambient state

**Reason.** Tool arguments and `ToolContext` change every tool's signature at once, and session is the largest caller.

**Work.** Parallel Change: one Struct per tool, then `ToolContext` replacing the ContextVars. Process-wide tables move to the session service.

**substrate-ui.** `substrate_boundary.py` exposes the owned `background` and `run_hold` tables. `server.py`'s calls to `full_suite`, `make_delegate` and `make_skill_tool` stay as they are. Tests that patch `TABLE` take an owned object.

**Done when.** No tool takes a positional list, no module-level mutable table remains in `session`, `tools` or `runs`, and the parked-session fixture resumes.

### 9. Composition

**Reason.** Fragments exist from stage 3 and are in use from stage 5. This stage finishes what the conversions left: joins, failure Decorators, and the export map on the declaration.

**Work.** `Join` replaces fan-in arithmetic. `on_failure` replaces per-body handling. The retired solver topology and placeholder terminations go.

**substrate-ui.** `server.py`'s application launches (`fanout_review_topology`, `best_of_n_verified_topology`, `research_sweep_topology`, `pair_coding_composite`) change only if a signature does.

**Done when.** One definition of a fan-in exists and no topology overwrites a termination.

### 10. Reading the record

**Reason.** The typed lifecycle events from stage 3 and the manifest Struct are in use everywhere that writes them.

**Work.** `Record` holds the loaded frames and the inspection queries. Blobs resolve by default. Writer and reader share the manifest Struct, filled from `Registration` until stage 11, and the manifest gains its initial-Producers field. Projections read typed events. Blob resolution by default lands as its own change, and so does a typed error, naming the kind and version, for a frame whose schema version the reader does not support.

**substrate-ui.** `api.read_record` (44 uses), `api.attach`, `api.narrate`, `api.narration_summary`, `api.topology_graph`, `api.run_graph`, `api.first_divergence`, `api.trace_ancestry`, `api.explain_producer`, `read_last_envelope` and the record-summary code in `server.py` keep working, because `substrate_boundary.py` exports dict readers built on `Record`.

**Done when.** Nothing in `projections/` takes `record: Any`, and every committed record differs only by the new initial-Producers field.

### 11. Builder removal

**Reason.** This is the contract phase of Parallel Change. `Runtime` holds the declaration directly from here, so the manifest Struct moves from `Registration` to the declaration.

**Work.** `Runtime` takes `Topology` directly. `TopologyBuilder`, `Registration` and the declaration's translation onto the builder are removed. The event-kind constant tables and their matching tests go, and the session's Producer-kind and Trigger-id constants have become enums. The tutorial and `docs/adding-a-topology.md` are rewritten for the declaration.

**substrate-ui.** `scripts/gen_kinds.py` reads kinds, Trigger subscriptions and Views from the `Topology` in place of `b.build()`. `demo_topologies.py`, `gen_demo_records.py`, `harness/shakeout/fixtures/write_session_shapes.py` and the tests that define topologies with `api.TopologyBuilder` convert. The Studio's validate message at `web/app/state/studio.ts:131` names the declaration in place of `TopologyBuilder`. The generated `.gen.ts` files stay the same, because event kinds keep their names.

**Done when.** No code in either repository imports or calls `TopologyBuilder` or `Registration`, and no string shown to the user names them.

### 12. Module organization

**Reason.** Every module now has its final shape, so each import path changes once. It breaks the most, so it comes last among the structural stages.

**Work.** Mikado Method to order the moves. `record/`, `encoding.py`, `errors.py` and `constants.py` move into the kernel, and standard Views, termination recipes, composition, Predicate combinators and `attach` move out. The cycles between `session`, `tool_loop`, `session_registry` and `runs` are removed. Non-topologies leave `topologies/`. Root modules move to their layers. `cli.py` becomes a package. `api.py` and `app.py` are removed in favour of the package root and named public modules. Tests move to mirror the package. Version 2.0.0.

**substrate-ui.** The import lines in `substrate_boundary.py` change path, one package at a time, along with Python held in strings in `harness/shakeout/handoff_live.ts` and `topologies_live.ts`, in `scripts/fetch-python-runtime.sh`, and the allow-list in `tests/test_server.py`. Private substrate code lives in `_internal` modules, and the import contract in substrate-ui forbids them. The canonical-home registry in `WORKING_AGREEMENT.md` changes with the moves, and the rule that the CLI imports only `substrate.api` has gone by then.

**Done when.** The import contracts pass in both repositories, and in substrate-ui only `substrate_boundary.py` and the listed Python strings import substrate.

### 13. Code style

**Reason.** Earlier stages delete most of what it would touch.

**Work.** Aliases, in-repository compatibility code and history in comments are removed. Tests that assert on source text become behaviour tests.

**substrate-ui.** No change from this stage.

**Done when.** A search for sprint and ticket numbers in `src/` finds none.

## Stages that can overlap

Stage 0 can start at any time. Stage 6 shares no code with the conversions in stage 5 until `tool_loop` and `session`, so the two can overlap up to that point. Stages 9 and 10 touch different code and can overlap. Everything else runs in the order given, because each stage depends on the shape the one before it leaves.

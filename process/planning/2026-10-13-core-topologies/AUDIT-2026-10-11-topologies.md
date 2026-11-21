# AUDIT: the topologies a session can reach — real or toy

*2026-10-11. Release roadmap step 4 (`substrate-ui/process/planning/ROADMAP-2026-10-11-before-distribution.md`). One finding per topology, on two dimensions: its build, measured against the session topology, and its purpose, measured by whether it does what it claims on real work and whether a session gains anything by calling it. Findings only; no actions.*

## 1. The set, and the baseline

A session reaches topologies through the toolkit tools and `delegate`, bound in `substrate-ui/server.py:675-702`:

- `list_topologies` returns the 18 names in `bundled.BUNDLED` (`topologies/bundled.py`). Each is a zero-argument factory with deterministic stand-in models and fixed inputs.
- `list_applications` returns the 5 manifests in `topologies/applications/*.manifest.toml`.
- `run_topology(name, inputs)` runs only applications (`server.py:3376`). Of the 5, three are one-shot (`code_review`, `best_of_n_verified`, `research_sweep`), one is a session composite (`pair_coding`), and one is refused (`daily`, `runs = "session"`).
- `delegate(task)` runs a child `tool_loop` on a real model.

So 15 of the 18 names `list_topologies` gives a session cannot be run by it. `run_topology` answers 404 for every bundled name that is not also an application.

**The baseline** is the session topology. It has seven properties, and each topology below is measured against them:

1. A ratified vocabulary (`process/signals/session-vocabulary.md`, v0.7, signed).
2. A spec section that says what it is for and how it works.
3. The record is the truth: the topology only appends, its state and prompts are pure functions of the record, and its events state what the model actually produced.
4. Both contracts: unit tests on the logic, and an observation test against a real model that checks behaviour, not wiring.
5. A bundled `ci_mode` record that replays and is current with the schema.
6. Real use: records of actual work in `~/.substrate`.
7. A rendered surface: the UI shows its events in readable form.

## 2. Evidence of use

`~/.substrate/sessions` holds 86 sessions. Across all of them, the toolkit calls were: `inspect_record` 17, `list_applications` 4, `list_records` 4, `list_topologies` 3 (+1 as a harness call), `run_topology` 3, `list_sessions` 1, `delegate` 0.

All three `run_topology` calls are in one session, `s_ab960f90985d49f796fd3754`, seqs 252–272. The model wanted a bash command run and tried three names in turn:

| Seq | Name tried | Result |
|---|---|---|
| 252 | `session` | 404 `unknown application 'session'` |
| 260 | `daily` | 400 `runs='session'; open it via POST /api/session` |
| 268 | `tool_loop` | 404 `unknown application 'tool_loop'` |

No session has ever completed a topology run. `~/.substrate/runs`, where those runs write their records, has been empty since the clear of 2026-10-08.

Outside sessions, one topology has done real work: the SWE-bench solver resolved 108 of 300 SWE-bench Lite instances on qwen3-coder:480b-cloud (n=3, 2026-06-27; `process/runs/assays/full/qwen3-coder_480b-cloud/README.md`).

Every other topology's only runs with a model are its `@realmodel` tests (`tests/test_realmodel_demos.py`) on `llama3.2:1b`. Those tests assert wiring (two distinct texts, an event of a kind exists, a Route fired), not usefulness. The file says so: "Whether the writer's revision *improves* the artifact is model-dependent and NOT asserted here."

## 3. Build, against the seven

Key: ✓ met · ◐ partial · ✗ missing.

| Topology | 1 Vocab | 2 Spec | 3 Record true | 4 Tests (unit / live) | 5 Bundled record | 6 Real use | 7 UI surface |
|---|---|---|---|---|---|---|---|
| `session` / `daily` (baseline) | ✓ v0.7 | ✓ | ✓ | ✓ / ✓ | ✓ 2026-10-11 | ✓ 86 sessions | ✓ transcript, console |
| `tool_loop` | ◐ kinds in session vocab | ◐ `docs/tool-loop/` | ✓ | ✓ / ✓ | ✓ calculator | ✓ as the session's engine; ✗ as a run | ◐ generic |
| `delegate` (tool) | ◐ session vocab §A fields | ✓ product spec r15 §5 | ✓ | ✓ 23 files / ✓ | — | ✗ 0 calls | ◐ |
| `code_review` / `fanout_review` | ◐ `ReviewSubject` locked; `CritiquePosted`, `VerdictRendered` "undocumented" (applications-vocabulary.md) | ✓ r15 §8 | ◐ severity is a hash of the text | ✓ / ◐ llama3.2:1b wiring | ✓ both | ✗ | ◐ generic |
| `best_of_n_verified` | ✓ via swebench-solver vocab §A | ✓ r15 §8 | ✓ | ✓ / ◐ | ✓ | ✗ | ◐ generic |
| `research_sweep` | ✓ applications-vocabulary | ✓ r15 §8 | ✓ | ✓ / ✗ | ✓ | ✗ | ◐ generic |
| `pair_coding` (composite) | ◐ session kinds | ✓ r15 §8 | ✓ | ✗ 0 tests / ✗ | — | ✗ | ✓ as two sessions |
| `pair_coding_chunked` | ✗ | ✗ README only | ✗ driver discards the model | ✓ / ◐ | ✓ | ✗ | ◐ generic |
| `swebench_repair` | ✓ swebench-solver-vocabulary | ◐ planning docs | ✓ | ✓ / ✓ assays | ✓ | ✓ benchmark, not session | ◐ assay surface |
| `debate` | ✗ | ✗ README only | ✓ | ✓ / ◐ | ✓ | ✗ | ◐ generic |
| `prisoners_dilemma` | ✗ | ✗ | ✓ | ✓ / ◐ | ✓ | ✗ | ◐ generic |
| `intel_asymmetry` | ✗ | ✗ | ✓ | ✓ / ◐ | ✓ | ✗ | ◐ generic |
| `natural_conversation` (+ `_bare`) | ✗ | ✗ | ✗ instruments discard the model | ✓ / ◐ | ✓ both | ✗ | ◐ generic |
| `adversarial_pair` | ✗ | ✗ | ◐ severity is a hash; artifact cut at 200 chars | ✓ / ◐ | ✓ | ✗ | ◐ generic |
| `recursive_decomposition` | ✗ | ✗ | ◐ decomposition is not a model's | ✓ / ◐ | ✓ | ✗ | ◐ generic |
| `game_of_life` (+ `_glider`) | ✗ | ✗ | ✓ | ✓ / n/a | ✓ both | ✗ | ✓ grid render |

"Generic" means the reveal graph shows producers and triggers, and the records surface opens the raw record. The UI has no typed rendering of `CritiquePosted`, `VerdictRendered`, `Synthesis`, `Finding`, `Turn`, `JointCall`, `SubtaskProposed` or `CodeChunk`: no file under `substrate-ui/web` names any of them. The one topology-specific render is the game-of-life grid (`reveal_component.ts:1947`).

The spec column refers to `current-design-direction/product-spec/PRODUCT-SPEC-2026-08-17-round15.md` §5b and §8. The kernel specs in `substrate/docs/specs` name no topology.

## 4. Purpose and capability

For each: what it claims, whether it does that on real work, and what a session gains by calling it.

### `session` / `daily` — real (baseline)
Claims a standing driver conversation with tools. It does that: 86 sessions, compaction live-tested on four drivers (K293). `daily` is the same topology. As an application it is correctly refused by `run_topology`, but `list_topologies` still offers both `session` and `daily`, and a model has tried to run both (§2).

### `tool_loop` — real as the engine, toy as a listed topology
The session runs on it. The bundled `tool_loop` entry is the calculator demo: `(2 + 3) * 4` with `add` and `mul` (`tool_loop/__init__.py:21`), or `llama3.2:1b` in walkthrough. A session already is a tool loop, so it gains nothing from the listing. The listing cost one failed call (seq 268).

### `delegate` — real build, never used
It hands a subtask to a child `tool_loop` on a real model. It has caps, cooperative cancel and its own record (`tool_loop/delegate.py:1-37`), with live tests (`test_realmodel_tool_spawn.py`, `test_realmodel_delegate_standing.py`). Across 86 sessions no model called it, including the one at seq 252 whose need it fits exactly: run a command in a child. The session gains a sub-agent with its own record. Whether that helps real work is unmeasured.

### `code_review` (application; `fanout_review` in the listing) — closest to real; output incomplete
It claims a five-role review of a real git diff with a judge. It does gather a real diff (`fanout_review.changed_files`: tracked and untracked, capped at 24,000 chars), runs five reviewers in parallel, and the judge reads the critiques (since UI sprint 099).

Four gaps:

- The session gets back only the last non-substrate event (`substrate_tools._extract_terminal_output`): `VerdictRendered{decision, cited_roles, n_critiques}`. The critiques themselves stay in the child record. Spec r15 §5b says it "returns a verdict plus the individual reviews."
- `severity` is `sum(text.encode()) % 5 + 1` (`code_review/__init__.py:56`), a hash, and it decides the verdict whenever the judge's reply names no verdict word.
- Each reviewer is told to name one issue in one sentence, and each critique is cut at 200 chars.
- The manifest defaults every reviewer to `kimi-k2.6:cloud` and the judge to `claude`, whatever the session runs on. `default_bundle = "reviewer"` names a bundle that does not exist, and nothing reads `default_bundle`.

Never run from a session. What a session gains: five independent second opinions on a diff, if the critiques came back.

### `best_of_n_verified` (application) — real loop, returns no answer
It claims N drafts, independent verification and selection. The loop is real: a drafter, a verifier judged by PASS/FAIL that fails closed (`best_of_n_verified.py:37`), and a retry with feedback. But the terminal event is `Solved{round, slot}` (`best_of_n/contracts.py:53`), so `run_topology` hands the session `{"round": 1, "slot": 0}` and not the answer. The session would have to find the `Candidate` with `inspect_record`. Spec r15 §8 says it "returns the survivor plus the verification trace." Defaults are `kimi-k2.6:cloud` drafting and `claude` verifying. Never run from a session.

### `research_sweep` (application) — real shape, session must paste the documents
It claims readers over documents, a completeness critic, then a synthesis. All three steps call a model and use its reply, and the terminal `Synthesis{text}` is the answer, so `run_topology` returns something usable. Two limits:

- `documents` must be a list of `{label, text}` on the wire (`server.py:569`). The session has to read each file and paste its text into the call. The topology's own `gather(paths)` is not reachable from the application.
- Each document is cut at 8,000 chars, each reader writes one or two sentences, and the readers' notes do not come back.

No live test. Never run from a session.

### `pair_coding` (composite application) — broken from a session
It claims a builder session with a standing reviewer. `_topology_run_composite` registers two sessions and answers `{builder_session_id, reviewer_session_id, …}` with no `run_id`. `_run_topology_impl` then reads `response["run_id"]` (`substrate_tools.py:169`) and raises `KeyError`, so every call from a session fails. Even with that fixed, nothing drives the builder: the calling session gets two ids and no tool that sends a turn to a session other than through `delegate`. The reviewer is given role `reviewer`; the `both_session_shapes` gate showed `fragment_source_failed · role · FileNotFoundError('reviewer.md')`, cause not traced. It has no tests.

### `pair_coding_chunked` — toy
It claims a driver that writes code chunk by chunk, steered by a navigator. The driver calls its model and discards the reply (`pair_coding/__init__.py:67`: `_ = await call_responder(...)`), then emits the canned chunk. With a real model the code is still `def solve(x): y = x + 1; return y`. The navigator's suggestion is routed and recorded, and has no effect on the code. Nothing for a session.

### `swebench_repair` — real capability, wrong door
The listed entry is the CI factory: a one-file fixture repo, `issue="off-by-one in f"`. The full solver behind it (localize → repair → select; `swebench_solver/assemble.py`) resolved 108/300 on Lite. A session cannot reach the solver: there is no application, and it needs a base checkout, a repo skeleton and the Docker select step. A session working on a bug in its own workspace could gain a best-of-N patch with test-based selection, the one topology with measured capability. As listed, nothing.

### `debate` — toy
Two speakers argue a fixed claim ("Open-source AI development is, on net, safer than closed development") for 3 rounds on `llama3.2:1b`, turns cut at 700 chars, no judge. The claim, the model and the round count are all fixed: no input reaches the topology from a session. Nothing for a session as built.

### `prisoners_dilemma` — toy
One round of a fixed scenario; each prisoner's `Decision` is parsed from its own turn. It is a demonstration of a typed outcome emitted by the deciding producer, not a tool. Nothing for a session.

### `intel_asymmetry` — toy
A fixed scenario (the "Karaganda-South facility") with two analysts holding private facts; `JointCall` is parsed from each turn. The private-information mechanic is real. The scenario is hard-coded and nothing reaches it from a session.

### `natural_conversation` (+ `_bare`) — toy, and its record misstates what happened
It claims an ablation: common ground, a repair detector and a grader, routed into the speakers, against a bare arm. All three instruments call a model and throw the reply away:

- `common_ground.py`: `_ = await call_responder(...)`; the "facts" are the first 40 chars of the last three turns.
- `repair.py`: `_ = await call_responder(...)`; the status is `misaligned` on even rounds and `ok` on odd ones, with the note "deterministic misalignment cue (round parity)", in walkthrough as in CI.
- `grader.py`: `_ = await call_responder(...)`; confidence and outcome are a hash of the previous turn.

On top of that, `natural_conversation_topology` never passes a model to the instruments (`_emergence_instruments(deterministic=not walkthrough)`), so they run on `DeterministicResponder(seed=999)` even in walkthrough. The docstrings say "walkthrough: the LLM judges". The WITH-vs-WITHOUT delta measures injected parity cues and text fragments, not a model's judgement. `test_instrument_ablation_delta` checks only that instrument kinds appear in one arm and not the other, so it passes.

### `adversarial_pair` — toy
A writer drafts "a short artifact (a few sentences)" with no task given, and a finder names one flaw. The finder's flaw is real and routed into the revision, but each artifact is cut at 200 chars, the severity is a hash, and there is no input for what to write. Nothing for a session.

### `recursive_decomposition` — toy
It claims a planner that spawns solvers that spawn solvers. The planner calls no model: it emits `"<task> :: part i"` for a fixed fanout. Every solver below `max_depth` emits `"<task> / sub j"` without a model. Only leaves call a model, with `"solve: build a feature :: part 0 / sub 1"`, and nothing assembles the leaf answers. It demonstrates the recursive trigger and the depth guard. As a decomposition it does none.

### `game_of_life` (+ `_glider`) — real simulation, nothing for a session
Conway's rule is correct and pure (`_life`), each cell runs as its own producer, and the grid renders in the UI. It is a demonstration of the runtime's fan-out and fan-in, with no model and nothing a session would call.

## 5. Findings across topologies

1. **The session is offered 18 names and can run 3.** `list_topologies` lists `bundled.BUNDLED`; `run_topology` runs `app.applications`. The one recorded attempt went through three wrong names. The tool descriptions do not say which list `run_topology` takes.
2. **No application returns what its spec says.** Spec r15 §5b and §8 promise the verdict plus reviews, the survivor plus trace, and the synthesis plus reader outputs. The code returns the last event's payload. That payload is the whole answer only for `research_sweep`.
3. **Application models do not follow the session.** Every manifest defaults its roles to `kimi-k2.6:cloud` and `claude`. A session on codex that calls `code_review` runs kimi and claude.
4. **Bundles and slots, as specified, do not exist.** Spec r15 §7b and §8 give each application a default bundle whose slots the session fills. `_topology_run` ignores the `bundle` argument; the `*.bundle/` directories are listed as session bundles instead (`bundles.py:63`); `default_bundle` is read by nothing.
5. **Four producers in two topologies call a model and discard the reply:** the `pair_coding_chunked` driver (`pair_coding/__init__.py:67`) and the `common_ground`, `repair` and `grader` instruments of `natural_conversation` (`instruments/common_ground.py:39`, `repair.py:43`, `grader.py:45`). Their records show a model call next to an outcome the model did not produce. Two more replace a model judgement with a hash: `code_review` severity and `adversarial_pair` severity.
6. **The demo topologies take no input.** `debate`, `prisoners_dilemma`, `intel_asymmetry`, `natural_conversation`, `adversarial_pair`, `game_of_life` and the bundled `tool_loop` have hard-coded subjects, a hard-coded model (`llama3.2:1b`) and no path from a session to change either.
7. **The live tests assert wiring.** No observation test checks that any non-session topology's output is useful. The one topology with a measured result, the SWE-bench solver, has no session path.
8. **Eight of the listed topologies have no vocabulary file:** `pair_coding_chunked`, `debate`, `prisoners_dilemma`, `intel_asymmetry`, `natural_conversation`, `adversarial_pair`, `recursive_decomposition`, `game_of_life`. `code_review`'s own kinds are marked "undocumented" in `applications-vocabulary.md`.

## 6. Verdicts

| Topology | Verdict | What it needs to become real from a session |
|---|---|---|
| `session` / `daily` | Real | Nothing; the listing should not offer it as runnable. |
| `tool_loop` | Real as the engine; the listed entry is a toy | The calculator entry has no session use. |
| `delegate` | Real build; unused | A real session task that calls it, observed. |
| `code_review` | Partly real | The critiques returned with the verdict; severity from the model, or none; reviewer models from the session's roster; a live observation test on a real diff. |
| `best_of_n_verified` | Real loop; unusable output | The selected answer and the verification trace returned; models from the roster; a live test. |
| `research_sweep` | Nearly real | Paths as input (the `gather` it already has); reader notes returned; a live test. |
| `pair_coding` | Broken | The `run_id` crash fixed; a way for the session to drive or hand off the builder; tests; the `reviewer.md` warning traced. |
| `pair_coding_chunked` | Toy | The driver writing the model's code, a task input, a purpose a session has. |
| `swebench_repair` | Real capability; no session path | An application over the session's own workspace and issue text, with the select step's Docker need stated. |
| `debate`, `prisoners_dilemma`, `intel_asymmetry` | Toy | Inputs (claim, scenario, model) from the session, and a reason a session would call them. |
| `natural_conversation` (+ `_bare`) | Toy; misleading record | Instruments that use their model's reply and are given one, before any delta means anything. |
| `adversarial_pair` | Toy | A task input, no 200-char cut, severity from the model. |
| `recursive_decomposition` | Toy | A planner and solvers that decompose with a model, and an assembly of leaf answers. |
| `game_of_life` (+ `_glider`) | Real simulation; no session purpose | None as a session tool; it demonstrates the runtime. |

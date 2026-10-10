# Sprint 265 — Why session-open fragments re-fire after a resume

```yaml
---
id: 265
status: closed
opened_at: 2026-10-09
closed_at: 2026-10-09
phase: 1
pass_kind: observation
roadmap: substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md
---
```

## why

On `s_9eee1b3a4d094346bb30039c`, seq 10–36, a resumed turn re-emitted the bundle and tools fragments (seq 13–20) after its first `UserMessage` (research F6). The cause is not traced.

## scope

Trace the re-emission against the kernel's resume path and the topology's initials. Either fix it so a resumed turn writes no session-open fragment, or record on the card why the fragments must re-fire and what each costs.

## found during K263 (2026-10-09)

- `FragmentCohort` (`session/views.py`) keeps one slot per session-open source, and the newest fragment wins. Its docstring gives the reason: a re-emission overwrites rather than stacks, the case this card traces. The same rule drops all but the last methodology of a bundle whose `extends` chain has two or more, so the model reads only the caller's. K263 kept the behavior, since its invariant was unchanged prompt bytes. Whatever this card finds about re-emission decides whether the slot can hold a source's whole set.
- An in-process `Runtime.resume` of a role + bundle + tools session (K263's counting script) writes no fragment in the resumed turn: 10 envelopes, `UserMessage` to `TerminationMatched`. The `s_9eee…` re-emission came through the daemon's resume, which this did not exercise.
- K261 already made the first message wait for the session prompt (`first-message-on-session-prompt`), and a resume does not re-run an initial (`test_fewer_producers_263.py::test_a_resume_writes_no_second_first_message`).

## trace (2026-10-09, written before the fix)

- **No re-emission.** `~/.substrate/sessions/s_9eee1b3a4d094346bb30039c/record` holds 261 events in one run (one `RunStarted`, `run_id 01M4F3YSGM98WCWZVT8ZPDXKJV`) over nine turns, every turn after the first resumed through the daemon. Each session-open source wrote one fragment in the whole record: `bundle_methodology` at seq 14, `tools_suite` at seq 19. No initial fired after seq 5.
- **What F6 saw.** Four initials started together at `RunStarted` (seq 2–5): `session_open`, `bundle_methodology_fragment`, `bundle_personality_fragment` and `tools_suite_fragment`. `session_open` ran first and wrote the first `UserMessage` at seq 10; the fragments followed at 13–20. That is the first turn of a fresh run, not a resume, and the fragments were late, not repeated. The first model call failed (seq 33), so the turn had not used them. K261 closed this race (`first-message-on-session-prompt`); K263 left one producer to wait for.
- **What follows.** `FragmentCohort` keeps one slot per session-open source and lets the newest win, with "a re-emission overwrites cleanly" as the reason. No session re-emits, so the rule guards against nothing. What it does do is drop every methodology but the last when a bundle's `extends` chain has two or more, and the model reads only the caller's. The fix keeps each source's fragments in arrival order.

### Predicted breaks

- None in the existing suites: no test sets up two fragments of one session-open source. Shipped bundles have no `extends`, so every CI record and every prompt of a real session so far is unchanged.
- The new test fails before the fix (only the last methodology in the prompt) and passes after it.

## prerequisites

- K263 closed (the producers being traced are `session_prompt`).

## context_files

- `sdd-kit-2/AGENTS.md`
- `substrate/process/planning/RESEARCH-2026-10-09-session-topology-structure-round4.md`
- `substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md`
- `substrate/process/signals/session-vocabulary.md`
- `substrate/process/BLACKBOARD.md`
- `substrate/src/substrate/kernel/runtime.py` (resume and initials)
- `substrate/src/substrate/topologies/session/__init__.py`
- `substrate/src/substrate/session_registry.py`

## signal contract

### Emits

None new.

### Invariants

- A fresh session's first turn is unchanged.

## artifact contract

### Files created

- `substrate/tests/test_resume_no_session_fragments_265.py` (if a fix lands)

### Files modified

- Named at trace time; ≤2 files.

### Content assertions

- The card's result names the cause with file and line.

### Command exit codes

- The new test, if any, returns 0, and non-zero before the fix.
- `uv run python -m pytest` (kernel fast suite), `ruff check`, `ruff format --check`, `mypy --strict src`, `lint-imports` return 0.
- `uv run --project ../substrate python -m pytest tests/` in substrate-ui returns 0.

## observation contract

### Driving steps

- Open a session in the installed app; send a turn; quit and reopen the app; send a turn.

### Expected

- The second turn's envelopes hold no session-open `PromptFragment`, or the card records why they appear.

## done criteria

The re-emission is explained, and fixed if it is a defect.

## result

- **Cause.** There was no re-emission. On `s_9eee1b3a4d094346bb30039c` the fragments at seq 13–20 were the session-open sources' first and only writes. They came late because `session_open` and the four source initials all started at `RunStarted` (seq 2–5), and `session_open` ran first. The race lived in `session/__init__.py`'s pre-K261 registration (every source and the opener an `initial`); K261 put the first message behind `first-message-on-session-prompt`, and K263 left one producer for it to wait on. Over that record's 261 events and nine turns, each source wrote once.
- **Fix that follows.** `views.py::FragmentCohort` kept one slot per session-open source with the newest winning, on the belief that resumes re-emit. It now keeps every session-open fragment in arrival order, so each link of a bundle's `extends` chain reaches the model. `test_session_open_fragments_265.py` failed before the change (`BASE-METHOD` missing from the prompt) and passes after; it also checks that a resumed turn writes no fragment.
- **Observation.** New gate `session_prompt_once_across_restart.ts` on the installed app: open a session, send "one", quit the app, reopen it, attach, send "two". The record holds 3 fragments at seqs 7–9, all before "one" (seq 13), and one `RunStarted`; the "two" prompt (after seq 30) names the same three.
- **Checks:**
  - Kernel suite: 1,357 passed, 4 skipped, 0 failed. The skips are named: `test_assay_swebench_harness_binding` ×2 (opt-in, `SWEBENCH_HARNESS_ENABLE`); `test_bundled_topologies` ×1 (`swebench_repair` is non-deterministic); `test_perf` ×1 (opt-in, `SUBSTRATE_PERF_GATE`).
  - UI suite: 215 passed, 0 skipped.
  - Installed app, rebuilt: `vm_smoke` 12 of 12; shakeout 3 runs, 0 bugs; all eleven gates pass.
  - CI records `session`, `daily` and `natural_conversation` match their pre-fix versions apart from ids and clocks. No record moved, as predicted.
- **Skips named on every run.** The previous full run reported 5 skips, and its output had been piped through `tail`, so the fifth could not be named. Both repos now pass `-ra` to pytest (`substrate/pyproject.toml` `addopts`, new `substrate-ui/pytest.ini`), so every run ends with one line per test that did not pass and its reason. The fifth skip of that run is not recoverable. The suite's runtime-dependent skips are the 14 real-model files' 4-second Ollama probes; that run was the slow one (14 min 48 s against about 10), which fits a probe timing out but is not confirmed. An attempt to recover the names from the K263 run's surviving output mis-numbered the marks, because the output began at 42%, and named `test_reference_passes_both_gates[is_armstrong]`, which has no skip. That attribution was wrong.
- **Prediction misses:** none in code. The counting error above was mine, in reading old output.

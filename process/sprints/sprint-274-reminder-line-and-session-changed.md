# Sprint 274 — The reminder line, and SessionChanged

```yaml
---
id: 274
status: closed
closed_at: 2026-10-10
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-default-guidance.md
asked: 2026-10-10 (Architect)
---
```

## why

The bundle's `per-turn.md` never reaches a session; `per_turn` renders at the top of the prompt; mid-session changes never reach the record.

## scope

- `per_turn` defaults from the bundle chain (manifest overrides), is written once as `PromptFragment(per_turn)`, and is placed right after the current `USER:` line.
- `SessionChanged{field, old, new}`: the next step carries one update line after the message; `FragmentCohort` drops replaced fragments of a changed source.

## design as built (written before the run, 2026-10-10)

- **`per_turn` is a session-open source.**
  - `session_prompt` gains a `per_turn` source. Its text is the manifest's `per_turn` when set, else the bundle chain's `per_turn` slots joined ancestor first. Provenance is `{"from": "manifest"}` or `{"from": "bundle", "bundles": [...]}`.
  - `PER_TURN` moves to `SESSION_OPEN_SOURCES`.
  - The model step no longer takes `per_turn` as a string: `compose_model_prompt` takes the newest `per_turn` fragment from the cohort and places its text on the line after the current turn's `USER:` line. "Newest" also covers records from before K261, which wrote one `per_turn` fragment per turn.
  - The seed-size warning counts the resolved text.
- **`SessionChanged` copies the background-task notice (UI sprint 104), not the interrupt.**
  - A daemon resume must carry a `UserMessage` (`pause_await_input(resume_condition=UserMessage)`), so injecting a separate event into a parked session would need a kernel change. Instead the model step does what it already does for `BackgroundTaskEnded`.
  - On the first step of a turn, it compares the topology's driver, bundle, `per_turn` and date with the last recorded values. A new view, `session_settings`, folds `SessionStarted`, the `per_turn` fragment and `SessionChanged`.
  - For each difference it records `SessionChanged{field, old, new}` and adds one line to that step's prompt, after the current message: `Environment update: <field> changed from <old> to <new>.`
  - The daemon rebuilds the topology from the manifest on every turn, so a PATCH or `/model` shows up here with no daemon change.
  - `SessionChanged` joins `TURN_EVENT_KINDS` and renders in history in place, so later steps keep the line.
- **A changed bundle or `per_turn` re-emits its sources.**
  - The trigger `session-prompt-on-session-changed` starts `session_prompt` again, limited to the changed sources.
  - `FragmentCohort` drops older fragments of a source when a newer fragment of the same source follows a `SessionChanged`.
  - The step that detects the change still uses the old fragments; the next step reads the new ones. The record shows both.
- **§ P.4 is amended** to say who writes `SessionChanged` (the model step) and where its line renders.

### Predicted breaks

- `test_prompt_built_once_261.py`: `PER_TURN` moves from the head to after the message.
- `test_session_prompt_vocabulary_v02.py`: the session-open and turn-scoped partition.
- The committed `session` and `daily` records, if their CI topology sets `per_turn`.
- `test_render_seed_alone_exceeds.py`: the warning reads the resolved `per_turn`.

## checks

- Every step of a tool turn carries the line right after the message.
- A synthetic `SessionChanged` puts one update line on the next step.

## result

- **Built as designed, with one change.**
  - `per_turn` is a session-open source, resolved from the manifest or the bundle chain (`resolve_per_turn`). `head_block` returns it apart, and the composer places it on the line after the current `USER:` line.
  - `SessionChanged` is written by the model step on a turn's first step from the `session_settings` view, and renders in history in place.
  - `session-prompt-on-session-changed` rewrites the changed sources. Their fragments carry `generation`, and the cohort keeps each source's newest.
  - **The change:** the update line for `per_turn` does not repeat the text ("the reminder line beside each message changed"). Repeated, a 318-byte hook line would sit in history once per change.
  - § P.9 records the as-built rules.
- **Test.** `test_reminder_line_and_session_changed_274.py`, 5 tests:
  - the line sits after the message on both steps of a tool turn, recorded once;
  - a bundle supplies it;
  - a driver change is recorded and told after the message;
  - no change writes nothing;
  - a bundle change records `bundle` and `per_turn` changes, the detecting step says so and still reads b1, and the next turn reads b2 only.
- **Checks.**
  - Kernel suite: 1,375 passed, 5 named skips, 3 failures, all the committed `session` and `daily` records. Regenerated: every prompt text is unchanged, the model's recorded input gains `settings`, and the topology gains the new trigger. The other 16 records were restored.
  - UI suite: 218 passed, 2 failures, then fixed:
    - `envelope_kinds.gen.ts` lacked `SessionChanged`. Regenerated, and `tsc` then required the UI to handle the kind: it renders a system row with the same line the model reads.
    - `test_server_session_patch_per_turn.py` pinned the line before the message. It now checks it after.
- **Prediction misses.** `test_prompt_fragment_tools_suite.py`, `test_session_vocabulary_constants.py` and `test_system_channel_272.py` broke without being predicted; `test_render_seed_alone_exceeds.py`, predicted, did not.
- **Installed app.** Checked with K273 on the build after U121.

- **Installed-app check (end of roadmap, 2026-10-10).** Build from the working tree: signed, not notarized, verification build. All 11 Electron gates pass. The `session_prompt_once_across_restart` gate first failed because it read raw JSONL and `standard` makes `PromptComposed` large enough to be a blob; the gate now resolves blobs and reports 7 fragments, written once and reused after a restart. Session `s_971d2e719c47407b8d8f052a`, on the app's own daemon, in a scratch git repo: the hook line sits on the line after the current message in all three model prompts; a PATCH of the driver recorded `SessionChanged(driver, claude → glm-5.2:cloud)`, the next prompt carried the update line after the message, and GLM answered "The driver is glm-5.2:cloud, per the environment update in this turn."

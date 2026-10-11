# Sprint 273 — The environment baseline

```yaml
---
id: 273
status: closed
closed_at: 2026-10-10
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-default-guidance.md
asked: 2026-10-10 (Architect)
---
```

## why

The specs' baseline was never built: `SessionStarted.baseline` is `{}`, so no model is told its workspace, date or model name.

## scope

- Compute at session open: workspace path; in a repo, root, branch, commit, README head (8 KiB), `git diff HEAD` (32 KiB); outside, cwd and hostname; platform; driver and model ID; date; `<repo>/.substrate/context.md`.
- Write it to `RunStarted.baseline` and `SessionStarted.baseline`, and as `PromptFragment(baseline)` on the system channel.

## design as built (written before the run, 2026-10-10)

- **The daemon computes; the kernel records.** Reading git, the clock and the platform is impure, so the session topology does not do it. A new module, `topologies/session/environment.py`, holds `session_baseline(workspace, driver_name, driver_command)`, which returns a dict, and `render_baseline(baseline)`, which returns the text the model reads. The daemon calls the first when it builds a session's topology and passes the dict as `session_topology(baseline=…)`.
- **What it holds** (§ P.2):
  - `workspace`;
  - in a git repo: `repo_root`, `branch`, `commit`, `readme_head` (first 8 KiB of `README.md`), `git_diff` (`git diff HEAD`, capped at 32 KiB with a marker);
  - outside one: `cwd` and `hostname`;
  - `platform`;
  - `driver` and `model_id` (the value after `--model` in a CLI command, else the driver name);
  - `date` (ISO, local);
  - `project_context` (`<repo or workspace>/.substrate/context.md`, capped at 8 KiB) when the file exists.

  Each git command runs with a 5-second timeout. A failure leaves that key out; it never stops the session.
- **Where it lands.** `b.baseline(**baseline)` puts it in `RunStarted.baseline`, the kernel's existing slot. `SessionStarted.baseline` gets the same dict. The `session_prompt` producer gains a `baseline` source: `PromptFragment(source=baseline, text=render_baseline(…), precedence=4)`. `SYSTEM_SOURCES` gains `baseline`, so the text goes on the system channel.
- **Once per session.** The daemon builds the topology on every turn, but `session_prompt` runs only on a fresh record (K265), so the fragment is written once. A later day's resume does not rewrite it; K274's `SessionChanged(field=date)` reports the new date.
- **CI stays deterministic.** `ci_session_topology` passes no baseline, so the committed records do not change.

### Predicted breaks

- UI tests that assert `SessionStarted.baseline == {}` for a daemon session, if any.
- No kernel CI record.

## checks

- A git-workspace session and a flat one each show their facts in `PromptComposed.system`.

## result

- **Built as designed.**
  - `topologies/session/environment.py`: `session_baseline`, `render_baseline` and `model_id`.
  - `PromptSource.BASELINE` at precedence 4, in the session-open set and in `SYSTEM_SOURCES`.
  - `session_topology(baseline=…)` writes it to `RunStarted.baseline` through `b.baseline`, to `SessionStarted.baseline`, and as one fragment.
  - The daemon computes it in `_build_session_topology_from_manifest` from the workspace, the driver and the responder's command.
- **Test.** `test_environment_baseline_273.py`, 5 tests:
  - a git workspace: root, branch, commit, README head, diff, `context.md`, model ID, date;
  - a flat workspace: cwd and host;
  - the diff cap;
  - `model_id` without `--model`;
  - a session records the dict on `RunStarted` and `SessionStarted`, writes one `baseline` fragment, and the driver receives its text as `system`, equal to `PromptComposed.system`.
- **Checks.**
  - Kernel suite: 1,371 passed, 5 named skips, 2 failures. Both were `test_session_prompt_vocabulary_v02.py`'s pinned source sets, which lacked `baseline`; updated, 9 of 9 pass. Not predicted: the card named only UI tests.
  - UI suite: 220 passed, including sessions that resume with a baseline.
  - No CI record moved. ruff, `mypy --strict` (134 files) and `lint-imports` are clean.

- **Installed-app check (end of roadmap, 2026-10-10).** Build from the working tree: signed, not notarized, verification build. All 11 Electron gates pass. The `session_prompt_once_across_restart` gate first failed because it read raw JSONL and `standard` makes `PromptComposed` large enough to be a blob; the gate now resolves blobs and reports 7 fragments, written once and reused after a restart. Session `s_971d2e719c47407b8d8f052a`, on the app's own daemon, in a scratch git repo: `SessionStarted.baseline` holds branch, commit, date, driver, model ID, platform, repo root and workspace; every prompt's `system` part carries the environment block with `Branch: main`; Claude answered "Today is 2026-10-10, and the workspace is on branch `main` at commit 79a75d9".

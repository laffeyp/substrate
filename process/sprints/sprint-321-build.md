# Sprint 321 — Build

```yaml
---
id: 321
status: closed
closed_at: 2026-10-13
phase: 2
pass_kind: functional
depends_on: [315, 316, 317, 318, 319]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
---
```

## scope

One card worked in its own worktree by a driven session until its checks pass or it cannot close; its report and branch returned to the caller; the build never merges (r8 § 4.1).

## observation contract

A deterministic build on a fixture repository ends `done` with its branch, commits and report; a card whose check cannot pass ends `stuck`.

## result

- **Built.** `topologies/runs/build.py`: `start_build` makes a worktree of the repository's HEAD on a new branch `build/<run_id>` and starts one driven worker (K318) there, held by the caller (K319); it returns the run id and branch at once. The worktree is the worker's only context: the role prompt and guidance bundle a session of its model class gets (`class_variant("default", model_class)`, rooted in the worktree; the caller's bundle), all file tools and `bash` rooted in the worktree, no memory index, no parent context. Its first message says where it is, to commit on its branch, and that failed checks come back as the next message, then the card (the plain fields, or the SDD card's text). A card whose first message is bigger than 0.6 of the model's window (the session's own seed check) is refused, naming both sizes, before any worktree is made. Limits default to 8 turns and 3 stalled turns. `card_from_form` reads a `build` call's plain fields or an SDD card file in the workspace (refused outside it); `make_build_tool` is the `build` tool, and a card refusal comes back as its error naming what is missing. The app server gives every session `build` on its own model, bundle and model class; records under `<sessions>/runs/`, worktrees under `<sessions>/wt/`. The build never merges.
- **Tests.** `tests/test_build_321.py`, 5: a build ends `done` with branch `build/r_b`, one commit, `b.txt` in its files and its check passed, while the repository's HEAD and files do not move; the role read is `default` and no memory fragment is read although the home has a memory index; a small model reads `default-small`; a check that cannot pass ends `stuck` with what is left; an oversized card is refused before a worktree exists; the tool reads plain and SDD cards, sets limits, refuses an incomplete card naming "how to tell it is done", and refuses a card file outside the workspace. App: `test_app_cli_folder_115.py` builds through `server._start_build` with the stand-in CLI, which runs in the build's worktree, and the branch exists while the repository stays on its own; the composition test expects `build`. Mutations: `memory=True` fails the memory check; dropping `class_variant` fails the small-model test.

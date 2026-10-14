# Sprint 320 — Review

```yaml
---
id: 320
status: closed
closed_at: 2026-10-13
phase: 2
pass_kind: functional
depends_on: [317, 319]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
---
```

## scope

A one-shot run that reviews a branch, a commit range or files in a named style and returns a report per reviewer; the styles are texts, picked from well-known review styles in published practice as part of this card (r8 § 4.3). Replaces the `code_review` application.

## observation contract

A deterministic reviewer on a fixture branch returns its report in the caller's record; two styles run in parallel and return two reports; the style set and its sources are written down.

## result

- **Built.** `topologies/runs/review_styles/`: `defects` (the session reviewer's text, `reviewer.md`, without its record paragraph, with Google eng-practices' Functionality and Tests), `design` (Google eng-practices: Design, Complexity, Naming, Comments, Consistency), `security` (the OWASP Code Review Guide's technical controls and vulnerability classes); `README.md` names the sources and why IEEE 1028's review types are not styles (they name a process, not what is looked at). `runs/review.py`: a target is a branch or commit (its changes since it left HEAD), a range `base..head`, or paths; `start_review` starts one reviewer per style, each a driven session (K318) held by the caller (K319) in a worktree detached at the target (`workspace.make_detached_worktree`), with `read_file`, `list_dir`, `glob`, `grep` only, a plain card whose check is the statement "the review names each finding: where it is, what is wrong, and the fix", one turn, and a first message of the style's text, the caller's focus and the diff (cut at 60,000 characters). An unknown style refuses before anything starts. `make_review_tool` is the `review` tool. `hold.run_notice` carries a run's words up to 4,000 characters (was 300), since a review's words are its output, and past that says how to read the report. The app server gives every session `review` and `run`; each reviewer runs on the session's model with its working directory in its worktree; records under `<sessions>/runs/`, worktrees under `<sessions>/wt/`. The `code_review` application (its manifest and the server's builder) is removed; the `code_review` library topology, its bundled record and the `code_review` guidance bundle stay.
- **Tests.** `tests/test_review_320.py`, 7: each style has its text and an unknown one is refused; targets resolve (branch, path, range); two styles give two runs that end `done`, each with a review, no files changed, a detached worktree at the target, the four read-only tools on its record, and the style text, focus and diff in its first message, while the repository's branch does not move; an unknown style starts nothing; the tool reads its form; a caller session's one `review` call records two `TopologyRunStarted`, two `TopologyRunEnded` with `done`, and its next prompt carries each review's text; a model's named call reaches both `review` and `run` as one dict. App: `test_app_cli_folder_115.py` now checks through `server._start_review` that each reviewer's CLI runs in its own worktree (the stand-in prints its cwd, which is the review); the composition test expects `review` and `run`. Mutations: giving reviewers `write_file` fails the record check; removing the `run` schema's passthrough fails the named-call test.

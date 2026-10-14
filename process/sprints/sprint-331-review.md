# Sprint 331 — Review

```yaml
---
id: 331
status: closed
closed_at: 2026-10-14
phase: 4
pass_kind: functional
depends_on: [330]
roadmap: process/planning/ROADMAP-2026-10-14-core-topologies-r3.md
---
```

## scope

r9 § 8.3: `review(target, styles, focus)`. One reviewer per style (defects, design, security; the style texts and their sources from round 1 are reused), each a run in a worktree detached at the target, read-only tools, one turn, its reply the review.

## observation contract

Two styles give two runs, each with its review in its report and its worktree at the target; the caller's record holds both ends.

## result

- **Built.** `topologies/runs/review.py` on run sessions (K329, K330): one reviewer per style in a worktree detached at the target (`workspace.make_detached_worktree`), with `read_file`, `list_dir`, `glob` and `grep`, the style's text, the caller's focus and the diff (cut at 60,000 characters) as its first message, one turn; its reply is the review. The style texts and their sources (`review_styles/`) are round 1's, unchanged. The `review` tool's description tells the calling model what to give it (an exact target, a focus sentence when it knows where the risk is); only the target is required. The `code_review` application stays, as round 9 does not name it.
- **Tests.** `tests/test_review_331.py`, 7: each style has its text; targets resolve; two styles give two runs, each ending `done` with its review, no files changed, no branch, its worktree detached at the target, the four read-only tools and the style text, focus and diff in its first message; an unknown style starts nothing; the tool reads its form; a caller session records both starts and both ends, and its next prompt carries each review; a model's named call reaches `review` and `run`.

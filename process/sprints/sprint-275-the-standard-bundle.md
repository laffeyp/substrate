# Sprint 275 — The standard bundle

```yaml
---
id: 275
status: closed
closed_at: 2026-10-10
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-default-guidance.md
asked: 2026-10-10 (Architect)
---
```

## why

The machine's working and writing standard reaches no Substrate model.

## scope

- Shipped `standard` bundle, `extends = ["harness"]`: `style.md` from `plain.md` and CLAUDE.md's writing sections; `methodology.md` from CLAUDE.md's other sections and memory's general rules, under Claude Code's header; `per-turn.md` the hook line. Copied as they are; Claude Code tool names mapped to Substrate's.
- The four application bundles extend `standard`.
- Golden head tests for each shipped bundle.

## checks

- The golden heads match.
- `code_review` reads harness, standard and its own lines in that order.

## result

- **Built.** The shipped `topologies/session/bundles/standard/` has `extends = ["harness"]`.
  - **`style.md`** (2,503 B) is `~/.claude/output-styles/plain.md` without its frontmatter.
  - **`methodology.md`** (13,720 B) is Claude Code's CLAUDE.md header, then `~/.claude/CLAUDE.md` whole, then "# Working rules from memory": the 25 general entries of the operator's memory index, as the index states them. The 19 project and SDD entries go to K276's repo memory.
  - **`per-turn.md`** is the `UserPromptSubmit` hook line.
  - **Tool names mapped, nothing else changed:**
    - `WebSearch`/`WebFetch` became `web_fetch`, and the `deep-research` clause, for a skill Substrate lacks, was dropped;
    - `Read` became `read_file`, and "subagent delegation" became `delegate`;
    - "invoke the `dellm` skill" became `skill("dellm")`, which K277 builds.
  - The four application bundles now declare `extends = ["standard"]`.
- **One change from the research.** Round 7 split CLAUDE.md's writing sections into `style.md`. Claude Code sends `plain.md` in the system prompt and the whole of CLAUDE.md in the first user block, and the faithful first copy does the same. Their overlap ("Every output is writing" in both) is kept as Claude Code sends it.
- **Test.** `test_standard_bundle_275.py`, 9 tests:
  - six golden heads, one per shipped bundle, in `tests/golden/heads/`; `standard`'s head is 17,916 B;
  - the chain of each bundle;
  - `code_review` reads standard's style then its own line, then the role, harness's loop rules, standard's working rules and its own, and the reminder lines in the same order;
  - the copied texts carry Substrate's tool names.
- **Checks** (targeted, per the Architect's 2026-10-10 rule): the K275 test plus the bundle, list, fragment and K274 tests, 45 passed; the UI's bundles-endpoint and PATCH-bundle tests, 12 passed. A full kernel run started for this card hung past 24 minutes and was stopped. The full suites run once, at the end of the roadmap.

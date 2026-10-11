# Sprint 277 — dellm in the kernel

```yaml
---
id: 277
status: closed
closed_at: 2026-10-10
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-default-guidance.md
asked: 2026-10-10 (Architect)
---
```

## why

The one skill to carry across has no mechanism in Substrate.

## scope

- A skill resolver over `<repo>/.substrate/skills/`, `~/.substrate/skills/`, shipped `topologies/session/skills/`.
- `SkillRequested` and a `skill_fragment` producer on `skill-fragment-on-skill-request`; `SKILL` is session-open, so the fragment stays.
- A `skill(name)` tool whose description lists the skills.
- Shipped `dellm`, copied as it is.

## checks

- An injected `SkillRequested` puts the body in every later step.
- `skill("dellm")` returns the body as a `ToolResult`.

## result

- **Built.**
  - `topologies/session/skills.py`: `skill_layers`, `resolve_skill` (repo, user, shipped; `-small` first for the small class), `list_skills`, `make_skill_tool`, and `skill_fragment_producer_factory`.
  - The shipped `skills/dellm/SKILL.md` is `~/.claude/skills/dellm/SKILL.md`, copied as written.
  - `PromptSource.SKILL` at precedence 40, session-open.
  - The daemon adds `skill` to every session's tools.
- **Changed from the design.** `SkillRequested` is not built (§ P.10). A parked session resumes only on a `UserMessage`, so the request rides that message's `slash_source` (`"skill:<name>"`).
  - `skill-fragment-on-user-message` starts `skill_fragment`.
  - `model-on-user-message` skips such a message, and `model-on-skill-fragment` starts the model when `skill_fragment` ends, the way `first_message` waits on `session_prompt`.
  - The `skill` tool lives in the session package, not in `tool_loop`, because the import contracts keep `tool_loop` below `session`. It is a `Tool` with its own schema, the documented extension seam.
- **Found by U120's gate.** The copied CLAUDE.md section that bans attribution must name `noreply@anthropic.com` and "Generated with" to ban them. The gate now skips that one section, from its heading to the next.
- **Test.** `test_dellm_277.py`, 5 tests:
  - the shipped skill and its listing;
  - a `skill:dellm` turn writes the fragment before the first `PromptComposed`, and both turns' prompts carry the skill once;
  - an unknown skill warns and the turn still answers;
  - the tool returns the body and names unknown skills;
  - a repo skill shadows the shipped one.
- **Checks** (targeted): the vocabulary, constants, K272, K274, trigger and producer tests, the CI-record tests and the interrupt e2e all pass. The `session` and `daily` records were regenerated: same kinds, same prompt texts, new topology. The UI's driver-profile gate passes.

# Sprint 279 — Codex and Cursor profiles

```yaml
---
id: 279
status: withdrawn
withdrawn_at: 2026-10-10
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-default-guidance.md
asked: 2026-10-10 (Architect)
---
```

## why

Both bring their own instruction files and attribution; Codex's binary instructs a `Co-authored-by: Codex` trailer, and this machine's Cursor config attributes commits and PRs to the agent.

## prerequisite found 2026-10-10

Neither CLI is logged in on this machine: `codex exec` returns 401, and `cursor-agent -p` asks for `agent login`. The operator logs each in once, with `codex login` and `cursor-agent login`, before the probes run.

## scope

- Probe each: ask the driver to quote its whole context.
- Profiles: Codex through `--ignore-user-config`, `--ignore-rules`, `--ephemeral`, `-c model_instructions_file`, `commit_attribution_enabled` off; Cursor through its own `CURSOR_CONFIG_DIR` with attribution off and rules off.

## checks

- Each driver quotes only Substrate's text.
- A commit through each carries no trailer.

## result

- **Withdrawn 2026-10-10 by the Architect:** future work, not part of this roadmap.

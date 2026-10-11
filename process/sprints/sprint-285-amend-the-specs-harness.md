# Sprint 285 — Amend the specs: harness drivers and their tool routes

```yaml
---
id: 285
status: open
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-harness-tool-calls.md
asked: 2026-10-10 (Architect)
---
```

## why

The specs describe a CLI driver as text in, text out.

## scope

- Product spec round 14, tech spec round 8, design spec round 3: harness drivers run their own loop with full permission; their own tool calls come from the stream; Substrate's tools reach them over MCP; both routes are on the record; the `/api/session/<id>/mcp` endpoint.
- Earlier rounds untouched. Each new section names what it supersedes.

## checks

- Each new round names the lines it supersedes.

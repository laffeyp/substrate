# Sprint 285 — Amend the specs: harness drivers and their tool routes

```yaml
---
id: 285
status: closed
closed_at: 2026-10-10
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

## result

- **Product spec round 14** (`current-design-direction/product-spec/PRODUCT-SPEC-2026-08-17-round14.md`), §R14.1–§R14.4: harness drivers with full permission; both tool routes on the record; cursor-agent's MCP only in a per-session sandbox; route-named tool cards; the per-session MCP endpoint. Superseded-in-part notes sit under §5f and §R13.5.
- **Tech spec round 8** (`current-design-direction/tech-spec/TECH-SPEC-2026-08-25-round8.md`), §R8.1–§R8.6: vocabulary v0.5, stream parsers, the MCP channel, the profile table, the endpoint, gates. Superseded-in-part notes sit under §1.9 and §R7.5.
- **Design spec round 3** (`handoff_latest/docs/DESIGN-SPEC-2026-08-31-round3.md`), §R3: harness tool cards.
- Earlier rounds untouched. The specs live outside the two git repos.

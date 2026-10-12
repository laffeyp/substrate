# Sprint 294 — A CLI driver's context window, resolved in order

```yaml
---
id: 294
status: closed
closed_at: 2026-10-11
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-11-compaction.md
asked: 2026-10-11 (Architect)
---
```

## scope

- Replace the flat 100,000-token window for every CLI driver with a chain: the harness's live report, the CLI's own settings, the maker's documented window for the session's model, Substrate's config, the default. Record which one answered.

## checks

- Unit tests for each layer and the order; claude's stream yields its window; the window reaches the history view; the live test passes on every driver family with claude's window recorded live.

## result

- **The chain** (`topologies/session/context_windows.py`, vocabulary § S.9):
  1. **Live.** Claude Code reports `modelUsage.<model>.contextWindow` on every call. `StreamUsage.context_window` carries it, `ModelReply.usage.context_window` records it (only when reported, so earlier records read the same), and `TurnHistory` keeps the latest; later steps budget on it. Codex and cursor-agent streams report no window.
  2. **The CLI's own settings.** Codex's `model_context_window` in `$CODEX_HOME/config.toml`; Codex's configured `model` is looked up in the documented table when the session names none.
  3. **Documented.** `DOCUMENTED_CONTEXT_WINDOWS`, keyed by the id the session passes with `--model` or `-m`, every entry naming its source page, read 2026-10-11. Anthropic: 1M for Fable 5.1 and 5, Opus 5.5, 5, 4.8, 4.7, 4.6, Sonnet 5.5, 5, 4.6, Haiku 5.5; 200k for the other Claude models in the catalog. OpenAI, the maximum input where the page states one: 922,000 for gpt-6-astra, gpt-6-sol, gpt-6.1-sol, gpt-6-luna and gpt-5.6-sol/terra/luna; 1,050,000 for gpt-5.5 and gpt-5.4 (no separate input limit stated); 272,000 for gpt-5 (400,000 window). Cursor's model page states no per-model window, so cursor-agent's ids have no entry.
  4. `[driver.<name>].context_tokens` in `~/.substrate/config.toml`. 5. 100,000.
- **Recorded.** `SessionStarted.driver_context_source`: `probed`, `fixed`, `cli_settings`, `documented`, `config` or `default`. `resolve_driver_context` returns the window and the source; the daemon passes both. `resolve_driver_context_tokens` keeps its signature. The old config reader `_cli_context_from_config` is removed; the default has one home.
- **On this machine's sessions:** claude with `claude-opus-5-5` (10 sessions) now resolves to 1,000,000, documented; codex with `gpt-6-astra` (8) to 922,000, documented; cursor-agent with `auto` (3) to the config or 100,000; sessions that name no model get claude's live window from their first reply.
- **Tests.** `test_context_window_chain_294.py`, 8 of 8; `test_render_cli_config_context.py`, 6 of 6. Session-area tests: 396 passed, 11 skipped. Live (`test_compaction_live_293.py`), all four driver families pass; claude's replies carry `context_window: 1000000`, and the test pins claude's budget with a small headroom since the live window overrides its 3,000. The `daily` and `session` bundled records regenerated for the new `SessionStarted` field.
- **Found on the way:** one cursor-agent session ran with `--model Available`: the cursor model list took its header line for a model id. Added to the release roadmap, step 3.

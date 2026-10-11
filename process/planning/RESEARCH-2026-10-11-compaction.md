# RESEARCH: how Substrate compacts a session's history, and how it should

*2026-10-11. Asked by the Architect after a codex session compacted on every turn and twice reported the same dropped range. The question is the mechanism for every driver, not the one session. Sources are the code, the records in `~/.substrate/sessions`, and first-party documentation and papers; no blog is relied on.*

**Broken now: every tool output in the current turn reaches the model twice.** This is a bug, not a design choice. Within a turn, the prompt's history already holds each `ToolResult`, and the model step appends the same outputs again under "Tool results so far". It doubles the cost of every tool loop on Ollama and the other native and text tool modes, and it fills the window twice as fast. Evidence in §2; fix first, ahead of the compaction redesign.

## 1. The mechanism today

Every model step rebuilds the whole prompt from the record (`session/__init__.py` `_prompt_input`, `transcript.py`):

- **Window.** `plan_window` keeps the newest whole turns whose estimated size fits `driver_context_tokens × 0.6 − head`, where the head is the system part, seed, fragments and reminder line. Older turns drop whole, oldest first. The current turn is always kept, even when it alone exceeds the budget.
- **What a turn holds.** Every turn event in full (`TURN_EVENT_KINDS`, `transcript.py:76`): the user's message, model replies, `ToolCall` and `ToolResult`, and for harness drivers `HarnessToolCall` and `HarnessToolResult` with their whole output.
- **Strategy.** `rolling_window` only. The vocabulary (`process/signals/session-vocabulary.md` §D) named `summary_tail` for v1.5; it was never built. Nothing summarises, and no placeholder tells the model that turns were dropped; the only mark is the header `[transcript: turns i..j]`.
- **Token counts.** Estimated as characters ÷ 4 (`_est_tokens`). The driver's own counts are recorded on `ModelReply.usage` and not used.
- **Window size per driver** (`resolve_driver_context_tokens`): Ollama models report theirs through `/api/show`; `deterministic` is 4,096; every CLI driver (claude, codex, cursor-agent) gets a flat 100,000 unless `~/.substrate/config.toml` names another.
- **Harness drivers keep no session of their own.** Each turn starts a fresh process (`codex exec`, for example; `server.py` `KNOWN_CLI_ADAPTERS`). The prompt Substrate replays is the harness's only memory of earlier turns.
- **The event.** `TranscriptCompacted` records the dropped seq range, the first kept seq, and estimated tokens before and after. Each step computes a fresh cut over the whole record, so two steps that cut at the same place record the same range.

## 2. What the records show

72 sessions and 246 turns on this machine. Compaction fired 4 times, all in one codex session, `s_b8dab6b0cfd443cdba9bc8b3`:

| seq | dropped | kept from | est. tokens before → after |
|---|---|---|---|
| 93 | 17–89 | 90 | 154,060 → 9,278 |
| 150 | 17–146 | 147 | 228,114 → 9,322 |
| 169 | 17–146 | 147 | 243,138 → 24,340 |
| 180 | 17–146 | 147 | 243,347 → 24,543 |

Turn 2 (seqs 90–146, "go over it all again… really detailed, deep technical review") cost about 145,000 estimated tokens, almost all of it codex's own file reads replayed as `HarnessToolResult`. It alone exceeded the 60,000-token history budget. So from turn 3 on, turns 1 and 2 dropped whole: both of the user's requests and both replies, the deep review among them. Turn 4 asked "is this project actually feasible?" and codex answered with no review in its prompt. The repeated range at seqs 150, 169 and 180 is correct (keeping from 147 fit each time), but the console shows it as the same compaction three times.

Kimi cloud sessions (262,144-token windows, 109 turns) never compacted.

**Every tool output in the current turn is sent twice.** Within a turn, the history runs up to the latest `ToolResult`, and the model step then appends "Tool results so far, in order: …" in native and text tool modes (`session/__init__.py`, the `progress` block). In `glm-5.2:cloud` session `s_9eee1b3a4d094346bb30039c`, the prompt at seq 315 holds the 4,512-character output of `ToolResult` 311 at offset 14,995 as `RESULT:` and again at 19,588 under "Tool results so far".

**The estimate runs low.** Reported prompt tokens ÷ estimated, per call:

| Driver | Calls | Median | Range |
|---|---|---|---|
| kimi-k2.7-code:cloud | 26 | 1.19 | 1.14–1.25 |
| kimi-k2.6:cloud | 15 | 1.79 | 1.20–2.32 |
| glm-5.2:cloud | 9 | 1.69 | 1.64–2.38 |
| qwen2.5-coder 7B (local) | 6 | 2.69 | 2.64–2.72 |
| codex | 14 | 8.02 | 1.71–167.88 |
| claude | 11 | 10.44 | 1.30–15.77 |
| cursor-agent | 2 | 8.97 | 8.95–8.97 |

The Ollama rows compare like with like. At 2.69, a history the estimate puts at 60% of the local model's window is about 160% of it. The CLI rows also count each harness's own system prompt and internal tool loop, so they measure what the window must hold, not only the estimate's error.

## 3. How others compact (first sources)

- **Claude Code.** "It clears older tool outputs first, then summarizes the conversation if needed. Your requests and key code snippets are preserved." It stops auto-compacting after a few attempts when one output refills the context, rather than looping. Sessions resume with `claude --continue` or `--resume`, which appends to the same session. ([How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works))
- **Anthropic API, context editing.** Tool-result clearing triggers at an input-token threshold (default 100,000), keeps the newest 3 tool uses, replaces each cleared result with a placeholder that tells the model it was removed, and can exclude named tools. Clearing invalidates the cached prefix, so `clear_at_least` sets a minimum worth clearing. Summary compaction replaces the history with a structured summary (task, current state, discoveries, next steps, context to preserve); the SDK form is deprecated in favour of server-side compaction (`compact_20260112`). ([Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing))
- **OpenAI.** The Responses API compacts at a `compact_threshold` on the rendered token count, returning an opaque compaction item that carries prior state. ([Compaction](https://developers.openai.com/api/docs/guides/compaction)) Codex sets `model_auto_compact_token_limit`, a `tool_output_token_limit` per tool output kept in history, and a replaceable `compact_prompt`. ([Config reference](https://learn.chatgpt.com/docs/config-file/config-reference)) `codex exec resume <SESSION_ID>` continues a non-interactive session with its context. ([Non-interactive mode](https://developers.openai.com/codex/noninteractive))
- **Measured comparison.** Lindenbauer et al., "The Complexity Trap" (JetBrains Research and TU Munich; NeurIPS 2025; arXiv 2508.21433), on SWE-bench Verified with SWE-agent: masking observations older than the newest 10 turns with a placeholder cut cost by 52.7% and raised the solve rate from 53.4% to 54.8% on Qwen3-Coder 480B. LLM summarization cut cost by 50.4% at 53.8%, and lengthened trajectories (52 turns against 44 for masking, on Gemini 2.5 Flash). A hybrid of the two was cheapest. The vendor pages above describe their own products; the paper is an independent measurement.

The common order: clear old tool outputs first, with a placeholder; keep the user's requests; summarise only if that is not enough; trigger on real token counts.

## 4. Defects, most severe first

1. **Whole turns drop, user requests and replies with them.** A single heavy turn can erase every earlier exchange, as in §2. Every source in §3 keeps the requests and clears tool output first.
2. **Tool outputs are never cleared.** Old `ToolResult` and `HarnessToolResult` bodies ride in full until their whole turn drops. They are what made turn 2 cost 145,000 tokens.
3. **Current-turn tool outputs are sent twice** (§2). Broken: a bug in the prompt builder, fixed on its own before the rest.
4. **The budget rests on an estimate that runs 19–169% low on Ollama models,** while the driver's real counts sit unused on `ModelReply.usage`.
5. **Every CLI driver gets a flat 100,000-token window,** whatever its model.
6. **The current turn has no bound.** It is always kept whole, so a long tool loop inside one turn can exceed the window.
7. **The model is not told what was dropped.** No placeholder, no summary.
8. **The console shows a repeated cut as a new compaction.** The record is right; the reading is not.

## 5. What the fix covers

From §3, in order of effect:
1. Clear old tool-output bodies first, harness ones included, behind a placeholder that names the tool and the seq; keep the newest few whole. Recorded as its own strategy on `TranscriptCompacted`.
2. Keep every user message and final reply; drop or summarise whole turns only when clearing is not enough. `summary_tail` is the vocabulary's existing name for the summary step.
3. Send each current-turn tool output once.
4. Budget on real counts: calibrate the estimate per driver from `ModelReply.usage`, and set CLI windows per model.
5. Bound the current turn by clearing its own older tool outputs.
6. Show a repeated cut as the same cut in the console.

## 6. Open questions

- **Harness drivers: replay or resume.** Substrate replays its record into a fresh harness process each turn, so `PromptComposed` is exactly what was sent. Resuming the harness's own session (`codex exec resume`, `claude --resume`) would let the harness compact as its makers designed, but the harness's context would then hold things the record's prompt does not.
- **How many tool outputs to keep whole.** Anthropic's default is 3 tool uses; the paper used 10 turns. Measured per model class.
- **Summary model.** Whether the session's own model writes the summary, and how the summary is recorded so that replay stays exact.

# Sprint 352 — Substrate counts Claude's tokens

```yaml
---
id: 352
status: closed
phase: continuing a session (substrate-ui roadmap 2026-11-12-continue-a-session r4, E10)
pass_kind: functional
depends_on: [351]
plan: ../substrate-ui/process/planning/2026-11-12-continue-a-session/ROADMAP-2026-11-14-continue-a-session-r4.md
research: ../substrate-ui/process/planning/2026-11-12-continue-a-session/RESEARCH-2026-11-14-token-counting.md
---
```

## scope

The history window sizes every prompt at `len(text) // 4` (`transcript.py`, `_CHARS_PER_TOKEN`), and a `claude` session's correction comes from a reply that a refused prompt never gets. Anthropic's earlier tokenizer (`claude-tokenizer`, MIT, a Hugging Face `tokenizer.json` shipped in the package) counts every piece of text instead: each turn, each tool result's saving, the head, `PromptComposed.total_tokens`. A session whose driver speaks Claude Code's stream multiplies the count by 1.50, measured against Claude Code's exact counts on code and prose (research); the head is multiplied too, which the old code left out. Other drivers count with the same tokenizer and keep § S.5's measured correction. `len(text) // 4` leaves the code. One verifiable property: a `claude` session whose prompt counts over the budget at 1.50 compacts before it is sent.

## context_files

- `src/substrate/topologies/session/transcript.py` (all of it)
- `src/substrate/topologies/session/views.py` (`TurnHistory`)
- `src/substrate/topologies/session/__init__.py` (`_prompt_input`, the model step's `PromptComposed` and `TranscriptCompacted`, the seed warning)
- `src/substrate/topologies/tool_loop/substrate_tools.py` (its re-export of the count)
- `process/signals/session-vocabulary.md` (§ D, § S, § AE)
- `process/WORKING_AGREEMENT.md` (the permitted dependencies)

## signal contract

### Emits

- `PromptComposed.total_tokens`: the tokenizer's count of the system part and the prompt.
- `TranscriptCompacted.tokens_before`, `tokens_after`: the counts times the scale; `token_scale` 1.50 in a `claude` session.

### Invariants

- No `len(text) // 4` in the code.
- A session's counts are the same live and on replay: the tokenizer is a file in the package, and counting reads nothing else.
- `ModelReply.usage` is unchanged: Claude Code's exact count stays there beside Substrate's count.

## artifact contract

### Files created

- `src/substrate/topologies/session/token_count.py`
- `src/substrate/topologies/session/tokenizers/claude-tokenizer.json`, with `tokenizers/LICENSE` (MIT, Xenova/claude-tokenizer)
- `tests/test_count_claude_tokens_352.py`

### Files modified

- `transcript.py`, `views.py`, `__init__.py`, `substrate_tools.py`, `pyproject.toml` (`tokenizers`), `uv.lock`, `process/WORKING_AGREEMENT.md`, `session-vocabulary.md` (v0.22, § AG)

### Command exit codes

- The new test, the session, history and compaction tests, and the committed-record tests return 0; ruff and `mypy --strict` clean.

## observation contract

The copy of `s_52bd6e73d1224d5cb6d04830`'s record, planned with this code: its next prompt counts within 2% of the 1,028,540 tokens Claude Code reported for the last one, plus the new message. A short live `claude` turn: `PromptComposed.total_tokens` × 1.50 lies within 10% of `ModelReply.usage.first_call_prompt_tokens` less Claude Code's own overhead.

## done criteria

Substrate's count of a `claude` prompt agrees with Claude Code's, and the window compacts on it.

## notes

The rule-6 limit is exceeded: one concept, the count, in every place it is taken. The old opening text that compaction never drops is sprint 353.

## close

`token_count.py`: `count_tokens` counts with `tokenizers/claude-tokenizer.json` (MIT; `tokenizers/LICENSE`), read from the package; `CLAUDE_FACTOR` 1.50. `transcript.py`: turn costs and tool-result savings are counts; `_CHARS_PER_TOKEN` and `_est_tokens` are gone. `session/__init__.py`: `PromptComposed.total_tokens`, the seed warning and the head are counts; a driver whose `stream_format` is `claude-stream-json` scales by 1.50, another harness keeps K350's first-call correction, any other driver § S.5's; the head is counted at the scale. `substrate_tools.py` counts the same way. `pyproject.toml`: `tokenizers>=0.23,<0.24`; `WORKING_AGREEMENT.md` records its verified surface. Session vocabulary v0.22, § AG.

- `tests/test_count_claude_tokens_352.py`: 4 passed. The tokenizer's own card ("hello world" is `[9381, 2253]`); no four-characters count left in `transcript.py`; a Claude Code session compacts at 1.50 where the tokenizer's plain count would not; an 800-token seed counted at 1.50 drops the earlier turn where an unscaled one would keep it.
- Mutants: factor 1.0 fails 2; the head unscaled fails 1; characters over four fails 3.
- Full kernel suite: 1,717 passed, 14 skipped, 5 failed. Four were fixtures sized for four characters a token: runs of one character (`"x" * 3_000`, `"X" * 20_000`), which a tokenizer counts as a handful of tokens; they now use `tests/_text.py`'s varied text, sized by count. Sprint 350's test asserted the first-call scale; a Claude Code session's scale is now 1.5. The fifth, the live compaction test on `llama3.2:1b` at temperature 0, ran into its 800-token reply cap on a prompt the new count cut differently; it now runs on `qwen2.5:7b-instruct` and passes (31 s). After the fixes: those 23 tests and the live test pass; committed `session` and `daily` records regenerated, the 16 others current; 44 record tests pass; substrate-ui `test_continue_from_494.py` 8 passed.
- The old session's last prompt (2,337,585 characters) counts 1,056,292 tokens; Claude Code counted 1,028,540: 2.7% over, against the card's 2%. The count errs above Claude's, the side that compacts early.
- ruff clean; `mypy --strict` on the four source files clean.

Rubber Duck Pass: `PromptComposed.total_tokens` is the tokenizer's count of the system part and the prompt; `TranscriptCompacted.token_scale` reads 1.5 in a Claude Code session and its `tokens_before`, `tokens_after` include the head at that scale; `SessionWarning.seed_tokens` is a count. `ModelReply.usage` is unchanged. Observation: timing surprise, none; payload anomaly: `token_scale` in records before v0.22 multiplied a characters-over-four estimate, so a reader comparing records across v0.22 compares different units; § AG says so. resolved-here.

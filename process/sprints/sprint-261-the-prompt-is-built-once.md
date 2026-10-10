# Sprint 261 — The prompt is built once and recorded exactly

```yaml
---
id: 261
status: closed
opened_at: 2026-10-09
closed_at: 2026-10-09
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md
---
```

## why

A real run sent the user's text twice, ahead of the seed (research F4). `PromptComposed.text` is not what the model reads, although section I locks that it is (F5). Lens-audit rows F098, F100, F101, F107, F108 and F469 close here.

## scope

One builder in `transcript.py` makes the whole prompt, in this order:
- the seed;
- the session fragments by precedence;
- the kept history;
- the current message, once;
- the tool text and directives the model step needs.

`PromptComposed.text` carries exactly those bytes, emitted once per model call. Also:
- `UserMessage.assembled_prompt` and the `user_message` fragment go;
- `_model_factory` sends `PromptComposed.text` and nothing else;
- the window size comes from the rendered estimate, not 800 tokens a turn (F098);
- the record is not read in full on every model call (F101).

## prerequisites

- K260 and U119 closed.

## context_files

- `sdd-kit-2/AGENTS.md`
- `substrate/process/planning/RESEARCH-2026-10-09-session-topology-structure-round4.md`
- `substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md`
- `substrate/process/signals/session-vocabulary.md`
- `substrate/process/BLACKBOARD.md`
- `substrate/src/substrate/topologies/session/__init__.py`
- `substrate/src/substrate/topologies/session/transcript.py`
- `substrate/src/substrate/topologies/session/composer.py`
- `substrate/src/substrate/topologies/session/user_message_fragment_producer.py`
- `substrate-ui/server.py` (`assembled_prompt` writer)

## signal contract

### Emits

- `PromptComposed` (one per model call; `text` equal to the driver's input)

### Invariants

- The vocabulary's section I wording, "bytes-identical to what the driver reads", holds.

## artifact contract

### Files created

- `substrate/tests/test_prompt_built_once_261.py`

### Files modified

- `substrate/src/substrate/topologies/session/__init__.py`
- `substrate/src/substrate/topologies/session/transcript.py`
- `substrate/src/substrate/topologies/session/composer.py`
- `substrate-ui/server.py`

### Content assertions

- `_model_factory` has no string joins that add to the prompt after `PromptComposed`.
- `assembled_prompt` is not written.

### Command exit codes

- `uv run python -m pytest tests/test_prompt_built_once_261.py` returns 0, and non-zero before the change.
- `uv run python -m pytest` (kernel fast suite), `ruff check`, `ruff format --check`, `mypy --strict src`, `lint-imports` return 0.
- `uv run --project ../substrate python -m pytest tests/` in substrate-ui returns 0.

## observation contract

### Driving steps

- A capture responder records each prompt. Turn 1 sends `UNIQUE-HELLO-42` with seed `SEED`; turn 2 sends a second line.
- Live: one turn on the installed app on `claude` and one on an Ollama model.

### Expected

- The user's text appears once per prompt, after the seed; turn 1's text appears once in turn 2's history.
- Each prompt equals the `PromptComposed.text` of its model call.
- Both live turns answer.

## done criteria

The model reads one prompt per call, in a plain order, and the record holds those exact bytes.

## result

- The model step builds each prompt (`transcript.compose_model_prompt` and `head_block`), records it as `PromptComposed`, and sends exactly that text; the record holds what the model read, once per model step. The composer, the per_turn and user_message fragment producers, their modules and five triggers were removed; `model-on-user-message` starts the model. Vocabulary section L records the change.
- The model sees the pre-K261 wording with two differences, checked by diffing captured prompts against the pre-K261 code on three cases (text-only tool turn, native tool turn, wrap-up): the seed comes first, and the user's message appears once. A cue I wrote after tool calls was found in an audit and removed; the original "Tool results so far" and "Last error was" lines were restored.
- The diff found a regression: a new session's first prompt went out without its session-open fragments (the first message raced them). The first message now waits for them (`first-message-on-session-prompt`, fresh records only).
- `assembled_prompt` carries only an attached `/context` slice; the server no longer prefixes per_turn into it.
- The history window is sized from each turn's rendered estimate (F098). Live on `llama3.2:1b` at Ollama's 2,048-token window (`test_realmodel_session_compaction.py`): compaction recorded, the model answered after each trim, Ollama read at most 1,025 prompt tokens, and our estimate ran 0.88-1.02 x Ollama's count after the first call. `docs/compaction.md` documents the strategy and the planned ones.
- K267 (input isolation) and K268 (history by reference) were cut from this sprint's findings and ran as their own sprints.
- Gates: kernel ruff, format, mypy --strict, lint-imports clean; kernel suite clean except the real-model demo tests set aside on 2026-10-09 (machine load: Ollama measured at 6.8 tokens/s on `llama3.2:1b` with a VM, Ableton Live and Xcode running); UI suite 215 passed after `test_server_session_patch_per_turn.py` was rewritten for the new per_turn path; all seven Electron gates pass against the installed app.

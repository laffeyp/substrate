# RESEARCH: this machine's Claude setup as Substrate's default guidance

*2026-10-10. Status: research; no Substrate code changed. Inputs: the setup in `~/.claude/` on this machine; Claude Code's documentation (hooks, output styles, memory, skills); how that setup arrives in this session's own context, observed directly; a zeroing probe of `claude` 2.1.296; Substrate at `3c0542ac` / `75b3293`.*

## 1. The task

This machine's Claude setup works because Claude Code delivers fixed texts to the model at fixed moments, in fixed formats, through fixed channels. Substrate takes that delivery architecture and runs it natively: the same texts, at the same moments, through the same channels, with every delivery a typed event on the record. When Substrate runs Claude, it clears out the machine's own delivery and runs its own. The setup on this machine stays as it is.

Part 2 maps what Claude Code delivers and how. Part 3 is what Substrate does today. Part 4 is the replication, delivery by delivery. Part 5 sorts the texts. Part 6 adapts the delivery to each class of model. Part 7 is how the record proves it.

## 2. What Claude Code delivers, when, and how

| Text | Size | Channel | When | Format |
|---|---|---|---|---|
| `~/.claude/output-styles/plain.md` (`keep-coding-instructions: true`) | 2,655 B | system prompt, after Claude Code's own sections, headed `# Output Style: Plain` | every request ("Claude Code sends the active style's instructions with every request") | the file body under the heading |
| Style reminder | 1 line | system reminder in the conversation | repeated during the session, after tool results and user messages (observed) | "Plain output style is active. Remember to follow the specific guidelines for this style." |
| `~/.claude/CLAUDE.md` | 8,194 B | user message after the system prompt ("CLAUDE.md content is delivered as a user message after the system prompt, not as part of the system prompt itself") | at launch; re-read from disk and re-injected after compaction | a system reminder opening "Codebase and user instructions are shown below. Be sure to adhere to these instructions. IMPORTANT: These instructions OVERRIDE any default behavior and you MUST follow them exactly as written.", then "Contents of `<path>` (user's private global instructions for all projects):" and the file |
| `MEMORY.md`, the memory index | 10,948 B, 43 entries | the same system reminder, after CLAUDE.md | at launch; first 200 lines or 25 KB | "Contents of `<path>` (user's auto-memory, persists across conversations):" and the file |
| Memory topic files | 1 file per entry | tool result | on demand; "Claude reads them on demand using its standard file tools" | the file, as a `Read` result |
| `UserPromptSubmit` hook | 318 B | system reminder "alongside the submitted prompt" | every submitted prompt | "UserPromptSubmit hook success: STYLE: Write like E. B. White and George Orwell. …" directly after the prompt text |
| Skills (`dellm`, `design-theory-pass`, `reviewer`) | 6,429 / 6,461 / 7,335 B | listing in context; body as a message | listing always; body when invoked, then it "stays there across later turns" | listing: name and description, capped at 1,536 characters each; body: the rendered `SKILL.md` "as a single message"; an identical re-invocation adds a short note instead of a second copy |

The sources: Claude Code's hooks, output-styles, memory and skills pages, read 2026-10-10, and the reminders as they arrive in this session's own context.

Four channels carry the setup:

- **System**: the style, on every request.
- **Session-open user block**: CLAUDE.md and the memory index, once, re-injected after compaction.
- **Beside each message**: the hook line, and the style reminder during tool work.
- **On demand**: skill bodies and memory topic files, loaded by a tool call and kept in history.

## 3. What Substrate does today

- **One channel.** Each model step sends one string as the user turn: `OllamaResponder` sends `messages=[{"role":"user", "content": prompt}]` (`adapters/models.py:221–224`; its `system` argument exists but no session sets it), and `CliResponder` passes the prompt as the last argv element of `claude -p` (`models.py:474–480`). Substrate has no system channel in use.
- **The prompt is rebuilt on every model step.** `compose_model_prompt` (`session/transcript.py`) builds it from three parts. First comes the head: the seed, then fragments by precedence: role 0, personality 3, per_turn 10, tools_suite 20, parent_context 30, methodology 50 and up, interrupt 95. Then the kept turns, the current one last. Then any background notices. The model step appends the tool list, results and directives, and records the whole text as `PromptComposed` (`session/__init__.py:467`).
- **Session-open fragments** come from the `session_prompt` producer once per session and sit in every step's head (`FragmentCohort`).
- **The style slot is empty.** The shipped `session` bundle has `personality.md` at 0 bytes.
- **The per-message slot is unwired.** `bundle.per_turn` is loaded from `per-turn.md` (`bundles.py:225`) and never reaches a session; a session's `per_turn` comes only from its manifest (default `""`, set by `PATCH /api/session/<id>`). When set, it renders in the head at precedence 10, at the top of the prompt, far from the current message. Since K261 it is not recorded as its own event.
- **No skills.** No tool loads a guide on demand.
- **The driver's own setup still loads.** `claude -p` runs with `~/.claude` loaded (round-1 research, D3).

## 4. The replication, delivery by delivery

### 4.1 Zero the driver

`claude -p` runs with `--tools "" --strict-mcp-config --setting-sources "" --disable-slash-commands --system-prompt <Substrate's system text>`. Probed 2026-10-10 with a one-line system prompt, the whole call took 678 input tokens.

The driver saw no CLAUDE.md, no memory, no hook, no style, no skill, no MCP tool, and no Claude Code system sections. `--system-prompt` replaces Claude Code's default system prompt, where `--append-system-prompt` would only add to it.

Three things remain:

- the line "You are a Claude agent, built on Anthropic's Claude Agent SDK.", fused to the front of the system text;
- an environment block giving the working directory, platform, model ID and date;
- the account e-mail reminder.

`SessionStarted` records the argv flags, so a reader of the record sees that the driver ran zeroed.

### 4.2 The system channel: the style

The style moves into the shipped `session` bundle's `personality.md` and reaches the model as `PromptFragment(source=bundle_personality)`, written once at session open with the bundle path as provenance. Nothing about that part is new.

The new part is the channel. `PromptComposed` gains a `system` field holding the text sent on the system channel, so the record still holds exactly what the model read. This is a vocabulary change: session vocabulary v0.4, § I, plus the `PromptComposed` Struct. A table in `vocabulary.py`, `SYSTEM_SOURCES = {bundle_personality}`, assigns sources to that channel. The model step sends `system` through the driver's own channel:

- `claude -p` through `--system-prompt`, after the zeroing flags of 4.1;
- Ollama through a `{"role": "system"}` message, with `system` passed per call rather than fixed at construction.

Claude Code sends the style on every request. Substrate rebuilds `PromptComposed` on every model step, so the style rides every step. That includes tool steps.

### 4.3 The session-open user block: CLAUDE.md and the memory rules

The CLAUDE.md text and the working rules from the memory index become the shipped `default` role, `prompts/default.md`. It reaches the model as `PromptFragment(source=role)`, written once at session open with `resolved_from` naming the file. It opens the user turn, at precedence 0, under the same header Claude Code uses:

> Codebase and user instructions are shown below. Be sure to adhere to these instructions. IMPORTANT: These instructions OVERRIDE any default behavior and you MUST follow them exactly as written.

Claude Code sends this block once and re-injects it after compaction. Substrate puts it at the head of every model step, so compaction cannot drop it. When `plan_window` drops old turns, the head stays.

### 4.4 Beside each message: the hook line

The hook line becomes the shipped bundle's `per-turn.md`. Three changes make `per_turn` match the hook:

1. **Source.** A session's `per_turn` defaults to its bundle's `per_turn` slot. The manifest value, set by PATCH, overrides it.
2. **Record.** The `session_prompt` producer writes `per_turn` once at session open as `PromptFragment(source=per_turn)`, with the bundle path or `"manifest"` as provenance. A PATCH writes a new one. `PromptSource.PER_TURN` moves from `TURN_SCOPED_SOURCES` to `SESSION_OPEN_SOURCES`, so the text is written once and placed many times. That move is the same v0.4 change as 4.2.
3. **Position.** `compose_model_prompt` renders `per_turn` directly after the current turn's `USER:` line, which is where the hook lands ("alongside the submitted prompt"). It no longer renders in the head.

The model step rebuilds the prompt on every step, so the line sits beside the current message on every tool step of the turn as well. That covers Claude Code's repeated style reminder in the same position.

### 4.5 On demand: skills

Skills become a Substrate tool, `skill(name)`. Claude Code's two deliveries map like this:

- **The listing.** The `skill` tool's description holds each shipped skill's name and description, capped at 1,536 characters each, the same cap. It reaches the model through the tool channel: `tools_suite` in text mode, the schema in native mode.
- **The body.** A call is `ToolCall(tool="skill", args=["dellm"])`. The `ToolResult` output is the `SKILL.md` body. It renders in history as a `RESULT:` line on every later step and turn until `plan_window` drops that turn, which matches "stays there across later turns". A second call with the body already in the kept history returns a note naming the earlier `ToolResult` seq, as Claude Code does with a short note.

Resolution uses the same three layers as `roles.py`:

1. `<repo>/.substrate/skills/<name>/SKILL.md`;
2. `~/.substrate/skills/<name>/SKILL.md`;
3. the shipped `topologies/session/skills/<name>/SKILL.md`.

`dellm` and `design-theory-pass` ship. `reviewer` checks SDD discipline and stays out of the default.

### 4.6 On demand: memory topic files

The general working rules from the memory index already ship in the role (4.3). The rest of a topic file is the reason and the incident behind a rule, which Claude Code reads with its `Read` tool when it needs them. That detail is not part of the default.

### 4.7 What the record gains

Claude Code shows its deliveries only through `/context` in a live session. Substrate writes each one as an event:

- the style and the role, as fragments with file provenance;
- the per-message line, as a fragment;
- each skill load, as a `ToolCall` and a `ToolResult`;
- every model step's exact input, as `PromptComposed`, with its `system` part.

A reader of any old record can see which version of each text a model read, and where in the prompt.

## 5. The texts

Each text goes to one channel. Wording that names a Claude Code feature is rewritten to Substrate's equivalent; the rule stays.

| Source text | Substrate file | Channel |
|---|---|---|
| `plain.md` | `bundle/personality.md` | system, every step |
| `CLAUDE.md`, all eight sections | `prompts/default.md` | session-open user block |
| Memory index entries that are working or writing rules | `prompts/default.md`, after the CLAUDE.md text | session-open user block |
| Hook line | `bundle/per-turn.md` | beside each message |
| `dellm`, `design-theory-pass` | `skills/<name>/SKILL.md` | `skill` tool |

The working and writing rules from the memory index:

- plain register;
- no market framing;
- report, don't prescribe;
- green is not proven;
- check the box before asserting infra;
- read the code, and grep repeated literals;
- no "shim";
- new versions, not in-place edits, for documents;
- no negative examples and no "schoolroom";
- no pattern-matched caveats;
- no consensus reversion;
- asides are not open questions;
- never command the user;
- hand over a working state;
- narrow UI asks change only that text;
- never pkill by pattern;
- batch commits;
- no artifacts, markdown only;
- no forks or subagents, so the driver does its own work.

Entries that are facts about this project, such as the Substrate roadmap, benchmarking, the SWE-bench plan, test-invocation gotchas and the SDD entries, stay with the project, in `<workspace>/.substrate/prompts/` (repo layer 1).

The wording changes are mechanical:

- `Read` becomes `read_file`;
- `WebSearch` and `WebFetch` become `web_fetch`, the one web tool in `full_suite`;
- "invoke the `dellm` skill" becomes `skill("dellm")`;
- "no subagent delegation" becomes "no `delegate`";
- the reference to the `deep-research` skill is dropped, since none ships.

## 6. Each class of model

The architecture is the same for every class: four channels, the same moments, the same events. A class changes the driver channel each part rides and the length of each text.

| Class | Drivers | How chosen | System channel | Session-open block, beside-message line | Skills | Texts |
|---|---|---|---|---|---|---|
| Claude | `claude` | CLI adapter name | `--system-prompt`, zeroed per 4.1 | the `-p` prompt; the tools go as the text-mode list | `skill` in text mode | full |
| Large open models | kimi, glm, deepseek-v4-pro, nemotron | Ollama `/api/show` `details.parameter_size` of 30B or more | Ollama `system` message | Ollama `user` message | `skill` as a native schema | full |
| Small local models | `qwen2.5:7b-instruct`, `qwen2.5-coder:7b`, `llama3.2:1b`, `llama3:8b`, `deepseek-r1:8b` | `parameter_size` under 30B | Ollama `system` message | Ollama `user` message | `skill` as a native schema with the `dellm` body only; none for a model without `tools` capability | compressed |

`parameter_size` comes back in two forms, `"8.0B"` for `llama3:8b` and `"1042000000000"` for `kimi-k2.6:cloud`; the classifier reads both.

The compressed texts for small models ship as their own bundle and role, `session-small` and `default-small`, resolved by the same loaders. The daemon picks them when the class is small. The full set is about 11.2 KB, roughly 2,800 tokens: the style at 2,655 B, CLAUDE.md at 8,194 B and the hook line at 318 B. The small set fits a head of 800 tokens, a tenth of `llama3:8b`'s 8,192-token window. It keeps every rule as one short imperative line and drops the explanations and examples.

The class and its texts are recorded in `SessionStarted`: the class name, the bundle and the role.

## 7. How the record proves it

Each delivery is checked on the record of a live session per class, by a gate that reads every model step's `PromptComposed`:

- `system` equals the shipped `personality.md`, on every step.
- The head opens with the role fragment, under the header, on every step.
- The `per_turn` text sits directly after the current `USER:` line, on every step of every turn.
- A skill load is a `ToolCall(tool="skill")` and a `ToolResult` holding the `SKILL.md` body, and later steps carry it in history.
- For `claude`, `SessionStarted` holds the zeroing flags, and the driver's reported input tokens on an empty turn equal the 678-token floor plus Substrate's own texts.

How closely each class follows the texts is measured on the round-1 task set (`RESEARCH-2026-10-10-how-substrate-presents-tools.md` §7). Three measures apply:

- machine-register markers per 1,000 words of answers, from the `dellm` catalog, with a target of zero;
- an acknowledgement line at the start of each answer;
- claims made with no tool call or record read behind them, with a target of zero.

The texts for a class are tuned until it meets all three.

## 8. Order of work

1. Zeroing flags and `--system-prompt` for `claude` (4.1).
2. Vocabulary v0.4: `PromptComposed.system`, `SYSTEM_SOURCES`, and `PER_TURN` moved to session-open; the system channel in both responders (4.2, 4.4).
3. The texts: `personality.md`, `default.md` and `per-turn.md` written from part 5.
4. `per_turn` from the bundle, recorded once, placed beside the message (4.4).
5. The `skill` tool, the skill resolver and the shipped skills (4.5).
6. The class classifier and the `session-small` and `default-small` texts (6).
7. The gates of part 7.

## Sources

- Claude Code documentation, read 2026-10-10: Hooks (https://code.claude.com/docs/en/hooks), Output styles (https://code.claude.com/docs/en/output-styles), Memory (https://code.claude.com/docs/en/memory), Skills (https://code.claude.com/docs/en/skills).
- This session's own context: the CLAUDE.md and memory reminder, the hook line after each prompt, the style reminder, the `# Output Style: Plain` system section.
- Probe, 2026-10-10: `claude -p --tools "" --strict-mcp-config --setting-sources "" --disable-slash-commands --system-prompt "…" --output-format json`, 678 input tokens (2 plus 676 cache-creation).
- `~/.claude/`: `CLAUDE.md`, `output-styles/plain.md`, `settings.json` (hook, `outputStyle: Plain`), `skills/*/SKILL.md`, the project `memory/MEMORY.md`.
- Ollama 0.34.1 `/api/show` `details` for `llama3:8b` and `kimi-k2.6:cloud`.
- Substrate: `topologies/session/session_prompt_producer.py`, `roles.py`, `transcript.py`, `__init__.py` (`_model_factory`), `interrupt_fragment_producer.py`, `bundle/`, `prompts/`; `bundles.py`; `adapters/models.py`; `substrate-ui/server.py` (`_build_session_topology_from_manifest`, session create, `_cli_command`).

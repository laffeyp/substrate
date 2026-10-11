# Proposal: Substrate's default guidance for every driver

*2026-10-10, round 4. Rounds 1 to 3 stay on disk. Round 4 makes six changes:*

- *It raises the proposal one level, so it covers every driver Substrate runs, with Claude Code as the first worked case.*
- *It opens with the state of the system today.*
- *It walks each piece from how it works now, to the change, to where the change slots in.*
- *It checks every change against Substrate's existing patterns.*
- *It settles the e-mail question.*
- *It rewrites the caching and model-class sections.*

*No code has changed.*

## 1. The state of the system today

Substrate has a complete machine for giving a model its standing instructions, and almost nothing runs through it.

The machine is the session-open producer, the bundle loader and the role resolver. At session open the `session_prompt` producer writes each source of standing text to the record as a `PromptFragment`, tagged with where it came from:

| Source | Precedence |
|---|---|
| role prompt | 0 |
| bundle style ("personality") | 3 |
| tool list | 20 |
| parent context | 30 |
| bundle methodology | 50 |

On every model step a view called `FragmentCohort` hands those fragments to the model step. The model step joins them into the head of the prompt, adds the transcript, and records the exact text as `PromptComposed`.

The vocabulary sits in `session-vocabulary.md` § I. Tests cover it:

| Area | Tests |
|---|---|
| bundle loading and `extends` | `test_bundles_229.py`, 7 |
| shipped bundles | `test_shipped_bundles_231.py`, 5 |
| role resolution | `test_role_prompt_resolver.py`, 6, and `test_prompt_fragment_role.py`, 7 |
| bundle fragments | `test_prompt_fragment_bundle.py`, 7 |
| fragment-source failures | `test_fragment_source_failure_handling.py`, 4 |
| the one producer | `test_fewer_producers_263.py`, 6 |
| fragments across a restart | `test_session_open_fragments_265.py`, 1 |
| the built prompt | `test_prompt_built_once_261.py`, 4 |
| the vocabulary | `test_session_prompt_vocabulary_v02.py`, 9 |
| live-model composition | `test_realmodel_prompt_composition.py`, 2 |

The tests check that a file becomes a fragment and a fragment reaches the prompt. None of them checks what the text says. They cannot, because there is very little text to check.

Here is the whole of the text a default session ships with.

`topologies/session/bundle/methodology.md`, 317 bytes:

> Work through the request. Read the tools before you call one. When a tool returns, read the result before your next step; when a tool fails, read the error and correct the next call, do not repeat the same call blind.
>
> Say what you did. Do not claim work you did not do. When the task is finished and verified, stop.

`topologies/session/bundle/personality.md`: empty.

`topologies/session/bundle/per-turn.md`: empty.

`topologies/session/prompts/default.md`, 848 bytes:

> You are a working companion in a terminal session. You share a workspace with the user and act on it through the tools attached to this session. Every action rides the substrate record: what you say, what you call, what comes back. The record is the source of truth about what happened; when you decide the next step, decide from the record, not from what you meant to do.
>
> Read the tool results above before your next call. A tool that failed is an observation, not a wall — read the error and correct the next call. Writing code is not the same as its working; after you change code, run it and read the real output before you call the work done. When the task is done and verified, stop and give a plain, concise answer.
>
> Say what you did. Do not claim work you did not do. When you are uncertain, name what you are uncertain about, then act.

Four other roles ship: `planner`, `reviewer`, `tester` and `explainer`, 2.4 to 3.6 KB each, chosen by name when a session is made.

The four application bundles each carry one style line:

- "Blunt. Specific. Name the file and the line every time." (`code_review`, which also has the per-turn line "Flag any unsafe pattern before you leave the file.")
- "Rigorous. A verified answer beats a plausible answer." (`best_of_n_verified`)
- "Collaborative. Read each other's work; the record is the source of truth about what happened." (`pair_coding`)
- "Thorough. A missing document is a hole in the answer." (`research_sweep`)

The wizard's `writing` template holds an early form of this machine's setup: "Every sentence carries a fact", "Replace each abstraction with the particular it covers for", and a per-turn ban on "delve, seamless, robust, comprehensive, underscore, showcase, tapestry, journey, landscape". No shipped bundle uses it.

Four parts of the machine were designed in the specs and never built:

1. **The environment baseline.** Product spec §7 and tech spec §1.6.5 describe repo root, branch, README head, `git diff HEAD` and `<repo>/.substrate/context.md`. `SessionStarted.baseline` is `{}` in every session.
2. **The bundle's per-turn slot.** It loads and never reaches a session. A session's `per_turn` comes only from a PATCH, and it renders at the top of the prompt instead of beside the message.
3. **`extends` onto a shipped bundle.** `resolve_extends` skips the shipped fallback. A test bundle with `extends = ["session"]` raised `BundleNotFoundError`.
4. **Mid-session changes.** `/model`, and a PATCH of the bundle or of `per_turn`, change the manifest and never reach the record. A bundle PATCH has no effect on the prompt at all: the session-open fragments were written once and are not written again.

One drift is also on record: § I gives bundle methodology the band 5–9, and the code uses 50.

So a model in a default Substrate session today reads 317 bytes of loop rules and the tool list, plus the 848-byte role in sessions opened after the 2026-10-08 fix. It gets no workspace path, no date, no model name, and no writing standard. The two latest session records show exactly that: their first prompt opened with `add(a, b) -> a+b`.

## 2. The idea, one level up

Every agent harness gives its model standing instructions the same way. It moves a few texts through a few channels at a few moments.

The moments are:

- every request;
- once at session open, re-sent if the context is compacted;
- beside every user message;
- when something in the environment changes;
- when someone asks.

The channels are the system prompt, the top of the user turn, the space beside the current message, and a message or tool result that stays in history.

Claude Code does this with `CLAUDE.md`, an output style, hooks and skills. Codex does it with `AGENTS.md`, base and developer instructions, an environment-context block and skills. Cursor Agent does it with project, user and team rules and `AGENTS.md`.

Substrate does the same job for every model it runs. It owns the texts, which are files in the repo. It owns the moments, which are triggers on record events. Its channels reach each driver in that driver's own form. Each delivery is an event on the record.

When the driver is itself a harness, Substrate first switches off that harness's own texts, so its own are the only ones the model reads.

Under this proposal, every driver gets:

| Moment | Text | Substrate home | Channel |
|---|---|---|---|
| every request | writing style | `bundle/style.md` | system |
| every request | environment | the baseline, computed at session open | system |
| session open | working rules | `bundle/methodology.md`, plus the role | top of the user turn |
| session open | memory index | `~/.substrate/memory/`, `<repo>/.substrate/memory/` | top of the user turn |
| every message | the reminder line | `bundle/per-turn.md` | beside the message |
| on change | environment update | `SessionChanged` | beside the message |
| on request | `dellm` | `skills/dellm/` | top of the user turn, or a tool result |

The drivers differ only in how each channel reaches the model, and in what has to be switched off first. A driver profile records both. The profile lives beside the driver's entry in `KNOWN_CLI_ADAPTERS`, the table that already holds each CLI's command and version pins. An Ollama driver has no profile: it brings nothing to switch off.

| Driver | Brings its own harness | System channel | What gets switched off |
|---|---|---|---|
| `claude` | yes | `--system-prompt` | `--tools ""`, `--strict-mcp-config`, `--setting-sources ""`, `--disable-slash-commands`; `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS=1` |
| `codex` | yes | `-c model_instructions_file=…` replaces Codex's base instructions; `-c developer_instructions=…` adds a developer message | `--ignore-user-config`, `--ignore-rules`, `--ephemeral`; `commit_attribution_enabled`; Codex's `AGENTS.md`, skills and memories, by config |
| `cursor-agent` | yes | none found; the text rides the prompt | its own config directory (`CURSOR_CONFIG_DIR`) with `attribution.attributeCommitsToAgent` and `attributePRsToAgent` false; user and project rules |
| Ollama cloud | no | `{"role":"system"}` message | nothing |
| Ollama local | no | `{"role":"system"}` message | nothing |
| `deterministic` | no | ignored | nothing |

Claude Code is worked out in full below. Codex and Cursor Agent are inventoried from their `--help`, their binaries and their documentation. Each needs the same probe Claude got before its profile is final: a call that asks the driver to quote its whole context.

Two findings from that inventory bear on §6. Codex's binary carries the instruction "Commit messages must end with `Co-authored-by: Codex <noreply@openai.com>`" behind a `commit_attribution_enabled` key. And this machine's `~/.cursor/cli-config.json` has both Cursor attribution switches set to `true`, which is Cursor's default.

## 3. Claude Code, the worked case

Claude Code delivers this machine's setup as follows. The sources are its documentation (hooks, output styles, memory, skills, env vars, settings, read 2026-10-10) and the reminders as they arrive in this session.

| Text | Size | Moment | Channel |
|---|---|---|---|
| `~/.claude/output-styles/plain.md` | 2,655 B | every request | system prompt, under `# Output Style: Plain` |
| style reminder | one line | during tool work | system reminder |
| environment block | about 1 KB | every request | system prompt: directory, git yes/no, platform, shell, OS, model and ID, cutoff, token budget, date |
| environment update | a few lines | when the directory changes | system reminder |
| `~/.claude/CLAUDE.md` | 8,194 B | session open; again after compaction | first user block, under "These instructions OVERRIDE any default behavior and you MUST follow them exactly as written." |
| `MEMORY.md` | 10,948 B | session open | the same block |
| memory topic files | one per entry | when needed | `Read` results |
| `UserPromptSubmit` hook | 318 B | every prompt | directly after the prompt |
| `dellm` | 6,429 B | listing always; body on `/dellm` or a Skill call | the body arrives as one message and stays |

The texts move into Substrate unchanged at first:

| This machine | Substrate file |
|---|---|
| `plain.md`, and CLAUDE.md's "Every output is writing" and "Unaddressed prose" | `bundle/style.md` |
| CLAUDE.md's other sections, and the general working rules from memory | `bundle/methodology.md`, joining the 317 bytes already there |
| the hook line | `bundle/per-turn.md` |
| `dellm` | `skills/dellm/` |
| this repo's project memories | `<repo>/.substrate/memory/` |

The `default` role keeps who the model is and that the record is the source of truth. Its duplicated rules go to the methodology, so each rule is written once.

The working rules belong in the bundle, not the role, because a session picks one role at a time: `reviewer`, `planner`, and so on. CLAUDE.md's rules hold whatever the role is. The bundle holds under every role.

## 4. Each piece: how it works now, the change, where it slots in

### Style

**Now.** The slot is called `personality`. The session-open producer writes it as `PromptFragment(bundle_personality)` at precedence 3, into the one user string. The `session` bundle's file is empty.

**Change.** The slot is renamed `style`, since every line in it is an instruction about writing. That means `style.md`, `Bundle.style`, `PromptSource.BUNDLE_STYLE` and the wizard question "How should the model write?". Old records keep `bundle_personality`, read through a legacy table, as `LEGACY_SESSION_END_REASONS` maps `timeout` to `turn_cap`. The text is §3's.

**Slot.** The fragment joins the system channel (next subsection).

### The system channel

**Now.** Each model step sends one string. Ollama receives `[{"role":"user","content":…}]`. `OllamaResponder` has a `system` argument set at construction, and no session sets it. `claude -p` receives the prompt as its last argument. `PromptComposed.text` is "bytes-identical to what the driver reads".

**Change.**

- `PromptComposed` gains a `system` field, so the record still equals what the model read.
- `vocabulary.py` gains `SYSTEM_SOURCES`, the set of sources whose fragments go to the system part.
- The composer splits the head on that set.
- The Responder call gains an optional `system=` argument.
  - `OllamaResponder` sends it as a system message.
  - `CliResponder` passes it through the profile's flag: `--system-prompt` for Claude, `-c model_instructions_file` for Codex. With no flag, as for Cursor, it is joined to the front of the prompt.
  - `DeterministicResponder` ignores it.

**Slot.** `SYSTEM_SOURCES = {bundle_style, baseline}` to begin with. For Claude, the profile adds the role, methodology and tool list to the system part, which §7 explains.

### Environment

**Now.** The kernel already has the primitive: `RunStarted.baseline`, filled by the topology builder's `b.baseline()`. The session's `SessionStarted.baseline` field exists. Both are `{}`. Claude Code's environment block reached the review's session only because Claude Code added it itself.

**Change.** At session open the daemon computes the baseline the specs describe:

- the workspace path;
- in a repo: root, branch, commit, README head (8 KiB) and `git diff HEAD` (32 KiB);
- outside a repo: cwd and hostname;
- the platform;
- the driver and its model ID;
- the date;
- `<repo>/.substrate/context.md`, when it exists.

**Slot.** It goes into `RunStarted.baseline` and `SessionStarted.baseline`, and the producer writes it as `PromptFragment(baseline)`, a new `PromptSource`, on the system channel.

### Working rules

**Now.** `bundle/methodology.md` is written at precedence 50, after the tool list at 20. § I says 5–9.

**Change.** The text is §3's. The precedence moves to 5, the band § I already names. That puts it after style (3) and before the tool list. Claude Code's header for CLAUDE.md goes in front of it.

The four application bundles declare `extends = ["session"]` and so inherit the working rules, the style and the per-turn line. That depends on one fix: `resolve_extends` falls back to the shipped bundles the way `load_bundle` does.

**Slot.** The existing `bundle_methodology` fragments. `FragmentCohort` already keeps one fragment per link of an `extends` chain (K265), ancestor first.

### The reminder line

**Now.** `per_turn` is a manifest string, empty unless a PATCH sets it. It renders in the head at precedence 10, at the top of the prompt. Since K261 no event records it. The bundle's `per-turn.md` loads and is never read.

**Change.**

- A session's `per_turn` defaults to its bundle chain's slot. A PATCH overrides it.
- The producer writes it once at session open as `PromptFragment(per_turn)`, with its source as provenance. `PER_TURN` moves from the turn-scoped set to the session-open set.
- The composer places it directly after the current `USER:` line, which is where Claude Code's hook lands. The specs said "prefix"; Claude Code puts it after the message; after is chosen, for the caching reason in §7.

**Slot.** `head_block` stops placing `per_turn`. `compose_model_prompt` places it after the current turn.

### Changes mid-session

**Now.** PATCH writes the manifest. The record never hears of it, and a bundle change never reaches the prompt.

**Change.**

- A PATCH of `driver`, `bundle` or `per_turn`, or a date rollover, writes `SessionChanged{field, old, new}`.
- The next step carries one line after the current message, for example "Environment update: model changed from glm-5.2:cloud to claude." This answers the review's F7, facts going stale with no marker.
- For a bundle or `per_turn` change, the producer writes the new fragments, and `FragmentCohort` drops the earlier fragments of the same source when it sees the `SessionChanged`.

**Slot.** A live run takes the event through `Runtime.inject_event`, the path `InterruptRequested` uses. A parked session takes it ahead of the next turn's `UserMessage`, on the path that resumes the run.

### `dellm`

**Now.** Substrate has no skills. The UI's prompt line routes `/` to a slash table in `session_controller.ts`: `/exit`, `/model`, `/name`, `/list`, `/interrupt`, `/clear`, `/help`.

`/interrupt` is the closest model:

1. The UI calls `POST /api/session/<id>/interrupt`.
2. `SessionRegistry.interrupt` injects `InterruptRequested` onto the live record.
3. The trigger `interrupt-fragment-on-interrupt-request` starts a producer that writes `PromptFragment(interrupt)`.
4. The model reads it on its next step.

Tools are entries in `full_suite`. A model calls one, the call is recorded as a `ToolCall`, the result as a `ToolResult`, and the result stays in history.

**Change.** Two ways to ask, the same two Claude Code has:

1. `/dellm` joins the slash table, and the text after it becomes the turn's message. The daemon injects `SkillRequested{name}`. A `skill_fragment` producer, started by `skill-fragment-on-skill-request`, writes `PromptFragment(skill)`. `SKILL` goes in the session-open set, so `FragmentCohort` keeps the fragment for the rest of the session. The cohort already appends session-open fragments whenever they arrive.
2. When a user asks in words, the model calls a `skill(name)` tool. The body comes back as a `ToolResult` and stays in history. The tool's description lists each skill and what it does.

**Slot.** The file resolves through the role layers: `<repo>/.substrate/skills/`, then `~/.substrate/skills/`, then the shipped `topologies/session/skills/`. Each model class gets its own version (§8). The model applies the skill to any text: a passage, a file it reads and rewrites, or its own draft.

### Memory

**Now.** Substrate has no memory. Product spec §7a rules out a database: knowledge lives "as text files a user owns", in named places. Claude Code's memory is a directory Claude writes to without anything recording it.

**Change.** Two memory directories:

- `~/.substrate/memory/` for the operator;
- `<repo>/.substrate/memory/` for a project.

Each holds a `MEMORY.md` index, one line per entry, and a topic file per entry. At session open the indexes are written as `PromptFragment(memory)`, capped at 200 lines or 25 KB each, the limits Claude Code uses. A model reads a topic file with `read_file` and saves one with `write_file` or `edit_file`, under rules in the methodology: the four kinds (user, feedback, project, reference), one fact per file, and a why and a how-to-apply on each correction.

**Slot.** The fragment is a session-open source. Every save is a `ToolCall`, so the record shows which session learned what. With its own setup switched off, Claude has no memory but this one, and every other model uses the same one.

## 5. Checking the changes against Substrate's patterns

Substrate's method is that vocabulary comes first and every change reuses a primitive before inventing one. The changes, checked one by one:

| Change | Existing pattern it uses | New |
|---|---|---|
| `style` rename | `PromptSource` enum; legacy map like `LEGACY_SESSION_END_REASONS` | nothing |
| system channel | `PromptComposed` keeps "the record equals the input" | the `system` field, and an optional `system=` on the Responder call |
| baseline | `RunStarted.baseline`, `SessionStarted.baseline`, the specs' design | one `PromptSource` value |
| methodology precedence 5 | § I's band | nothing; fixes a drift |
| shipped `extends` | `load_bundle`'s shipped fallback | nothing; fixes a bug |
| `per_turn` | session-open fragments (K263, K265) | nothing; moves a source between two sets |
| `SessionChanged` | `InterruptRequested` injected through `Runtime.inject_event` | one Struct |
| `/dellm` | the slash table; `InterruptRequested` and its fragment producer | one Struct (`SkillRequested`), one `PromptSource`, one producer |
| `skill` tool | `full_suite` tools | one tool |
| memory | session-open fragments; `read_file`, `write_file`, `edit_file` | one `PromptSource` |
| driver profiles | `KNOWN_CLI_ADAPTERS` entries | a few fields per entry |

Three new pieces stay:

- the `system` field;
- `SessionChanged`;
- the skill pair.

Each has a precedent it copies.

One invention from round 3 is dropped. Round 3 gave small models their own file names, such as `style.small.md`. That is a naming rule Substrate does not have. Bundles and roles already select text by name, so small models get a shipped `session-small` bundle and a `default-small` role, and the daemon picks those names (§8).

The work follows SDD's order:

1. The new `PromptSource` values, the two Structs, the `system` field and the precedence move are written into `session-vocabulary.md` first, as one ratified version.
2. Each change is then a sprint card with a unit test and an observation on a live session record.

## 6. Attribution and e-mail

No model run by Substrate ever writes attribution: no `Co-Authored-By`, no "Generated with", no model credit in a commit, a PR or a file. Each harness gets its own switch:

- Claude: `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS=1`, which removes Claude Code's git instructions. Neither probe received any attribution text even before it was set.
- Codex: `commit_attribution_enabled` set off.
- Cursor: a Substrate-owned config directory with both `attribution` switches false.

The methodology carries the rule for every model.

Substrate never reads, stores or sends anyone's e-mail address, and no model it runs sends mail. A search of `substrate/src`, `server.py` and `web/` found no e-mail handling and no attribution strings.

The e-mail block Claude Code shows its own model belongs to Claude Code's login. Claude Code builds it from `oauthAccount.emailAddress` in its own config file. Switching off Claude's setup does not touch that file: `--setting-sources ""` skips settings and CLAUDE.md, and the login and its profile stay where they are. Substrate leaves Claude Code's login alone and never reads the address.

Cursor is the one place a technical need may force a change to a harness config: its attribution switches live in its config directory. If its credentials live there too, the Substrate-owned directory has to carry a login of its own. The Cursor probe settles that.

Every build runs a gate:

- It searches Substrate's own texts and code for an e-mail pattern and for attribution strings, and fails on any match.
- For each harness driver, it makes a commit in a scratch repo through Substrate, and fails if the commit message carries a trailer.

## 7. Prompt caching

Every step sends the whole prompt again; that is how these models work. A provider can still skip re-reading the part it saw on the last call, and that saving is real for both Claude and local Ollama. Substrate gets none of it from Claude today, and it gets Ollama's only by luck.

**Claude.** Anthropic's cache stores the prompt in blocks and matches only whole blocks it has seen before. Substrate sends everything as one block, the single `-p` argument. That block differs on every step, because the transcript grows.

Measured on 2026-10-10: two calls with the same 4,280-token opening inside `-p` each wrote the whole prompt to the cache and read none of it. The same text moved into `--system-prompt` was read from the cache on the second call, 3,689 tokens, with 578 written. So every Claude step in Substrate today pays to read its whole prompt fresh.

The fix is the system channel. For Claude, everything that holds still for a session goes in `--system-prompt`: style, environment, role, methodology, memory index and tool list. Only the transcript and the current turn go in `-p`.

**Ollama local.** Ollama keeps the computed state of the last prompt and reuses the longest prefix the next prompt shares with it. Measured on `qwen2.5:7b-instruct` with a 1,914-token prompt:

- 707 ms to read it the first time;
- 11 ms to read it again;
- 56 ms with three lines added at the end;
- 691 ms with one line added at the top.

One changed line near the top costs the whole read again, on every step. Substrate today keeps its head stable by accident. The proposal makes it a rule: anything that changes goes at the end. That covers the reminder line, environment updates, the current message, tool results and the call directive. The interrupt fragment is the one exception left: it sits at the end of the head, and it fires about once a session.

**Ollama cloud.** `glm-5.2:cloud` reports `prompt_eval_duration` as 0. Whether the provider caches cannot be seen from here. The same layout costs nothing there.

Compaction is the one event that still breaks the prefix. Dropping the oldest turn shifts the transcript, though the head stays cached. Claude Code's cache entries lasted an hour in the probe.

## 8. Model classes

Three things decide how Substrate presents itself to a model:

- whether the driver brings its own harness;
- how large its context window is;
- whether it can take native tool calls.

They sort the drivers into three classes.

**Harness agents: `claude`, `codex`, `cursor-agent`.** Each arrives with its own tools, loop and instruction files. Substrate switches those off (§2), sends its own texts through the profile's system channel, and presents its tools as a text list with a JSON call format, since none of these CLIs takes Substrate's schemas. Each turn costs a fixed overhead before Substrate's text: 656 to 678 tokens for Claude, measured. Codex and Cursor are still to be probed.

Substrate assumes 100,000 tokens of context for a CLI driver unless `~/.substrate/config.toml` says otherwise (`transcript.py`). These drivers get the full texts. For Claude, the tool list and call format move into the system channel, which settles two of the review's findings. F3: a list inside the user turn read as injected text. R1: with its own tools gone, Claude needs telling that Substrate's tools are the only ones.

**Large open models: kimi, glm, deepseek-v4-pro, nemotron through Ollama.** They bring nothing, so Substrate is their whole harness. Their windows run from 203K to 1M tokens. They take tool schemas natively, and they get the full texts in an Ollama system message.

**Small local models: `qwen2.5:7b-instruct`, `qwen2.5-coder:7b`, `llama3.2:1b`, `llama3:8b`, `deepseek-r1:8b`.** They are also bare. Their real windows are small:

- 8,192 tokens for `llama3:8b`;
- 32,768 for the two qwen models;
- 131,072 for the others.

`OllamaResponder` asks for 32,768 unless a session sets `num_ctx`. The full texts come to about 2,800 tokens, a third of `llama3:8b`'s window before a single turn. These models get the `session-small` bundle and the `default-small` role, about 800 tokens together, with every rule cut to one imperative line. Their `dellm` is `dellm-small`: the word and structure lists and the four passes, without the reasons and sources. `llama3:8b` reports no tool support, so it gets the text call format and no `skill` tool; `/dellm` still works for it.

The daemon chooses the class:

- A CLI adapter is a harness agent.
- An Ollama model is small if `/api/show` reports fewer than 30 billion parameters. Ollama reports it as `"8.0B"` for `llama3:8b` and `"1042000000000"` for `kimi-k2.6:cloud`.

`SessionStarted` records the class, the bundle and the role.

## 9. What the driver's review asked for

The review came from session `s_6aa52a8f…`, where Claude drove Substrate.

- **F2, R1, R2: two tool systems, with no rule for which counts.** §2 switches off Claude's own tools, and §8 names Substrate's as the only ones.
- **F3: the tool list read as injected text.** For Claude it moves into the system channel.
- **F4: four layers of instructions in conflict.** The four were Claude Code's system prompt, CLAUDE.md, the hook and Substrate's prompt. Switching off Claude Code's layers leaves Substrate's alone. Attribution is gone (§6). The acknowledgement line and a JSON tool call fit one reply, line first, which `parse_tool_call` already accepts.
- **F4: the methodology repeated Claude Code's loop rules.** `--system-prompt` removes Claude Code's copy.
- **F7, R8: environment facts went stale.** The baseline and `SessionChanged` fix this.
- **§6 of the review: untested claims stated flatly.** The methodology carries "research, don't fabricate" and "name your evidence" beside the writing rules, and the record shows which claims have a tool call behind them.

The tool-presentation items, R3 to R11, are covered in `RESEARCH-2026-10-10-how-substrate-presents-tools.md`.

## 10. Copying first, improving later

The first pass copies this machine's texts across as they are. It changes only tool names (`Read` becomes `read_file`) and drops features Substrate lacks.

Improving the texts comes after, and it can be measured. Substrate's assay harness already runs arms against cases over trials. One arm is a session with the copied texts, the other a session with a candidate revision. Both get the same goal on the same workspace. A grader scores the result, the register words per 1,000 against the `dellm` catalog, and the claims with no tool call behind them. Each class gets its own run.

The pieces exist today, so the first comparison, copied texts against the current 317 bytes, can run as soon as the texts are in place.

## 11. Gates and order of work

A gate reads every `PromptComposed` in a live session per class and checks that:

- the system part holds style and environment;
- the head opens with the role and methodology;
- the reminder line sits right after the current message;
- `/dellm` leaves `SkillRequested` and a fragment;
- `skill` leaves a `ToolCall` and a `ToolResult`;
- `/model` leaves `SessionChanged` and an update line;
- a memory save leaves a `ToolCall` into a memory directory;
- a second Claude step reads from the cache.

The attribution and e-mail gate of §6 runs on every build.

The order of work:

1. The vocabulary version: `style`, `baseline`, `skill`, `memory`, `SYSTEM_SOURCES`, `PromptComposed.system`, `SessionChanged`, `SkillRequested`, precedence 5, and `PER_TURN` moved to the session-open set.
2. The Claude profile and the attribution gate.
3. The system channel through the Responder call.
4. The copied texts.
5. Shipped `extends`, with the application bundles extending `session`.
6. The baseline.
7. `per_turn` placement and `SessionChanged`.
8. Memory.
9. `dellm`.
10. Classes, with `session-small`, `default-small` and `dellm-small`.
11. The Codex and Cursor probes and profiles.
12. The first assay comparison.

## Sources

- Product spec `current-design-direction/product-spec/PRODUCT-SPEC-2026-08-17-round12.md` §2a, §7 to §7b, §14; tech spec `current-design-direction/tech-spec/TECH-SPEC-2026-08-25-round6.md` §1.6.5, §9; design spec `handoff_latest/docs/DESIGN-SPEC -2026-08-31-.md`.
- Claude Code documentation (code.claude.com/docs/en/: hooks, output-styles, memory, skills, env-vars, settings), read 2026-10-10. Codex `AGENTS.md` guide (learn.chatgpt.com/docs/agent-configuration/agents-md) and Cursor rules (cursor.com/docs/context/rules), read 2026-10-10.
- Binaries:
  - `claude` 2.1.296: the `userEmail` block from `oauthAccount.emailAddress`; `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS`.
  - `codex` 0.157.0: `model_instructions_file`, `developer_instructions`, `include_environment_context`, `commit_attribution_enabled`, and the `Co-authored-by: Codex` instruction.
  - `cursor-agent` 2026.09.23: `CURSOR_CONFIG_DIR`, `attributeCommitsToAgent` and `attributePRsToAgent`, default true.
  - `~/.cursor/cli-config.json` on this machine.
- Probes, 2026-10-10:
  - Claude with its setup switched off: 678 and 656 tokens.
  - Claude cache, text in `-p`: no reads. Text in `--system-prompt`: 3,689 tokens read on the second call.
  - Ollama `qwen2.5:7b-instruct`: 707, 11, 56 and 691 ms.
  - `glm-5.2:cloud`: no prompt timing reported.
- The driver's review, session `s_6aa52a8f0e3b436c8092fd21`; records `s_9eee1b3a4d094346bb30039c` and `s_6aa52a8f0e3b436c8092fd21`.
- Substrate:
  - `bundles.py`;
  - `topologies/session/` (`session_prompt_producer.py`, `roles.py`, `transcript.py`, `views.py` `FragmentCohort`, `__init__.py`, `interrupt_fragment_producer.py`, `bundle/`, `prompts/`);
  - `topologies/applications/*.bundle/`;
  - `templates/bundles/`;
  - `adapters/models.py`;
  - `topologies/session_registry.py`;
  - `process/signals/session-vocabulary.md` § I;
  - the tests named in §1.
- substrate-ui: `server.py` (`KNOWN_CLI_ADAPTERS`, session create, PATCH, interrupt) and `web/vm/session_controller.ts` (`slashCommands`, `interruptTurn`).
- `~/.claude/`: `CLAUDE.md`, `output-styles/plain.md`, `settings.json`, `skills/dellm/SKILL.md`, the project memory.

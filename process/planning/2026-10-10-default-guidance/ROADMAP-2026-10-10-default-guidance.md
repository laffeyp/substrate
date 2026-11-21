# ROADMAP: Substrate's default guidance for every driver

*2026-10-10.*

**Input.** `RESEARCH-2026-10-10-substrate-default-guidance-r7.md`, plus the decisions taken in conversation on 2026-10-10.

**Goal.** Every model Substrate runs gets this machine's working and writing standard. Each driver gets it at the same moments, through that driver's own channels, on top of Substrate's harness rules. Every delivery is an event on the record. A harness driver's own setup is switched off first.

## Decisions taken for this roadmap

| Decision | Source | What it decides |
|---|---|---|
| Add, don't replace | Architect, 2026-10-10 | Today's `session` bundle and `default` role stay unchanged as the harness layer. The machine's texts go in a new `standard` bundle that extends it. |
| `personality` becomes `style` | Architect | The slot, field and `PromptSource` are renamed; a legacy table reads old records. |
| `session` becomes `harness` | Research r7 §5 | The bare bundle's new name. The old name resolves through the legacy table. |
| Style stacks across `extends` | Research r7 §4 | One fragment per link, ancestor first, as methodology does. Caller-wins goes. |
| The system channel carries style and environment only | Architect | Every other text stays where the delivery theory puts it. |
| Prompt caching is opt-in only | Architect | `driver_params.cache_layout`, default false, `claude` only, with no UI control and no default anywhere. |
| No attribution, ever | Architect | No model run by Substrate writes `Co-Authored-By`, "Generated with", or any model credit. Each harness's own switch is turned off. |
| Substrate never touches e-mail | Architect | Substrate reads, stores and sends no address. A harness's login stays as the harness keeps it. |
| `dellm` is the one skill, on request only | Architect | Available two ways: `/dellm`, or a `skill` tool call. One version per model class. |
| Copy first | Architect | The texts go in as they are. Revision comes later, through assay comparisons. |
| Memory: two directories of text files | Architect | `~/.substrate/memory/` and `<repo>/.substrate/memory/`. Indexes load at session open; writes go through the file tools. |
| Codex and Cursor follow Claude | Architect | They are inventoried now and probed and profiled after Claude works. |

## Order and checks

Each step's check runs against the installed Substrate.app wherever the step changes behaviour.

**1. K270: session vocabulary v0.4 (document).**
- *Work:* section P of `session-vocabulary.md` locks the following:
  - the `style` rename and stacking;
  - `harness`;
  - `PromptSource` values `baseline`, `skill` and `memory`;
  - `SYSTEM_SOURCES`;
  - `PromptComposed.system`;
  - the `SessionChanged` and `SkillRequested` Structs;
  - precedence 5 for every methodology link;
  - `PER_TURN` in the session-open set;
  - the legacy tables.
- *Check:* every name used by K271–K280 and U120–U122 appears in section P.

**2. K271: bundles stack and extend.**
- *Work:*
  - rename `personality` to `style` and `session` to `harness`, with the legacy tables;
  - style stacks per link;
  - `resolve_extends` falls back to shipped bundles;
  - every methodology link takes precedence 5.
- *Check:* a `standard`-shaped test chain composes `harness` then `standard` style and methodology, in order. Old records still load.

**3. K272: the system channel.**
- *Work:*
  - `PromptComposed.system`;
  - the composer splits the head on `SYSTEM_SOURCES`;
  - the Responder call takes `system=`: an Ollama system message, a profile flag for a CLI, ignored by the deterministic double.
- *Check:* `PromptComposed.system` plus `.text` equals what each responder sent, captured.

**4. U120: the Claude driver profile.**
- *Work:*
  - `KNOWN_CLI_ADAPTERS["claude"]` gains the strip-out flags and `--system-prompt`, and runs with `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS=1`;
  - `SessionStarted` records the flags;
  - the attribution and e-mail gate.
- *Check:* a live `claude` session's driver quotes no CLAUDE.md, hook, style or skill text. The gate passes.

**4a. U123: driver slash commands pass through.** (Added 2026-10-10.)
- *Work:* a prompt line starting with `//` sends `/<rest>` to a driver whose profile allows it, as its own call, recorded as `DriverCommand` and `DriverCommandResult` and kept out of the model's history. The Claude profile drops `--disable-slash-commands`.
- *Check:* `//context` shows Claude's context report with no model turn; an Ollama session refuses it in one line.

**5. K273: the environment baseline.**
- *Work:* compute the baseline at session open into `RunStarted.baseline` and `SessionStarted.baseline`, and write `PromptFragment(baseline)` on the system channel.
- *Check:* a session in a git workspace and one outside both show their facts in `PromptComposed.system`.

**6. K274: the reminder line and `SessionChanged`.**
- *Work:*
  - `per_turn` defaults from the bundle chain, is written once, and sits right after the current message;
  - the `SessionChanged` Struct, its update line, and the cohort dropping replaced fragments.
- *Check:* every step of a tool turn carries the line right after the message. A synthetic `SessionChanged` puts an update line on the next step.

**7. K275: the `standard` bundle.**
- *Work:*
  - `standard` holds the machine's texts, copied as they are;
  - the application bundles extend it;
  - golden head tests for each shipped bundle.
- *Check:* the golden heads match. `code_review` reads harness, standard and its own lines in that order.

**8. U121: the daemon uses it.**
- *Work:*
  - the default bundle moves to `standard`;
  - PATCH and `/model` write `SessionChanged`;
  - `cache_layout` joins `driver_params`.
- *Check:* a new session in the installed app opens on `standard`. `/model` mid-session puts an update line in the next prompt. `cache_layout` is refused for an Ollama driver.

**9. K276: memory.**
- *Work:* the two directories, `PromptFragment(memory)` at session open with the 200-line / 25 KB cap, and the memory rules in `standard`'s methodology.
- *Check:* an index loads; a save shows on the record as a `ToolCall` into a memory directory.

**10. K277: `dellm` in the kernel.**
- *Work:*
  - the skill resolver over three layers;
  - `SkillRequested` and the `skill_fragment` producer;
  - the `skill` tool;
  - the shipped `dellm`.
- *Check:* an injected `SkillRequested` puts the body in every later step. A `skill("dellm")` call returns it.

**11. U122: `/dellm`.**
- *Work:* the slash command injects `SkillRequested`, and its text becomes the turn's message.
- *Check:* `/dellm <paragraph>` in the installed app returns the paragraph rewritten, with the skill fragment on the record.

**12. K278: model classes.**
- *Work:* the classifier (harness agent; Ollama under or over 30B), plus `standard-small`, `default-small` and `dellm-small`, all recorded in `SessionStarted`.
- *Check:* `llama3:8b` opens on the small set within 800 tokens; `kimi-k2.6:cloud` opens on `standard`.

*Steps 13 and 14 were withdrawn on 2026-10-10 by the Architect: Codex and Cursor profiles, and the assay comparison, are future work, not part of this roadmap. Their cards stay on disk as withdrawn.*

**13. K279: Codex and Cursor profiles (research, then build).**
- *Work:* the context-quote probe for each; then profiles that switch off their instruction files, skills, memories and attribution.
- *Check:* each driver quotes only Substrate's text, and a commit through each carries no trailer.

**14. K280: the first assay comparison.**
- *Work:* `standard` against `harness` on the same goals, per class. The `default` role's three duplicated rules go into the same comparison.
- *Check:* a report with the trial counts the benchmarking-power memo requires, or the result is stated as unproven.

**15. K281: amend the specs.** (Added 2026-10-10, Architect.)
- *Work:* the next round of each spec the roadmap changed: product spec round 13, tech spec round 7, and the design spec if U121–U123 changed it. Each is a copy of the current round, with new sections marked as new and superseded sections kept under a note naming what replaces them.
- *Check:* every behaviour a closed card changed appears in a new or superseding section; no prior round is edited.

## Sprint cards

| Sprint | Repo | Card |
|---|---|---|
| K270–K281 | substrate | `substrate/process/sprints/sprint-270…281-*.md` |
| U120–U123 | substrate-ui | `substrate-ui/process/sprints/sprint-120…123-*.md` |

**Next direction after this roadmap:** distribution.

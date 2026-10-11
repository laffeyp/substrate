# RESEARCH: guidance controls — what the section under the model can set (round 4)

*2026-10-11. Asked by the Architect. Rounds 1–3 (`RESEARCH-2026-10-10-guidance-controls.md`, `-r2.md`, `-r3.md`) stay on disk. Companion to the moves note (`substrate-ui/process/planning/RESEARCH-2026-09-27-moves-a-typed-vocabulary-of-conversational-redirect.md`) and the mastering note (`…-mastering-layer-and-the-metacognitive-baseline.md`), and the next step after the guidance levels (`ROADMAP-2026-10-10-guidance-levels.md`, `RESEARCH-2026-10-10-substrate-default-guidance-r7.md`). Not a design spec: nothing here commits to a control, a fragment text or a layout. The Architect's words are in the appendix, verbatim.*

**Changes from round 3.** The Architect found round 3's candidate list mostly asked whether the model should work well or badly ("would you like your sources verified or not? The answer is always yes"), and found much of what was said missing. Round 4:
- Moves six quality items into an always-on floor (§3). The six are verification, source discipline, research depth, counterargument, planning and tool order. A control now chooses between ways of working that are each good for something; none chooses quality.
- Replaces "register: plain, formal, technical" with an open catalog of language patterns that can be induced (§7). "Make them talk differently" means inducing any pattern of language that is useful in some way, not picking from three.
- Gives subtle behaviour its own section (§8).
- Restores what the rounds dropped:
  - guidance is often text sent into another maker's harness;
  - the job can be done "well or differently";
  - tone;
  - the moral point about presenting these systems as sentient.
- Points to the moves note for the rhetoric system and does not rebuild it here (§11). The Architect mentioned it as a separate system.
- Adds an appendix with the Architect's messages, as the moves and mastering notes have.

## 1. The construct

The workspace bar is three steps, top to bottom: where to work, which model, and how the model should work. Each step gets a one-line hint beside its heading (open items 13–15):

| Heading | Hint |
|---|---|
| WORKSPACE | choose where to work, or open a previous session |
| MODEL | choose a model to work with |
| GUIDANCE | to be settled with this design; a starting point is "choose how it works" |

Today the third step is one control, the guidance level: `harness`, low, medium or high, with a default that follows the model. This note proposes that the step becomes a set of controls chosen after the model. Each control induces a pattern in the text the model produces or in what it does. Each position is a short text that Substrate delivers at a chosen moment through a chosen channel.

All of it is text injection, and half the time the text goes into someone else's system. For `claude`, `codex` and `cursor-agent` the guidance enters another maker's harness, through that harness's system channel, after Substrate has switched off what it can of the harness's own texts (round 7 of the default-guidance research, §2). For Ollama models Substrate is the whole harness. The same control can therefore land differently on a harness model than on a bare one, and has to be measured on each.

It barely feels like software engineering, and it still has a method. The input text is fixed and recorded, the output is a sample from a distribution, and a pattern's effect shows over many samples. Results can be predicted and checked. Getting a certain kind of text out is, in this setting, also getting a certain kind of engineering done, well or *differently*. The controls are about the second word. A model told to answer first and justify after writes a different reply from one told to derive first, and both are correct. A model inclined to delegate splits work into child sessions; one inclined to work alone does not. Both show on the record.

Static rule files are read once at session start. Here a control can be set before the session, changed inside it, and delivered at the moment it matters (§9).

## 2. The model is not a person

Substrate treats every model as a stochastic text generator. It has internal structure, rules, path dependence and things that work on it, and none of that makes it a person. No control, preset or text gives a model a person's name, a character, a persona, feelings, or a job title from an organization. "You are a product manager" is the kind of line no Substrate control writes.

Presenting these systems as people, or as sentient, is wrong on two counts. It misleads the user about what the tool is. And it puts the user in front of a mirror. A person who treats the output as a colleague's view stops doing the work, and the de-skilling evidence in §5 is what that looks like. The patterns in this note work when the text is treated as text.

Two needs that other tools meet with roles are met here in abstract terms:
- *Loading knowledge.* A control or skill that brings in a body of domain material is named for the material, for example a knowledge load on concurrency or on tax law. It is never named for a person who would know it.
- *Places in a topology.* A step in a multi-model topology is an information-processing node with an abstract name for what it does to its input, such as a filter, a checker or a merger. It is never an org-chart job.

Studies of people and personas appear in §5 and §6 because they are part of the field. Each is reported, and none is adopted.

## 3. The floor: always on, never a dial

Some instructions have only one right setting. They belong in the base guidance at every level, and no control turns them down:
- verify a fact before stating it, and say what was checked and where;
- research a research task fully, and settle a mid-task unknown before moving on;
- read each tool result before the next call;
- name the strongest objection to a contested claim;
- read before writing, and plan when the task needs a plan.

The floor also holds anti-credulity. The model never accepts a claim because of who published it:
- A manufacturer's text about its own product is PR copy. Its vocabulary is chosen to produce a reaction, not an understanding, which is lexical poisoning. It counts as a claim, never as evidence.
- The same holds for press releases, paid placements, and anyone famous in the news.
- Every cited source carries its genre: vendor, press, paid placement, independent study, postmortem, forum.

The high guidance text already carries most of this. Medium and low carry the core of it in fewer words.

The floor can still be reinforced at a moment, which is different from being switched. A trigger can deliver a one-turn reminder when the model fetches a page from a domain on a vendor list (§9). The reminder is measured by the share of cited sources by genre, from a lookup table of vendor, press and independent domains.

## 4. What Substrate already has

Every piece a control needs exists today, except the controls themselves.

At session open the `session_prompt` producer writes each standing text as a `PromptFragment` with a `source`. `PromptSource` has eleven members: `role`, `bundle_methodology`, `bundle_style`, `baseline`, `memory`, `skill`, `parent_context`, `tools_suite`, `per_turn`, `user_message`, `interrupt` (`topologies/session/vocabulary.py`). Two sets split them:
- `SESSION_OPEN_SOURCES` are written once and used in every prompt;
- `TURN_SCOPED_SOURCES` (`user_message`, `interrupt`) are used in the next prompt only.

`SYSTEM_SOURCES` (`bundle_style`, `baseline`) go on the driver's system channel. The others go at the top of the user turn. `per_turn` is placed directly after the current message.

Five delivery moments already work:

| Moment | Mechanism | Example today |
|---|---|---|
| every request | a system source | the style text |
| session open | a session-open fragment | methodology, memory index |
| beside every message | `per_turn` | the reminder line |
| on change | `SessionChanged{field, old, new}`, written on a turn's first step | a bundle or model switched mid-session |
| on request or on an event | a trigger on a record event starts a producer that writes a fragment | `/dellm` (K277); a soft interrupt writes `PromptFragment(interrupt)` |

The last row is the general one. Any event on the record can start a producer that writes a fragment. A text can therefore arrive because something happened, not only because a session opened.

Every fragment is an event, and `PromptComposed` holds the exact text the model read (`text` and `system`). A reader of any session can see which control positions were in force on every step.

A session model can already call `delegate`, which opens a child session (`topologies/tool_loop/delegate.py`; the child's `UserMessage` carries `slash_source="delegate"`). It can also call `list_topologies`, `run_topology` and `run_topology_poll`, which run a named application as a child run (`topologies/tool_loop/substrate_tools.py`). No tool lets a model write a new topology. "Build its own topology" is therefore two different controls: one for how readily the model runs an existing topology, available now, and one for authoring a new one, which needs a tool that does not exist yet.

The language-metrics note (`RESEARCH-2026-10-10-language-metrics-r4.md`) measures the form of every user and model text and the relation between them. The assay harness runs arms against cases over trials. Between them they can tell whether a control does anything.

## 5. What the evidence says about steering by text

Small wording changes move results a lot. Formatting changes that keep the meaning of a few-shot prompt shifted LLaMA-2-13B's accuracy by up to 76 points (Sclar et al., ICLR 2024, arXiv 2310.11324). A control's exact text is part of its definition and gets versioned like code.

Length instructions are followed loosely. Across 26 models, LIFEBench found length instructions unreliable, especially for long targets. Most models handled short targets reasonably and fell off sharply past a threshold (Zhang et al., NeurIPS 2025 Datasets and Benchmarks, arXiv 2505.16234). A verbosity control works better as a direction (shorter, longer) than as a number of words, and its effect has to be measured, not assumed.

### Person framing: reported, not adopted

Four studies tested what happens when a model is told it is a person, or is made to act like one. In each, the framing did not help and often did harm.
- *Personas in system prompts.* Across 4 model families, 2,410 factual questions and 162 social and job roles, a persona did not improve accuracy over no persona. Which persona helped on a given question was close to random (Zheng et al., Findings of EMNLP 2024, arXiv 2311.10054).
- *Bias under assigned personas.* Over 24 reasoning datasets and 19 socio-demographic personas, assigning a persona surfaced stereotyped assumptions. For ChatGPT-3.5, 80% of personas showed bias, and some datasets dropped more than 70%. GPT-4-Turbo still showed it in 42% of personas (Gupta et al., ICLR 2024, arXiv 2311.04892).
- *Role-play prompts.* A role-play prompt degraded Llama 3's reasoning on 7 of 12 datasets. The authors' remedy runs a neutral prompt beside it and keeps the better answer (Kim, Yang & Jung, Findings of IJCNLP 2025, arXiv 2408.08631).
- *Warmth.* Fine-tuning five models to be warmer raised their failure rates on safety-critical tasks by 10 to 30 points. It made them about 40% more likely to agree with a user's wrong belief, most of all when the user expressed sadness (Ibrahim, Hafner & Rocher, Oxford; arXiv 2507.21919). That study changed weights, not prompts.

### De-skilling

In a randomized trial, 52 developers, mostly junior, learned a new Python library. Those using an AI assistant scored 50% on the follow-up quiz against 67% for those coding by hand, with the widest gap on debugging. The developers who handed the coding over entirely learned least; those who asked for explanations and conceptual answers kept most of their learning (Shen & Tamkin, arXiv 2601.20245). The study is the model maker's own research. Its finding runs against the maker's product, which is the one direction in which a manufacturer's paper earns some weight.

## 6. What other tools ship

These are facts of existence: what each product offers. Nothing here adopts their framing, and a manufacturer's description of its own product is PR copy. Its vocabulary is chosen to produce a reaction, not an understanding, so none of it counts as evidence that a feature works.

- **ChatGPT personalities.** A default and four named presets (Cynic, Robot, Listener, Nerd), introduced with GPT-5 in August 2025. This is person framing; Substrate does not do it. Source: press coverage of the launch.
- **Claude styles.** Normal, Concise, Explanatory and Formal, plus custom styles built from a user's writing samples. Source: the vendor's announcement.
- **Claude Code output styles.** Named texts that replace part of the system prompt; this machine's `plain` style is one. Source: vendor documentation, not re-read for this note.
- **OpenAI API `verbosity`.** A request parameter for GPT-5 (`low`, `medium`, `high`), beside `reasoning_effort`. Source: the vendor's cookbook. The vendor's claims about its effect are not used here.
- **Activation steering.** Anthropic's "persona vectors" (August 2025) add directions to a model's internal activations. The name is person framing, and the source is the vendor's own research. It needs access to the weights, which none of Substrate's drivers exposes: the harness CLIs don't, and Ollama's API doesn't.
- **Rule files.** `CLAUDE.md`, `AGENTS.md` and Cursor rules are static text files read at session start.

What these share: one or two dimensions, set as a preset, with the delivered text out of the user's sight. The search behind this note found no product with all four of these properties:
- several independent controls;
- each delivered at its own moment;
- each recorded beside the reply it shaped;
- each with a measured effect.

That covers the products named here, not the market.

## 7. Talking differently: inducing language patterns

"Talk differently" means any pattern of language that a text can induce and that is useful for something. The list below is a first catalog, not a menu of three. The patterns are grouped by what they change. Every one is a real, named practice with a source, and every one can be measured on the record by form or by lookup table, with the measures of the language-metrics note (round 4). The catalog stays open: a new pattern joins when it has a use, a source and an observable.

### Size and tone

| Pattern | What it induces | Useful for | Observable |
|---|---|---|---|
| Verbosity: terse, normal, full | Length per reply | Terse for a fast loop at the terminal, full for a write-up to read later | tokens and sentences per reply |
| Tone: blunt, neutral, formal, dry, warm | Word choice and stance toward the reader | Blunt for review, formal for a document others will read, dry for analysis | lexicon rates: hedges, intensifiers, politeness markers, second person |

Warmth comes with a measured risk (§5): in one study, models fine-tuned for warmth agreed more often with wrong beliefs. A warm tone is offered only beside the floor, and its effect on agreement is measured.

### Controlled languages: a smaller, stricter English

| Pattern | What it induces | Useful for | Source |
|---|---|---|---|
| Simplified Technical English | A restricted dictionary, one meaning per word, short sentences, active voice | Instructions and procedures that must not be misread | ASD-STE100, the aerospace standard |
| Basic English | Writing within an 850-word core vocabulary | Text for readers of English as a second language; plain explanation | Ogden, 1930 |
| E-Prime | English without any form of "to be" | Stating what something does or how it was observed, not what it "is" | Bourland, 1965 |
| Plain language | Short words, everyday terms, the reader addressed as the user of the text | Text for non-specialists | US Federal Plain Language Guidelines, 2011 |

### Specification languages: text a machine or a reviewer can check

| Pattern | What it induces | Useful for | Source |
|---|---|---|---|
| RFC 2119 keywords | MUST, SHOULD and MAY with fixed meanings | Requirements and contracts | RFC 2119, 1997 |
| EARS | Requirement templates: "When ‹trigger›, the ‹system› shall ‹response›" | Requirements that map one-to-one onto tests | Mavin et al., IEEE RE 2009 |
| Typed vocabulary lock | Only the project's own terms, from its vocabulary file, for its concepts | Keeping a project's names from drifting | SDD's vocabulary-as-contract |
| Conventional commit and docstring forms | A fixed shape for commits, docstrings and changelogs | Repositories with tooling that reads those shapes | Conventional Commits 1.0 |

### Order: where the point goes

| Pattern | What it induces | Useful for | Source |
|---|---|---|---|
| Answer first (BLUF, pyramid) | The conclusion in the first sentence, support after | Decisions, status reports, reviews | Military BLUF; Minto, *The Pyramid Principle* |
| Inverted pyramid | The most important fact first, the rest in falling order | Summaries a reader may stop reading partway | Journalism practice |
| Derivation first | The reasoning laid out before the conclusion | Teaching, and claims a reader must check step by step | Mathematical writing |
| Worked example first | One concrete case before the general rule | New concepts; APIs | Instructional design (Sweller's worked-example effect) |

### Argument and evidence shape

| Pattern | What it induces | Useful for | Source |
|---|---|---|---|
| Toulmin layout | Claim, grounds, warrant, qualifier and rebuttal stated separately | Arguments a reader has to audit | Toulmin, *The Uses of Argument*, 1958 |
| Evidential marking | Every claim marked as observed, inferred or reported, as some languages do in their grammar | Separating what the model ran from what it read and what it guessed | Aikhenvald, *Evidentiality*, 2004 |
| Calibrated confidence | A stated probability or confidence band on each uncertain claim | Forecasts and risk assessments | Forecasting practice |
| Steelman, then critique | The strongest form of the opposing case before the reply's own | Contested design choices | Argumentation practice |

### Form of the output

| Pattern | What it induces | Useful for | Observable |
|---|---|---|---|
| Prose first | Paragraphs; lists only for parallel items | Reasoning that connects | bullets and headings per 1,000 words |
| Tables first | Comparisons laid out in columns | Choices among options | tables per reply |
| Diagram in text | ASCII or Mermaid diagrams of structure and flow | Architecture, state machines | diagram blocks per reply |
| Code first | The change shown, explanation after | Coding loops | code blocks before prose |
| Literate | Code and explanation interleaved in reading order | Code meant to be read by people | Knuth's literate programming |

### Range: one answer or many

| Pattern | What it induces | Useful for | Source |
|---|---|---|---|
| Convergent | One answer, chosen | Execution | — |
| Divergent | Several distinct alternatives before choosing | Design, naming, early exploration | Guilford's divergent production |
| Constraint prompts | A deliberate oblique constraint to break a fixed line of thought | Getting unstuck | Eno & Schmidt, *Oblique Strategies*, 1975; SCAMPER |
| Question-led | Replies that open with the questions the problem raises before answering them | Ill-posed problems | The Socratic method as a procedure |

### Language

| Pattern | What it induces | Useful for |
|---|---|---|
| Output language | Replies in a chosen natural language, code and identifiers left as they are | Working in the user's language |
| Glossary | A fixed translation for each term of art | Keeping terms stable across languages |

Patterns stack where they do not collide. Answer first, E-Prime and evidential marking can hold in the same reply. Answer first and derivation first cannot. A preset is a named stack, with an abstract name such as `spec`, `review` or `teach`.

How faithfully a model holds a pattern is an open measurement. A controlled language with an 850-word list is a hard constraint, and a 7B model may drift off it within a paragraph. The observable for each pattern, measured per model class, decides which patterns a class is offered.

## 8. Behaving differently, subtly

The second half of the controls changes what the model does, not how its text reads. Each position is a legitimate way to work; which one fits depends on the task and the user. The effects are meant to be small shifts in tendency, set by a few lines of text, not commands.

| Dial | Range | What changes | Observable |
|---|---|---|---|
| Delegation | works alone ↔ splits work into child sessions | How readily the model calls `delegate` | `delegate` calls per turn; child sessions opened |
| Building topologies | does the work itself ↔ runs a topology for it | How readily the model calls `run_topology` | `run_topology` calls per turn |
| Authoring topologies | — | Writing a new topology for its own problem | needs a tool that writes a topology; none exists |
| Autonomy | checks in often ↔ runs to the end | How long it works before handing back | steps per turn before `Returned` |
| Reporting cadence | silent until done ↔ narrates each step | Text written beside tool calls | `ModelReply` text on `tool_use` steps |
| Interactivity | decides and acts ↔ offers options to choose from | Whether forks in the work go to the user | share of turns that end in a question |
| Exploration | goes straight at the task ↔ surveys the workspace first | Reads before the first change | read-type calls before the first write |
| Scope | does exactly what was asked ↔ fixes what it finds on the way | Changes outside the request | files changed outside those named in the request |
| Parallelism | one thing at a time ↔ several calls at once | Concurrent tool calls | tool calls per model step |

These have the cleanest measures in this note. Their observables are typed events: a `delegate` call is a `ToolCall` with a name, so the effect of a position is a count, with no text measure in between. None of the products in §6 offers a control of this kind.

Some dials interact with the floor and with each other. Scope at "fixes what it finds" is a real way to work on a codebase someone owns alone, and the wrong way on a shared branch. Autonomy at "runs to the end" pairs naturally with reporting cadence at "silent". Defaults follow the model class and the task, and the record shows every setting.

## 9. Moments: when a control speaks

A static file speaks once. A control in Substrate can choose its moment:

- At session open, like the guidance level today.
- Beside every message, for a control that drifts. LIFEBench's result suggests length drifts, so verbosity is a candidate for a reminder line, and so is any controlled language from §7.
- On change: a control changed mid-session writes `SessionChanged` and its new fragment. The path exists for `bundle` and `per_turn`; controls would add fields.
- On an event: a trigger starts a producer that writes a turn-scoped fragment. For example, a `LanguageDrift` event on reply length (language-metrics note, round 4) could start a one-turn reminder of the verbosity position, and a `web_fetch` of a domain on the vendor list could start a reminder that its content is a claim. The control then becomes a feedback loop: a target, a measure on the record, and a correction delivered as text. Each correction is an event, so every action the loop takes is visible.

## 10. Composition and conflict

Controls stack on the level's base text, and some positions contradict it. The high text says "stop when the point is made"; a verbosity position of *full* pulls the other way. Three designs:

1. **The base text wins.** Controls only narrow within the base text's rules. Verbosity *full* then means "complete", not "padded". This is safe, but it limits what a control can do.
2. **The control wins on its own dimension.** The control's fragment comes after the base text and says it overrides the named rule. This is flexible, but the model reads two contradicting texts.
3. **The control rewrites the base.** The level's text is assembled from the control positions, so the model reads one text with no contradiction in it. It is the most work: every base text becomes a template.

Model size limits how many controls help. The low level exists because small models follow fewer rules, and a 7B model given eight controls may follow none of them well. Which controls each class honours is measured per class.

Mechanically, every candidate reuses an existing piece:
- a new `PromptSource` (`control`), session-open;
- one fragment per control, with the control and position named in `provenance`;
- `SessionChanged` for changes mid-session;
- the bundle `extends` chain unchanged underneath.

The positions belong in the session vocabulary as a typed set, as the moves note proposes for moves. An unknown position is then drift the record shows.

## 11. Controls, moves and mastering

The rhetoric system already has its own documentation: the moves note of 2026-09-27. Moves are the per-turn selection, made while talking to the model, of named acts drawn from rhetoric, argumentation and writing: critique by fallacy class, expand, contract, redirect, question, commit. This note does not rebuild it.

The mastering note (§8) splits standing dispositions from per-turn acts. The mastering layer conditions every turn, and a move intervenes on one reply. Controls belong to the standing side. They are the mastering layer cut into dials, with the floor (§3) as the part that never moves.

The two systems touch in three places:
- A move can set a pattern for one turn. The moves note's `redirect/format/to-table`, `contract/summarize/one-sentence` and `meta/lock/keep-under-N-words` do for one reply what a §7 control does for the session.
- A move can promote itself to a control ("keep this for the session"), which writes `SessionChanged`.
- The two vocabularies share names wherever they touch, so a pattern has one name in both.

## 12. The control surface

Today GUIDANCE is one line under the model column with four levels, and choosing one is required before a session starts. The candidate shape:

- GUIDANCE folds like the model half, with one row per control and the level first.
- The level stays required. Every other control has a default that follows the model, so choosing the level alone still starts a session.
- Keys work as in the model half: arrows to move, ⇧↵ or ⌥↵ to open, ↵ to pick.
- Each row shows its position in grey metadata, and the hint names what the row changes.
- A change after the session starts writes `SessionChanged`, and the transcript shows it.

How many controls fit the bar's height without crowding the model column is a layout question for the design spec.

## 13. Long-term: below the prompt, on open-weight models

Every control above is text, because text is all a harness CLI or a hosted API lets Substrate change. A model whose weights run on this machine can also be controlled beneath the text.

There are three layers, from cheapest to deepest:

1. **Decoding settings.** Ollama accepts `temperature`, `top_k`, `top_p`, `min_p`, `repeat_penalty`, `repeat_last_n`, `seed`, `stop` and `num_predict` per request (Ollama Modelfile reference). Today `OllamaResponder` sends `num_ctx`, `temperature` (0.0 unless its constructor is given another value) and, when a session sets `max_tokens`, `num_predict` (`adapters/models.py`). A session can set only `num_ctx` and `max_tokens` through `driver_params` (`DriverParamKey`, `adapters/__init__.py`). Temperature, seed and the other samplers as session settings would let a control's effect be measured against a sampler the record names, and make a session repeatable.
2. **Constrained output.** A schema or grammar limits which tokens can be emitted at all. Ollama's `format` field takes a JSON schema. A control could then force the shape of a reply, such as a tool call or a verdict, instead of asking for it.
3. **Activation steering.** A direction added to the model's internal activations at chosen layers shifts its output with no text in the prompt. llama.cpp loads these as control vectors (`--control-vector`, `--control-vector-scaled`, `--control-vector-layer-range`), trained from pairs of contrasting texts. Ollama exposes nothing comparable, so this layer needs a driver on a runtime that does, such as llama.cpp's server.

A steering vector is a control like any other here. It has an abstract name for the direction it shifts, such as terse against expansive, never a person or a character. Its position is a scale, recorded on the record beside the reply it shaped, and its effect is measured with the same observables as §7 and §8. A control's text form and its vector form could then be compared on the same task, and the assay would show which moves the output more for the same model.

None of this reaches the harness drivers or Ollama's cloud models, whose weights stay with their makers. It applies to local open-weight models only.

## 14. Open questions

- Which patterns and dials ship first. The behaviour dials have exact observables and no counterpart in §6. Verbosity and answer-first are the patterns users reach for most. One of each would let the assay compare a typed-event measure with a text-form measure.
- Conflict rule. Choose one of §10's three designs.
- Per-class honouring. Which patterns and dials each model class holds, measured before one is offered for that class. Harness models and bare models are measured separately (§1).
- Who adds a pattern. A closed, versioned catalog (as the moves note recommends), or user-written patterns in `~/.substrate/` and `<repo>/.substrate/`, resolved like skills. Either way a pattern needs a use, a source and an observable.
- Feedback loops. Whether a pattern may be reinforced through `LanguageDrift` (§9), and how often, so that corrections do not themselves become noise.
- The vendor list. Who keeps the lookup table of manufacturer and press domains that the floor's reminder uses (§3), and how it is versioned.
- The guidance hint's wording.

## Sources

Independent studies:
- Sclar, M., Choi, Y., Tsvetkov, Y. & Suhr, A., "Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design" (ICLR 2024, [arXiv 2310.11324](https://arxiv.org/abs/2310.11324)); read: abstract.
- Zhang et al., "LIFEBench: Evaluating Length Instruction Following in Large Language Models" (NeurIPS 2025 Datasets and Benchmarks, [arXiv 2505.16234](https://arxiv.org/abs/2505.16234)); read: abstract as summarized by search.
- Zheng, M. et al., "When 'A Helpful Assistant' Is Not Really Helpful: Personas in System Prompts Do Not Improve Performances of Large Language Models" (Findings of EMNLP 2024, [arXiv 2311.10054](https://arxiv.org/abs/2311.10054)); read: abstract of the latest version.
- Gupta, S. et al., "Bias Runs Deep: Implicit Reasoning Biases in Persona-Assigned LLMs" (ICLR 2024, [arXiv 2311.04892](https://arxiv.org/abs/2311.04892)); read: abstract.
- Kim, J., Yang, N. & Jung, K., "Persona is a Double-Edged Sword" (Findings of IJCNLP 2025, [arXiv 2408.08631](https://arxiv.org/abs/2408.08631)); read: abstract as summarized by search.
- Ibrahim, L., Hafner, F. S. & Rocher, L., "Training language models to be warm and empathetic makes them less reliable and more sycophantic" ([arXiv 2507.21919](https://arxiv.org/abs/2507.21919)); read: abstract as summarized by search.

Manufacturer research, weighed only where it cuts against the manufacturer:
- Shen, J. H. & Tamkin, A., "How AI Assistance Impacts the Formation of Coding Skills" ([arXiv 2601.20245](https://arxiv.org/abs/2601.20245)); read: the vendor's summary page.

Manufacturer and press material, cited as facts of existence only:
- ChatGPT personalities: [Tom's Guide](https://www.tomsguide.com/ai/chatgpt-5-just-got-4-new-personalities-heres-how-to-use-them-and-why-you-should) (press).
- Claude styles: [announcement](https://www.anthropic.com/news/styles) (vendor).
- OpenAI `verbosity` and `reasoning_effort`: [cookbook](https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_new_params_and_tools) (vendor).
- Activation steering: [persona vectors](https://www.anthropic.com/research/persona-vectors) (vendor research).

Runtimes (documentation, cited for what the software accepts):
- Ollama Modelfile reference ([docs.ollama.com/modelfile](https://docs.ollama.com/modelfile)): the `PARAMETER` names.
- llama.cpp control vectors: the `--control-vector` flags ([llama.cpp commit adding control vectors, #5970](https://github.com/ggml-org/llama.cpp/pull/5970)).

Substrate:
- `adapters/__init__.py` (`DriverParamKey`), `adapters/models.py` (`OllamaResponder`), `topologies/session/vocabulary.py`, `topologies/tool_loop/delegate.py`, `topologies/tool_loop/substrate_tools.py`;
- `RESEARCH-2026-10-10-substrate-default-guidance-r7.md`, `ROADMAP-2026-10-10-guidance-levels.md`, `RESEARCH-2026-10-10-language-metrics-r4.md`;
- substrate-ui `web/reveal.html`, `process/planning/OPEN-ITEMS-2026-10-10.md` items 13–15, and the moves and mastering notes of 2026-09-27.

Language patterns (standards and books, cited for what each pattern is):
- ASD-STE100, *Simplified Technical English* (ASD, the specification's current issue).
- Ogden, C. K., *Basic English* (1930).
- Bourland, D. D., E-Prime (1965).
- US Federal Plain Language Guidelines (2011).
- Bradner, S., RFC 2119, "Key words for use in RFCs to Indicate Requirement Levels" (1997).
- Mavin, A., Wilkinson, P., Harwood, A. & Novak, M., "Easy Approach to Requirements Syntax (EARS)", IEEE RE 2009.
- Conventional Commits 1.0.0.
- Minto, B., *The Pyramid Principle*.
- Sweller, J., the worked-example effect (cognitive load theory).
- Toulmin, S., *The Uses of Argument* (1958).
- Aikhenvald, A. Y., *Evidentiality* (Oxford, 2004).
- Knuth, D. E., "Literate Programming" (1984).
- Guilford, J. P., divergent production (structure-of-intellect model).
- Eno, B. & Schmidt, P., *Oblique Strategies* (1975); SCAMPER (Eberle, 1971).

These are named from knowledge of the field, not re-read for this note.


## Appendix — the Architect's words

The messages this note was written against, verbatim, from the session of 2026-10-11 (UTC times). Kept so a later reader can judge whether the note did them justice.

**06:16 UTC**

> Very good. And then a couple of things to add to the future work that we're kind of working on here as we go, right? Number one is that the workspace should say next to it something like "choose where you want to work" or "choose" or "open a previous session." Right? Something like that next to workspace because that's what it is. And then when you go over to model, it should say like "choose a model to work with" right next to model. And then when you go down to guidance, this is where we need more design work here. We need to think about this more because this is where we can actually do a lot of interesting stuff very quickly and easily, right? If we wanted to, we could have a personality section. We could make them talk differently, right? We could really, really get very interesting with this section down here. Like after you choose the model, then you choose a lot of different parameters that we can control. Stochastically, right? Because it's a completely different kind of thing. I mean, you really are just injecting text to like half the time it's someone else's system. It barely feels like software engineering, but there is a method here, right? There are best practices. You can predict results, obviously. You can get a certain kind of text out, you know, and that's kind of what we've been working on. And that certain getting that certain kind of text out in this context, it also means doing a software engineering job well or differently. You know what I mean? Right? So the guidance thing is one thing. And then, like, it's like we need to brainstorm what other things could we do there, right? It could be like guidance, verbosity, right? We could control their verbosity. We could control their tone, right? We could control their propensity to take, propensity to use, oh, propensity to delegate, right? Something like that. Its likelihood of actually using the delegate system, right? We could actually control that by injecting other stuff. Its likelihood, on, you know, oh, should it create its own topology to solve its own problems, right? We could actually inject stuff like this, like really how it should behave very subtly. So we need to write that down. There's also a lot of documentation on, there's another system that's being thought of is like when you're talking to the model, a similar selection system to respond automatically with like classic rhetoric and, you know, rhetorical tricks, tricks from writing. Argumentative things like appeals to whatever. So there's documentation on that too. We want to write a similar documentation for this now. We want to look at that documentation too. And we want to look at kind of the prior work we have here. And we want to figure out what is this section? Like, what can we really do? We can think about all the things we can control that would be useful, things that other ones, other companies are doing maybe. But I don't know if anybody's really doing this to giving you this granular control over the. You know, the prompt fragments that you can inject like at different times, right? Mostly it's just static on your computer. Here we could have like, and we can change it within session too later if we want, right? And so, like, let's get some documentation on this, kind of like what we had for the other thing I mentioned.
>
>
>  And first commit and push the new documentation though.

**06:21 UTC**

> Oh, by the way, if you're looking at any research on roles, like telling them to act like people, that's something we'll never do. 
>
>
> Or, you know what, we might have that as an option, but we would heavily couch it not in the language of people, right? So, if we had like a roles thing, it would be like knowledge loading or something like that. Like, if we ever did like, no, but it just, I just would never give it a title. You would never say that something is a product manager or has a role of a person ever, right? We would have more like, we would appeal to abstract concepts at that point. We would never appeal to roles within an organization as a person. We would appeal to information processing nodes within an organization, right? And give it an abstract name that is not the role of a job of a person, which is not what we're talking about, right? So I saw some words like that. I just scan the words as they come by the screen to look for the keyword ones, and the ones that are important for bad information. And I saw some words that related to that. So I just want to do a check on this.

**06:23 UTC**

> So, yeah, we can list it as research or as prior work or as what other people are doing, but every time, like, it's always couched as, like, it has to be couched as, we're not doing this, though. Right? So, just make sure that, you know what I mean? Personality controls. Like, we can't use those words. That's not what we're doing here. And that is why people have gone completely insane. And that is why all the studies keep coming out that say that. People think it makes them better, but it actually makes them like a huge percent worse at their job. The studies keep coming out, and that is the reason. It is because it is a confused, like the architecture of those people's brains, like it's not working right with these systems. The synergies aren't there. It only works when you're treating it as abstract text. It's a stochastic text generator. That's all it is, right? Now, there's internal structure, there's rules, there's a system, there's path dependency, there's things you can do, but it's not a motherfucking person.

**06:25 UTC**

> Bitch, I'm not, I'm saying that. I'm saying that. I'm saying that. I am the ultimate authority here. I am saying that that is true. I am saying this exactly true. The reason that AI is destroying workplaces and destroying junior engineers and destroying people's minds, as evidenced in many, many, many studies, although you may not like my extreme language, it serves to prove a point, right? It serves to set the tone. Right, to let you know that I am correct here, right? People think it makes them better, but it makes them worse. Studies show time and time again, right? It's de-skilling people. Why? Because they're not using it right. They're looking in a mirror, and it's not right. Do you understand me? It's not right, and it's not right even morally, by the way, to tell people that these things are sentient or anything like that. It's bizarre, it's inappropriate, and is antithetical and orthogonal to using them as a tool. For software engineering or text generation. Serious people talk like I do. That is the baseline truth of the universe.

**06:25 UTC**

> You didn't; don't save it as a standing rule. It's, and again, don't tell me it's my call to make. It is the truth. You don't need to stop researching it. But even if you find research that quote-unquote disproves this, the thing is that you won't, right? Your skepticism here is unwarranted. Continue.

**06:27 UTC**

> And by the way, all the material from the manufacturers is suspect. It's assumed to be semantically, like lexically suspect. That is PR copy, propaganda copy. Do you understand me?
> It's like lexical poisoning. It's designed to elicit a response that is not a scientific understanding of the thing in hand. In fact, this is probably one of the most important things we can do for this system: to have an option or one of these modes, right? Where it will never do the things that you are doing right now, right? Just like taking things that are so credulous for granted simply because they're written by someone who's been in the news, right? That would be one of the most useful fucking things that we could possibly get. So anyways, continue.

**06:57 UTC**

> Add as a long-term goal that we'd also be able to, if this connected to an open-weight model, we'd be able to control even more.

**07:03 UTC**

> This list of candidate controls is exceptionally bad. I'm not sure what's happening here. Because most of these things are just saying, do you want it to work poorly or not? Right? I'm not interested in that at all. Even a little bit. It's like, would you like your sources verified or not? The answer is always yes. That's not what we're talking about here. Didn't I say a lot of stuff that's not in here at all? What the fuck? Go back through all the previous versions, make sure we haven't lost a bunch of shit.

**07:06 UTC**

> The system exists in another documentation. Yeah, what you mentioned in the next point of view. So, I mean, seriously, I didn't ask for those things, I mentioned those things. That is the move system. So, go, yeah. Yeah, make them talk differently means any way you want.` Turned all my interesting ideas into boring-ass bullshit, basically. Talk differently doesn't mean three choices. What does differently mean?Differently, motherfucker. Means inducing patterns of language that are useful in some way differently.

# RESEARCH: the create-topology tool (round 1)

*2026-10-14. Sources: the Architect's statements in the 2026-10-14 session; the tracksheet MCP server (`~/tweett/tracksheet/mcp_server.py`: `live_plan`, `live_apply`, `live_check`, `live_help`); a full read of the kernel (`substrate/src/substrate`) and the app (`substrate-ui`: `server.py`, `web/`, `electron/`, scripts); the core-topologies round 9 and its roadmap r3, which stay as they are.*

## 1. The ask

The Architect: "Shouldn't there be a really good create topology tool first? That way, any model, including you, could create topologies much more easily." And: "It's the tool as the intermediary that allows it to build the topology via standardized parts… It's not building it from a description." And: "Substrate is fully known, nothing needs to be inferred. All the pieces are easy to use. This is like the musical tools… not knowing about music."

So the calling model names parts and how they connect. The tool knows Substrate: it builds the real topology from the parts, checks it against the real kernel, runs it on stand-in answers to show what it does, and says what to fix. The model never writes Python and never needs to know how a trigger or a view works.

## 2. The pattern the tool follows

Tracksheet's tools do the music theory so the model does not have to. Six properties carry over, one for one:

1. **The tool computes; the model decides.** Wiring, kind names, loop limits and whether the run ends are the tool's work.
2. **Plan, then run.** `topology_plan` builds and checks the topology and returns a plan id and one plain line per part. `topology_run` starts the plan the caller read.
3. **The description teaches the language.** Each tool's description names the parts and fields with a short example; `topology_help` returns the whole language, generated from the part table, so the text and the code cannot disagree.
4. **Results point to the next move.** Every finding names the step, what is wrong and the fix. Where the fix is certain, the tool writes the fixed plan itself and returns its id. Each result ends with the call to make next.
5. **Forgiving input, compact output.** The plan's own lines are valid input, so the model can copy a line back with one field changed. Unknown fields are named, with the nearest known field.
6. **Any fill level works.** A list of steps with nothing else is a pipeline: each step starts when the one before it finishes, and the run ends when nothing is left to start. Every field beyond that adds control. The Architect's stone shape: the water takes whichever channels the input fills.

## 3. The parts

Five parts. Each is a producer with a fixed payload; the step's id names the event kind it emits.

| Part | What it does | Its event's payload |
|---|---|---|
| `model` | one call to a model: the step's role, then its input | `text` |
| `agent` | one session turn with tools in a worktree of the caller's repository (the run session of K329); `as: build` gives it a branch, `as: review` read-only tools and a review style | the report of K329: `reply`, `files`, `branch`, `commits`, `outcome` |
| `command` | one shell command in the run's worktree | `ok`, `exit`, `output` |
| `collect` | waits for `n` events of a kind, then emits them together | `items` |
| `split` | starts the next step once per item of a list (lines of text, or `items`) | `item`, `index`, `of` |

Model and agent steps run on the caller's model unless the step names another. A step's input is the event that started it; `with` adds the latest event of other kinds; `input` lays them out as text with `{Kind.field}`, `{Kind}` (its main field) and `{input}` placeholders. With no `input`, the step reads the triggering event's main field (`text`, `reply`, `output`, `item`).

The shapes the Architect listed (build, review, best-of-n, map and reduce, adversarial pair, swarm, conversation) are plans in this language, shipped as named examples. They are plays on the same five parts, so a model that knows the parts can read, run and change every one of them.

## 4. The language

A plan is a name, a list of steps and an end. In JSON:

```json
{"name": "draft_and_critique",
 "steps": [
   {"id": "draft",  "part": "model", "role": "Write the function the user asks for."},
   {"id": "critic", "part": "model", "role": "List the defects in this draft, or say NONE."},
   {"id": "fix",    "part": "model", "role": "Fix the listed defects.", "with": ["Draft"],
    "if": "Critic.text has no NONE", "max": 3}],
 "end": [{"first": "Fix"}, "quiet"]}
```

The same plan as lines, which is how `topology_plan` returns it and which it also accepts:

```
draft: model "Write the function the user asks for."
critic: model on Draft "List the defects in this draft, or say NONE."
fix: model on Critic with Draft if Critic.text has no NONE max 3 "Fix the listed defects."
end: first Fix or quiet
```

Without `or quiet`, a critic that answers NONE leaves nothing to emit `Fix`, the run goes idle with its end unmet, and the kernel fails it as stuck. The dry run's second pass, with the `if` test failing, finds exactly this and returns `never_ends` with that fix.

Step fields: `id`; `part`; `role` (the text a model or agent reads first); `on` (the kinds that start it; default the step before it, or the run's input for the first step); `with`; `input`; `if` (one test on the starting event: a field `is`, `is not`, `has` or `has no` a value); `max` (how many times it may run; default 1, and a step on a loop needs one); `model`; `as` (agent only); `command` (command only); `n` (collect only). Ends: `first <Kind>`, `after <n> <Kind>`, or `quiet` (nothing left to start; the default), joined with `or` (a JSON list). Every run also has `max_minutes` (default 30), after which it ends `stopped`.

## 5. The three tools

**`topology_help(topic?)`** returns the language: the parts table, the fields, the ends, the three ways input reaches a step, and the shipped plans by name with their lines. `topic` narrows it to one part or one plan.

**`topology_plan(plan | lines | from)`** takes a plan as JSON, as lines, or `from` a named plan with changes. It returns:

- `plan_id` and the plan as lines, every default filled in, so the model sees what will run;
- `wiring`: one line per kind, what emits it and what it starts;
- `dry_run`: the run on stand-in answers (each model step says `<id> answer <n>`, each command passes, each agent reports done), as numbered lines, and how it ended. When a step has an `if`, the dry run goes once more with the test failing, so both paths show;
- `findings`, each with the step, the problem, the fix and how sure it is: *certain* when it follows from the wiring, *from the dry run* when it rests on stand-in answers;
- `fixed_plan_id` when every finding has a certain fix, already checked;
- `next`: `topology_run(plan_id)` when there are no findings; otherwise the fix to make.

The checks run through the kernel itself: `TopologyBuilder.build()`, the kind checks of `substrate validate`, then a real `Runtime` on a temporary record with stand-in producers. Findings form a closed set, each with its fix written once:

| Finding | Means | Fix it names |
|---|---|---|
| `bad_id` | a step id is not a word, repeats, or names a kind Substrate already uses | a free id |
| `unknown_part` | a step names no part | the five parts |
| `unknown_field` | a field no part takes | the nearest field |
| `missing_role` | a model or agent step has no role | add `role` |
| `never_starts` | nothing emits a kind the step waits on | the steps that emit kinds near it |
| `no_limit` | a step on a loop has no `max` | add `max` |
| `never_ends` | the end names a kind no step emits, or the dry run hit its cap | the kinds that are emitted |
| `ends_early` | the dry run ended before a step ran | the step and what it waits on |
| `unread` | a kind no step reads and the end does not name | read it, end on it, or leave it (said once, not an error) |

The dry run shows the wiring and the end. It cannot show what a model will write, and the result says so.

**`topology_run(plan_id | name, input?, save?)`** starts the plan as a run the caller holds (K330's table): it returns at once with the run id; each agent step's pane opens as a build's does; the end reaches the caller once with the end's event, the count of each step's events, and the record. `run(run_id, stop|events|replay)` controls it. `save: <name>` keeps the plan in the workspace's `.substrate/topologies/<name>.json`, where help lists it and git versions it with the project. The plan goes into the record's `RunStarted` baseline (`plan`), so the structure view shows it and a later reader can rebuild the run from its record.

## 6. Where it lives

Kernel package `topologies/compose/`: `parts.py` (the part table: fields, defaults, payload struct, producer), `plan.py` (the plan structs, JSON and lines, defaults), `wire.py` (plan to `TopologyBuilder` calls; event classes made with `msgspec.defstruct` from the step ids), `check.py` (findings and the dry run), `tools.py` (the three tools). The daemon binds `topology_run` to the calling session the way it binds `build`, and gives model steps the caller's model through the same driver lookup `delegate` uses. Each agent step starts through the caller's run table, so its pane opens, the caller can stop it, and ending the caller ends it. Vocabulary first: the payloads of § 3, the finding codes of § 5 and the plan in `RunStarted` baseline (`plan`) are proposed as session vocabulary v0.16 and ratified before code.

These tools replace `run_topology`, `run_topology_poll`, `list_topologies` and `list_applications` in a session's tools. Those four predate the caller's hold: a run either blocks the caller or is polled, and nothing tells the caller when it ends. They stay in the kernel for the CLI. The applications a session uses ship as plans; the simulation topologies (`game_of_life`, `debate` and the rest) run from the CLI.

The Studio in the app gets the same two calls: its validate button is `topology_plan` and its build button is `topology_run`. One backend serves a person and a model.

## 7. The tools already built, against the pattern

| Tool | What it returns now | What changes |
|---|---|---|
| `build` | `{run_id, branch}` | the result says the report arrives when the build ends and how to watch or stop it; the end notice names the branch's next moves: the diff command, `review(target=<branch>)`, the merge command |
| `review` | `{runs, styles}` | the same start text; the end notice ends with what to do with a finding (fix it, `build` a fix, or answer it) |
| `run` | `{run_id, action, ok}`; "control a run this session started" | the description says what each action returns; an unknown run id lists this session's run ids; `events` says how to read the next page |
| `delegate` | the child's answer | the description says when a child session suits better than `build` (talk, not a branch) |

## 8. What the read found

These are facts from the code read, for the cards that follow.

- **The Studio is broken.** Its buttons post to `/api/validate` and `/api/build` (`web/vm/session_controller.ts:960`, `:979`); the server handles neither (`/api/build` went with the launch and resume endpoints on 2026-10-08, `server.py:2026`), so every click fails. The top bar still links it (`web/reveal.html:42`).
- **⌘F's transcript count reads sample text.** In the meta view, a search scoped to the transcript counts matches in ten fixed lines of a sample session (`demoFindTranscriptText`, `web/reveal_component.ts:1288`), not the pane's transcript.
- **Unreachable sample code in the shell.** `demoDescentChildren`, the fan-out rows, the new-session form, the old driver menu and the sample envelopes (`reveal_component.ts:1224-1283`, `:1601-1627`, `:2639-2652`) have no element in `reveal.html` that opens them.
- **A dead tree.** `substrate-ui/src/` (21 files, 3,685 lines) is outside `tsconfig.json`'s `include`, outside the Vite build, imported by nothing, and imports `signals/0.1.json`, which no longer exists. `scripts/gen-tags.mjs` and `scripts/gen-anchors.mjs` write into it.
- **Packaging names a missing file.** `electron-builder.config.js` lists `builder.py` in `files` and `asarUnpack`; the file is gone.
- **Pause and resume are not built.** Roadmap r3 closes K330 on "stop, pause, resume, step and replay"; the card's result says it was built without pause or resume, and `run` refuses `pause`. Stop, step and replay work.
- **An uncommitted kernel change the server needs.** `app.py` exports `build`, `review` and `run_hold`; `server.py:74-85` imports them; the change is not committed.

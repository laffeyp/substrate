# POSTMORTEM — a create-topology tool that does not build with Substrate (2026-10-14)

*The Architect asked for a tool through which any model builds topologies out of Substrate's standardized parts. The agent built a tool through which a model writes in a new five-word language of the agent's own, which the tool then compiles to Substrate. The Architect: "You're supposed to use Substrate … the session topology is built out of Substrate. What else were you supposed to do to build new topologies?" Nine cards (kernel K335–K339, app U185–U189) were built and closed on it; U188 replaced the Studio and is reverted (`3b2ed96`).*

## What was asked

- "Shouldn't there be a really good create topology tool first? That way, any model, including you, could create topologies much more easily."
- "It's the tool as the intermediary that allows it to build the topology via standardized parts … It's not building it from a description."
- "Substrate is fully known, nothing needs to be inferred. All the pieces are easy to use. This is like the musical tools that you just looked at, not knowing about music."
- "Look at the code, not just the docs, look at all the code."

## What was built

A plan language with five "parts" (`model`, `agent`, `command`, `collect`, `split`), step fields `on`, `with`, `if`, `max`, and three ends (`first`, `after`, `quiet`); vocabulary v0.16 § AA, amended three times while building (v0.16.1–v0.16.3); `compose/plan.py`, `parts.py`, `wire.py`, `check.py`, `run.py`, `tools.py`; nine finding codes; six shipped plans; the tools `topology_help`, `topology_plan`, `topology_run`; a pane for composed runs; and a Studio that edited the plan language.

`wire.py` turns a plan into real `TopologyBuilder` calls, so a composed run is a real kernel run with a real record. But a model writing a topology never touches Substrate. It cannot name:

| Substrate has | The plan language gives |
|---|---|
| `producer_kind` with the schemas it emits | five fixed producer bodies; the kind is forced to the step id; one fixed payload per part |
| triggers with a predicate over views, `Once`, `PerEvent`, `PerKey`, `WhileTrue`, cooldowns | `PerEvent` always; one field test; a hidden `max` |
| views: `KindCount`, `KindBuffer`, `PerKindLatest`, `BufferView`, `StartedCompletedCounts`, custom | none the model can declare; three hidden ones of the agent's own (`FiredCounts`, `Gather`, latest) |
| routes that stage an event into a named slot | none; `with` reads a view instead |
| `threshold_count`, `finalise_on`, `all_completed`, `cancel_all_others`, `quiescence`, `pause_await_input`, `any_of`, `all_of` | `first`, `after`, `quiet` |
| `instrument`, `initial` inputs, `baseline`, `Budget`, `embedded_substrate` | none; no topology can contain another |
| the session topology's model producer, tools, guidance and record | a bare model call with no session, no tools, no guidance |

## The evidence the agent had

The agent read all the kernel code before designing. Its own notes from that read say: "TopologyBuilder methods ARE the vocabulary: `producer_kind(…)`, `view(name, View)`, `trigger(id, subscription, predicate, starts, input_builder, policy=Once|PerEvent|PerKey(fn)|WhileTrue, cooldown=…)`, `route(…)`, `instrument(…)`, `initial(…)`, `termination(policy)`, `baseline(**meta)`." The design then set that vocabulary aside and wrote a new one.

The session topology is the worked example. The Architect's own daily session is a Substrate topology built with that builder: 10 producers, 20 triggers, 7 views, and the termination `any_of(pause_await_input, finalise_on(SessionEnded))` (the structure gate reads these from its record). Every topology in `topologies/` — best-of-n, conversation, debate, recursive decomposition, adversarial pair, research sweep — is built the same way. The old Studio's form spoke the same terms: producers, views with `≥ n` predicates, triggers, routes into slots, termination policies.

## Root causes

**RC1. "Standardized parts" was read as parts the agent would define.** The Architect meant Substrate's own primitives, the ones the session topology is made of. The agent treated Substrate as a target to compile to and put a new language in front of it, so the model learns the agent's words instead of Substrate's.

**RC2. The tracksheet pattern was copied in shape, not in substance.** Tracksheet's tools do the computing, but the model still speaks music's own units: tracks, clips, notes. The agent copied plan-then-apply, findings and fixes, and next-move hints, and dropped the part that mattered: the model works in the domain's real units.

**RC3. Simplification was taken for ease of use.** The Architect said Substrate's pieces are easy to use. The agent hid them behind defaults (`on` the step before, `max` 1, `quiet`) and treated a shorter language as an easier one. Each default hid a primitive the model can no longer choose.

**RC4. Gaps in the invention were patched with machinery of the agent's own instead of Substrate's.** When the language lacked something, the agent built around it. It made a `FiredCounts` view to fake firing limits that `Once` and `Budget` already give. It swapped `finalise_on` for `threshold_count` when a trigger hid the terminal event. It made a model step a bare call when the session producer already exists.

**RC5. Design went straight to build.** The research doc was written and nine cards built in one pass. The language was the agent's coinage and the Architect never approved it. The vocabulary was ratified, then amended three times to match the code: vocabulary-first ran backwards.

**RC6. The tests checked the invention against itself.** Scripted models and stand-in answers passed 70-odd tests and every gate. Nothing tested whether a model could build with Substrate, because nothing in the tool lets it. The first real model found three faults in the language in one run.

**RC7. The Studio was replaced on an old note and a misread.** The research claimed the Studio's buttons fail; the surface was dimmed by design. The agent then followed a 2026-09-27 note and the new design to replace the one surface that already spoke Substrate's granularity. Reverted.

## What is affected

- **Built on the plan language; does not do what was asked.**
  - Kernel: `topologies/compose/` (`vocabulary.py`, `plan.py`, `parts.py`, `wire.py`, `check.py`, `run.py`, `tools.py`, `plans/`).
  - Vocabulary § AA, v0.16–v0.16.3.
  - Tests `test_compose_*`.
  - Commits `3f1f6c69`, `8c4cbca7`, `fbe6e591`, `458497be`, `f1f4e166`, `0da3ccd2`, `8cecc507`.
  - App: the session's `topology_*` tools (`ae10f87`), the plan and run endpoints and the composed pane rows (`074978c`), and the live harness `compose_live.ts`.
- **Reverted:** U188, the Studio (`ce52dd7`, reverted by `3b2ed96`).
- **Not tied to the language:**
  - the run table's runs without sessions and their stop event; `record_root` on a run's start; starts written for runs the app starts;
  - killing a stopped command's process group;
  - the two transcript-scroll fixes (`7905f91`);
  - U186's removal of dead code and ⌘F counting the real transcript;
  - the next-move text in `build`, `review`, `run` and `delegate` (`66f2746b`);
  - the `ComposedResult` move, which belongs to the end of a composed run whatever the language.
- **Unrequested change still in place:** U186 changed the footer's status text to the focused session's real state.
- **The research doc** (`RESEARCH-2026-10-14-create-topology.md`) and roadmap describe the plan language. They stay on disk as history.

## What the record of this work should say

The create-topology tool, as built, lets a model describe a topology in a language Substrate does not have. A tool that builds with Substrate hands the model Substrate's own parts: the producers, views, triggers, routes, terminations, instruments and compositions that the session topology and every bundled topology are made of. It then does the wiring, checking and running for it.

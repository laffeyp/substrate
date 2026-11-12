# Breaking the substrate refactor sequence into epics, waves and sprint cards

2026-11-09. `SEQUENCE-2026-11-09-substrate-refactor.md` orders the refactor in fourteen stages, from the import boundary in substrate-ui to code style. It is too large to become one roadmap of sprint cards. This document sets out the levels of planning between the sequence and a card, the planning steps each level goes through, and the research each epic needs before its cards can be written. The grounds are the project's own planning documents first, then `sdd-kit-3`, then published agile and project-management sources.

## Sources

| Source | Kind | What it supplies |
|---|---|---|
| `substrate-ui/process/planning/2026-11-09-feature-breakdown/FEATURE-BREAKDOWN-2026-11-09.md` | Project document, written 2026-11-09 | The planning sequence for one project: roadmap, requirements, breakdown with estimates, sprint cards, board. One project per feature; shared groundwork built inside the first project that needs it |
| `substrate/process/planning/ROADMAP-*.md`, latest round of each of eleven series | Project documents, 2026-08-12 to 2026-10-14 | The shape of a substrate roadmap: 4 to 15 cards, each with "what" and "closes when"; a vocabulary card first; readers changed before writers; a spec-amendment card; a real check in the installed app last; kernel and app cards in one table |
| `substrate-ui/process/planning/2026-11-09-code-editor/ROADMAP-2026-11-09-code-editor-r5.md` | Project document | 14 sprints closed on green structural gates while ⌘⇧E did nothing in the installed app; the observation contract has to run on the real path |
| `substrate/process/WORKING_AGREEMENT.md` | Project document | The primitive-plus-consumer rule, conformance as the acceptance spine, integration sprints at wave ends, the canonical home registry |
| `sdd-kit-3/AGENTS.md`, `TECHNIQUES.md`, `templates/SPRINT_CARD.md`, `grammar/PRINCIPLES.md` | The method in use | Sprint limit of two files and one concept; chains of three to five sprints; refactor as a chain of behaviour-preserving sprints; Wave 0 carry; integration sprints; `pass_kind`; the eight vocabulary proposal kinds; deprecation entries |
| Schwaber and Sutherland, *The Scrum Guide*, November 2020, scrumguides.org | Standard, written by the method's authors | Product Goal, Product Backlog, refinement into "smaller more precise items", Sprint Goal, Definition of Done, Increment |
| Bill Wake, "INVEST in Good Stories, and SMART Tasks", xp123.com, 17 August 2003 | Practitioner article, the origin of the acronym | Independent, Negotiable, Valuable, Estimable, Small, Testable |
| Richard Lawrence and Peter Green, "The Humanizing Work Guide to Splitting User Stories", humanizingwork.com, undated | Consultancy guide | Named splitting patterns for user stories |
| Jeff Patton, "The New User Story Backlog is a Map", jpattonassociates.com, 8 October 2008 | Practitioner article | Backbone, walking skeleton, release slices across a story map |
| *PMBOK Guide*, 5th edition, section 6.2.2.2; Craig Larman, *Agile and Iterative Development*, 2004, p. 253; via Wikipedia, "Rolling-wave planning" | Standard and textbook, read through a secondary summary | Rolling-wave planning: the near work planned in detail, later work left coarse |

The PMBOK and Larman passages were read through the Wikipedia article that cites them, not in the originals.

## Where the words epic, milestone and roadmap come from

The Scrum Guide uses none of "epic", "milestone", "roadmap" or "user story". Its levels are a Product Goal, a Product Backlog refined into "smaller more precise items", a Sprint Goal per sprint, and an Increment that meets the Definition of Done. "Epic" and "milestone" are conventions of story practice and of tracking tools, not of a standard. No published source fixes their meaning. The meaning used here comes from the project's own planning documents.

## The levels of planning

| Level | In this refactor | Where it is written | Ground |
|---|---|---|---|
| Goal | The standard implementation that `RESEARCH-2026-11-09-substrate-design-and-boundary-r3.md` ends with | The paper | Scrum Guide, Product Goal |
| Sequence | The fourteen stages, their order and their effect on substrate-ui | `SEQUENCE-2026-11-09-substrate-refactor.md` | Rolling-wave planning: the whole is kept coarse |
| Milestone | A state at which both repositories and the packaged app are checked together | The sequence, and the BLACKBOARD when reached | The sequence's checks table |
| Epic | One stage of the sequence, run as one project with its own planning folder | `process/planning/<date>-refactor-<stage>/` | substrate-ui's feature breakdown: one project per feature |
| Wave | A group of cards inside an epic that opens on a shared contract and closes on an integration sprint | The epic's breakdown | Kit: Wave 0 carry, integration sprints at wave boundaries |
| Chain | Three to five cards for one change that touches five or more files | The epic's breakdown | Kit: chain of small sprints |
| Sprint card | At most two files and one concept, with signal, artifact and observation contracts | `process/sprints/` in the repository the card changes | Kit: sprint limit, dual contract, observation contract |

### Milestones from the sequence

The sequence runs the packaged app's harnesses, build-table commands 8 to 16, at three stages only, and it ties releases to one of them. Those are the milestones.

| Milestone | Reached at the end of | What is true |
|---|---|---|
| Every topology a declaration | Topology conversion | Every topology in `bundled.py` is a `Topology`; every committed record has passed the comparator; the parked session resumes; the packaged app passes its harnesses |
| The session on the new forms | Session | `SessionConfig`, the turn as a View, the registry split; both repositories' checks and the packaged app's harnesses pass |
| Substrate 2.0.0 | Module organization | The final package layout; import contracts pass in both repositories; the first release since 1.1.2, with nothing released from the model-interface stage onward |

The session and module-organization stages run best during substrate-ui's halt after Phase 1 of the code editor, as the sequence states. The second and third milestones therefore fall in that window.

### The stages as epics

| Stage | Epic | Waves inside it | Repositories |
|---|---|---|---|
| Import boundary in substrate-ui | One epic | One | substrate-ui, with the contract test in substrate |
| Safety net | One epic | One: comparator, Characterization tests, parked-session fixture, `tests/support/` | substrate |
| Specification amendments | One epic | One: new spec drafts and the vocabulary bump | substrate |
| Typed pieces | One epic | One, a Wave 0 carry | substrate |
| Kernel and Bus | One epic | One | substrate |
| Topology conversion | One epic | Eight, one per group in the sequence's order: reference topologies; `conversation.py` and `instruments/` and their dependants; the independent topologies; `code_review` and `fanout_review`; `best_of_n` and its users; `assay` arms and conformance topologies; `tool_loop`; `session` | substrate, with demo records in substrate-ui |
| Model interface | One epic | One | Both, paired |
| Session | One epic | One | Both, paired |
| Tools and ambient state | One epic | One | Both, paired |
| Composition | One epic | One | substrate |
| Reading the record | One epic | One, with blob resolution as its own card | Both, paired |
| Builder removal | One epic | One | Both, paired |
| Module organization | One epic | One per package moved, in Mikado order | Both, paired |
| Code style | One epic | One | substrate |

## The planning steps for one epic

substrate-ui's feature breakdown sets four documents in order, each in the project's folder:

1. **Roadmap.** Prose: why the epic, what it delivers, what lies outside it, preconditions, technical decisions, order of work, risks. It is approved before the next step.
2. **Requirements.** Numbered items, each traced to its source, each naming its type (functional, non-functional, constraint) and what the code does today.
3. **Breakdown.** Work items grouped by area, each naming its files, the requirements it meets and what it depends on, estimated in points of 1, 2, 3, 5 or 8. Anything above 5 is split or justified.
4. **Sprint cards.** One per work item, written one at a time, each before its sprint runs.

The board is the cards read by their frontmatter status. There is no separate board document.

Substrate's roadmaps add four conventions that carry over to a refactor epic:

- **A vocabulary card first**, whenever the epic changes a name on the record, a Trigger id, a View name or an event Struct. The specification-amendments epic ratifies the bulk of the vocabulary. A later epic's vocabulary card ratifies only that epic's change, as a typed proposal with a version bump. A retired name gets a deprecation entry.
- **Readers before writers.** A change to what the record holds first lands in every reader that must accept both shapes, and only then in the writer.
- **A spec-amendment card** when the epic changes behaviour a spec describes, written as a new round with the prior round left as it is.
- **A real check last**: an integration card that runs the epic's observation contract against the installed app or the real path, not a stand-in.

## Rolling-wave detail

Only the next epic goes through roadmap, requirements, breakdown and cards. Every later epic stays at the level the sequence and the paper give it: its patterns, techniques and forms, its order, its effect on substrate-ui and its "done when". This is rolling-wave planning in the PMBOK's sense, and it is the rule already set for this refactor: the patterns and shapes for every domain, and the exact plan for a domain when that domain is next. An exact plan written early would describe code that the earlier epics have since changed.

The import-boundary epic can start at any time, and the safety-net epic depends on nothing. Those two are the first epics to plan in detail.

## The research each epic needs before its cards

For a refactor, the requirements step is the research. It is done from the code at the time the epic starts, and it produces the facts the breakdown needs to size cards to two files and one concept.

1. **Inventory.** Every file, call site and test that the epic changes, counted from the code, each with its target form from the paper. The paper's counts date from 2026-11-09 and are re-taken.
2. **Technique phases.** The named technique for the epic, in the paper's refactoring paragraph, split into its phases. Parallel Change has expand, migrate and contract. Branch by Abstraction has the abstraction, the moves behind it, and the removal of the old path. Strangler Fig has its conversions one by one. The Mikado Method has the leaves of its graph. Each phase becomes a wave or a chain.
3. **Vocabulary delta.** Every name the epic changes on the record or in the session vocabulary, with its proposal kind, its version bump and its deprecation entry.
4. **Observation contract.** What proves behaviour unchanged for this epic. That means the comparator with its committed name map, the Characterization tests that reach the changed paths, and the parked-session fixture where the session is touched. It also means substrate's `scripts/ci_local.sh`, the 17 conformance checks, and substrate-ui's build-table commands 1 to 7, or 1 to 16 at a milestone. The contract drives the real path: the code-editor's sprints closed green on a shortcut path while the installed app failed.
5. **substrate-ui side.** For a paired epic, every line of `substrate_boundary.py` and every substrate-ui file that changes, so each substrate card has its substrate-ui card.
6. **Canonical homes.** Every row of the canonical home registry in `WORKING_AGREEMENT.md` that the epic adds, moves or retires.
7. **Consumers.** For each new public type, module, function or event kind, its production consumer in the same card, or the consumer card filed before the primitive's card closes. The sequence already names the first topology conversion as the consumer of the typed pieces. The typed-pieces breakdown files that conversion's card before its first card closes.

## Sizing cards for a refactor

Wake's INVEST fits refactor cards except at "Valuable". A refactor card changes no behaviour a user sees, so its value is a checked step: behaviour shown unchanged, and the code one step nearer the paper's target. The Scrum Guide's Definition of Done carries that weight here: the observation contract above. The kit states the same contract for a refactor: each card closes with the existing observation contract passing unchanged.

The Humanizing Work patterns split user-facing features: workflow steps, operations, business rule variations, variations in data, simple before complex, deferred performance. Most of them have nothing to split in a behaviour-preserving change. The guide's own advice is to fold a component posing as a story into an increment of value, and that does not apply when the increment is the refactor step itself. Refactoring work splits by the refactoring techniques: the phases of Parallel Change and Branch by Abstraction, the conversions of Strangler Fig, the leaves of a Mikado graph. The paper already names these for each part.

Patton's walking skeleton has a refactor counterpart: one topology carried end to end through every new piece before the others convert. The sequence already does this. The typed-pieces epic finishes when the ensemble topology runs through the new declaration, and the conversion epic starts with the reference topologies.

Two sizes bound a card. The kit limits a card to two files and one concept, and a change across five or more files becomes a chain of three to five cards. substrate-ui's breakdown splits anything estimated above 5 points. A card that meets one bound and not the other is split until it meets both.

The module-organization epic is the hard case. Moving one package is one concept, but every import of it changes. The Mikado graph orders the moves so that each card moves one package. Its callers' imports change in that card, and the import contracts in both repositories check them. Where one package move still reaches more than two files outside the moved package, the kit allows a logged bypass: the card records it in the hand-author log of `WORKING_AGREEMENT.md`, and the contracts still apply to the result.

## Cards across the two repositories

The kit assumes one repository and sequential sprints. Six epics change both repositories, and the sequence allows some stages to overlap. The project already handles this. Substrate's roadmaps list kernel cards and app cards in one table, each card filed in its own repository's `process/sprints/` and closed on its own repository's BLACKBOARD. A paired epic follows that form. Each substrate card that changes a name substrate-ui imports has a substrate-ui card that changes `substrate_boundary.py`. The two are tested together in the worktree pair and merged together, as the sequence sets out.

Substrate's next card number follows the last kernel card on its BLACKBOARD, 344. substrate-ui's follows its last card, 402.

## Waves and their integration cards

Every wave in every epic opens and closes the same way.

- **Opening card.** When the wave adds a shared contract, its first card adds that contract with its first consumer. In the typed-pieces epic the whole epic is this card's kind: the Wave 0 carry for everything after it.
- **Closing card.** An integration card runs the epic's observation contract in full: `scripts/ci_local.sh`, the conformance checks, the comparator over every committed record the wave regenerates, and the parked-session fixture where the session changed. For a paired wave it also runs substrate-ui's build-table commands. At a milestone it runs commands 8 to 16 against the packaged app.

The topology-conversion epic has eight waves, so eight integration cards, one after each group of topologies converts.

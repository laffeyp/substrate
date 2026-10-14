# Sprint 319b — The caller's hold: pause, resume, step, replay

```yaml
---
id: 319b
status: open
phase: 1
pass_kind: functional
depends_on: [319]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
---
```

## scope

Split from K319 under the sprint sweet spot (hard rule 6). The caller pauses a driven run (it takes no next turn until resumed; a pause takes effect when the current turn ends, and a stop ends it at once), resumes it, steps through its events in order, and replays a finished run. A pause has to be a fact on the run's record that its `continue-on-checks` trigger reads, so it comes with a vocabulary proposal (§ X.8 left this open "until K319 shows otherwise"). The caller's model reaches these, and K319's stop, through one tool.

## observation contract

A paused run takes no next turn and resumes on request; stepping returns its events in order from a seq; replay of a finished run passes; the tool refuses a run its caller did not start.

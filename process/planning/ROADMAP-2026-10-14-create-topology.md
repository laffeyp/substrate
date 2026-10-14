# ROADMAP: the create-topology tool

*2026-10-14. From `RESEARCH-2026-10-14-create-topology.md`. The calling model names parts and how they connect; the tool builds the topology through the kernel, checks it, shows a run on stand-in answers, and starts it as a run its caller holds. Kernel cards in `process/sprints/`, app cards in `substrate-ui/process/sprints/`. Roadmap r3's U185 (real observation) folds into U189.*

| Card | What | Closes when |
|---|---|---|
| K335 | Vocabulary v0.16: composed topologies | the five parts' payloads, the nine finding codes with their fixes, and the plan in `RunStarted` baseline (`plan`) are ratified with a rationale |
| K336 | Parts and plans | a plan in JSON or in lines becomes a kernel topology with every default filled; each of the five parts runs; the plan's lines read back as the same plan |
| K337 | The plan's checks | each finding code fires on a plan built to cause it and names its fix; the dry run shows the steps in order and how the run ended, both ways through an `if`; a plan whose findings all have certain fixes returns a checked fixed plan |
| K338 | The three tools | `topology_help`, `topology_plan`, `topology_run`; a run held by its caller, its end told once; `save` writes the workspace file; the shipped plans; the code topologies run by name; the four old run and list tools gone |
| K339 | The built tools on the pattern | `build`, `review`, `run` and `delegate` say what comes next in their results and notices; an unknown run id lists the session's runs |
| U186 | Housekeeping from the read | the dead `src/` tree and its two generators gone; `builder.py` out of the packaging; the sample code out of the shell; ⌘F counts the real transcript |
| U187 | A composed run in the app | the daemon's plan and run endpoints for a session; a composed run's pane shows each step's event as a row; agent steps open their panes |
| U188 | The Studio on plan and run | the Studio's validate shows the plan's lines, dry run and findings; its build starts the run |
| U189 | Real observation | in the installed app, a real model makes a plan with the tool, fixes a finding, runs it and reads the end; it also delegates, reviews a branch and builds a card |

Then pause and resume for held runs (r3's K330 left them out), the autonomous build and the swarm as plans.

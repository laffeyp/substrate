# process/refactor-reviews/

Refactor plans and reviews of oversized or misshapen modules. Distinct from the sibling
`REVIEW-*.md` files at `process/` root, which cover per-sprint SDD-discipline reviews and
per-epic closure reviews.

A refactor review names a module (or a cluster of modules) that has grown past the point where
per-sprint sweet-spot discipline can hold it, diagnoses the shape under Python best practice
read through SDD + substrate, and proposes a landing plan as a chain of behavior-preserving
sprints per TECHNIQUES.md #43. Nothing here dispatches until Architect ratification.

## On file

- `PLAN-2026-08-28-hygiene-splits.md` — plans for server.py (2,608 → package), session_registry.py
  (1,232 → package), cli.py (1,750 → package), delegate.py (663 → package), substrate_tools.py
  (736 → package), plus one cross-cutting primitive extraction (`substrate.testing.run_topology_sync`
  collapses four duplicate factory shapes). Six plans, ~40 sprints, ~3 weeks of Architect-and-Agent
  time.

The two repository-cleanup plans that lived here — `PLAN-2026-08-31-repo-cleanup-DEEP.md` and
`PLAN-2026-08-31-repo-cleanup-for-public-release.md` — were not module-refactor reviews. They moved
on 2026-11-20 to `process/planning/2026-11-20-repo-organization/superseded/`, the prior rounds of the
repository-organization work.

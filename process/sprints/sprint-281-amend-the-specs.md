# Sprint 281 — Amend the specs

```yaml
---
id: 281
status: closed
closed_at: 2026-10-10
phase: 1
pass_kind: documentation
roadmap: substrate/process/planning/ROADMAP-2026-10-10-default-guidance.md
asked: 2026-10-10 (Architect)
---
```

## why

The default-guidance roadmap changes what the specs describe: the bundle's slots and names, where `per_turn` goes, the baseline, a system channel, driver profiles, `SessionChanged`, skills, memory and slash pass-through. The specs must say what Substrate now is.

## scope

For each spec the roadmap changed, write the next round as a copy of the current one plus marked changes. Prior rounds stay on disk.

- **New sections**, each headed as new in this round and naming the sprint that built it.
- **Superseded sections** keep their text, under a note naming the section that replaces them.

The specs, and the sections the roadmap touches:

- **Product spec**, now `current-design-direction/product-spec/PRODUCT-SPEC-2026-08-17-round12.md`, next round 13:
  - §2a slash commands (`/dellm`, the `//` pass-through);
  - §7 the baseline;
  - §7a the layers (`harness`, `standard`, memory, skills);
  - §7b bundles (`style`, stacking, per-turn placement, shipped `extends`);
  - §14 the Claude Code comparison.
- **Tech spec**, now `current-design-direction/tech-spec/TECH-SPEC-2026-08-25-round6.md`, next round 7:
  - §1.6.5 seed assembly, replaced by fragments, the system channel and the baseline;
  - §9 bundles;
  - the session vocabulary sections it cites.
- **Design spec**, now `handoff_latest/docs/DESIGN-SPEC -2026-08-31-.md`, if the UI work (U121–U123) changed what it describes: the slash inventory, and the default bundle at session create.

## checks

- Every behaviour the roadmap's closed cards changed is described in a new or superseding section, each naming its card.
- No prior round is edited.

## result

- **Product spec round 13**, `current-design-direction/product-spec/PRODUCT-SPEC-2026-08-17-round13.md`.
  - A copy of round 12 with a round note under the title.
  - "Superseded in part" notes under §2a, §7, §7a, §7b and §14.
  - New sections §R13.1–§R13.9: default guidance, bundle slots, baseline, system channel, harness drivers with attribution and e-mail, memory, skills, slash commands, environment updates.
- **Tech spec round 7**, `current-design-direction/tech-spec/TECH-SPEC-2026-08-25-round7.md`.
  - A copy of round 6.
  - Notes under §1.6.5, §3a, §6, §9 and §13.
  - New sections §R7.1–§R7.8 with the modules, names and vocabulary sections.
- **Design spec round 2**, `handoff_latest/docs/DESIGN-SPEC-2026-08-31-round2.md`.
  - A copy of round 1 · checkpoint 2.
  - A note on the prompt-line router.
  - §R2: `/dellm`, `//`, the `standard` default, environment-update rows.
- **Check:** every behaviour the closed cards changed appears in a new section, each naming its card. No prior round was edited. K279 and K280 were withdrawn, and the specs do not describe them.

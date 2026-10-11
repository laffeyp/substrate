# Sprint 287 — The high guidance text, made generic

```yaml
---
id: 287
status: closed
closed_at: 2026-10-10
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-guidance-levels.md
asked: 2026-10-10 (Architect)
---
```

## why

The `standard` bundle was copied from one operator's Claude Code setup (K275, "copy first, improve later"). The Architect asked for a line-by-line pass: generic to any model, `dellm`-ed, nothing that refers to Claude.

## result

- **`methodology.md`** (16,107 bytes rewritten):
  - Claude Code's own header is gone.
  - "No Claude attribution in git, ever" became "No model attribution in git". It keeps every rule (trailer, footer, file credit) and names no vendor.
  - Every rule speaks about "the user", not as "I". "Reading files" says "when the user asks for…", and the opt-outs are the user's.
  - The duplicate "Every output is writing" section is gone; `style.md` carries it.
  - "Working rules from memory" (25 lines of one operator's memory index, a profile of the operator and this project's history) is gone. Memory loads at session open from `~/.substrate/memory/` and `<repo>/.substrate/memory/` (K276), where those rules belong.
  - The general working rules in it became "Working discipline", six lines: a passing test is not proof; report the state; do the small work yourself; change only what was asked; hand over a working state; earn every caveat.
- **`style.md`** got a `dellm` pass. "Load-bearing" and padding are gone, and the em-dashes became commas and colons.
- **`bundle.toml`** has a new description: high guidance.
- **Tests.**
  - `test_guidance_generic_287.py` scans every shipped bundle text, skill and role prompt (17) for a model, vendor or person name, and for first-person speech outside quotation marks: 35 passed.
  - `test_standard_bundle_275.py` was rewritten for the new headings. The golden heads for `standard`, `code_review`, `pair_coding`, `best_of_n_verified` and `research_sweep` were regenerated and their diffs read. The `standard` head went from about 19,950 characters to 12,047.
  - The UI's attribution gate (`test_driver_profile_120.py`) skips the renamed section, and `test_daemon_uses_standard_121.py` pins the new opening line.

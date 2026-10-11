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

## redone (2026-10-10, Architect)

The first pass rewrote nearly every sentence of the high text. The Architect: rewriting was for medium and low; high is the operator's own text with the least edits that make it generic; and no level names a tool. A harness model's tools are its own, and Substrate's reach it over MCP under other names (`mcp__substrate__read_file`), so `read_file` named in the guidance was wrong for every harness driver.

- **High is restored from git** (`794b397f^`). Of its 150 lines, 24 changed:
  - **Names.** Claude and Anthropic are out of the attribution section, which is now headed "No model attribution in git, ever".
  - **Voice.** "When I tell you…", "I'd rather…", "my summary" and "his feedback" now refer to the user.
  - **Tools.** `read_file`, `web_fetch`, `delegate`, `write_file` and `edit_file` are out, and `skill("dellm")` became "the `dellm` skill".
  - **Memory entries.** Six that describe one operator or this project are gone: the profile, grep repeated literals, no subagents, code organization, pkill, artifacts. Two dated asides are trimmed.

  Every other line is as written, including Claude Code's opening line, which names no model, and the duplicated "Every output is writing" section. High's head is 4,613 tokens; the original was about 4,988.
- **`style.md`** is restored; its only change is "use the `dellm` skill".
- **Medium and low** lose their tool names.
- **Tests.** `test_guidance_generic_287.py` adds a no-tool-names check over every bundle text, skill and default role prompt (57 passed). `test_standard_bundle_275.py` pins the restored headings and the removed entries. The golden heads were regenerated.
- **Open.** `prompts/reviewer.md:66` ("Use `inspect_record` and `read_file`") is a Substrate role prompt, not imported guidance; it still names tools.

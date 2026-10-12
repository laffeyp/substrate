# Sprint 300 — Change tests read the prompt for the message after the change

```yaml
---
id: 300
status: open
phase: 1
pass_kind: functional
roadmap: process/planning/ROADMAP-2026-10-12-changes-on-time.md
postmortem: process/planning/POSTMORTEM-2026-10-12-mid-session-changes-arrive-late-r2.md
context_files:
  - tests/test_length_tone_controls_296.py
  - tests/test_guidance_mid_session_298.py
  - tests (K274's change tests)
---
```

## scope

The K274 and K296 change tests assert on the third message's prompt after a change on the second; K298's asserts only the history line. After: each asserts on the prompt for the message on which the change was recorded, for every field with rewritten text. Written before K299's code, as its red.

## observation contract

The rewritten tests fail on the current kernel with the old text in that prompt, and pass after K299.

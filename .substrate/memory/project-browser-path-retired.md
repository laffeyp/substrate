---
name: project-browser-path-retired
description: Substrate UI's browser (Chrome) path is retired; only Electron-app harnesses matter; browser harnesses get deprecated, not fixed
metadata:
  type: project
---

As of 2026-10-08 the user ruled the browser implementation of the substrate-ui shell dead: it will never be tested in Chrome again. Harnesses that drive the shell through `chromium.launch` (the six Axis A shakeout flows caret_pin, pane_split, pane_header_clip, pane_prompt_isolation, reveal_mode_direction, model_reply_render, plus the old tests/walkthrough.js + tests/harness/** bridge-era scripts) are to be deprecated, not repaired.

**Why:** the Electron app (source and packaged) is the only product surface; effort on browser harnesses buys nothing.

**How to apply:** in reviews/audits, one "deprecate" finding per browser harness instead of itemizing its defects. Headless flows that drive SessionController + NodeSubstrateClient against the server stay in scope, since the Electron app runs that same controller and server. Related: [[project-substrate-single-instance]].

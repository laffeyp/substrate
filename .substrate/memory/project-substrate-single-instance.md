---
name: project-substrate-single-instance
description: "Substrate runs as one app per machine; ~/.substrate is its single store by design — dev+packaged overlap is transitional, not a defect"
metadata:
  node_type: memory
  type: project
  originSessionId: fbeecb0e-302f-4ee4-93f1-dc5db0e43766
  modified: 2026-09-29T07:48:52.564Z
---

Substrate is designed as one app running per computer. `~/.substrate/` (sessions, runs, daemon.sock, config) is the single store on purpose. Two instances sharing it (a dev `npm run electron` beside the installed `.app`) only happens because development and packaging overlapped in late Sept 2026.

**Why:** On 2026-09-29 I called the shared folder "the biggest configuration value the review missed"; the user corrected it — concurrency is not a supported mode, so it is not a finding.

**How to apply:** Do not flag shared `~/.substrate` state or socket/boot-scan collisions between instances as design defects or review gaps. At most note them as a test-setup hazard while dev and packaged builds coexist. Related: [[feedback-no-pattern-matched-caveats]].

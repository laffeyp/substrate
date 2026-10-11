---
name: feedback-read-all-specs-together
description: "When a tech spec section bears on the work, also read the matching product spec section and the design spec if one exists; the specs together are the source"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 54c3a66a-fcc6-405d-b4d7-25deaac5e44f
  modified: 2026-10-10T19:32:27.260Z
---

Reading the tech spec alone is half the source. The product spec (`current-design-direction/product-spec/PRODUCT-SPEC-2026-08-17-round12.md`), the tech spec (`current-design-direction/tech-spec/TECH-SPEC-2026-08-25-round6.md`) and the design spec (`handoff_latest/docs/DESIGN-SPEC -2026-08-31-.md`) are read together for any feature they cover.

**Why:** 2026-10-10, while researching Substrate's prompt delivery (bundles, per-turn, seed), the user said: "Whenever you read a tech spec, you also have to read that part of the product spec… All of those specs are the thing, not just one."

**How to apply:** before stating what Substrate was designed to do, read the feature's section in each spec, then compare against the code. Related: [[feedback-old-docs-are-history-not-plan]], [[feedback-read-the-code-grep-repeated-literals]].

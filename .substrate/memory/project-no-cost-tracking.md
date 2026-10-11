---
name: project-no-cost-tracking
description: "Substrate never tracks money/cost/$ — instrument tokens + time only; \"matched compute\" = tokens/time/calls, not dollars"
metadata: 
  node_type: memory
  type: project
  originSessionId: b961bf01-3a14-4cb4-a99f-1ee07812dc68
  modified: 2026-10-10T20:27:53.734Z
---

Cost / dollars / a price table is permanently OUT OF SCOPE for substrate. It is an open-source model orchestrator. Per the user (2026-06-25), emphatic and permanent: "cost is not a concern of this project, and never has been and never should be, never will be."

What IS legitimate to instrument: resource accounting that *consumed* compute — **tokens and wall time** (and model-call counts). These are interesting because they measure work done, not because they map to money.

**Why:** the benchmarking/[[project-substrate-benchmarking-phase]] design drifted into a "$ (priced per model)" dimension and a `_models.py` docstring promising "cost is DERIVED at report time from a price table." That whole money axis is a category error for this project. The `ModelUsage` code is correct to carry `prompt_tokens / completion_tokens / wall_ms` and NO cost; `UsageTotals`/`ArmReport` correctly report tokens + wall + calls only.

**How to apply:** treat any cost/$/price-table reference as a defect to remove, not a gap to fill. "Matched compute" means matched tokens / wall time / call counts across arms, never matched dollars. When reviewing the benchmarking design doc (§4.4) and `reference/_models.py` ModelUsage docstring, flag the residual money language for deletion. Never propose a price table, cost field, or dollar figure.

**Design is never driven by cost either (2026-10-10).** Saving money or tokens is never the motivation for a design choice; the user: "If saving money is the motivation here, the engineering is bad." Hunt hidden cost logic ("pays", "saving", "costs N tokens", optimizations made for cost) in design docs and remove it. This does not ban caching as a topic: caching facts may stay; they just never justify a choice on cost grounds. The hard line (2026-10-10): prompt caching is never baked into a design. It exists only as an explicit opt-in (for Substrate: the `cache_layout` key in session `driver_params`, default false, no UI/bundle/profile default), because rearranging the prompt for cache hits hides how the model is fed and stops it getting the full context in the open.

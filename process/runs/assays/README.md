# process/runs/assays — index

*Current as of 2026-11-20. One directory per assay or SWE-bench evaluation run. The 2026-08 runs are the SWE-bench assay corpus; the `length_drift_2026-10-12*` runs feed three language tests under `tests/`. Tracked directories are kept as evidence; the five largest confirmatory and smoke runs are gitignored and live on disk only.*

| Run | Date | Tracked files | Note |
|---|---|---|---|
| `wire_check_n300_2026-08-10` | 2026-08-10 | 7,307 | the largest wire-check assay |
| `lite_n300_6arm_2026-08-10` | 2026-08-10 | 3,582 | SWE-bench Lite, N=300, six arms |
| `lite_n300_6arm_v2_2026-08-11` | 2026-08-11 | 3,543 | Lite N=300 six arms, v2 |
| `lite_n300_6arm_shim_2026-08-11` | 2026-08-11 | 1,491 | the same with the rate-limit shim |
| `lite_n300_6arm_local_2026-08-11` | 2026-08-11 | 1,084 | the same, local models |
| `shim_check_n30_pro_2026-08-11` | 2026-08-11 | 968 | shim check, N=30, Pro tier |
| `full` | 2026-08 | 292 | a full assay run |
| `wire_check_n10_2026-08-10` | 2026-08-10 | 41 | wire check, N=10 |
| `wire_check_2026-08-10` | 2026-08-10 | 15 | wire check |
| `matrix` | — | 4 | assay matrix run |
| `container` | — | 3 | container assay run |
| `repair` | — | 2 | repair-topology verify run |
| `length_drift_2026-10-12` | 2026-10-12 | 2 | length-drift experiment (read by the language tests) |
| `length_drift_2026-10-12_k299` | 2026-10-12 | 2 | the same on the fixed kernel |
| `confirmatory_lite_2026-08` | 2026-08 | 0 (gitignored) | SWE-bench Lite confirmatory; ~9.1 GB on disk |
| `confirmatory_verified_2026-08` | 2026-08 | 0 (gitignored) | SWE-bench Verified confirmatory |
| `host` | — | 0 (gitignored) | host-run outputs |
| `smoke` | — | 0 (gitignored) | smoke-run outputs |
| `ws_gate` | — | 0 (gitignored) | workspace-gate outputs |

# process/signals — index

*Current as of 2026-11-20. The project's locked vocabularies and their audit trail. The kernel vocabulary is the contract the runtime validates every emission against; the session topology and the per-area topologies carry their own.*

| File | What it is |
|---|---|
| `current.json` | the live kernel vocabulary; version 0.4, identical to `0.4.json` |
| `0.1.json` … `0.4.json` | the numbered locks, each the kernel vocabulary at that version; `0.1`–`0.3` are the audit trail |
| `0.1-rationale.md` … `0.4-rationale.md` | the rationale for each lock and each version bump |
| `proposals.json` | open and ratified vocabulary proposals |
| `session-vocabulary.md` | the session topology's own vocabulary; v0.20 as of 2026-11-14 |
| `applications-vocabulary.md` | the application topologies' vocabulary |
| `swebench-solver-vocabulary.md` | the SWE-bench solver's vocabulary |
| `REVIEW-2026-08-25-session-vocabulary.md` | a review of the session vocabulary |
| `research-pass.md` | a research pass over the vocabularies |

The kernel vocabulary changes through a typed proposal in `proposals.json` and a version bump; `current.json` tracks the latest numbered lock, and the earlier locks stay as the audit trail.

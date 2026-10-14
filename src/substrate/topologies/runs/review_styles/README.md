# Review styles

The texts a Review run sends its reviewer, one per style (kernel sprint K320; research
`process/planning/RESEARCH-2026-10-13-core-topologies-r8.md` § 4.3). The Architect asked that the
styles be picked from well-known review styles in published practice. The sources stay here, out of
the text the model reads.

| Style | What it asks | Source |
|---|---|---|
| `defects` | Does the change work: correctness, then security, then performance, each finding with its failure scenario and fix. | Substrate's reviewer role prompt (`topologies/session/prompts/reviewer.md`), unchanged; Google Engineering Practices, "What to look for in a code review": Functionality, Tests (https://google.github.io/eng-practices/review/reviewer/looking-for.html). |
| `design` | Is it well designed, does it fit the system, is it as simple as it can be; naming, comments, consistency. | Google Engineering Practices, the same page: Design ("the most important thing to cover in a review"), Complexity, Naming, Comments, Consistency. |
| `security` | How it could be attacked or leak, by technical control and by vulnerability. | OWASP Code Review Guide v2, "Examples by Technical Control" (authentication, authorization, session management, input validation, error handling, secure deployment, cryptographic controls) and "Examples by Vulnerability" (injection, cross-site scripting, cross-site request forgery, logging, race conditions) (https://wiki.owasp.org/index.php/OWASP_Code_Review_Guide_Table_of_Contents). |

IEEE 1028 (Standard for Software Reviews and Audits) names five review types: management review, technical review, inspection, walk-through, audit. They describe how a review is run, not what it looks at, so they are not styles here. More styles are more texts; the topology does not change.

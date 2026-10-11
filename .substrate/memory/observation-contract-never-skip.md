---
name: observation-contract-never-skip
description: "Never claim behavior-touching work is done without running its observation contract; scope test tooling into the repo, never /tmp"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c5f5786b-ac39-4cfa-8bb3-319304032ea2
---

The user sharply corrected me (twice in one session) for declaring a UI change done with the live E2E "not run — Playwright absent in this env, backend-only change," and proposing to continue. That is the finished≠worked rationalization SDD hard rule 9 (observation contract) exists to stop.

**Why:** a REQUIRED contract that gets skipped ships a lie that looks like a pass. "The environment doesn't have the tool" is NEVER a license to skip — it is an instruction to make the environment have the tool and then run it. And the deeper cause was tooling scope: the Playwright install lived in ephemeral `/tmp/pw-substrate` (a prior session's, vanished), which is *why* it "couldn't be run." Un-scoped, out-of-repo test tooling makes a required contract skippable.

**How to apply:** for any behavior-touching change (UI, runtime behavior, anything with an observation contract), actually RUN the observation contract before claiming it works — no "backend-only" rationalizing around it. Keep the test harness reproducible FROM THE REPO: a pinned devDependency + committed lockfile (e.g. `substrate-ui/package.json` + `package-lock.json` pin Playwright; `node_modules/` gitignored; `channel:'chrome'` drives system Chrome), documented as a one-command setup (`npm install && npm run e2e`). If a tool is missing, install it scoped to the repo, then run.

**For any VISUAL surface, grading is TWO tracks and BOTH are required** (a second, sharper correction the user gave the same day): STRUCTURAL (DOM/text assertions — `npm run e2e`) AND PERCEPTUAL (capture key-frame screenshots and the agent — a vision-model judge — actually VIEWS them: `npm run capture` → Read each PNG). The kit names this in three places: AGENTS hard rule 9 ("expected screenshot / visible behavior"), foundation 01 signal type #2 ("Screenshots at Key Frames"), TECHNIQUES Visual/UI "Two-track visual grading". **A green structural track is the most dangerous cover for a skipped perceptual pass** — it is genuinely rigorous and still only half; this exact gap hid a real stale-inspector bug for nine review rounds. If you cannot point to a screenshot you looked at, the visual observation contract is unmet. When the perceptual pass finds a defect, pin it with a structural assertion AND keep looking. Relates to [[review-sdd-discipline]].

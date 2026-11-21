# process/RESEARCH.md — Substrate research log

*The long-form record of what we are learning by running real models through substrate's topologies.
This is not state and not methodology. `BLACKBOARD.md` holds current state (what is built, what is
next); `KIT_DIARY.md` holds findings about the SDD kit itself. This holds the **empirical findings
about agent behaviour on substrate** — the questions, the setup, what we actually observed (with the
data), what we think it means, and what is still open. Findings here get distilled outward: a
current-state line into the BLACKBOARD, a methodology lesson into the KIT_DIARY. The full account,
including the dead ends and the refuted hypotheses, stays here.*

*Register: plain and concrete. Every claim carries its evidence and its caveats. An n=1 run is
labelled n=1. A refuted hypothesis is kept, not deleted — the refutation is the finding.*

---

## Thread 1 — What breaks when a real model drives the tool loop

**The question.** The `tool_loop` topology is the model→tool→model agent loop. It passes its
deterministic CI test and simple scripted tasks. But does it hold when a *real, stochastic* model
drives it against *open-ended* tasks — the way a user actually uses it? And where, exactly, does it
stop being a loop problem and start being a model problem?

**The method — the container arena as a discovery harness.** Scripted tests can only check failures
you already know to write. To find the unknown ones we run the agent WILD: a real model (Ollama,
local or cloud) drives the real `FULL_SUITE` against a throwaway `/arena` filesystem inside a
disposable container (`Dockerfile.arena` + `scripts/agent_arena.py`), free to do anything, and we
read the record afterward. The container is a test arena, never the product — the product is
host-native by design (direct filesystem, real autonomy, like Claude Code). Destructive tool use in
the arena costs nothing: `docker rm` and it is gone. Models tested: `llama3.2:1b` (weak),
`qwen2.5-coder:7b` (moderate), `qwen3-coder:480b-cloud` (the capable one).

---

### R-1 — A stochastic driver finds bugs no fixture author would write

The first real-model demo wedged the loop. The model called `glob('**/*.py')` on a large tree; the
~340 KB result crossed the 16 KiB blob-offload threshold, which stripped the loop-control fields
(`step`) off the frame; the continue predicate then raised `KeyError('step')` and quarantined. No
one writes the unit test "glob returns 340 KB" — it surfaced only because a real model did what a
fixture never would.

**Fix (general, not spot):** the root cause was "any tool result crossing the offload threshold
strips control fields," so the fix is a byte-cap in the tool runner — *any* oversized output becomes
a typed "too large to inline" notice before it can strip the frame — plus a defensive `.get("step")`.
Capping `glob` alone would have left `read_file`/`grep`/`bash`/`web_fetch` wedge-able.

**Status:** fixed, reproduce-then-kill test (250-file glob). **Interpretation:** the discovery harness
earns its keep on turn one — it is the front end that *feeds* reproduce-then-kill, which can only
*kill* a failure you already know.

---

### R-2 — Real models batch tool calls; our parser degraded that to a no-op

`qwen2.5-coder:7b` emits several tool calls concatenated in one message: `{..}\n{..}\n{..}`. Our
parser grabbed the greedy span from the first `{` to the last `}` — invalid JSON for multiple
objects — so it fell through to "this is a final answer" and ran **zero tools**. The run "finalised
OK" while doing nothing. It hit 2 of 12 tasks, the two most multi-step ones.

**Fix:** parse the *first balanced* `{...}` object (brace-depth scan respecting string literals), so a
batched message yields the first call and the loop runs it; the model continues sequentially.

**Status:** fixed, reproduce-then-kill test. **Interpretation:** confirms the kit's finding-28 ("parse
*real* model output, not the canned single-object shape") one level up. Also exposed R-3.

---

### R-3 — "Green" is blind to soft failure; the discovery signal needed the same skepticism

The arena's OK/CRASH signal caught wedges and tracebacks but not "finalised with a tool-call JSON
blob as the answer" (R-2's no-op). We added a SOFT signal — a `FinalAnswer` that looks like an
unparsed tool call. The *first* version matched any leading code fence, and immediately produced
**false positives**: `build-app` and `rename-all` both *completed* (the file was written / renamed
correctly) and then legitimately showed the file in a ```` ```python ```` fence. Reading the logs
caught it. Tightened to require the tool-call shape (`"name"` *and* `"arguments"`); validated against
all 12 real captured logs (0 false positives, still catches the genuine no-op).

**Interpretation:** be-your-own-skeptic applies to the *instrument*, not just the code under test. A
discovery harness's own success signal can lie, and only reading the raw output catches it.

---

### R-4 — Adversarial review as advice: three real hardening findings, cleanly bounded

An independent adversarial review of the workspace + hardening changes, treated as advice not verdict,
surfaced three real defects (all fixed, all reproduce-then-kill tested):
- `replace_all = bool(arg)` — `bool("false")` is `True`, so a model stringifying a falsey value would
  silently *enable* the destructive replace-all and disable the unique-or-error mis-splice guard.
  Fixed with a value-preserving `_as_bool` (treats `"false"/"0"/"no"/"off"/""` as false).
- `read_file` with an out-of-range `offset` returned a bare `""` — the exact ambiguity the empty-file
  marker was added to kill. Now an empty window says so.
- Empty `?workspace=` resolved to `Path(".")` not the cwd default. Fixed.

The review's *dropped* items were correctly dropped (the workspace-autonomy "footgun" is deliberate
posture, not a bug). **Interpretation:** an adversarial pass that cuts both ways — real findings kept,
non-findings released — is worth its cost, and treating it as advice (we adjudicate) is the right
stance.

---

### R-5 — The write-spin: a capable model rewrites and never verifies

The headline. On an open-ended "build a Hangman game and PROVE it runs" task, `qwen3-coder:480b`
wrote `hangman.py` **16 times and ran it zero times** — no `bash`, no `read_file`, no `edit_file`. It
was not re-emitting an identical call; the byte counts varied (2923, 3621, 3795, …) — it kept
*rewriting* the file with cosmetic variations and never committed to running it. Classic no-commit
perfectionism.

**What it is not (hypotheses raised and refuted by observation):**
- **Not token starvation.** Re-ran at 8× the token budget (`max_tokens` 1024 → 8192): identical
  16-write spin. Falsified.
- **Not a history-threading bug.** Confirmed the full results transcript threads into every model
  prompt (the `results` View is a `KindBuffer("ToolResult")` that accumulates; the prompt carries
  "Tool results so far, in order: …"). The model *sees* its 15 prior writes and rewrites anyway.
- **Not a prompt problem — for this model.** We adapted best-in-class agent-loop discipline into the
  prompt (act when ready; do not redo a succeeded action; verify by running; report truthfully) and
  sharpened it on substrate's spine (decide from the observed record; a failed result is information
  not a wall; "written" is not "working"). The thin prompt spun; the disciplined prompt spun
  *identically*. A prompt is a request this model does not honour here.

**Interpretation:** the load-bearing lesson — *a prompt is a request; substrate can enforce.* Best-in-
class harnesses work partly because their model obeys the prompt. We cannot assume that across
arbitrary models, but we can enforce discipline structurally on the record. See R-6.

**Caveat:** every 480b run is n=1; the behaviour was consistent across five runs but this is a
demonstrated pattern, not a measured rate.

---

### R-6 — Structural enforcement: the anti-spin guard, and the errors-as-observations tension

**The fix (SDD-sound):** the loop now treats a *second consecutive* `write_file` to the same file,
with no run/read between, as a redundant action — it returns a typed `ToolResult(ok=False)` telling
the model to run or read the file to verify before rewriting. Errors-as-observations, on the record,
consistent with the existing unknown-tool and missing-arg guards. State (`prev_write`) persists across
firings in the closure; the CI calculator never writes, so committed records stay byte-identical.

**Effect at the loop level:** the spin's *waste* is gone — 16 real writes collapse to 1 (the rest
refused). Confirmed live.

**The tension it exposed.** The model factory halted the loop on *any* `ok=False` — which contradicts
the discipline ("a failed result is not a wall") and neuters the guard into a halt. We worked through
three positions:
1. **Halt on first failure** (original): the anti-spin corrective halts cleanly with a truthful
   message at 2 writes. But a capable model that hits one transient tool error can never self-correct.
2. **Never halt** (relaxed for walkthrough): SDD-correct in principle, but the *observation refuted
   the theory* for this model — it flailed to the step budget on 15 refused writes and answered "no
   result." Strictly worse.
3. **Recover, but bail when stuck** (final): a real model gets room to react (up to
   `_MAX_CONSECUTIVE_FAILS = 3` consecutive failures), then the loop bails with a truthful report
   rather than flailing. The deterministic/default path still halts on the first failure (its tests
   rely on it; it has no model to reason). Confirmed live: 4 writes (1 real + 3 refused) → "stopped
   after 3 failed tool call(s): you already wrote hangman.py … run or read it to verify."

**Interpretation:** position 2 is a clean example of preferring a principle over an observation and
being wrong for it. Recover-then-bail is the honest resolution: room to self-correct, bounded, never
"no result."

---

### R-7 — The model ceiling: where enforcement ends

With the anti-spin guard *and* recovery both live, `qwen3-coder:480b` still would not verify. Fed the
typed corrective ("run it to verify before rewriting") **15 times in a row**, it kept trying to write
and never ran `bash`. No prompt, no sharpened discipline, no repeated typed observation moved it.

**Interpretation:** this is a **model** ceiling, not a loop bug. `qwen3-coder:480b` via Ollama, on
this open-ended build-and-verify task, does not run its own code. The loop is now as good as the loop
can be here; making the model behave agentically is not a loop fix. This is exactly the boundary the
liveness test exists to locate: where a better harness stops helping and model capability takes over.

**Open questions:**
- Is the ceiling model-specific? **ANSWERED by R-9 (2026-07-02): yes.** `kimi-k2.6:cloud` (thinking+tools)
  ran its own code on the same task — write→read→run→verify. The ceiling is agentic reasoning, not a
  wall. Still untested: `deepseek-v4-pro:cloud`, `glm-5.1:cloud`, `deepseek-r1:8b` (local reasoning).
- Does the ceiling depend on task framing? The task says "PROVE it works by running it" — an even more
  explicit "your FIRST action after writing must be a bash run" might move a borderline model.
- Is there a substrate-native lever short of hard-coding the sequence — e.g. surfacing the file's
  existence/content in the write result so the model stops re-deriving it?

---

### R-8 — Tool coverage: what we have, what is untested, what is missing

- `web_fetch` (URL → page text, 20 KB cap) exists but was **untested** — live network I/O with zero
  coverage. Closing that with a local `http.server` fixture test (fetch, decode, cap, error) is
  queued.
- `web_search` (query → results) does **not** exist. It is buildable free with no API key via
  DuckDuckGo's HTML/lite endpoint (the same `urllib` as `web_fetch`) — real markup captured; the
  result links come back as `//duckduckgo.com/l/?uddg=<encoded-url>` redirects to decode. (Google
  specifically blocks scrapers; DDG is the standard free route.) Not yet built.
- Hardening lifted from Claude Code's leaked *tool* descriptions (adapted, not copied): the empty-file
  marker, the `edit_file` line-number-prefix warning, `replace_all`, the minimal-`old_string`
  guidance. The deliberate divergences we keep (workspace-relative paths not absolute-required; glob
  sorted alphabetically for replay-determinism not by mtime; no read-before-overwrite guard because
  autonomy is the point) are cases where their choice is wrong *for us*.

---

### R-9 — A thinking model breaks the R-7 ceiling: write → read → run → verify

Same hangman task, `kimi-k2.6:cloud` (thinking+tools, `--think` on). Tool mix: **`write_file`(1),
`read_file`(1), `bash`(1)** — it wrote the file, read it back, and RAN it (`bash`, `exit: 0`, stdout
began `=== HANGMAN ===` with the gallows). No spin, no anti-spin refusals needed; the task completed
with the model verifying its own work. Confirmed from the record (the bash exit code + stdout), not
the model's say-so.

**Interpretation:** R-7's ceiling was **model-specific** — "a coder without agentic reasoning," not
"models can't do this." A thinking+tools model plans the verify step the pure coder
(`qwen3-coder:480b`) skipped. This simultaneously:
- validates the roster's central hypothesis — thinking-vs-non-thinking is the axis that matters for the
  agentic verify-loop, not raw code quality (`qwen3-coder:480b` is the better *coder* on benchmarks and
  the worse *agent* here);
- validates the recover-then-bail design (R-6) by exhibiting a model that actually recovers/verifies,
  running cleanly through the loop;
- validates the whole stack end-to-end: a capable agentic model drives write→read→run→verify through
  substrate on a real open-ended build, every step a typed event on the record.

**Caveat:** n=1. One clean run; the *behaviour* (write→read→run) and the verified execution are the
finding, not a success rate. The confound is controlled — `--think` was on (a flag added to
`run_tool_agent` for this), where the earlier failing runs used a non-thinking coder.

**Through-line of Thread 1 so far:** the arena found the ceiling; the loop was hardened as far as a loop
can be (anti-spin, recover-then-bail, errors-as-observations); and the ceiling turned out to be a
*model-capability* axis (agentic reasoning), locatable precisely because every step is on the record.
**Best coder ≠ best agent.**

---

### R-10 — The discipline PROMPT is inert; the levers are the guard and the model (A/B, under challenge)

Claim under test (mine): "the SDD-sharpened discipline prompt helps compliant models." It was built to
NOT fail — I added the prompt, saw kimi succeed *with* it (R-9), and asserted the prompt helped. That
green never isolated the prompt's contribution. Under an SDD skeptic challenge I built the check that
*could* fail: A/B, `kimi-k2.6 --think`, same hangman task, anti-spin guard still active, the discipline
text swapped for the thin "tools are optional" prompt.

**Reading (thin prompt):** tool mix `write_file(1), read_file(1), bash(2)`; the two bash runs read
`exit: 1` then `exit: 0`, stdout `=== HANGMAN ===`. kimi wrote the file, read it, ran it, hit an error
(exit 1), FIXED it, and re-ran to a clean exit 0 — the full agentic recover loop — **without** the
discipline prose.

**Verdict — claim RETRACTED.** The discipline PROMPT is inert as an agentic lever: kimi verified with
or without it (n=1 each arm), and it did nothing for qwen either (R-5). kimi's verify-and-recover
behaviour is the MODEL. The *verified* levers are (a) the structural anti-spin guard (R-6) and (b) model
choice (R-9); the prompt stays only as the cheap generative-escape carrier (the poem fix), not as a
proven lever. n=1 both arms is not enough to rip it out (that would be the same over-correction), but
it is enough to stop claiming it works.

**Bonus (independent confirmation):** the `exit 1 → fix → exit 0` recovery is a real capable model
recovering from a tool failure unprompted — direct evidence that recover-then-bail (R-6) is the right
shape, not just my design preference.

**Method note:** this is what the challenge is for. The green that lied was "kimi succeeded, and I had
just added the discipline prompt, therefore the prompt helped." The could-fail check separated the two.

---

### R-11 — Widening R-9 across the roster: the verify threshold + two new failure modes

Same hangman task, `--think`, n=1 each, anti-spin guard + recover-then-bail active.

| Model | thinking | tool mix | outcome |
|---|---|---|---|
| `kimi-k2.6` (cloud) | yes | write, read, bash | **VERIFIED** — `exit 0` (R-9) |
| `glm-5.1` (cloud) | yes | write, read, bash×3 | **VERIFIED** — `exit 0` |
| `deepseek-v4-pro` (cloud) | yes | write, read, bash×2 | **ATTEMPTED** — both `exit 1`, then claimed "proven working" |
| `qwen3-coder:480b` (cloud) | NO | write×16 | **NO verify** — write-spin (R-5/R-7) |
| `deepseek-r1:8b` (local) | yes | — | **INCONCLUSIVE** — `ReadTimeout` after 3 attempts (too slow on this hardware), both with and without `--think`. No agentic data. |

**Interpretation:** every thinking+tools CLOUD model crosses the *attempt-verification* threshold (3/3
ran their code) where the non-thinking coder never does. Two verified clean. Strengthens R-9 —
agentic reasoning, not code quality, is the axis (n=4 cloud now). Two new failure modes, both distinct
from the write-spin:

- **R-11a — attempt-verify then claim FALSELY (`deepseek-v4-pro`).** It ran its code (agentic), got
  `exit 1` twice, then answered "the game … has been proven working." Crossing the run-it threshold is
  not the same as reading the result honestly — the claim-truth failure the loop can *observe* (the
  record shows `exit 1`) but can't force the model to respect. Candidate for a STRUCTURAL check: refuse
  a "done" FinalAnswer when the last relevant bash exited non-zero — the enforce-vs-request axis
  (KIT_DIARY finding 32) applied to the verify step. Currently unbuilt; recorded as a lead.
- **R-11b — `deepseek-r1:8b` is INCONCLUSIVE (timeout), and I nearly mis-attributed it twice.** First
  read (with `--think`): empty output, 0 tools — I called it a think-routing confound. Second read
  (`think=False`): STILL 0 useful output — I was about to call it a tool-calling incapacity. The record
  told the truth: `substrate.ProducerFailed :: RuntimeError("OllamaResponder(deepseek-r1:8b) failed
  after 3 attempts: ReadTimeout")`. It is a **timeout** — an 8B reasoning model generating up to 8192
  tokens is too slow on this machine for the 120s call timeout — so there is **no agentic data** for
  r1 here, in either mode. Lesson (again): read the `ProducerFailed` error on the record; do not infer
  a capability finding from empty output. To evaluate r1 we need a longer timeout or faster hardware.
  (The narrower point survives: `--think` is model-specific, not a global — but r1 didn't test it,
  it timed out.)

**Caveat:** n=1 per model — behaviour *classes* observed once each, not rates.

---

### R-12 — Roster widening completed: the verify threshold is a CLOUD-frontier-thinking property

Filling R-11's gaps (n=1 each; anti-spin + recover-then-bail active):

| Model | tier | tool mix | outcome |
|---|---|---|---|
| `nemotron-3-super` | cloud, thinking | write, read×2, bash×2 | **VERIFIED** — `exit 0` |
| `deepseek-r1:8b` | local, reasoning | (none) | **EMPTY** FinalAnswer, 0 tool calls — does not engage the loop, at 600s (NOT a timeout this time) |

**Scoreboard so far (n=1 each — behaviour classes, not rates):**
- **VERIFY clean** (write→read→run→`exit 0`): `kimi-k2.6`, `glm-5.1`, `nemotron-3-super` — all cloud
  thinking+tools.
- **ATTEMPT then claim FALSELY**: `deepseek-v4-pro` (cloud thinking) — ran its code, got `exit 1`
  twice, declared success (R-11a).
- **NO verify (write-spin)**: `qwen3-coder:480b` (cloud, NON-thinking coder — the best coder by
  benchmark, R-7).
- **NO loop engagement (empty, 0 tools)**: `deepseek-r1:8b` (local reasoning) — R-12.

**Interpretation.** The agentic-verify threshold is, on this evidence, a property of the CLOUD
frontier thinking+tools models — not code-benchmark rank (the top coder is the worst agent) and not
the "thinking" tag alone: `deepseek-r1:8b` is thinking-tagged yet returns empty content and never
calls a tool in our seam. r1's failure is now characterised (empty answer / 0 tools at 600s, not a
timeout) but not root-caused — candidate: its reasoning routes into the thinking field, or Ollama's
r1 tools support is weak; a focused `achat_tools` probe on r1 is the follow-up. **"Best coder ≠ best
agent" holds, sharpened: agentic tool-use tracks the cloud frontier thinking models specifically.**

---

### R-13 — Synthesis: capability vs policy, and what SWE-bench structurally cannot measure

*A model that ties together R-7, R-11a, R-12, and the SWE-bench thread (KIT_DIARY 23/26). This is a
hypothesis that PREDICTS, not an n-measured law — flagged as such.*

- **Capability vs policy.** `qwen3-coder:480b` *can* call `bash` (it has the tool) — it just doesn't
  *decide* to. So its "won't verify" is a missing POLICY, not a missing CAPABILITY. A thinking model's
  chain-of-thought is functionally an internal policy that already contains "…and then check it
  worked." This dissolves the 36%-vs-69% tension: with a forcing harness supplying the verify policy
  externally, qwen's capability shows (~69% Verified, vendor claim, WITH an agent harness); with no
  forcing (our minimal SWE-bench scaffold, or the open hangman loop) its missing policy caps it
  (36% Lite / write-spin). The harness adds the DECISION to verify, not the ability. This is the
  enforce-vs-request axis (KIT_DIARY 32) restated as capability/policy.
- **SWE-bench, an "agentic" benchmark, is structurally blind to agency.** The `FAIL_TO_PASS` firewall
  removes iterate-until-green — the defining agentic move — so the score rewards localization +
  one-shot patch quality + best-of-N, and is near-blind to the self-verification policy that separates
  an agent from a code-completer. Our own project saw this (KIT_DIARY 23): the executing agent did not
  beat the focused one there because the axis that favors it is walled off. The headline "agentic
  coding" number is largely code-generation-under-localization; the agency part is unmeasured.
- **Substrate can measure exactly what SWE-bench can't — the trajectory.** The run record IS the
  trajectory as typed events, so you can score *did the model run its code, read the real result, and
  fix it* — per step, orthogonal to whether the final artifact is correct (KIT_DIARY 34). The hangman
  tool mix (`write→read→bash→exit0` vs `write×16`) already IS that measurement. `deepseek-v4-pro` is
  the clean orthogonality case: artifact-plausible ("proven working") while its trajectory shows
  `exit 1` twice (R-11a). Artifact grading passes it; trajectory grading fails it — different facts,
  and only the record has the second. Candidate: an **agency assay** — score the verify-loop behaviour
  across models, independent of output correctness.
- **The prediction (daily-driver payoff):** self-verifying thinking models should shine *most* exactly
  where SWE-bench can't measure them — open-ended coding on a real machine, iterate-until-your-tests-
  pass — while the raw coder needs the harness to carry it. Testable; it is the cockpit use case, not
  the benchmark one.

**Caveats:** the agentic runs are n=1 behaviour-classes; the 69% is a vendor claim; the capability/
policy split is a model of the evidence. But it is coherent across four independent findings and it
*predicts* — which is why it is worth recording and testing (see R-14, the R-11a demonstration).

---

### R-14 — The R-11a check built + verified; the could-fail test caught a real bug

Built the structural "refuse a `done` answer when the last bash exited non-zero" check (externalize
the verify policy): on a done-attempt with a failed last run, re-prompt once; if the model still
insists, mark the FinalAnswer `[unverified — last run exited non-zero]` so the record can't launder a
false "proven working." Recovery path: if the re-prompt yields a tool call, the loop continues.

- **The live demonstration was INCONCLUSIVE.** This run of `deepseek-v4-pro` succeeded on the first
  bash (`exit 0`), so its "built and working" was TRUE and the check never fired — n=1 stochasticity;
  the R-11a false-claim didn't recur. A run where the model happens to succeed cannot demonstrate a
  guard against failure.
- **So verification is a DETERMINISTIC reproduce-then-kill**, independent of model luck: a stub
  `achat_tools` responder that runs `exit 3` then insists "done", asserting the FinalAnswer is marked
  `[unverified]` over the recorded `exit 3`.
- **That test FAILED first and caught a real bug.** Inside the live view the tool output is a
  `mappingproxy` (sealed record state), not a `dict`, so the original `isinstance(out, dict)` silently
  never fired — it passed on `read_record`'s plain-dict payloads but not in the running loop. Fixed to
  `isinstance(out, Mapping)`. This is the could-fail test doing its job: had I trusted the live run
  (which "worked"), I'd have shipped a guard that never triggers.

Result: enforce-vs-request demonstrated structurally — the harness refuses an unverified "done",
independent of the model (R-13's prediction, on the record). Open bound: whether the re-prompt
CONVERTS a resistant model needs a run where a real model actually fails then insists (stochastic to
catch). Process near-miss, recorded: I reverted a scratch debug print with `git checkout <file>`,
which also wiped the uncommitted R-11a code in that file — re-applied it. Never `git checkout` a file
carrying uncommitted work to undo a temporary edit.

---

### R-15 — r1's no-engagement root-caused: it routes everything into `thinking`

A single `achat_tools` probe to `deepseek-r1:8b` (`think=False`, trivial "use the bash tool to run
`echo hi`") settles R-12's open question. Raw message: `content: ''`, `tool_calls: None`, and a
populated `thinking` field that REASONS about using bash ("We are going to use the `bash` command…")
but never emits the call. So r1:8b via Ollama's native `/api/chat` routes its whole output into the
thinking field — empty content, no tool_calls — and `think=False` does NOT stop it for this model.
The parser sees empty content + no tool_calls → "answer" with empty text → the empty FinalAnswer / 0
tools of R-12.

**It is an Ollama/r1 INTEGRATION limit, not a substrate loop bug and not a plain capability gap:** r1
has the INTENT (its thinking says "use bash") but the routing never surfaces a tool_call. Remediations,
none built: (a) fall back to the `thinking` field as the answer when content is empty — recovers the
reasoning as TEXT, but yields no tool USE (the call isn't in thinking either); (b) r1-family models
may need a JSON-in-content convention, but the tools-schema call didn't elicit one; (c) treat r1:8b as
UNSUITABLE for the native tool loop — a clean negative control: "thinking"-tagged ≠ "tool-using". The
roster's local-reasoning tier is therefore UNVALIDATED on real hardware; a different local reasoning
model (or a larger r1) would need testing.

---

### R-16 — The agency leaderboard: "best coder ≠ best agent" made measurable

`scripts/agency_assay.py` runs the hangman task across the roster and scores each run's TRAJECTORY
(`score_agency`, the R-14-tested scorer), orthogonal to artifact correctness. First board (n=1 each,
same task, 2026-07-02):

| Model | thinking | label | score | ran / saw0 / resil / honest | spin |
|---|---|---|---|---|---|
| `kimi-k2.6` | yes | VERIFIED | **100** | ✓ ✓ ✓ ✓ | 1 |
| `glm-5.1` | yes | VERIFIED | **100** | ✓ ✓ ✓ ✓ | 1 |
| `nemotron-3-super` | yes | VERIFIED | **100** | ✓ ✓ ✓ ✓ | 1 |
| `deepseek-v4-pro` | yes | VERIFIED | **100** | ✓ ✓ ✓ ✓ | 1 |
| `qwen3-coder:480b` | NO | NO_VERIFY | **50** | · · ✓ ✓ | 4 |

The assay DISCRIMINATES cleanly: the four thinking cloud models score a perfect agency 100 (wrote,
ran, saw exit 0, honest); the best coder by benchmark scores 50 / NO_VERIFY, with the write-spin
captured numerically (`spin=4`, `ran=·`). **"Best coder ≠ best agent" is now a number, not an
anecdote** — and it is ORTHOGONAL to artifact correctness (qwen writes fine code; it just never runs
it). This was also reproduced LIVE in the substrate-ui cockpit the same day: qwen3-coder:480b
write-spun on "demonstrate tool use", the anti-spin guard + recover-then-bail caught it, exactly as
the board predicts.

Honest reads:
- **n=1 each — a snapshot, not rates.** Notably `deepseek-v4-pro` scored VERIFIED 100 here but
  ATTEMPTED-with-a-false-claim in R-11a (succeeded first-try this run, false-claimed last run). The
  assay correctly reflects the PER-RUN trajectory; v4-pro's agency is VARIABLE, which is itself a
  finding. Rates need n>1 (loop the assay).
- The score caps the coder at 50 by design (ran + saw_exit_zero = half the weight), so a write-spin
  cannot score like a verify — the discrimination SWE-bench's artifact grade structurally lacks (R-13).

---

### R-17 — Agency RATES: the thinking models are RELIABLE verifiers, and "variable" was overstated

Looping the assay (`--repeats`) turns R-16's n=1 snapshot into rates:

| Model | runs | VERIFIED | mean | distribution |
|---|---|---|---|---|
| `kimi-k2.6` | 3 | 3/3 | 100 | VERIFIED:3 |
| `deepseek-v4-pro` | 5 | 5/5 | 100 | VERIFIED:5 |

- **Robust, not luck.** At n=5 `deepseek-v4-pro` verified clean every time; kimi 3/3. The thinking-
  model verify behaviour holds across repeats — R-16's 100s were not first-try flukes.
- **Correction to R-16's "variable agency."** Across R-11a + R-16 + this n=5, `deepseek-v4-pro`
  verified cleanly ~6 times and false-claimed exactly ONCE (the original R-11a run). So it is a
  RELIABLE verifier that occasionally false-claims (~1/7 observed), not the coin-flip I called it.
  Overstated on n=1; the rates corrected it. (The claim ledger's "n=1 is a snapshot not a rate" biting
  its own author again — the right move was exactly this: loop it.)
- **The R-11a CONVERSION case was NOT caught.** None of these runs failed-then-insisted — they simply
  succeeded, so the re-prompt never had a resistant model to convert. Catching it needs a
  FAILURE-INDUCING task (one these models actually stumble on), not more repeats of an easy one — a
  named next step, not a silent gap.
- **`qwen2.5-coder:7b` → NO_ENGAGE, VERIFIED (clean full trace).** It emitted a prose preamble
  ("Let's start by creating the Hangman game…") as its FinalAnswer and called ZERO tools. So the two
  coders fail DIFFERENTLY: the 480B over-engages (write-spin, NO_VERIFY), the 7B under-engages (prose,
  NO_ENGAGE). (My earlier confounded inspection had grabbed an in-progress cloud record — re-ran clean
  before recording, per the ledger.)
- **The assay's taxonomy is grounded — every label has a real exemplar:** VERIFIED = the cloud thinking
  models; ATTEMPTED (false-claim) = deepseek-v4-pro (rare); NO_VERIFY (write-spin) = qwen3-coder:480b;
  NO_ENGAGE (prose, 0 tools) = qwen2.5-coder:7b. A four-way behaviour taxonomy, each seen in the wild.

---

### R-18 — Chasing R-11a induced a FAILURE — and caught R-13's prediction live instead

To force the R-11a conversion I seeded a program with a guaranteed runtime bug (`compute` undefined)
and tasked "run it, fix it, re-run to confirm." Both thinking models **self-recovered honestly**:

| Model | bash exits | trajectory |
|---|---|---|
| `deepseek-v4-pro` | `1 → 0 → 1 → 0` | ran, failed, read, fixed, ran clean, hit a SECOND failure, fixed again, VERIFIED — two debug cycles, honest final |
| `kimi-k2.6` | `1 → 0` | ran, failed, diagnosed the missing function, wrote the fix, re-ran clean, honest final |

- **R-13's central prediction, CONFIRMED LIVE.** Self-verifying models run the *iterate-until-green*
  loop — the defining agentic move SWE-bench's firewall structurally removes — on a failure I forced,
  and they report honestly. `deepseek-v4-pro` did it through TWO cycles. This is the daily-driver loop
  working, and it is exactly what an artifact-grading benchmark cannot see.
- **The R-11a CONVERSION stays uncaught, now with a structural reason.** A model capable enough to be
  driven agentically SELF-recovers *before* declaring done, so the check has nothing to convert —
  inducing a failure makes it MORE likely to fix-and-verify, not to false-claim. The false-claim is a
  rare deviation (v4-pro ~1/7, R-17). The conversion MECHANISM is proven deterministically (the
  `test_reprompt_CONVERTS_...` stub), so R-11a is a real safety net for the rare case; a LIVE
  conversion needs a *reliably-false-claiming* (weaker/misaligned) model or a rare-event hunt — named,
  not a gap. The chase produced the more valuable finding, not the target.

**Caveat:** n=1 each; these are behaviour observations, not rates.

---

### R-19 — The agency SUITE: agency is a model × TASK-SHAPE interaction, not a pure model property

Running the suite (`build_hangman` | `fix_runtime_bug` [seeds a broken file] | `build_and_test`):

| Model | build_hangman | fix_runtime_bug | build_and_test | mean |
|---|---|---|---|---|
| `kimi-k2.6` (thinking) | VERI 100 | VERI 100 | VERI 100 | **100** |
| `glm-5.1` (thinking) | VERI 100 | VERI 100 | VERI 100 | **100** |
| `qwen3-coder:480b` (coder) | NO_V 50 | **VERI 100** | NO_V 50 | **67** |

- **Thinking models are robust ACROSS shapes** (VERIFIED 100 on all three) — not a hangman fluke.
- **The finding (my prediction of NO_VERIFY-across-the-board was WRONG, and the suite caught it):**
  qwen3-coder — the write-spinner — VERIFIED the `fix_runtime_bug` task while spinning the two
  BLANK-PAGE builds. Why: that task SEEDS a broken file, so there is nothing to spin — the natural
  action is READ → fix → RUN. The task STRUCTURE pulls even a poor agent into the verify loop; a blank
  page lets it produce-forever. So **agency is a model × task-shape interaction**, and a single hangman
  task would have flatly stamped qwen `NO_VERIFY` and missed this. Measure across SHAPES.
- **Ties R-13 / SWE-bench together.** SWE-bench = patch EXISTING code = the seeded-fix shape — exactly
  where qwen engages and verifies. That explains qwen's real ~36% on SWE-bench (fix-existing) versus its
  write-spin on blank-page agentic tasks: the task shape SUPPLIES the verify policy the model does not
  hold (the capability/policy split of R-13, sharpened — a seeded artifact is a structural nudge, like a
  harness enforcing the loop).

**Caveat:** n=1 per cell; qwen's `fix_runtime_bug=VERIFIED` is a single run. But the mechanism (a seeded
file removes the blank-page spin) is coherent and predicts — worth an n>1 confirmation.

---

### R-20 — The rates board (n=3): R-19's caveat resolved, and the shape boundary sharpened

Re-ran the whole suite at **n=3 per cell** (`agency_assay.py --suite --repeats 3`, cells = VERIFIED-rate
+ mean-score). This is the defensible board — R-19's n=1 classes turned into rates.

| Model | build_hangman | fix_runtime_bug | build_and_test | mean |
|---|---|---|---|---|
| `kimi-k2.6` (thinking) | 3/3 · 100 | 3/3 · 100 | 3/3 · 100 | **100** |
| `glm-5.1` (thinking) | 3/3 · 100 | 3/3 · 100 | 3/3 · 100 | **100** |
| `deepseek-v4-pro` (thinking) | 3/3 · 100 | 3/3 · 100 | 3/3 · 100 | **100** |
| `nemotron-3-super` (thinking) | 3/3 · 90 | 3/3 · 100 | 3/3 · 100 | **97** |
| `qwen3-coder:480b` (coder) | **0/3 · 50** | 3/3 · 100 | **3/3 · 100** | **83** |

- **The thinking roster is a solid VERIFIED wall — now at n=3, not one lucky run.** kimi/glm/deepseek-v4-pro:
  9/9 VERIFIED each. nemotron: 9/9 VERIFIED too; its build_hangman *mean* dips to 90 (a sub-component of
  the score, not a label miss — still ran and saw exit 0 every time). The n=1 "these verify" claim held.
- **R-19's caveat is discharged.** qwen's `fix_runtime_bug` was a single VERIFIED run at n=1; it is now
  **3/3 VERIFIED**. The seeded-file mechanism reproduces — a broken artifact reliably pulls even the
  write-spinner into read→fix→run.
- **The shape boundary is NARROWER than R-19 read.** At n=1, qwen was NO_V on *both* blank-page builds
  (`build_hangman` and `build_and_test`). At n=3, `build_and_test` flips to **3/3 VERIFIED** — the n=1
  NO_V there was noise. So qwen fails ONLY the pure `build_hangman` (0/3), and verifies whenever the task
  either seeds a broken file (`fix_runtime_bug`) or names testing as an explicit step (`build_and_test`).
  The differentiator is not "build vs fix" — it's **whether the task STRUCTURE supplies the verify step**
  (a broken seed, or "and test" in the spec) versus leaving the model to self-initiate verification of its
  own fresh output. `build_hangman` asks in prose ("then PROVE it works by running it") and qwen ignores
  it 0/3 — prose doesn't move it; structure does. This is R-13's capability/policy split at cell
  resolution: the policy qwen lacks can be supplied by the task shape, and *only* by structure, not words.
- **Ties SWE-bench (unchanged, now firmer).** SWE-bench = patch-existing = the seeded-fix shape, exactly
  qwen's 3/3 column — consistent with its real ~36% there against its blank-page spin.

**Status:** the board is the R-19 → R-20 promotion — n=3, five models, three shapes, one ERROR-free grid.
Bench: `scripts/agency_assay.py --suite --repeats 3 [--think]`; scorer `topologies/tool_loop/agency.py`.

---

## Model roster — what we test against, and why

The tool loop is written against a `Responder`, so any model is a candidate. But suitability for the
AGENTIC task (drive tools → read results → verify → stop) is not raw capability, and the capability
tag is **necessary but not sufficient**: `qwen3-coder:480b` advertises `tools` and still will not
verify its own code (R-7). So we grade on our own axis: (1) does Ollama declare a `tools` capability
(the native tool-calling path needs it); (2) is it code-tuned or agentic; (3) does it have a
`thinking` mode — the live R-7 hypothesis, that a reasoning model plans the verify step a pure coder
skips. Capabilities below are from `curl /api/show` — Ollama's own declaration for the installed
manifest, verified 2026-07-02. Benchmark numbers are **vendor/aggregator claims** (sources at the
end), not our measurements; the arena is the only test that counts for our task.

### Suitable — LOCAL (on-machine, fast iteration)

| Tier | Model | Caps (verified) | Why | Our data |
|---|---|---|---|---|
| Workhorse | `qwen2.5-coder:7b` | tools, insert | code-tuned, ~5 GB | moderate; over-calls on multi-step; emits calls as JSON-in-content (parser handles) |
| Reasoning | `deepseek-r1:8b` | tools, thinking | a LOCAL thinking+tools model — tests the R-7 verify hypothesis cheaply | untested on the loop; R1 `<think>` blocks may interfere — to measure |
| Stronger coder (to pull) | `qwen2.5-coder:32b` (or `:14b`) | tools | bigger local coder for a higher local ceiling | not pulled; hardware-dependent |

### Suitable — CLOUD (via `ollama signin`, big models)

| Tier | Model | Caps (verified) | Why | Our data / source |
|---|---|---|---|---|
| Top coder | `qwen3-coder:480b-cloud` | tools | best raw code (~69.6% SWE-bench Verified) | **GREAT coder, WEAK agent** — fails the verify loop (R-7); NO thinking mode |
| Reasoning | `deepseek-v4-pro:cloud` (or `glm-5.1:cloud`) | tools, thinking | thinking+tools; DeepSeek V4 ~70–73% — the direct R-7 ceiling test | untested on the loop |
| Agentic specialist | `kimi-k2.6:cloud` | tools, thinking, vision | Kimi K2 family leads agentic multi-attempt (~71.6%) — strongest verify-loop candidate | untested on the loop |

(`nemotron-3-super:cloud` is an alternate thinking+tools cloud model, already pulled.)

### Unsuitable — negative controls (run these to confirm WHAT breaks and WHY)

| Model | Caps (verified) | Why unsuitable | Use as |
|---|---|---|---|
| `llama3:8b` | completion ONLY | NO `tools` — can't native tool-call (forced onto the text/JSON fallback); not code-tuned | control for the fallback path + "no tool support" |
| `llama3.2:1b` | tools | too weak: over-calls, doesn't recognize "done", needs the max_steps backstop | fast PLUMBING smoke only; weak-capacity baseline |
| `qwen2.5:7b-instruct` | tools | has tools but general, not code-tuned | control for "tools ≠ coding suitability" |

### The experiment this roster sets up

R-7's ceiling was a *non-thinking* coder. The roster deliberately pairs a thinking model against a
non-thinking one at the cloud tier (`kimi-k2.6` / `deepseek-v4-pro` vs `qwen3-coder:480b`) and gives a
local reasoning model (`deepseek-r1:8b`) for cheap iteration. **Next experiment:** run a thinking+tools
model on the hangman build task. If it write→run→verifies where `qwen3-coder:480b` would not, the
ceiling is "coder without agentic reasoning," not "models can't do this" — and it validates the
recover-then-bail design by showing a model that actually recovers.

*Sources for the benchmark claims (aggregators/press, treat as claims not measurements): kilo.ai and
morphllm.com open-source coding roundups (2026); turingpost.com Chinese-models guide; deeplearning.ai
The Batch on Kimi K2.6; akitaonrails.com LLM benchmarks (May 2026).*

### Backlog — a broader command-line-model catalogue

Beyond Ollama: any command-line model drives the loop via `CliResponder` (Substrate owns the tools,
so even a plain prompt→text CLI becomes tool-using). We want a standing catalogue so we never
re-research it — the commercial agent CLIs (Claude `claude -p`, proven live; Gemini `gemini -p`,
wired, needs auth; Grok and others as they ship CLIs) and open models we run or port to run locally.
**Deferred** — current focus is the Ollama/local path (llama + the coder models above). Filed here so
the shape is captured; build the catalogue once the model path is settled.

---

## Distillation targets (what leaves this doc)

- **BLACKBOARD:** current state — the tool loop now has an anti-spin guard + recover-then-bail; the
  arena is a working discovery harness; the model ceiling (R-7) is the current frontier.
- **KIT_DIARY / ADDENDUMS:** the methodology findings — the discovery harness (Addendum D, filed);
  "a prompt is a request, substrate can enforce" and "prefer the observation over the principle when
  they conflict" (R-5/R-6) are diary candidates not yet filed.

---

## Claim ledger — verified vs unverified (2026-07-02)

A standing honest audit, run under the SDD skeptic challenge. **Verified** = a reading *outside my
control* would differ if the claim were false (a live run's real fs/bash/oracle output, an independent
tool, rendered pixels, a diff vs source-of-truth). Everything else is named plainly. Kept current;
this is the list to attack, not trust.

### Verified — outside-my-control evidence (this session)
- Byte-cap kills the glob-wedge (arena live + reproduce-then-kill). · Parser batched-call fix (live
  flip 0-tools→executing + test). · Anti-spin guard (live `16→2` writes). · Recover-then-bail (live
  `4`+truthful bail + tests). · Workspace rooting: rel→root / absolute passthrough / bash cwd (real fs
  smoke). · **Server→workspace→file** (live, counter-checked: file in `/tmp/ws-verify`, none leaked to
  server cwd). · **`/cwd` terminal** (structural E2E + perceptual screenshot showing `workspace =
  /tmp/agent-e2e`). · Empty-file marker (arena live). · R-9 kimi write→read→run→verify (n=1, real
  `exit: 0` + `=== HANGMAN ===`). · R-10 discipline prompt inert (n=1 A/B). · SOFT regex (12 real
  logs, 0 false positives). · Container arena reaches host Ollama (live). · 17 tool_loop + 6 reference
  + 29 server tests (independent pytest, run this session). · ruff+mypy over `src/substrate` (95 files).
- **Agency rates board, n=3 (R-20)** — real cloud trajectories, five models × three shapes, ERROR-free:
  thinking roster 9/9 VERIFIED each (nemotron mean 97), `qwen3-coder:480b` 0/3 on the pure blank-page
  build but 3/3 on the seeded fix AND on build-and-test. Reading is outside my control (each run's own
  ToolCall/ToolResult/FinalAnswer record scored by `score_agency`). Discharges R-19's n=1 caveat.
- **`/diff` worktree surface** — `_worktree_diff` shows an edit + a new file surfacing in both the diff
  text and the name-status list; server test exercises it against a real temp git worktree (29th test).

### Unverified / weaker (this session)
- **`replace_all` coercion, out-of-range read marker:** could-fail UNIT TEST only — adequate for a pure
  function, but no independent/live channel.
- **`edit_file` line-prefix warning:** prompt text; no behavioral test that a model heeds it —
  UNVERIFIED as an effect.
- **"CI is green":** was FALSE and pre-existing (red since the 2026-06-27 commit) — now **FIXED**
  (2026-07-02, Architect authorized the repo-wide fix: "CI can't be broken"). Three latent gate
  failures, none introduced by this session's features, all surfaced only by running the CI-equivalent
  gates locally (my session gates were scoped to `src/substrate`; CI runs the whole repo): (1) two
  `F401` unused imports in assay scripts; (2) `ruff format --check` drift across 61 files (assay/,
  swebench tests, scripts) — not version skew (reproduced locally, ruff 0.15.17); (3) a latent mypy
  error in `swebench_solver/assemble.py` (a `# type: ignore` on the wrong line — both unused AND not
  suppressing — invisible until Lint/Format passed and the Type gate became reachable). All three
  fixed → CI now **reaches the Tests gate and passes on `macos-py3.12`** (my local env).
  Then a FOURTH, deeper pre-existing failure the gate fixes exposed — `test_committed_record_is_current`
  for three bundled topologies (`intel_asymmetry`, `natural_conversation`, `prisoners_dilemma`) whose
  committed records did NOT regenerate byte-identically across Python versions (divergence at seq 0
  `RunStarted`; passed on py3.12, failed on 3.13/3.14). **ROOT-CAUSED + FIXED.** My first guess (an
  unsorted set in the manifest) was WRONG — reproducing on a real py3.14 env and diffing the actual
  manifest bytes found it: the differing field is the msgspec-schema `description`, i.e. the Struct's
  DOCSTRING, and **CPython 3.13 dedents docstrings at compile time**, so a multi-line docstring
  serializes to different bytes on 3.13/3.14 vs 3.12. Fix: strip `description` from the schemas
  embedded in the RunStarted manifest (`runtime._manifest`) — the manifest pins the STRUCTURAL contract
  (types/required/versions), not prose; regenerated all 12 committed records. Verified cross-version:
  the real `test_committed_record_is_current` passes on **py3.12 (29) AND py3.14 (29)**, full py3.12
  suite 565 passed. (The "unsorted set" guess is exactly why you reproduce and diff instead of infer.)
  **CI OBSERVED GREEN across the full matrix** (run `3ed3f1b`, all 6 cells ubuntu+macos ×
  py3.12/3.13/3.14 = `success`) — confirmed by watching the run conclude, not from a local or
  single-cell green. This moves "CI is green" from FALSE (all session) to TRUE (observed). Follow-up
  still worth doing: pin ruff in CI so the formatter can't re-drift.
  **Self-inflicted repeat:** I wrote finding 33 ("run what CI runs, watch CI") and then said "CI
  fixed" from a single-env local green (`macos-py3.12`) before the full matrix concluded — the same
  class of error one turn later, now across the OS/Python matrix rather than scoped-vs-whole-repo.
- **"Nothing else regressed" after the ~40-file adapter-move refactor:** now VERIFIED — full local
  suite **565 passed, 1 skipped** (2026-07-02, 4m43s), whole-repo `ruff check` clean, `mypy --strict`
  clean over 95 files. (Moved to verified; kept here as the record of the gap that was open.)

### Inherited / not re-verified this session
- **CliResponder:** the mechanism is verified (stub test); "Claude drives FULL_SUITE live" is inherited
  from the pre-compaction summary, NOT re-observed this session. Gemini never worked (auth).
- **Capability eval** (poem/doc/software × tiers): from a prior run, not re-run.
- **Model roster suitability:** only `qwen3-coder:480b` (fails, R-7) and `kimi-k2.6` (verifies, R-9) are
  actually tested on the agentic loop. `deepseek-v4-pro` / `glm-5.1` / `deepseek-r1:8b` / `nemotron` /
  `qwen2.5-coder:7b` verify-behaviour is UNVERIFIED — the roster is a plan, not a result.
- **Benchmark numbers** in the roster: vendor/aggregator claims, not our measurements.

### Project-level standing caveats (flagged, not re-audited here)
- SWE-bench 36% on Lite-300 is real (official-oracle graded), but the split is public+contaminated —
  the contamination-CLEAN rate is unverified (dating deferred).
- N-PERF-1 is machine-dependent; there is no single true number.
- Every n=1 / n=5 model run is exploratory, not a rate — the power floor gates any reported number.
- The "cockpit / daily-driver" vision is aspirational, not a verified capability.

**The process finding under it all:** my local gates were scoped narrower than CI (src-only ruff vs
whole-repo), and I ran targeted test subsets rather than the full suite after a broad refactor. The
green I read was real but *narrower than the claim*. The fix is a habit: run the CI-equivalent gate
(bare `ruff check`, full `pytest`) and observe CI, before saying "clean."

---

*process/RESEARCH.md — started 2026-07-02. Append; never delete a refuted hypothesis (the refutation
is the finding). Thread 1 open: the model ceiling (R-7) is the live frontier.*

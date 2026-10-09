# The tool-loop agent — explainer + runbook

*How to run a real local LLM as an agent driving substrate's tool loop: the model reads a task, calls
tools, reads the results, and either calls another tool or answers — every step a typed event on the
run record. Built and verified live against Ollama on 2026-07-01. Register: plain and concrete.*

*Status of the surrounding vision: this is the working programmatic seam (M1), now driven from a
terminal-first `substrate-ui` (`chat` to talk, `/exit` to leave, a model picker) and by any
command-line model via `CliResponder` (Claude live). A container test arena (§7) runs it wild for
edge-case discovery. A per-conversation workspace root and an opt-in per-tool approval gate remain
named-but-unbuilt — see §5.*

---

## 1. What it is

The classic "AI agent with tools" loop — model → tool → model → … → answer — expressed as a Substrate
topology. The difference from a hand-rolled agent loop: **the loop, the conversation, the tool calls,
and the replay are the runtime's job, not the caller's.** Each model turn and each tool run is its own
Producer instantiation, so every step is an independently inspectable, replayable typed event on the
record. A failed tool is an observation (a typed `ToolResult(ok=False)` the model reads), never a
crash. The step budget ends the run gracefully on a `FinalAnswer`.

You hand it: a **task** (plain English), a **tool suite** (the real `FULL_SUITE` — read/write/edit/
grep/glob/bash/web_fetch, or your own), and a **model** (any local Ollama model). You get back: a run
record showing exactly what the model did.

## 2. How it works (the seam)

Three moving parts, all on the log:

- **`model` Producer** — reads the task + the tool results so far, calls the model, and emits either a
  `ToolCall` (name + args) or a `FinalAnswer`. Bounded by `max_steps`; at the budget it is fired once
  more with tools disabled so the run *always* ends on a `FinalAnswer`, never a silent stall.
- **`tool` Producer** — runs the named tool on each `ToolCall` and emits a `ToolResult`. Unknown tool,
  missing/ambiguous args, an exception, or a non-encodable return all come back as a typed
  `ToolResult(ok=False)` with a clear `error` — the model reads it and can correct.
- **Triggers** — `run-tool` (each `ToolCall` → its tool), `continue` (each `ToolResult` re-fires the
  model), `wrap-up` (at the budget, fire the model with tools off), and termination on the first
  `FinalAnswer`.

**The model seam** is a `Responder` (`substrate.adapters` — `OllamaResponder` for a real local LLM,
`DeterministicResponder` for the CI stand-in). The topology is written against the Responder, not any
model; you choose the model by which Responder you hand it.

**Native tool-calling, tolerant across models.** `OllamaResponder.achat_tools(prompt, tools)` passes the
tool JSON schemas to Ollama's `/api/chat` `tools` field and returns the raw reply. `parse_tool_call`
then handles it **two ways**, because real models differ — verified live: `llama3.2:1b` returns a
native `tool_calls` array; `qwen2.5-coder:7b` emits the *same* call as a JSON object in `content`. The
parser reads native `tool_calls` first, falls back to a JSON-in-content parse, and maps the model's
**named** args back to the tool's positional signature. Building only the native path would silently
fail on qwen — so both are handled and both are tested against the captured real shapes.

## 3. Runbook

### Prerequisites

- **Ollama running** on `http://localhost:11434` and a model pulled:
  ```bash
  ollama serve            # if not already running
  ollama pull llama3.2:1b        # fast, native tool_calls, weak (over-calls)
  ollama pull qwen2.5-coder:7b   # more capable; emits calls as JSON-in-content
  ```
- The substrate venv (run everything through `uv run` from the `substrate/` repo, so `substrate`
  imports and the `openai-compat` extra — httpx — is present).

### Run it — one command

The committed entrypoint `scripts/run_tool_agent.py` is the fastest way (`{workdir}` is substituted
with a scratch dir the agent may use):

```bash
cd substrate
# mutating suite (edit/write/bash) — point it at a scratch dir:
uv run python scripts/run_tool_agent.py --model qwen2.5-coder:7b \
    --task "Create a file at {workdir}/out.txt containing exactly: substrate works. Then answer."

# inspect-only (no edit/write/bash), a weaker/faster model:
uv run python scripts/run_tool_agent.py --model llama3.2:1b --read-only \
    --task "Glob '**/*' under {workdir} and tell me how many files there are."
```

Flags: `--model` (any Ollama model), `--task` (`{workdir}` substituted), `--workdir` (default: a temp
dir), `--max-steps` (tool-call budget), `--read-only` (drop edit/write/bash), `--max-tokens`. It prints
each ToolCall/ToolResult/FinalAnswer and where the full replayable record landed.

### Run it — from Python

The agent is the `tool_loop` topology in walkthrough mode with a real Responder and the real suite:

```python
import asyncio
from pathlib import Path
from substrate.api import Runtime, read_record
from substrate.adapters import OllamaResponder
from substrate.topologies.tool_loop import tool_loop_topology
from substrate.topologies.tool_loop.tools import FULL_SUITE

async def main() -> None:
    workdir = Path("/tmp/agent-run")          # a scratch dir the agent may write into
    record = workdir / "record"
    result = await Runtime(record).run(
        tool_loop_topology(
            model=OllamaResponder("qwen2.5-coder:7b", max_tokens=256),
            walkthrough=True,            # real model, not the CI stand-in
            deterministic=False,         # real I/O tools => not byte-reproducible (honest)
            tools=FULL_SUITE,            # read/write/edit/grep/glob/bash/web_fetch + calculator
            task=f"Create a file at {workdir/'out.txt'} containing exactly: substrate works. "
                 "Use write_file, then give a one-line final answer.",
            max_steps=6,
        )
    )
    print("status:", result.status)
    for e in read_record(record):
        if e["kind"] in ("ToolCall", "ToolResult", "FinalAnswer"):
            print(e["kind"], e["payload"])

asyncio.run(main())
```

Run it: `cd substrate && uv run python your_script.py`.

### Read what happened

- **Programmatically:** `read_record(record)` yields every event — `ToolCall` (tool + args),
  `ToolResult` (output/ok/error), `FinalAnswer`, plus the runtime lifecycle events. This is the ground
  truth: what the model actually did, replayable.
- **Visually:** point the console at it — `cd substrate && uv run python
  ../substrate-ui/server.py --port 8799`, open `http://127.0.0.1:8799/`, and the run's graph + event stream +
  scene render from the same record. (The console reads records; it does not yet *drive* the agent —
  §5.)

### The knobs (`tool_loop_topology`)

| arg | meaning |
|---|---|
| `model` | the `Responder` (e.g. `OllamaResponder("llama3.2:1b")`); `walkthrough=True` defaults it to `llama3.2:1b` |
| `walkthrough` | `True` = real model; `False` = the deterministic CI stand-in (calculator) |
| `deterministic` | must be `False` with real-I/O tools (they mutate the host / hit the network) |
| `tools` | `FULL_SUITE`, `CALCULATOR`, or your own `dict[str, Tool]` |
| `task` | the plain-English instruction the model works toward |
| `max_steps` | tool-call budget; at the budget the model answers with tools off |

### Choosing a model

- `llama3.2:1b` — fast, emits **native** `tool_calls`, but weak: it over-calls and doesn't reliably
  recognize "done" (the `max_steps` wrap-up backstops it).
- `qwen2.5-coder:7b` — more capable; emits calls as **JSON-in-content** (the parser handles it).
- Cloud tags (`qwen3-coder:480b-cloud`, etc.) work through the same seam once `ollama signin` is done.

## 4. Known behaviors (honest)

- **Small models over-call.** Both llama and qwen re-called `write_file` several times before the
  wrap-up forced a final answer — they don't reliably notice the task is done. The file was written
  correctly; the inefficiency is model/prompt quality, not a defect in the loop. Mitigate with a
  stronger model, a tighter task ("call write_file exactly once, then answer"), or a lower `max_steps`.
- **Under-specified or ambiguous calls fail cleanly.** A missing required arg returns
  `write_file: missing required argument(s): text`; an `edit_file` `search` that isn't unique returns
  `search text is not unique … add surrounding context`. These are typed observations the model reads
  and can correct — not crashes and not silent mis-edits.
- **Determinism.** A walkthrough run is never stamped deterministic (a real model isn't reproducible),
  so it doesn't threaten the committed CI records, which use the pure calculator suite.

## 5. The workspace — where the agent operates

`FULL_SUITE` is **autonomous by design**: `edit_file`, `write_file`, and `bash` act on the filesystem
directly, with no per-tool approval prompt — exactly like Claude Code operating in your project. That
autonomy is the point, not a hazard: it's what lets the agent actually do work. What it means today,
and where it's going:

- **Per-conversation workspace root (built).** `full_suite(root)` roots the tools at a working
  directory: relative paths and `bash` resolve inside it, absolute paths still go where you name them
  (pathlib's `root / "/abs"` yields `/abs`). This is ergonomics, not a jail — the autonomy is
  unchanged; the root just gives the agent a home instead of resolving against wherever the server
  launched. In the terminal, `cwd <path>` sets it (unset = the server's launch dir, the Claude-Code
  posture); the server accepts `?workspace=` and echoes it back so the terminal shows it; the runbook
  uses `--workdir`. `FULL_SUITE` (root=`.`) preserves the old cwd-relative behavior for existing callers.
- **Read-only when you only want to look** — the read-only subset (`read_file`/`list_dir`/`glob`/
  `grep`/`web_fetch`) is there for inspection without changes.

## 6. What's built vs next

Built (the working proof-of-concept):
- **The `substrate-ui` terminal drives it** — `chat` enters a conversation, you just type to talk, the
  model responds, `/exit` leaves; a model picker chooses the driver (default: the biggest OSS model).
  Multi-turn, context carried, animating in the graph.
- **`CliResponder`** — any command-line model drives the tools (Claude proven live; Gemini identical,
  needs its own auth).
- **Capability eval** — `scripts/eval_agent_models.py` runs real tasks (poem / doc / software) across
  Ollama model tiers, so a model's behavior (e.g. refusing to generate without a tool) is measurable.
- **Container test arena** (`Dockerfile.arena` + `scripts/agent_arena.py`) — see §7.

Next:
- **Opt-in per-tool approval** (`pause_await_input`) for operators who want a gate.
- **Read-before-edit precondition** (backlogged from Claude Code's leaked edit tool) — deferred: the
  uniqueness guard already fails a blind edit with the wrong `search`, so the marginal value is low
  and it needs conversation-scoped state the stateless tools don't carry (see `tool-loop-tool-suite.md`).
- **MCP** — importing best-in-class open-source tool servers alongside the owned built-ins (M2).

## 7. Wild testing in a container — edge-case discovery (NOT the product)

The product is **host-native and stays that way**: direct filesystem access, real autonomy,
exactly like Claude Code operating in your project. Containerizing the product would be pointless —
it needs your real machine, your files, your Ollama. The autonomy is the feature.

The **container is only a test arena**: a disposable place to let a model go *wild* with the real
`FULL_SUITE` and catch crashes and edge cases we'd never think to script — the way the
`glob '**/*.py'` → blob-offload → wedged-loop bug surfaced only when a real model demoed the tool
on a big tree. Destructive tool use costs nothing here: `docker rm` and it's gone.

- **The model stays on the host.** Only the agent loop and its tool side-effects run in the
  container; the model call goes back out to host Ollama via `OLLAMA_BASE_URL`
  (`http://host.docker.internal:11434`), which the `OllamaResponder` reads with no call-site change.
- **Build once, run wild:**
  ```bash
  cd substrate
  docker build -f Dockerfile.arena -t substrate-arena .
  uv run python scripts/agent_arena.py --model llama3.2:1b   # or any pulled model, repeatable
  ```
  It runs a matrix of deliberately open-ended / adversarial tasks (`glob-storm`, `build-app`,
  `recursive-grep`, `just-a-poem`, `self-destruct`, `ambiguous-edit`) each in its own throwaway
  container and tabulates **OK / CRASH** — CRASH being the *interesting* outcome (a scenario to
  reproduce-then-kill). Per-run logs land in `arena-logs/`.
- **A run is CRASH** when the loop did not finalise cleanly — a non-zero exit, or a
  `PredicateQuarantined` / `ProducerFailed` / `Traceback` on the record.

This is how we get to the errors and scenarios we've never seen: point real models at real tasks in
a place where they can break things freely, and read the record afterward.

---

*Cross-ref: `tool-loop-tool-suite.md` (the suite design + NEXT), `tool-suite-audit-round1.md` (the
tool-quality audit + the both-tracks/own-plus-MCP decision), `interactive-agent.md` (the M1 theory
pass), `cockpit-design-round1.md` + `director-framing-round1.md` (where this is heading). Code:
`topologies/tool_loop/{__init__,tools}.py`, `adapters/models.py`, `scripts/run_tool_agent.py`.*

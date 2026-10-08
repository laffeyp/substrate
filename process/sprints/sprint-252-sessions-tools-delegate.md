# Sprint 252 — Sessions, tools and delegate

```yaml
---
id: 252
status: open
opened_at: 2026-10-08
pass_kind: remediation
roadmap: substrate-ui/process/planning/ROADMAP-2026-10-08-lens-audit-remediation.md
ledger_rows: 64
---
```

## why

A hard interrupt during a tool call fails the turn (probe); per_turn appears once per kept turn plus once (probe); a created session reports RUNNING; fan-out children default to the stub and escape the cascade (findings §2, §6).

## sources

- Hunt and Thomas, DRY.
- Roadmap decision: a created session is PARKED.

## scope (ledger rows)

Each row closes as named; a row the sprint cannot close halts the sprint.

| id | close | finding |
|---|---|---|
| F041 | fix | api.py:325-326 — comment (written sprint 107) says the kind modules are "leaf modules, so resolving them imports no topology code"; importing substrate.topologies.session.vocabulary runs substrate/topologies/session/_… |
| F043 | fix | session_registry.py:435 — create() writes status RUNNING for a session that has never run a turn. A created-but-unused session reads "running" (a turn in flight) until a boot scan or shutdown reclassifies it; the UI's… |
| F044 | fix | session_registry.py:116 — SessionManifest.workspace_shape is `str` though WorkspaceShape {flat, worktree, isolate} exists (80-87); web/reveal_component.ts:454 sends 'isolated' / 'sandbox' / 'flat'. Two vocabularies fo… |
| F045 | fix | session_registry.py:474-544 — the manifest's field list exists three times: the Struct, _manifest_to_dict, _manifest_from_dict (hand-written), plus _VALID_STATUS (1501) re-listing the enum. msgspec can convert both ways. |
| F046 | fix | session_registry.py:66-72 docstring says the STATUS_* aliases "stay … during the sweep"; they were dropped (2026-09-02 commit "drop STATUS_* aliases"). |
| F047 | fix | session_registry.py:721-727 turn_sync docstring: raises SessionEndedMidTurn when the session is already "ended"; since the 2026-09-25 ruling an ended session accepts turns (749-750). |
| F048 | fix | session_registry.py:833 `getattr(result, "status", "paused")` literal default; :972,974 producer kinds "model"/"tool" as literals (the session topology's kind names). |
| F049 | fix | session_registry.py:1431-1450 — _scan_record_status loads the entire record into a list to read its last envelope; boot_scan runs it for every non-ended session. |
| F050 | fix | session_registry.py:1022-1025 — interrupt waits 1.0 s for the loop to run the cancel closure; a busy loop (a long synchronous tool body? no — tools run in threads; a long predicate/view) returns None ("no turn in flig… |
| F051 | fix | session_registry.py (kernel package root) imports topologies.session, tool_loop.background (1200), and is re-exported by api: an application registry inside the kernel package. |
| F052 | fix | session_registry.py:1188-1194 _record_has_envelopes "back-compat wrapper" — check for callers. |
| F053 | fix | VERIFIED: _record_has_envelopes has no callers (dead). Workspace "shape": kernel WorkspaceShape{flat,worktree,isolate}; server.py:2241-2264 raw "flat"/"worktree"/"isolate"; server.py:1441-1443,1611 a fourth value "san… |
| F054 | fix | _daemon.py:14-18 — "not re-exported from substrate.api"; sprint 107 re-exported it as api.daemon_client. |
| F055 | fix | _daemon.py:8,65-69 — TCP fallback defaults to 127.0.0.1:8765. The app binds an ephemeral port (--port 0, sprint 079) and 8765 is the shakeout harness's default port; with the UDS absent, the CLI would talk to whatever… |
| F056 | fix | VERIFIED cli.py:1782-1809 — `substrate builder` opens ~/.substrate/studio.html or points at http://127.0.0.1:8765/studio.html; the server serves no studio.html (web/ has only reveal.html; no "studio" route in server.p… |
| F057 | fix | VERIFIED cli.py:1234-1240,1256-1269 — the REPL says `/list applications` and `/run` need "piece-E" endpoints "not yet shipped"; server.py serves GET /api/applications (3894) and POST /api/topology/<name>/run (2033). `… |
| F058 | fix | cli.py:1250-1251 — `/replay` prints "byte-identical replay at Level-3(a)"; Level 3(a) checks preconditions only (the `replay` command at 570-575 says "re-execution NOT performed"). |
| F059 | fix | cli.py:1326-1329 — sets SUBSTRATE_SESSION in the CLI's own environment "so the daemon's bash-tool subprocesses inherit" it; the bash tool runs in the daemon process, which this never reaches (no other reader of SUBSTR… |
| F060 | fix | cli.py:1455,1533-1567 — `session rm` refuses sessions "active in the last 24h" but measures created_at, not activity. |
| F062 | fix | cli.py:332,778 — `{"finalised": …, "failed": …, "paused": …}[result.status]` literal dict keys (the status gate cannot see dict keys); cli.py:850 kind "Grade" literal. |
| F072 | fix | bundles.py:3-15 — module docstring describes a "seed assembler"; lines 329-336 record that it was deleted in sprint 065. |
| F073 | fix | bundles.py:67-81 and 283-294 — the shipped-bundle locations (topologies/session/bundle, applications/<app>.bundle) are coded twice. |
| F075 | fix | testing.py:20 — a fifth copy of `_load(record)`. |
| F076 | fix | tool_loop/__init__.py:500-506,434-441,54 — the 12,000-byte tool-output cap and the `_step` default are justified by "an offloaded payload strips the loop-control fields off the frame"; since sprint 092a/095 triggers a… |
| F077 | fix | tool_loop/__init__.py:173,361,443,466 tool-name literals "bash"/"write_file"/"read_file" (TOOL_NAME_* constants exist in tools.py); :535,539,553,563,572 kind literals "ToolResult"/"ToolCall"/"FinalAnswer" in subscript… |
| F078 | fix | tools.py:509,532 — bash returns the FIRST 8,000 bytes of stdout and the LAST 2,000 chars of stderr with no truncation marker; a build whose failure is at the end of stdout reads as the head only. (read_file and grep w… |
| F079 | fix | background.py:144-191,165-172 — TaskTable._tasks is never pruned and every bash call (foreground too) creates two files under substrate_home()/bash/<sha1(owner)>/ that nothing deletes; deleting a session leaves them (… |
| F080 | fix | tools.py:613-617 — glob's describe says "(sorted)"; since sprint 107 results come in walk order (sorted within each directory). tools.py:104-106,288-290 repeat the stale blob-offload rationale. |
| F081 | fix | tools.py:586-672,688-767 — each tool's identity is written four times: the dict key literal, Tool.name (constant), the `describe` prose (which names the arguments), and the _TOOL_SCHEMAS entry keyed by a literal. Spri… |
| F082 | fix | VERIFIED delegate.py:432 — a fan-out child spec without `driver` defaults to "deterministic"; server.py:175 resolves that to the seeded DeterministicResponder, so the child "answers" stub[0]:<hash> and the fold report… |
| F083 | fix | delegate.py:445-456 — fan-out children are registered as ordinary sessions (they appear in the user's session list) with no composite_of link, so the parent's end/delete cascade never reaches them and nothing ends or … |
| F084 | fix | delegate.py:948-951 — schema tells the model timeout_seconds has "default 600.0"; the default is None since sprint 101. delegate.py:11-12 says bash uses subprocess.run(timeout=60) (bash is Popen with 120/600 since 101… |
| F085 | fix | delegate.py:974-977,987-990 — fan-out schema offers workspace_shape "flat \| worktree" (stored unvalidated) and `isolate` (ignored by _run_one); fan-out results report steps -1 always. |
| F086 | fix | delegate.py:713-718 — every delegate call counts the whole parent record to learn its last seq; the standing-session path (747-759, 787-792) reads the reviewer record twice. |
| F087 | fix | substrate_tools.py:40-46 — redefines the seven TOOL_NAME_* constants already defined in tools.py:67-73 (comment says "the migration never landed"; it landed in tools.py). Two copies. |
| F088 | fix | substrate_tools.py:216-218 — run_topology's describe tells the model timeout_seconds defaults to 600; _daemon.run_topology defaults to None since sprint 101. |
| F089 | fix | substrate_tools.py:189-206 — _extract_terminal_output reads without resolve_blobs; an application terminal payload over 16 KiB returns to the model as a $blob stub. |
| F090 | fix | substrate_tools.py:626-636 — list_records docstring says it walks `<records_root>/runs/*/` too; the code walks only the sessions directory. |
| F091 | fix | substrate_tools.py:522-524 — every inspect_record events page re-reads and blob-resolves the whole record. |
| F092 | fix | substrate_tools.py:13-15 cite tools.py:64 and :357 (stale line numbers); :287 "Budget cap,: both" (garbled). |
| F093 | fix | CONFIRMED session/__init__.py:1118-1128 — park-on-interrupt fires only when the cancelled producer is the MODEL. A hard interrupt during a tool call (what ctrl+c / Esc / quit / /end / delete send when a tool is live: … |
| F094 | fix | session/__init__.py:496,528,553,559 — every ModelReply carries model_usage={}; the session never records tokens or latency (ModelUsage and call_responder_metered exist, unused here). |
| F095 | fix | session/__init__.py:245 and tool_loop/__init__.py:55 — two _MAX_CONSECUTIVE_FAILS = 3 constants; session/__init__.py:3-20,389-393 docstrings describe scaffolded bodies and a deferred TOOL: parse path (both replaced). |
| F096 | fix | session/__init__.py:900,1038,1042,1055,1069,1084,1092,1137,1194 — kind literals "ToolResult"/"ToolCall"/"FinalAnswer"/"PromptComposed"/"InterruptRequested" beside vocabulary constants imported from .vocabulary for oth… |
| F097 | fix | session/__init__.py:85-103 — `all_completed` refused by regex over the composed policy NAME string. |
| F098 | fix | transcript.py:177-193,312-337 — the rolling window keeps K = budget / 800 turns from a fixed per-turn guess and never checks the rendered prompt's estimated size (tokens_estimated is computed, then only reported). A t… |
| F099 | fix | transcript.py:20-22 — "Real spend telemetry flows through ModelUsage on ModelReply"; ModelReply.model_usage is always {} (session/__init__.py). |
| F100 | fix | transcript.py:255-263 with server.py _build (per_turn prefixed into UserMessage.assembled_prompt) — the comment says per_turn "no longer injects here", but every rendered USER line uses assembled_prompt, which already… |
| F101 | fix | transcript.py:312-314 — every model firing (every step of every turn) reads and blob-resolves the whole record; :339-359 every firing after the window fills writes a new TranscriptCompacted (and renders the full trans… |
| F102 | fix | vocabulary.py:81,88-101 — BACKGROUND_TASK_ENDED is defined but missing from SESSION_KINDS, so is_session_kind("BackgroundTaskEnded") is False; the module says "eight" kinds (3, 293) and "seven" prompt sources (282) — … |
| F103 | fix | vocabulary.py:13-16 — claims "zero raw literals … outside this file"; session/__init__.py subscribes with "PromptComposed" (1038,1137) and "InterruptRequested" (1194) literals although PROMPT_COMPOSED exists. |
| F104 | fix | views.py:63 — ModelFailures compares producer kind to "model" (PRODUCER_KIND_MODEL exists). |
| F105 | fix | composer.py:5-31,88-92 — docstring: fires on UserMessage, reads a KindBuffer, "sprint 059 landing state" with positional seqs, telemetry "lands on ModelReply.model_usage" — all superseded (FragmentCohort, chained trig… |
| F106 | fix | parent_context_producer.py:41 — slice cap 64 KiB "matches delegate.py's default"; delegate.py:65 uses 8,192. :44-107 copies delegate's _format_context_event/_extract_context_slice (acknowledged at :61-63); :20-25 the … |
| F107 | fix | composed-prompt order by precedence: role 0, personality 3, per_turn 10, tools_suite 20, parent_context 30, methodology 50+, interrupt 95, user_message 100. role_producer.py:9-10 states the intent "methodology before … |
| F108 | fix | per_turn_producer.py:10-17 — "dual-path … duplication is intentional through the migration" (sprint 064 finished; the duplication persists through assembled_prompt — see transcript finding). |
| F109 | fix | ci.py:20-21 — "eight Structs, ten triggers, five producer kinds, three Views" (now 10+ structs, 17 triggers, 18 producer kinds, 6 views). |
| F111 | fix | bundled.py:73-101,207-214 — register_all() calls EVERY bundled factory to register one name; _fanout_review_ci runs `git init`/commits under substrate_home()/ci-fixtures, and swebench_repair_ci builds a fixture there … |
| F291 | closes with the finding it resolves | `_daemon` 8765: server.py:1620-1623 default `SUBSTRATE_UI_PORT=8765`; the packaged app passes `--port 0`; `substrate daemon` CLI fallback (`_daemon.py:68`) reaches this server only when it was started standalone witho… |
| F313 | fix | workspace_shape vocabularies: kernel WorkspaceShape {flat, worktree, isolate}; server `_classify_workspace_shape` {worktree, sandbox, path} + "per-session-sandboxes" (l.1608); server `_list_sessions_snapshot` bucket "… |
| F452 | closes with the finding it resolves | VERIFY RESOLVED [E/H] substrate/src/substrate/session_registry.py:435 — `create()` writes status=RUNNING for a session that has run no turn. tests/test_server_session_list.py:47-68 pins it: a just-created session land… |
| F453 | fix | session_registry.py:66-72 — SessionStatus docstring says the STATUS_* module aliases "stay as aliases … below"; there are none (grep: 0 definitions, 0 uses). |
| F469 | closes with the finding it resolves | l.126 per_turn duplication — CONFIRMED BY PROBE (scratchpad/probe_per_turn.py: real SessionRegistry + server._build_session_topology_from_manifest, per_turn "PFX::", two turns, a responder that records prompts). The s… |
| F470 | closes with the finding it resolves | l.60 workspace_shape — CONFIRMED, five vocabularies for one field: kernel WorkspaceShape {flat, worktree, isolate} (session_registry.py:80-87) while SessionManifest.workspace_shape is `str` (:116); server POST /api/se… |

## checks

- Hard interrupt during a slow tool → Park, turn parked (probe becomes a test).
- per_turn appears once in the composed prompt (probe becomes a test).
- create() writes PARKED; GET /api/session lists it under parked.
- Fan-out children carry composite_of, require a driver, and end with the parent.
- ModelReply carries ModelUsage tokens and latency.
- WorkspaceShape is the only shape vocabulary; the server rejects other values.
- bash output truncation carries a marker; TaskTable and bash files are pruned on session delete.

## result

(filled at close)

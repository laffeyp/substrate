# Sprint 272 — The system channel

```yaml
---
id: 272
status: closed
closed_at: 2026-10-10
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-default-guidance.md
asked: 2026-10-10 (Architect)
---
```

## why

Every driver gets one user string. Claude Code sends style and environment in its system prompt; Substrate has nowhere to put them.

## scope

- `PromptComposed.system`; the composer splits the head on `SYSTEM_SOURCES` (`bundle_style`, `baseline`).
- The Responder call takes `system=`: `OllamaResponder` sends a system message; `CliResponder` passes it through the driver profile's flag, or prefixes it when there is none; `DeterministicResponder` ignores it.

## design as built (written before the run, 2026-10-10)

- **The Responder protocol does not change.** `respond(prompt) -> str` is public (`substrate.protocols`), and the ensemble and rate-limit wrappers, plus any custom `[[responder]]`, implement it. A responder that has a system channel says so with an attribute, `system_channel = True`, the same way the model step already detects `achat_tools` and `arespond_metered`. Its `arespond`, `arespond_metered`, `achat_tools` and `achat_tools_metered` take a keyword-only `system: str = ""`.
- **One rule for the rest.** `call_responder_metered(responder, prompt, *, system="")` and the native tool call pass `system=` to a responder with the attribute. Any other responder gets `system`, a blank line, then the prompt, as one string, which is § P.3's rule for a driver with no channel.
- **Ollama.** The per-call `system` becomes the system message; the constructor's `system` stays as the fallback when a call passes none.
- **CLI.** `CliResponder` takes `system_flag: list[str] | None` (from the driver profile, U120). With a flag it runs `[*command, *system_flag, system, prompt]`; without one it prefixes. U120 sets the flag for `claude`.
- **The composer.** `head_block` returns the system part and the user part separately. Fragments whose source is in `SYSTEM_SOURCES` go to the system part in precedence order; the seed stays in the user part. `compose_model_prompt` returns `(system, text, seqs)`, and `PromptComposed` records both.
- **No change to any record yet.** `SYSTEM_SOURCES` is `{bundle_style, baseline}`. The harness style is empty, and K273 has not built the baseline yet, so every CI record's `system` is `""` and its `text` is unchanged.

### Predicted breaks

- Tests that unpack `compose_model_prompt` or `head_block` (`test_prompt_built_once_261.py`, `test_prompt_window_261.py`, `test_render_seed_alone_exceeds.py`).
- The committed CI records, through the new `system` field on `PromptComposed`.

## checks

- For each responder, a capture shows the bytes sent equal `PromptComposed.system` plus `.text`.

## result

- **Built as designed.**
  - `PromptComposed.system` (default `""`).
  - `SYSTEM_SOURCES = {bundle_style}`; K273 adds `baseline`.
  - `head_block` and `compose_model_prompt` return the system part, the head and the seqs.
  - `OllamaResponder.system_channel = True`, with a per-call `system` on every public call.
  - `CliResponder(system_flag=…)`, a `system_channel` property and `_argv`.
  - `call_responder` and `call_responder_metered` take `system=`, and `joined_prompt` serves a responder with no channel. The Responder protocol is unchanged.
- **Test.** `test_system_channel_272.py`, 6 tests:
  - the head split;
  - a channel driver gets `(system, text)` exactly as recorded;
  - a plain driver gets `system`, a blank line, then `text`;
  - no system text changes nothing;
  - CLI argv with and without a flag, kept by `at()`;
  - Ollama's per-call system message and its constructor fallback.
- **Checks.**
  - Kernel suite: 1,364 passed, 5 named skips, 4 failures, then fixed:
    - `test_bundled_topologies.py[session]`, `[daily]` and `test_session_topology_bundled.py`, predicted: the committed `session` and `daily` records gain `system`. Regenerated; with run ids, CRCs and times masked, the only change is the schema field and `system: ""` on each `PromptComposed`. The other 16 records were restored.
    - `test_realmodel_session_compaction.py`, not predicted: its `_Observed` subclass overrode the private `_achat` with the old two-argument signature, so every call raised `TypeError`. The subclass now passes `system`, and the live test passes (18 s, `llama3.2:1b`).
  - UI suite: 215 passed. ruff, ruff format and `mypy --strict` are clean. `docs/api.md` regenerated.
- **Prediction misses.** `test_prompt_window_261.py`, `test_history_by_reference_268.py` and `test_realmodel_session_compaction.py` unpack `compose_model_prompt`; the card named `test_render_seed_alone_exceeds.py` instead, which does not. All three were updated.
- **Installed app.** No session's prompt changes yet: the system part is empty until `standard` (K275) or the baseline (K273). The installed-app check runs with U120, where Claude receives the system text through `--system-prompt`.

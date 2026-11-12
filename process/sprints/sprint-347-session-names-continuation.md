# Sprint 347 — A session names the conversation it continues

```yaml
---
id: 347
status: closed
closed_at: 2026-11-12
phase: continuing a session (substrate-ui roadmap 2026-11-12-continue-a-session r1, E3)
pass_kind: functional
depends_on: [346]
plan: ../substrate-ui/process/planning/2026-11-12-continue-a-session/ROADMAP-2026-11-12-continue-a-session-r1.md
---
```

## scope

`SessionManifest` gains `continued_session: str | None` (default None): the path of a JSON file holding `{"turns": [...], "provenance": {...}}`. `SessionRegistry.create` takes it; the session topology's builder reads the file when the session opens and passes it to `session_prompt_sources`, which adds the `continued_session` source (sprint 346). A manifest without the field reads as before. One verifiable property: a session created with the field opens with the `continued_session` fragment; one created without it opens as today.

## context_files

- `src/substrate/topologies/session_registry.py` (`SessionManifest`, `create`)
- `src/substrate/topologies/session/__init__.py` (the builder's sources, `parent_context` at line 1318)
- `src/substrate/topologies/session/session_prompt_producer.py`

## signal contract

### Emits

- The sprint 346 fragment, on a session that names a continuation.

### Invariants

- Old manifests load unchanged; a session without the field builds the same topology.

## artifact contract

### Files modified

- `src/substrate/topologies/session_registry.py`, `src/substrate/topologies/session/__init__.py`

### Files created

- `tests/test_session_continued_347.py`

### Command exit codes

- `uv run pytest tests/test_session_continued_347.py` and the registry's tests return 0.

## observation contract

Through the registry, as the daemon does: create with a turns file, run one turn on the deterministic driver; the record holds the fragment, and `PromptComposed` holds the rendered turns. A second session without the field: no such fragment.

## done criteria

A session created to continue a conversation opens with it.

## notes

Primitive-plus-consumer: the production consumer of this manifest field is substrate-ui sprint 494 (`../substrate-ui/process/sprints/sprint-494-continue-from-claude-code.md`), the server route that sets it.

## self-review checklist

- [x] Scope is concrete and bounded.
- [x] Two files.
- [x] Consumer named, its card on disk.
- [x] Artifact contract is gradable.
- [x] Observation contract present.

## close

`SessionManifest.continued_session` (the turns file's path), `create(continued_session=)`, and the field's round trip through `manifest.json`, written only when set (`session_registry.py`); `session_topology(continued_session=)` hands it to `session_prompt_sources` (`session/__init__.py`). The topology factory reads the file: the daemon's is substrate-ui sprint 494's; the test's is the same shape.

- `tests/test_session_continued_347.py`: 3 passed. Through the registry, created with a turns file and run one deterministic turn: the record holds one `PromptFragment` of source `continued_session` and the first `PromptComposed` holds `USER: Remember the word: heron.` and `MODEL: OK, heron.`; created without one: no such fragment, and `manifest.json` has no `continued_session` key; the field survives a reload.
- With the source's, K340's and the vocabulary's tests: 57 passed. ruff clean; `mypy --strict` on both files clean.
- Mutant (the builder not handing the field on): 1 of 3 fails.

Rubber Duck Pass: on a continued session the record opens with the session-open fragments plus one `continued_session` fragment, then the turn as before. No observations.

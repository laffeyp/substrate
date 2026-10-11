# Sprint 271 — Bundles stack and extend

```yaml
---
id: 271
status: closed
closed_at: 2026-10-10
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-default-guidance.md
asked: 2026-10-10 (Architect)
---
```

## why

Style is caller-wins, so a child's one line would replace an inherited writing standard. `resolve_extends` cannot reach a shipped bundle. Methodology precedence is 50 plus the link position, against § I's 5–9 band.

## scope

- Rename `personality` to `style` (slot file, `Bundle.style`, `PromptSource.BUNDLE_STYLE`, wizard templates) and the shipped `session` bundle to `harness`, each with its legacy table.
- Style stacks: one fragment per link, ancestor first.
- `resolve_extends` falls back to shipped bundles as `load_bundle` does.
- Every methodology link takes precedence 5; `seq` keeps ancestors first.

## design as built (written before the run, 2026-10-10)

- **Shipped bundles get one home.** `topologies/session/bundle/` moves to `topologies/session/bundles/harness/`, and `bundle.toml` names it `harness`. `_shipped_bundle_dir(name)` looks in `topologies/session/bundles/<name>/`, then `topologies/applications/<name>.bundle/`. K275 adds `standard` and `standard-small` beside `harness`.
- **Legacy names.** `LEGACY_BUNDLE_NAMES = {"session": "harness"}` in `bundles.py`; `load_bundle` maps the name before it looks. `LEGACY_PROMPT_SOURCES = {"bundle_personality": "bundle_style"}` in `vocabulary.py`, and `parse_prompt_source(raw)` applies it. `FragmentCohort` parses through it, so a resumed pre-v0.4 session keeps its style fragment.
- **Style slot.** `Bundle.style`; slot files `style.md` or `style/`; a bundle with no style file but a `personality.md` still loads it. The wizard templates, `substrate bundle create` and the UI's bundle list read `style`.
- **Stacking.** `bundle_style_fragments` writes one fragment per non-empty link, ancestor first, all at precedence 3.
- **Precedence.** Every methodology link at 5. `head_block` sorts on `(precedence, seq)`, and the producer writes ancestors first, so order holds. The methodology now comes before the tool list (20) in the head; that is the band § I set.
- **Shipped `extends`.** `load_bundle(..., shipped_fallback=)` defaults to "no explicit root"; `_c3_linearise` passes `True`, so a chain reaches shipped ancestors. `resolve_chain` becomes `resolve_extends`.
- **Default name.** The daemon's and delegate's default bundle literal becomes `harness`; the UI's `bundleSlug` default likewise. U121 later moves it to `standard`.

### Predicted breaks

- `test_bundles_229.py`, `test_shipped_bundles_231.py`, `test_cli_bundle_subverbs_222.py`, `test_mad_lib_wizard_232.py`, `test_all_wizard_templates_232b.py`: `personality` names and the `session` bundle name.
- `test_prompt_fragment_bundle.py`: caller-wins becomes stacking; precedence 50 becomes 5.
- `test_session_prompt_vocabulary_v02.py`: the enum's member set.
- `test_fewer_producers_263.py`, `test_session_open_fragments_265.py`: `bundle_personality` references.
- `test_prompt_built_once_261.py` and the committed `session` and `daily` CI records: the methodology moves ahead of the tool list.
- substrate-ui: the bundles endpoint test if it reads `personality`.

## checks

- A test chain shaped like `harness` then `standard` composes both styles and both methodologies in order.
- Old records with `bundle_personality` and manifests naming `session` load.

## result

- **Built as designed.**
  - `topologies/session/bundle/` is now `topologies/session/bundles/harness/`, named `harness`.
  - The style slot is `style.md`, with `personality.md` read when no `style.md` exists.
  - `LEGACY_BUNDLE_NAMES` and `LEGACY_PROMPT_SOURCES` read old names; `parse_prompt_source` applies the second, and `FragmentCohort` parses through it.
  - Style stacks per link, and every methodology link sits at precedence 5.
  - `resolve_extends` reaches shipped bundles; `resolve_chain` is now `resolve_extends`.
  - The default bundle literal is `harness` in `server.py`, `delegate.py` and the UI's `bundleSlug`.
- **One change from the design.** The old name maps to `harness` only when no user bundle has that name. `test_bundles_list.py::test_list_bundles_user_bundle_shadows_shipped` keeps a user bundle called `session`, and it still shadows.
- **Tests.**
  - New: `test_bundles_stack_271.py` (an old `bundle_personality` fragment stays in the cohort; the parser maps the old name).
  - Three tests added to `test_bundles_229.py`: `personality.md` loads as style; `session` loads `harness`; a user bundle extends a shipped one.
  - `test_prompt_fragment_bundle.py`'s caller-wins test is now a stacking test across three links.
- **Checks.**
  - Kernel suite: 1,361 passed, 5 named skips, 1 failure: `test_api_docs_cover_the_surface.py`, because the committed `docs/api.md` lacked the new `load_bundle` signature and paths. Regenerated, it passes.
  - UI suite: 215 passed after its two predicted tests moved to `harness`.
  - ruff, ruff format, `mypy --strict` (133 files), `lint-imports` and `tsc` are clean.
- **Prediction misses.**
  - `test_prompt_built_once_261.py` and the committed `session` and `daily` CI records did not move: none of them names a bundle.
  - `test_bundles_list.py` and `test_api_docs_cover_the_surface.py` broke without being predicted.
- **Installed app.** No behaviour a session shows changes here: the harness text is the same bytes, and the methodology now comes before the tool list. The installed-app check runs at U121, when the default moves to `standard`.

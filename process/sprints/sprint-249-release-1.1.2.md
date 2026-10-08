# Sprint 249 — Release substrate-kernel 1.1.2 to PyPI

```yaml
---
id: 249
status: in_progress
opened_at: 2026-10-08
pass_kind: release
---
```

## why

The Architect, 2026-10-08: "then kernel can come last today", after the substrate-ui Sprint 107 pass. PyPI holds 1.1.1 (2026-09-29); 13 kernel commits since carry the Sprint 093–107 work. The app no longer depends on PyPI (UI Sprint 100 bundles the kernel from the commit), so this release is for the library's other users.

## scope

- `pyproject.toml` 1.1.1 → 1.1.2; `uv.lock` follows.
- `CHANGELOG.md`: the 1.1.2 entry, and the 1.0.1, 1.1.0 and 1.1.1 entries that never landed.
- Release from a commit CI passed (Humble and Farley, *Continuous Delivery*, ch. 5: promote the artifact that passed the gates).

## checks

- CI green on the release commit (Ubuntu and macOS, Python 3.12–3.14).
- `uv build` from a clean tree; `twine check` passes on the wheel and the sdist.
- The built wheel installs into an empty venv; `substrate.__version__ == "1.1.2"`; `substrate.api.RunStatus` and `SessionRegistry` import.
- After upload: `pip install substrate-kernel==1.1.2` from PyPI into an empty venv gives the same.
- Tag `v1.1.2` on the release commit, pushed.

## result

(filled at close)

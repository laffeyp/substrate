# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Bundle loader + extends chain + seed assembler — piece H.

The tech spec lays the on-disk shape at `~/.substrate/bundles/<name>/`:
five prose slot files (or slot folders), a `corpus/` directory, and a
`bundle.toml` metadata + composition block. This module loads a bundle,
resolves its `extends` chain via C3 linearisation, and assembles the
seed string a session opens with.

Sprint 229 ships the loader + extends + assembler. Sprint 230 ships
slot declaration + binding + fallback (a separate concept — the
per-topology manifest's `[slots]` block picks values from the bundle
loaded here). Sprint 231 ships the five default bundles. Sprint 232
ships the Mad Lib wizard on top of the shape here declares.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from msgspec import Struct

from .naming import check_path_component


class BundleError(Exception):
    """Base class for bundle loading failures. Carries the bundle name
    and the failing path for the operator to debug."""


class BundleNotFoundError(BundleError):
    """No `<bundles_root>/<name>/` directory exists on disk."""


class BundleShapeError(BundleError):
    """Both a file (`methodology.md`) and a folder (`methodology/`) exist
    at the same prose slot. The resolver refuses to guess which one wins."""


class BundleCycleError(BundleError):
    """The extends chain has a cycle. The message names the full cycle
    path so the operator can pick a link to cut."""


class BundleChainTooDeepError(BundleError):
    """The extends chain nests deeper than `_MAX_EXTENDS_DEPTH` (8) — the
    C3 linearisation bail-out. A caller with a legitimate deep chain
    should flatten it into fewer wider bundles instead of raising the
    cap; the cap is a soft-limit against pathology, not scale."""


_MAX_EXTENDS_DEPTH = 8
_PROSE_SLOTS: tuple[str, ...] = ("methodology", "personality", "per_turn")


def _default_bundles_root() -> Path:
    from .home import substrate_home

    return substrate_home() / "bundles"


def _bundles_root(override: Path | None) -> Path:
    return override if override is not None else _default_bundles_root()


def _shipped_bundle_dir(name: str) -> Path | None:
    """Sprint 231: default bundles ship inside the installed package at
    two locations at two locations:
      - `topologies/session/bundle/`                     -> "session"
      - `topologies/applications/<app>.bundle/`          -> "<app>"

    `load_bundle(name)` falls back here when the user's bundles dir
    has no entry — the operator gets a working default without any
    `~/.substrate/bundles/` writes, and can shadow the shipped default
    by scaffolding a `~/.substrate/bundles/<name>/` of the same name."""
    if name == "session":
        candidate = Path(__file__).parent / "topologies" / "session" / "bundle"
        return candidate if candidate.is_dir() else None
    candidate = Path(__file__).parent / "topologies" / "applications" / f"{name}.bundle"
    return candidate if candidate.is_dir() else None


class Bundle(Struct, frozen=True):
    """One loaded bundle. Fields match the tech spec.

    - `name`, `description`, `schema_version`, `extends`: `[bundle]`
      metadata block.
    - `methodology`, `personality`, `per_turn`: the three prose slots.
      Each is the concatenated text (empty string if no slot file
      exists — the loader does not raise on missing prose; a fresh
      bundle just has empty slots).
    - `corpus_paths`: paths from `[corpus].paths`, resolved against the
      bundle directory. The seed assembler does not embed the corpus;
      it lands as read_file targets available to the session.
    - `retrieval_kind`: `[retrieval].kind`; `"none"` in v1.
    - `tools_enabled`: `[tools].enabled` — the session-open allowlist
      piece B's `POST /api/session {tools: [...]}` consumes.
    """

    name: str
    description: str
    schema_version: int
    extends: tuple[str, ...]
    methodology: str
    personality: str
    per_turn: str
    corpus_paths: tuple[str, ...]
    retrieval_kind: str
    tools_enabled: tuple[str, ...]


def _read_prose_slot(bundle_dir: Path, slot_name: str) -> str:
    """File-or-folder shape. Both present raises
    `BundleShapeError`. Folder shape: `<slot>/*.md` concatenated in
    filename-sort order with a `---` separator (matches piece A's
    role-prompt folder shape at `resolve_role_prompt`)."""
    slot_dashed = slot_name.replace("_", "-")
    candidates = [
        bundle_dir / f"{slot_name}.md",
        bundle_dir / f"{slot_dashed}.md",
    ]
    folder_candidates = [
        bundle_dir / slot_name,
        bundle_dir / slot_dashed,
    ]
    file_hit = next((path for path in candidates if path.is_file()), None)
    folder_hit = next((path for path in folder_candidates if path.is_dir()), None)
    if file_hit is not None and folder_hit is not None:
        raise BundleShapeError(
            f"bundle at {bundle_dir}: both {file_hit.name} and {folder_hit.name}/ "
            f"exist at the {slot_name!r} slot; pick one — the resolver refuses to guess."
        )
    if file_hit is not None:
        return file_hit.read_text(encoding="utf-8").rstrip("\n")
    if folder_hit is not None:
        parts = [
            path.read_text(encoding="utf-8").rstrip("\n")
            for path in sorted(folder_hit.glob("*.md"))
        ]
        return "\n\n---\n\n".join(parts)
    return ""


def load_bundle(name: str, *, bundles_root: Path | None = None) -> Bundle:
    """Load one bundle from `<bundles_root>/<name>/`. Reads
    `bundle.toml` plus the three prose slots plus the corpus/retrieval/
    tools blocks. Raises `BundleNotFoundError` if the directory is
    absent; `BundleShapeError` on a duplicate slot; propagates
    `tomllib.TOMLDecodeError` on a malformed `bundle.toml`."""
    check_path_component("bundle", name)
    root = _bundles_root(bundles_root)
    bundle_dir = root / name
    if not bundle_dir.is_dir():
        # Sprint 231: fall back to the shipped defaults inside the
        # installed package. `~/.substrate/bundles/<name>/` shadows the
        # shipped default when present; absent, the shipped version
        # loads. A caller with `bundles_root=` override skips this
        # fallback (tests use it to isolate).
        if bundles_root is None:
            shipped = _shipped_bundle_dir(name)
            if shipped is not None:
                bundle_dir = shipped
        if not bundle_dir.is_dir():
            raise BundleNotFoundError(f"no bundle at {bundle_dir}")
    toml_path = bundle_dir / "bundle.toml"
    if not toml_path.is_file():
        raise BundleError(f"bundle at {bundle_dir}: missing bundle.toml")
    raw = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    bundle_block = raw.get("bundle")
    # mypy narrowing: assign the isinstance-guarded shape to a typed
    # local so the four `metadata.get(...)` accesses below type-check.
    # The ternary that used to live here read the same key twice and
    # mypy could not narrow across it (REVIEW-2026-08-28 Q1).
    metadata: dict[str, Any] = bundle_block if isinstance(bundle_block, dict) else {}
    # Piece-B compat: 224a-e's scaffolding wrote top-level `name` too.
    # Fall back to that shape so a `substrate bundle create <n>` bundle
    # loads without needing a manual re-shape.
    bundle_name = str(metadata.get("name") or raw.get("name") or name)
    description = str(metadata.get("description") or raw.get("description") or "")
    schema_version = int(metadata.get("schema_version") or raw.get("schema_version") or 1)
    extends_raw = metadata.get("extends") or raw.get("extends") or ()
    if not isinstance(extends_raw, (list, tuple)):
        raise BundleError(
            f"bundle at {bundle_dir}: `extends` must be a list of bundle names; "
            f"got {type(extends_raw).__name__}"
        )
    extends = tuple(str(entry) for entry in extends_raw)

    corpus_block = raw.get("corpus") or {}
    corpus_paths_raw = (corpus_block.get("paths") if isinstance(corpus_block, dict) else None) or ()
    if not isinstance(corpus_paths_raw, (list, tuple)):
        raise BundleError(
            f"bundle at {bundle_dir}: `[corpus].paths` must be a list; "
            f"got {type(corpus_paths_raw).__name__}"
        )
    corpus_paths = tuple(str(bundle_dir / path) for path in corpus_paths_raw)

    retrieval_block = raw.get("retrieval") or {}
    retrieval_kind = str(
        retrieval_block.get("kind") if isinstance(retrieval_block, dict) else "none"
    )

    tools_block = raw.get("tools") or {}
    tools_raw = tools_block.get("enabled") if isinstance(tools_block, dict) else None
    if tools_raw is None:
        tools_enabled: tuple[str, ...] = ()
    elif isinstance(tools_raw, (list, tuple)):
        tools_enabled = tuple(str(name) for name in tools_raw)
    else:
        raise BundleError(
            f"bundle at {bundle_dir}: `[tools].enabled` must be a list; "
            f"got {type(tools_raw).__name__}"
        )

    return Bundle(
        name=bundle_name,
        description=description,
        schema_version=schema_version,
        extends=extends,
        methodology=_read_prose_slot(bundle_dir, "methodology"),
        personality=_read_prose_slot(bundle_dir, "personality"),
        per_turn=_read_prose_slot(bundle_dir, "per_turn"),
        corpus_paths=corpus_paths,
        retrieval_kind=retrieval_kind,
        tools_enabled=tools_enabled,
    )


def _c3_linearise(
    name: str, bundles_root: Path, seen: dict[str, Bundle], path: list[str]
) -> list[Bundle]:
    """Depth-first C3 walk. `path` tracks the current chain for cycle
    detection; `seen` de-dups (first-occurrence-wins per the C3
    diamond rule). Raises `BundleCycleError` if the chain revisits an
    ancestor, `BundleChainTooDeepError` if the chain nests past
    `_MAX_EXTENDS_DEPTH`."""
    if name in path:
        cycle = " -> ".join(path[path.index(name) :] + [name])
        raise BundleCycleError(f"bundle extends cycle: {cycle}")
    if len(path) >= _MAX_EXTENDS_DEPTH:
        raise BundleChainTooDeepError(
            f"bundle extends chain nests deeper than {_MAX_EXTENDS_DEPTH}: "
            f"{' -> '.join([*path, name])}"
        )
    bundle = seen.get(name)
    if bundle is None:
        bundle = load_bundle(name, bundles_root=bundles_root)
        seen[name] = bundle
    ordered: list[Bundle] = []
    for parent_name in bundle.extends:
        for ancestor in _c3_linearise(parent_name, bundles_root, seen, [*path, name]):
            if ancestor.name not in {existing.name for existing in ordered}:
                ordered.append(ancestor)
    ordered.append(bundle)
    return ordered


def list_bundles(bundles_root: Path | None = None) -> list[Bundle]:
    """Enumerate every shipped and user bundle. Returns Bundles sorted by name.

    Sources, in name-shadowing order (later wins if a name collides):
      1. Shipped defaults under `topologies/session/bundle/` (name "session")
         and `topologies/applications/<app>.bundle/` (name "<app>").
      2. User bundles under `_bundles_root(bundles_root)` — every direct
         subdirectory that contains a `bundle.toml` file is loaded via
         `load_bundle(name)`; per `load_bundle`, a user bundle of the same
         name shadows the shipped default.

    A missing bundles root yields the shipped list only. A subdirectory
    without a `bundle.toml` is skipped silently (matches `load_bundle`'s
    "no manifest → BundleNotFoundError" contract only when the caller
    asks for that specific name; enumeration does not raise).

    Sprint 238: added as the substrate-side prerequisite for substrate-ui
    sprint 034a's `GET /api/bundles` endpoint. The daemon calls this and
    surfaces `[{name, description, slot_count}]` to the UI's bundle picker.
    """
    # Two pools: shipped names (loaded without bundles_root so load_bundle
    # falls through to _shipped_bundle_dir) and user names (loaded with the
    # user_root so they shadow correctly). A name in both pools loads from
    # user_root and the shipped entry is skipped — user shadows shipped.
    shipped: set[str] = set()
    session_dir = Path(__file__).parent / "topologies" / "session" / "bundle"
    if session_dir.is_dir() and (session_dir / "bundle.toml").is_file():
        shipped.add("session")
    apps_dir = Path(__file__).parent / "topologies" / "applications"
    if apps_dir.is_dir():
        for child in apps_dir.iterdir():
            if (
                child.is_dir()
                and child.name.endswith(".bundle")
                and (child / "bundle.toml").is_file()
            ):
                shipped.add(child.name[: -len(".bundle")])
    user: set[str] = set()
    user_root = _bundles_root(bundles_root)
    if user_root.is_dir():
        for child in user_root.iterdir():
            if child.is_dir() and (child / "bundle.toml").is_file():
                user.add(child.name)
    bundles: list[Bundle] = []
    for name in sorted(shipped | user):
        source_root: Path | None = bundles_root if name in user else None
        try:
            bundles.append(load_bundle(name, bundles_root=source_root))
        except (BundleNotFoundError, BundleShapeError):
            # A subdirectory with a bundle.toml that fails structural checks
            # is a real bug in that bundle, not this enumerator's problem.
            # Skip it here; load_bundle(name) raises for callers that
            # specifically ask for it.
            continue
    return bundles


def resolve_extends(name: str, *, bundles_root: Path | None = None) -> list[Bundle]:
    """C3 linearisation of a bundle's `extends` chain. Returns bundles
    in resolution order: every ancestor before its descendant, first-
    occurrence-wins on diamonds. The last entry is always the named
    bundle itself.

    Raises `BundleCycleError` on a cycle, `BundleChainTooDeepError` on
    a chain deeper than 8, `BundleNotFoundError` on any missing bundle
    in the chain, `BundleShapeError` on a slot ambiguity.
    """
    root = _bundles_root(bundles_root)
    return _c3_linearise(name, root, seen={}, path=[])


# Sprint 065 (2026-09-01): deleted assemble_seed, assemble_seed_from_chain,
# SlotUnfilledError, SlotKindMismatchError, _validate_slot_kind, bind_slots.
# Zero call sites outside their own tests. The prompt-composition arc
# (sprints 058-064) replaced their shape with the fragment/composer
# Producer graph — bundle prose slots emit as PromptFragment(source=
# bundle_methodology|bundle_personality) via `topologies/session/
# bundle_producer.py`. The composed seed lives on the record now, not
# in a Python string returned from a helper function nothing called.


__all__ = [
    "Bundle",
    "BundleChainTooDeepError",
    "BundleCycleError",
    "BundleError",
    "BundleNotFoundError",
    "BundleShapeError",
    "list_bundles",
    "load_bundle",
    "resolve_extends",
]

# spec-audit: 2026-09-01

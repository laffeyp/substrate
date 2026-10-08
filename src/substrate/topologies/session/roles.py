# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Role-prompt resolver — the four-layer fallback.

Resolution order for `<role>`:

  1. `<repo>/.substrate/prompts/<role>.md` (or `<role>/*.md` folder shape)
  2. `~/.substrate/prompts/<role>.md` (or folder shape)
  3. `substrate/src/substrate/topologies/session/prompts/<role>.md`
  4. Not found → `RegistrationError`.

Folder shape (the topology-layer contract): if `<role>/` is a directory at a layer, concatenate its
`*.md` files in lexical order with one blank line between. Both a bare
`.md` file AND a `<role>/` directory at the SAME layer is an ambiguous
config and raises `RegistrationError` — the resolver must not pick one
silently. A `<role>.md` at layer 1 and a `<role>/` at layer 2 is fine
(layer 1 wins).
"""

from __future__ import annotations

from pathlib import Path

from ...kernel.topology import RegistrationError
from ...naming import check_path_component


def _shipped_prompts_dir() -> Path:
    return Path(__file__).parent / "prompts"


def _user_prompts_dir() -> Path:
    from substrate.api import substrate_home

    return substrate_home() / "prompts"


def _read_folder(folder: Path) -> str:
    parts: list[str] = []
    for md in sorted(folder.glob("*.md")):
        parts.append(md.read_text(encoding="utf-8").rstrip("\n"))
    return "\n\n".join(parts)


def _resolve_at_layer(base: Path, role: str) -> tuple[str, Path] | None:
    """Return `(text, source_path)` for the role at this layer, or None.
    `source_path` is the file (bare `.md`) or the folder (concatenated
    shape) — whichever produced the text. Callers that only want the text
    read `[0]`; callers that want provenance read `[1]`.
    """
    file_path = base / f"{role}.md"
    folder_path = base / role
    has_file = file_path.is_file()
    has_folder = folder_path.is_dir()
    if has_file and has_folder:
        raise RegistrationError(
            f"role {role!r}: both {file_path} and {folder_path}/ exist at the same "
            f"layer; pick one (rename or remove) — the resolver refuses to guess."
        )
    if has_file:
        return (file_path.read_text(encoding="utf-8"), file_path)
    if has_folder:
        return (_read_folder(folder_path), folder_path)
    return None


def resolve_role_prompt_with_source(
    role: str, *, repo_root: Path | None = None
) -> tuple[str, Path]:
    """Return `(text, source_path)` for a role prompt.

    Sprint 061: the `role_producer` yields `PromptFragment(source=role,
    text=text, provenance={"role_name": role, "resolved_from": str(path)})`
    so the record self-describes which file supplied the prompt. The
    existing `resolve_role_prompt` stays as a thin wrapper for callers
    that only want the text.
    """
    check_path_component("role", role)
    if repo_root is not None:
        layer1 = _resolve_at_layer(repo_root / ".substrate" / "prompts", role)
        if layer1 is not None:
            return layer1
    layer2 = _resolve_at_layer(_user_prompts_dir(), role)
    if layer2 is not None:
        return layer2
    layer3 = _resolve_at_layer(_shipped_prompts_dir(), role)
    if layer3 is not None:
        return layer3
    raise RegistrationError(
        f"no role prompt found for --role {role!r}. Looked in: "
        f"<repo>/.substrate/prompts/, ~/.substrate/prompts/, "
        f"{_shipped_prompts_dir()}/. Ship a {role}.md at one of these layers."
    )


def resolve_role_prompt(role: str, *, repo_root: Path | None = None) -> str:
    """Return the resolved role prompt string.

    `repo_root` is the current working repo (usually `Path.cwd()` at the
    daemon's create-session moment); when `None`, layer 1 is skipped.
    Missing at every layer raises `RegistrationError` naming the role.
    Thin wrapper over `resolve_role_prompt_with_source` — the text is the
    same either way; drop the path when the caller does not need it.
    """
    text, _ = resolve_role_prompt_with_source(role, repo_root=repo_root)
    return text


__all__ = ["resolve_role_prompt", "resolve_role_prompt_with_source"]

# spec-audit: 2026-09-01

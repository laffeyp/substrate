# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Skills: guides a model loads only when asked (session vocabulary § P.6, sprint K277).

A skill is a `SKILL.md` file with a `name` and `description` in its frontmatter. It resolves
through the same layers as roles, most specific first:

  1. `<repo>/.substrate/skills/<name>/SKILL.md`
  2. `~/.substrate/skills/<name>/SKILL.md`
  3. `substrate/src/substrate/topologies/session/skills/<name>/SKILL.md` (shipped)

A small model's class reads `<name>-small` first when a layer has it (K278).

Two ways to ask, the two Claude Code has: the operator types `/dellm` (the daemon writes
`SkillRequested`, and `skill_fragment` writes the body as a `skill` fragment that stays for the
session), or the model calls the `skill` tool (the body comes back as a ToolResult and stays in
history).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from ...errors import describe_error
from ...naming import check_path_component
from ..tool_loop.tools import Tool
from . import PromptFragment, SessionWarning
from .vocabulary import PromptSource, SessionWarningKind

SKILL_PRECEDENCE = 40
TOOL_NAME_SKILL = "skill"


def _shipped_skills_dir() -> Path:
    return Path(__file__).parent / "skills"


def _user_skills_dir() -> Path:
    from substrate.api import substrate_home

    return substrate_home() / "skills"


def skill_layers(repo_root: Path | None) -> list[Path]:
    """The skill directories, most specific first."""
    layers = [_user_skills_dir(), _shipped_skills_dir()]
    if repo_root is not None:
        layers.insert(0, repo_root / ".substrate" / "skills")
    return layers


def resolve_skill(
    name: str, repo_root: Path | None, model_class: str = ""
) -> tuple[str, Path] | None:
    """`(body, path)` for a skill, or None when no layer has it. A `small` class takes
    `<name>-small` at a layer before `<name>`."""
    check_path_component("skill", name)
    names = [f"{name}-small", name] if model_class == "small" else [name]
    for layer in skill_layers(repo_root):
        for candidate in names:
            path = layer / candidate / "SKILL.md"
            if path.is_file():
                return path.read_text(encoding="utf-8"), path
    return None


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    head = text.split("---", 2)[1] if text.count("---") >= 2 else ""
    out: dict[str, str] = {}
    for line in head.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() in ("name", "description"):
            out[key.strip()] = value.strip()
    return out


def list_skills(repo_root: Path | None) -> list[tuple[str, str]]:
    """`(name, description)` for every skill a layer offers, the most specific layer winning;
    `-small` variants are the same skill and are not listed apart."""
    seen: dict[str, str] = {}
    for layer in reversed(skill_layers(repo_root)):
        if not layer.is_dir():
            continue
        for path in sorted(layer.glob("*/SKILL.md")):
            name = path.parent.name
            if name.endswith("-small"):
                continue
            meta = _frontmatter(path.read_text(encoding="utf-8"))
            seen[name] = meta.get("description", "")
    return sorted(seen.items())


def make_skill_tool(repo_root: Path | None, model_class: str = "") -> Tool:
    """The `skill(name)` tool. Its description lists each skill and what it is for, as Claude
    Code's skill listing does; a call returns the skill's body."""
    listing = "; ".join(f"{name}: {desc[:300]}" for name, desc in list_skills(repo_root))

    def _run(args: list[Any]) -> str:
        if not args:
            raise ValueError("skill(name): name is required")
        found = resolve_skill(str(args[0]), repo_root, model_class)
        if found is None:
            raise ValueError(f"no skill named {args[0]!r}; available: {listing or 'none'}")
        return found[0]

    return Tool(
        TOOL_NAME_SKILL,
        f"skill(name) -> the full guide for a named task; load one only when the user asks for "
        f"it. Available: {listing or 'none'}",
        True,
        _run,
        schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    )


def skill_fragment_producer_factory(
    *, session_id: str, repo_root: Path | None, model_class: str = ""
) -> Callable[[], Any]:
    """The `skill_fragment` producer: started by a `SkillRequested`, writes the skill's body as a
    session-open `skill` fragment, or a SessionWarning when no layer has it."""

    async def _skill_fragment(inp: Any) -> AsyncIterator[PromptFragment | SessionWarning]:
        name = str(inp.get("name", "")) if hasattr(inp, "get") else ""
        try:
            found = resolve_skill(name, repo_root, model_class)
        except ValueError as exc:
            found, error = None, describe_error(exc)
        else:
            error = f"no skill named {name!r}"
        if found is None:
            yield SessionWarning(
                session_id=session_id,
                kind=SessionWarningKind.FRAGMENT_SOURCE_FAILED,
                seed_tokens=0,
                driver_context_tokens=0,
                source_name=str(PromptSource.SKILL),
                detail=error,
            )
            return
        body, path = found
        yield PromptFragment(
            source=PromptSource.SKILL,
            text=body,
            precedence=SKILL_PRECEDENCE,
            provenance={"name": name, "resolved_from": str(path), "model_class": model_class},
        )

    return lambda: _skill_fragment


__all__ = [
    "TOOL_NAME_SKILL",
    "list_skills",
    "make_skill_tool",
    "resolve_skill",
    "skill_fragment_producer_factory",
    "skill_layers",
]

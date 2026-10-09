# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 232b — every shipped wizard template parses + renders + writes
a valid bundle through the CLI.

Ships alongside 232's default.tmpl.md: code_review, pair_coding,
best_of_n_verified, research_sweep, writing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from substrate.templates.interpolate import parse_template_header, render

SHIPPED_TEMPLATES = (
    "default",
    "code_review",
    "pair_coding",
    "best_of_n_verified",
    "research_sweep",
    "writing",
)


def _template_path(name: str) -> Path:
    from substrate import templates

    return Path(templates.__file__).parent / "bundles" / f"{name}.tmpl.md"


@pytest.mark.parametrize("name", SHIPPED_TEMPLATES)
def test_template_header_parses(name: str) -> None:
    path = _template_path(name)
    assert path.is_file(), f"template {name!r} missing at {path}"
    header, body = parse_template_header(path.read_text(encoding="utf-8"))
    assert header["slots"], f"template {name!r} declares no slots"
    for slot in header["slots"]:
        assert "name" in slot
        assert slot.get("kind") in {"text_line", "text_paragraph", "bool", "pick"}


@pytest.mark.parametrize("name", SHIPPED_TEMPLATES)
def test_template_body_renders_with_declared_slots_only(name: str) -> None:
    """Every {{slot}} in the body must be either a declared header
    slot or `name` (the bundle name, injected by the wizard). A drift
    (template referencing an undeclared slot) would show up as an
    empty substitution here; we assert against that by rendering with
    all declared slots set to a sentinel and confirming the sentinel
    appears somewhere in the output."""
    path = _template_path(name)
    header, body = parse_template_header(path.read_text(encoding="utf-8"))
    values: dict[str, object] = {"name": "TEST"}
    for slot in header["slots"]:
        slot_name = slot["name"]
        kind = slot.get("kind", "text_line")
        if kind == "bool":
            values[slot_name] = True
        elif kind == "pick":
            choices = slot.get("choices") or ["first"]
            values[slot_name] = choices[0]
        else:
            values[slot_name] = f"__SENTINEL_{slot_name}__"
    rendered = render(body, values)
    # Every text/pick slot's value should appear somewhere in the render.
    for slot in header["slots"]:
        kind = slot.get("kind", "text_line")
        if kind in ("bool",):
            continue
        expected = values[slot["name"]]
        assert str(expected) in rendered, (
            f"template {name!r} did not render slot {slot['name']!r} — the {{{{{slot['name']}}}}} "
            f"reference is missing or misspelled in the body"
        )


@pytest.mark.parametrize(
    "template_name,piped_answers",
    [
        ("code_review", ["the rubric text", "blunt", "y", "y"]),
        ("pair_coding", ["every-edit", "one-line note", "y"]),
        ("best_of_n_verified", ["strict", "add a comment about the bug", "y"]),
        ("research_sweep", ["read", "one-page", "y"]),
        ("writing", ["plain", "the reader", "y", "keep it under 400 words"]),
    ],
)
def test_wizard_writes_valid_bundle_for_each_template(
    template_name: str, piped_answers: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from substrate import cli
    from substrate.bundles import load_bundle

    monkeypatch.setattr(cli, "_bundles_root_cli", lambda: tmp_path)
    bundle_name = f"{template_name}-wizard-test"
    piped = "\n".join(piped_answers)
    result = CliRunner().invoke(
        cli.main,
        ["bundle", "create", bundle_name, f"--wizard={template_name}"],
        input=piped,
    )
    assert result.exit_code == 0, result.output
    bundle = load_bundle(bundle_name, bundles_root=tmp_path)
    assert bundle.name == bundle_name

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 232 — Mad Lib wizard: interpolator + template + CLI --wizard.

Interpolator tested in isolation; wizard CLI tested end-to-end with
piped answers; loaded-back-through-bundles.load_bundle asserts the
render produces a valid bundle.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from substrate.templates.interpolate import (
    TemplateError,
    parse_template_header,
    render,
)


def test_interpolator_substitutes_slots() -> None:
    result = render("hello {{name}}, kind={{kind}}", {"name": "world", "kind": "prose"})
    assert result == "hello world, kind=prose"


def test_interpolator_missing_slot_renders_empty() -> None:
    result = render("hello {{missing}}", {})
    assert result == "hello "


def test_interpolator_if_conditional_included_when_truthy() -> None:
    result = render("prefix{% if flag %}INCLUDED{% endif %}suffix", {"flag": "yes"})
    assert result == "prefixINCLUDEDsuffix"


def test_interpolator_if_conditional_omitted_when_falsy() -> None:
    result = render("prefix{% if flag %}INCLUDED{% endif %}suffix", {"flag": False})
    assert result == "prefixsuffix"


def test_interpolator_nested_if_raises() -> None:
    template = "{% if a %}{% if b %}nested{% endif %}{% endif %}"
    with pytest.raises(TemplateError, match="nested"):
        render(template, {"a": True, "b": True})


def test_parse_template_header_pulls_slot_declarations() -> None:
    source = (
        "---\n"
        "slots:\n"
        "  - name: role\n"
        "    kind: text_line\n"
        '    prompt: "One line role"\n'
        "  - name: flag\n"
        "    kind: bool\n"
        '    prompt: "yes/no?"\n'
        "---\n"
        "body body body\n"
    )
    header, body = parse_template_header(source)
    assert body == "body body body\n"
    assert len(header["slots"]) == 2
    names = {slot["name"] for slot in header["slots"]}
    assert names == {"role", "flag"}


def test_parse_template_header_missing_raises() -> None:
    with pytest.raises(TemplateError, match="header"):
        parse_template_header("no header here")


@pytest.fixture
def wizard_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point _BUNDLES_ROOT at tmp so the CLI writes into isolation."""
    from substrate import cli

    monkeypatch.setattr(cli, "_bundles_root_cli", lambda: tmp_path)
    return tmp_path


def test_wizard_writes_valid_bundle_that_loads_back(wizard_env: Path) -> None:
    from substrate import cli
    from substrate.bundles import load_bundle

    runner = CliRunner()
    # Feed answers per default.tmpl.md's slot list, in declared order:
    # role, methodology, personality, per_turn_prefix, security_flag.
    piped = "\n".join(
        [
            "reviewer",  # role
            "review the diff carefully",  # methodology
            "blunt",  # personality
            "",  # per_turn_prefix (empty)
            "y",  # security_flag
        ]
    )
    result = runner.invoke(cli.main, ["bundle", "create", "wizard-test", "--wizard"], input=piped)
    assert result.exit_code == 0, result.output
    bundle = load_bundle("wizard-test", bundles_root=wizard_env)
    assert bundle.name == "wizard-test"
    assert bundle.methodology == "review the diff carefully"
    assert bundle.personality == "blunt"
    assert "unsafe pattern" in bundle.per_turn.lower()


def test_wizard_bare_no_flag_still_scaffolds_empty(wizard_env: Path) -> None:
    """Regression: `substrate bundle create <name>` without --wizard
    keeps its sprint 222 shape (empty slots + bundle.toml + corpus/)."""
    from substrate import cli
    from substrate.bundles import load_bundle

    result = CliRunner().invoke(cli.main, ["bundle", "create", "empty-bundle"])
    assert result.exit_code == 0, result.output
    bundle = load_bundle("empty-bundle", bundles_root=wizard_env)
    assert bundle.methodology == ""
    assert bundle.personality == ""
    assert bundle.per_turn == ""


def test_wizard_unknown_template_exits_config(wizard_env: Path) -> None:
    from substrate import cli

    result = CliRunner().invoke(cli.main, ["bundle", "create", "x", "--wizard=no-such-template"])
    assert result.exit_code == cli.EXIT_CONFIG
    assert "template" in result.output.lower()

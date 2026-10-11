# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Model classes and guidance levels (session vocabulary § P.7, § R; sprints K278, K288).

Four classes decide how much guidance a session gets by default:

- `harness_agent`: a CLI that brings its own harness (`claude`, `codex`, `cursor-agent`). It gets
  the high level.
- `large`: an Ollama model of 70 billion parameters or more, or of unreported size. Substrate is
  its whole harness; it gets the high level.
- `medium`: an Ollama model from 14 to under 70 billion parameters. It gets the medium level.
- `small`: an Ollama model under 14 billion parameters. Its window is small (8,192 tokens for
  `llama3:8b`), so it gets the low level, and `default-small` and `dellm-small` in place of the
  full role prompt and skill.

The four guidance levels are four bundles: `harness` (Substrate's loop rules only), `standard-low`,
`standard-medium` and `standard` (high). The operator can choose any level for any model; the class
gives only the default.

Ollama reports parameter size two ways: `"8.0B"` for `llama3:8b`, `"1042000000000"` for
`kimi-k2.6:cloud`. A size Ollama does not report leaves the model `large`.
"""

from __future__ import annotations

import re
from enum import StrEnum

HARNESS_AGENT = "harness_agent"
LARGE = "large"
MEDIUM = "medium"
SMALL = "small"
SMALL_BELOW_PARAMETERS = 14_000_000_000
MEDIUM_BELOW_PARAMETERS = 70_000_000_000


class GuidanceLevel(StrEnum):
    """How much working and writing guidance a session carries (K288)."""

    HARNESS = "harness"  # the default level: Substrate's loop rules only
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Each level's bundle. `standard-low` was `standard-small` before K288; the old name still resolves.
LEVEL_BUNDLES: dict[GuidanceLevel, str] = {
    GuidanceLevel.HARNESS: "harness",
    GuidanceLevel.LOW: "standard-low",
    GuidanceLevel.MEDIUM: "standard-medium",
    GuidanceLevel.HIGH: "standard",
}
_CLASS_LEVELS: dict[str, GuidanceLevel] = {
    HARNESS_AGENT: GuidanceLevel.HIGH,
    LARGE: GuidanceLevel.HIGH,
    MEDIUM: GuidanceLevel.MEDIUM,
    SMALL: GuidanceLevel.LOW,
}


def guidance_level(model_class: str) -> GuidanceLevel:
    """The level a model of this class gets when the operator chooses none."""
    return _CLASS_LEVELS.get(model_class, GuidanceLevel.HIGH)


def guidance_bundle(level: str) -> str:
    """The bundle that carries a level."""
    return LEVEL_BUNDLES[GuidanceLevel(level)]


_SUFFIX = {"": 1, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
_SIZE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([KMBT]?)\s*$", re.IGNORECASE)


def parameter_count(reported: object) -> int | None:
    """The parameter count Ollama's `details.parameter_size` reports, in either form."""
    if isinstance(reported, (int, float)):
        return int(reported)
    m = _SIZE.match(str(reported or ""))
    if not m:
        return None
    return int(float(m.group(1)) * _SUFFIX[m.group(2).upper()])


def classify(*, is_cli: bool, parameter_size: object = None) -> str:
    """The class of a driver: a CLI is a harness agent; an Ollama model is small below 14B
    parameters, medium below 70B, and large otherwise or when its size is unknown."""
    if is_cli:
        return HARNESS_AGENT
    count = parameter_count(parameter_size)
    if count is None:
        return LARGE
    if count < SMALL_BELOW_PARAMETERS:
        return SMALL
    if count < MEDIUM_BELOW_PARAMETERS:
        return MEDIUM
    return LARGE


def class_variant(name: str, model_class: str) -> str:
    """The role prompt or skill a class reads in place of `name`: `<name>-small` for the small
    class. Guidance bundles go by level instead (`guidance_bundle`)."""
    return f"{name}-small" if model_class == SMALL else name


__all__ = [
    "HARNESS_AGENT",
    "LARGE",
    "LEVEL_BUNDLES",
    "MEDIUM",
    "MEDIUM_BELOW_PARAMETERS",
    "SMALL",
    "SMALL_BELOW_PARAMETERS",
    "GuidanceLevel",
    "class_variant",
    "classify",
    "guidance_bundle",
    "guidance_level",
    "parameter_count",
]

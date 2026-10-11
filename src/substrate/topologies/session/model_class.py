# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Model classes (session vocabulary § P.7, sprint K278).

Three classes decide how much guidance a session sends:

- `harness_agent`: a CLI that brings its own harness (`claude`, `codex`, `cursor-agent`). Its own
  setup is switched off by its driver profile; it gets the full texts.
- `large`: an Ollama model of 30 billion parameters or more. Substrate is its whole harness; it
  gets the full texts.
- `small`: an Ollama model under 30 billion parameters. Its window is small (8,192 tokens for
  `llama3:8b`), so it gets `standard-small`, `default-small` and `dellm-small`.

Ollama reports parameter size two ways: `"8.0B"` for `llama3:8b`, `"1042000000000"` for
`kimi-k2.6:cloud`. A size Ollama does not report leaves the model `large`.
"""

from __future__ import annotations

import re

HARNESS_AGENT = "harness_agent"
LARGE = "large"
SMALL = "small"
SMALL_BELOW_PARAMETERS = 30_000_000_000

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
    """The class of a driver: a CLI is a harness agent; an Ollama model is small below 30B
    parameters and large otherwise, or when its size is unknown."""
    if is_cli:
        return HARNESS_AGENT
    count = parameter_count(parameter_size)
    if count is not None and count < SMALL_BELOW_PARAMETERS:
        return SMALL
    return LARGE


def class_variant(name: str, model_class: str) -> str:
    """The shipped text a class reads in place of `name`: `<name>-small` for the small class."""
    return f"{name}-small" if model_class == SMALL else name


__all__ = [
    "HARNESS_AGENT",
    "LARGE",
    "SMALL",
    "SMALL_BELOW_PARAMETERS",
    "class_variant",
    "classify",
    "parameter_count",
]

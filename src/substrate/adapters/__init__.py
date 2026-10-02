# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""substrate.adapters — the model / tool adapter layer (a peer of substrate.api).

Home for the concrete backends a topology's Producers call: the `Responder` implementations
(`DeterministicResponder` / `OllamaResponder`) and the async `call_responder` helpers. A peer of
`api`, deliberately NOT a submodule of the acceptance-test `reference` package where these used to
live — so a new adapter (a CLI-agent Responder, an MCP tool bridge) has a canonical home beside the
model ones instead of accreting under `reference/` or `cli.py`. The `Responder` protocol itself
lives in `substrate.protocols` and is public as `substrate.api.Responder`.

Back-compat: `substrate.reference` still re-exports these (the public surface substrate-ui consumes),
via a back-compat re-export at `reference/_models.py`. New code should import from `substrate.adapters`.
"""

from __future__ import annotations

from enum import StrEnum

from .ensemble import EnsembleResponder
from .models import (
    CliResponder,
    ContextTokensUnknown,
    DeterministicResponder,
    DriverIntrospectionUnavailable,
    ModelUsage,
    OllamaResponder,
    Responder,
    call_responder,
    call_responder_metered,
)
from .rate_limit import (
    OllamaQuota,
    ProviderQuota,
    ProviderRateLimited,
    RateLimitedResponder,
)


class DriverFamily(StrEnum):
    """The two driver families the daemon dispatches on. Sprint 070:
    raw `"deterministic"` / `"ollama"` string comparisons across the
    daemon become typed enum members. Specific model tags (e.g.
    `"kimi-k2.6:cloud"`) stay as free-form strings — those are external
    configuration values, not internal enum-shaped identifiers.
    Boundary handlers validate via `DriverFamily(raw_value)`."""

    DETERMINISTIC = "deterministic"
    OLLAMA = "ollama"


class DriverParamKey(StrEnum):
    """The `driver_params` keys the SessionRegistry validator accepts.
    Sprint 070: raw-string keys become typed enum members. Adding a new
    key means adding a member — pre-070 required editing both the
    validator and every caller.
    """

    THINK = "think"
    MAX_TOKENS = "max_tokens"
    NUM_CTX = "num_ctx"
    TIMEOUT = "timeout"
    # UI Sprint 087c: the CLI model the version picker chose; the daemon's
    # driver resolver turns it into the CLI's model flag.
    DRIVER_VERSION = "driver_version"


__all__ = [
    "CliResponder",
    "ContextTokensUnknown",
    "DeterministicResponder",
    "DriverFamily",
    "DriverIntrospectionUnavailable",
    "DriverParamKey",
    "EnsembleResponder",
    "ModelUsage",
    "OllamaQuota",
    "OllamaResponder",
    "ProviderQuota",
    "ProviderRateLimited",
    "RateLimitedResponder",
    "Responder",
    "call_responder",
    "call_responder_metered",
]

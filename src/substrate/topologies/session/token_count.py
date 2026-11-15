# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""A prompt's tokens, counted (session vocabulary § AG, K352).

The history window plans with these counts: each turn, each tool result's saving, the head, and
`PromptComposed.total_tokens`. The tokenizer is Anthropic's earlier published Claude tokenizer
(`tokenizers/claude-tokenizer.json`, MIT; see `tokenizers/LICENSE`), read from the package, so a
count is the same live and on replay.

Claude's current models use a tokenizer Anthropic does not publish. Measured on 2026-11-14 against
Claude Code's exact first-call counts (Claude Opus 5.5, its own overhead taken off), this
tokenizer's count times 1.43 to 1.50 gave Claude's: 1.497 and 1.461 on Python and TypeScript, 1.434
and 1.425 on English prose. A session whose driver speaks Claude Code's stream multiplies by
`CLAUDE_FACTOR`, the top of that range. Research:
`substrate-ui/process/planning/2026-11-12-continue-a-session/RESEARCH-2026-11-14-token-counting.md`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final

from tokenizers import Tokenizer

TOKENIZER_NAME: Final[str] = "claude-tokenizer"
CLAUDE_FACTOR: Final[float] = 1.50
_TOKENIZER_FILE: Final[Path] = Path(__file__).parent / "tokenizers" / "claude-tokenizer.json"


@lru_cache(maxsize=1)
def _tokenizer() -> Tokenizer:
    return Tokenizer.from_file(str(_TOKENIZER_FILE))


@lru_cache(maxsize=512)
def count_tokens(text: str) -> int:
    """The tokenizer's count of `text`; 0 for empty text."""
    if not text:
        return 0
    return len(_tokenizer().encode(text, add_special_tokens=False).ids)


__all__ = ["CLAUDE_FACTOR", "TOKENIZER_NAME", "count_tokens"]

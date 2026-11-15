# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Varied text for size fixtures (K352). A run of one character tokenizes to a handful of tokens,
so a fixture sized in characters needs words that vary, as a prompt's do."""

from __future__ import annotations

_WORDS = (
    "the record holds every event the session writes and the window counts each turn before "
    "it sends the prompt to the model which reads tool output files replies and messages"
).split()


def varied_text(n_chars: int) -> str:
    """`n_chars` characters of words numbered so neighbouring words differ."""
    out: list[str] = []
    size = 0
    i = 0
    while size < n_chars:
        word = f"{_WORDS[i % len(_WORDS)]}{i % 97}"
        out.append(word)
        size += len(word) + 1
        i += 1
    return " ".join(out)[:n_chars]

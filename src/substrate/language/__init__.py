# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Language measures: form and lexicon-lookup measures of the text in a Substrate session
(RESEARCH-2026-10-10-language-metrics-r4.md; sprints 302-304). Pure functions; nothing here
reads or writes a record."""

from substrate.language.profile import LIBRARY_VERSION, Params, profile
from substrate.language.text import PREPROCESSING, Parsed, Token, TokenKind, parse, words

__all__ = [
    "LIBRARY_VERSION",
    "PREPROCESSING",
    "Params",
    "Parsed",
    "Token",
    "TokenKind",
    "parse",
    "profile",
    "words",
]

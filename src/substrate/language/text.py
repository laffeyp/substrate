# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""substrate-text-1: the split of one text into tokens, sentences and format counts.

The rules are docs/language/substrate-text-1.md; each comment names the rule it implements. The
expected output for every rule is tests/fixtures/language/substrate-text-1.json.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

PREPROCESSING: Final = "substrate-text-1"


class _Block(StrEnum):
    """The prose block a line belongs to while parsing (B5, B6, B8)."""

    NONE = ""
    PARAGRAPH = "paragraph"
    ITEM = "item"
    QUOTE = "quote"


class TokenKind(StrEnum):
    WORD = "word"
    CODE = "code"
    URL = "url"
    EMAIL = "email"


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    kind: TokenKind


@dataclass(slots=True)
class FormatCounts:
    """Markup counted while parsing; the format measures turn these into rates."""

    paragraphs: int = 0
    headings: int = 0
    list_items: int = 0
    table_rows: int = 0
    block_quotes: int = 0
    code_blocks: int = 0
    code_spans: int = 0
    bold_spans: int = 0
    em_dashes: int = 0
    exclamations: int = 0
    questions: int = 0
    urls: int = 0


@dataclass(frozen=True, slots=True)
class Parsed:
    """One text after substrate-text-1.

    `tokens` is every token in document order; `sentences` holds the sentences of paragraphs,
    list items and block quotes; `units` holds those sentences plus each heading and table cell,
    so phrase matching never runs across a heading or cell boundary.
    """

    tokens: tuple[Token, ...]
    sentences: tuple[tuple[Token, ...], ...]
    units: tuple[tuple[Token, ...], ...]
    format: FormatCounts = field(default_factory=FormatCounts)


# N2: read for tokenizing only.
_FOLD: Final = str.maketrans(
    {"’": "'", "ʼ": "'", "＇": "'", "‐": "-", "‑": "-", " ": " ", " ": " "}
)
# S2.
ABBREVIATIONS: Final = frozenset(
    {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "cf", "e.g", "i.e", "fig", "approx"}
)

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_CLOSING_HASHES = re.compile(r"(?:^|[ \t]+)#+[ \t]*$")
_TABLE = re.compile(r"^ {0,3}\|")
_DELIMITER_ROW = re.compile(r"^[\s|:-]*-[\s|:-]*$")
_BREAK = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_ITEM = re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])[ \t]+(.*)$")
_QUOTE = re.compile(r"^ {0,3}> ?(.*)$")
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)\s]*(?:\s+\"[^\"]*\")?\)")
_AUTOLINK = re.compile(r"<((?:https?://|www\.)[^>\s]+)>")
_URL = re.compile(r"(?:https?://|www\.)\S+")
_URL_TAIL = ".,;:!?)]'\""
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__")
_TERMINAL = re.compile(r"([.!?…]+)([)\]\"'”’»*_]*)(?=\s|$)")

# Private-use characters stand for code spans, URLs and emails while a line is split, so nothing
# inside them splits a sentence or yields other tokens (I1, I4).
_PUA_BASE: Final = 0xE000


def _is_word_char(ch: str) -> bool:
    """W1: letters, marks, digits and the underscore. `isalnum` is true for every L and N
    category; only marks need the category lookup."""
    return ch.isalnum() or ch == "_" or (not ch.isascii() and unicodedata.category(ch)[0] == "M")


class _Inline:
    """Holds the opaque tokens of one text while its lines are split."""

    def __init__(self, counts: FormatCounts) -> None:
        self.opaque: list[Token] = []
        self.counts = counts

    def _hold(self, token: Token) -> str:
        self.opaque.append(token)
        return chr(_PUA_BASE + len(self.opaque) - 1)

    def code_spans(self, s: str) -> str:
        """I1: a backtick run opens a span that the same-length run closes."""
        if "`" not in s:
            return s
        out: list[str] = []
        i = 0
        while i < len(s):
            if s[i] != "`":
                out.append(s[i])
                i += 1
                continue
            j = i
            while j < len(s) and s[j] == "`":
                j += 1
            run = j - i
            k = j
            close = -1
            while k < len(s):
                if s[k] == "`":
                    m = k
                    while m < len(s) and s[m] == "`":
                        m += 1
                    if m - k == run:
                        close = k
                        break
                    k = m
                else:
                    k += 1
            if close < 0:
                out.append(s[i:j])
                i = j
                continue
            self.counts.code_spans += 1
            out.append(self._hold(Token("`" + s[j:close].strip() + "`", TokenKind.CODE)))
            i = close + run
        return "".join(out)

    def links_and_addresses(self, s: str) -> str:
        """I2 and I4."""
        s = _LINK.sub(lambda m: m.group(1), s)
        s = _AUTOLINK.sub(lambda m: self._url(m.group(1)), s)

        def url(m: re.Match[str]) -> str:
            raw = m.group(0)
            body = raw.rstrip(_URL_TAIL)
            return self._url(body) + raw[len(body) :]

        s = _URL.sub(url, s)
        return _EMAIL.sub(lambda m: self._hold(Token(m.group(0), TokenKind.EMAIL)), s)

    def _url(self, text: str) -> str:
        self.counts.urls += 1
        return self._hold(Token(text, TokenKind.URL))

    def emphasis(self, s: str) -> str:
        """I3: `*` and `~~` go; a `_` run goes when a non-word character or an edge is beside it."""
        self.counts.bold_spans += len(_BOLD.findall(s))
        s = s.replace("*", "").replace("~~", "")
        if "_" not in s:
            return s
        out: list[str] = []
        i = 0
        while i < len(s):
            if s[i] != "_":
                out.append(s[i])
                i += 1
                continue
            j = i
            while j < len(s) and s[j] == "_":
                j += 1
            before = s[i - 1] if i > 0 else " "
            after = s[j] if j < len(s) else " "
            if _is_word_char(before) and _is_word_char(after):
                out.append(s[i:j])
            i = j
        return "".join(out)

    def prepare(self, s: str) -> str:
        s = self.code_spans(s)
        s = self.links_and_addresses(s)
        s = self.emphasis(s)
        self.counts.em_dashes += s.count("—")
        self.counts.exclamations += s.count("!")
        return s.translate(_FOLD)

    def tokens(self, s: str) -> list[Token]:
        """W1-W3 on a prepared string."""
        out: list[Token] = []
        i, n = 0, len(s)
        while i < n:
            ch = s[i]
            code = ord(ch) - _PUA_BASE
            if 0 <= code < len(self.opaque):
                out.append(self.opaque[code])
                i += 1
                continue
            if not _is_word_char(ch):
                i += 1
                continue
            j = i + 1
            while j < n:
                c = s[j]
                if _is_word_char(c):
                    j += 1
                    continue
                if j + 1 < n and _is_word_char(s[j + 1]):
                    if c in "'-.":
                        j += 2
                        continue
                    if c == "," and s[j - 1].isdigit() and s[j + 1].isdigit():
                        j += 2
                        continue
                break
            out.append(Token(s[i:j].casefold(), TokenKind.WORD))
            i = j
        return out

    def sentences(self, s: str) -> list[list[Token]]:
        """S1-S4 on one prepared segment (a block, or the part of one between hard breaks)."""
        out: list[list[Token]] = []
        start = 0
        for m in _TERMINAL.finditer(s):
            run = m.group(1)
            if run == "." and m.start() > 0 and _is_word_char(s[m.start() - 1]):
                # S2: the token that touches the period; only the last chunk is tokenized.
                chunk = s[start : m.start()].rsplit(None, 1)[-1]
                last = self.tokens(chunk)[-1:]
                if last and last[0].kind is TokenKind.WORD:
                    word = last[0].text
                    if word in ABBREVIATIONS or (len(word) == 1 and word.isalpha()):
                        continue
            if "?" in run:
                self.counts.questions += 1
            out.append(self.tokens(s[start : m.end()]))
            start = m.end()
        out.append(self.tokens(s[start:]))
        return [t for t in out if t]


def parse(text: str) -> Parsed:
    """substrate-text-1 on one text."""
    counts = FormatCounts()
    inline = _Inline(counts)
    tokens: list[Token] = []
    sentences: list[tuple[Token, ...]] = []
    units: list[tuple[Token, ...]] = []

    def emit_unit(toks: list[Token], is_sentence: bool) -> None:
        if not toks:
            return
        tokens.extend(toks)
        units.append(tuple(toks))
        if is_sentence:
            sentences.append(tuple(toks))

    def flush_prose(lines: list[str]) -> None:
        # B8: soft breaks join with a space; a hard break (two spaces, or a backslash) ends a segment.
        segment: list[str] = []
        for line in lines:
            hard = line.endswith("  ") or line.endswith("\\")
            segment.append(line.rstrip(" \\") if hard else line.strip())
            if hard:
                _emit_segment(" ".join(segment))
                segment = []
        if segment:
            _emit_segment(" ".join(segment))

    def _emit_segment(raw: str) -> None:
        for sent in inline.sentences(inline.prepare(raw)):
            emit_unit(sent, True)

    def flush_cells(row: str) -> None:
        cells = row.strip().strip("|").split("|")
        for cell in cells:
            emit_unit(inline.tokens(inline.prepare(cell)), False)

    lines = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    block: list[str] = []
    kind = _Block.NONE
    fence: tuple[str, int] | None = None

    def flush() -> None:
        nonlocal block, kind
        if block:
            flush_prose(block)
        block, kind = [], _Block.NONE

    def start(new_kind: _Block, first: str) -> None:
        nonlocal block, kind
        flush()
        block, kind = [first], new_kind
        if new_kind is _Block.PARAGRAPH:
            counts.paragraphs += 1
        elif new_kind is _Block.ITEM:
            counts.list_items += 1
        elif new_kind is _Block.QUOTE:
            counts.block_quotes += 1

    for line in lines:
        if fence is not None:  # B1
            m = re.match(
                r"^ {0,3}(" + re.escape(fence[0]) + "{" + str(fence[1]) + r",})[ \t]*$", line
            )
            if m:
                fence = None
            continue
        if not line.strip():  # B2
            flush()
            continue
        m = _FENCE.match(line)
        if m:  # B1: a fence may interrupt a paragraph
            flush()
            fence = (m.group(1)[0], len(m.group(1)))
            counts.code_blocks += 1
            continue
        m = _HEADING.match(line)
        if m:  # B3
            flush()
            counts.headings += 1
            body = _CLOSING_HASHES.sub("", m.group(2) or "")
            emit_unit(inline.tokens(inline.prepare(body)), False)
            continue
        if _TABLE.match(line):  # B4
            flush()
            if not _DELIMITER_ROW.match(line):
                counts.table_rows += 1
                flush_cells(line)
            continue
        if _BREAK.match(line):  # B7
            flush()
            continue
        m = _ITEM.match(line)
        if m:  # B5
            start(_Block.ITEM, m.group(1))
            continue
        m = _QUOTE.match(line)
        if m:  # B6
            if kind is _Block.QUOTE:
                block.append(m.group(1))
            else:
                start(_Block.QUOTE, m.group(1))
            continue
        if kind is not _Block.NONE:  # B8: continuation
            block.append(line)
        else:
            start(_Block.PARAGRAPH, line)
    flush()
    return Parsed(tuple(tokens), tuple(sentences), tuple(units), counts)


def words(parsed: Parsed) -> list[str]:
    """The word tokens of a text, in order: the input of every lexical measure."""
    return [t.text for t in parsed.tokens if t.kind is TokenKind.WORD]

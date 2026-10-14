# substrate-text-1: preprocessing for language measures

*Version 1, 2026-10-12 (sprint 302). Every language measure starts from this split of a text into tokens and sentences. A stored value names `substrate-text-1`; a change to any rule below is a new version, because a tokenizer change moves nearly every measure at once (`RESEARCH-2026-10-10-language-metrics-r4.md`). The fixtures in `tests/fixtures/language/substrate-text-1.json` define the expected output; each names the rule it tests.*

## Input and output

The input is one text: a `UserMessage.text`, a `ModelReply.text` or a `PromptComposed` text. The output is:

- **tokens**, in document order: every word token from headings, paragraphs, list items, block quotes and table cells;
- **sentences**: lists of tokens from paragraphs, list items and block quotes only. Headings and table rows are not sentences; their tokens count in **tokens** and not in the sentence series.

A sentence with no token is dropped. An empty text has no tokens and no sentences.

## 1. Normalization

**N1.** The text is put in Unicode NFC. NFC composes `e` + U+0301 into `é` and changes nothing a reader would see. NFKC is not used: it rewrites fullwidth forms, ligatures and superscripts, which are visible choices of the writer.

**N2.** For tokenizing only, these characters are read as their ASCII form: U+2019, U+02BC and U+FF07 as the apostrophe `'`; U+2010 and U+2011 as the hyphen `-`; U+00A0 and U+202F as a space. The text itself keeps the originals, so format counts (em-dashes, curly quotes) see what was written. En and em dashes are not hyphens.

**N3.** Word tokens are case-folded with Python's `str.casefold()` (`Straße` → `strasse`). Code, URL and email tokens keep their case.

## 2. Blocks

The text is read line by line into blocks, following the CommonMark constructs model replies use.

**B1. Fenced code.** A line of three or more backticks or tildes, indented at most three spaces, opens a code block; a line of the same character, at least as long, closes it. An unclosed fence runs to the end of the text. A fence may interrupt a paragraph. Code blocks give no tokens and no sentences; format measures count them.

**B2. Blank lines** end the current block.

**B3. ATX headings.** A line of one to six `#` followed by a space or the line's end, indented at most three spaces, is a heading. Trailing `#`s are removed. `#hashtag` and `#5` are not headings.

**B4. Tables.** A run of lines starting with `|` (after up to three spaces) is a table. The delimiter row (only `|`, `-`, `:` and spaces) is dropped. Each cell is tokenized.

**B5. List items.** A line starting (after any indent) with `-`, `*` or `+` and a space, or one to nine digits, `.` or `)` and a space, starts a list item; the marker is not text. Following non-blank lines that start no other block continue the item.

**B6. Block quotes.** A leading `>` and one optional space are removed; the rest is read as paragraph text.

**B7. Rules.** A line of three or more `-`, `*` or `_` and nothing else (spaces allowed) is a thematic break and gives no text. Setext headings are not recognized: a `---` line under text is a break, and the text above stays a paragraph.

**B8. Paragraphs.** Any other lines. Within a paragraph or list item, a line break is soft (read as a space), except a hard break: a line ending in two or more spaces or a backslash. A hard break ends a sentence. This is CommonMark's rule; model replies rely on it for `**Model:** x` lines.

## 3. Inline markup

Applied inside headings, paragraphs, list items, block quotes and table cells.

**I1. Code spans.** A run of backticks opens a span that the same-length run closes. The span is one token, written as a backtick, its content with outer spaces removed, and a backtick (``` ``a`b`` ``` → `` `a`b` ``). The span is opaque: nothing inside it splits a sentence or yields other tokens. An unmatched backtick is plain text.

**I2. Links and images.** `[text](url)` and `![text](url)` keep `text` and drop the target. `<scheme://…>` autolinks become the URL.

**I3. Emphasis.** `*` is removed wherever it appears outside code. A run of `_` is removed when a space, punctuation or the edge of the block is on at least one side, so `snake_case_name` keeps its underscores and `_italic_` loses them. `~~` is removed.

**I4. URLs and emails.** `http://`, `https://` or `www.` followed by non-space characters is one URL token; trailing `. , ; : ! ? ) ] ' "` are not part of it. `local@domain.tld` is one email token.

## 4. Word tokens

**W1.** A word token is a run of letters, marks, digits and `_` (Unicode categories L, M, N, and U+005F), in which these single characters join the characters on either side:

- `'` (after N2) between two letters or digits: `don't`, `model's`;
- `-` (after N2) between two letters or digits: `well-known`, `state-of-the-art`, `claude-opus-5-5`, `2026-10-12`;
- `.` between two letters or digits: `e.g`, `file.txt`, `3.5`, `v2.5`;
- `,` between two digits: `1,000`.

**W2.** An apostrophe or hyphen at either end of a run is not part of the token: `'quoted'` → `quoted`, `students'` → `students`, `pre-` → `pre`.

**W3.** Everything else is not a token: punctuation, symbols, emoji, arrows, `%`, `/`, `:` (so `10:30` → `10`, `30`), en and em dashes.

## 5. Sentences

Sentences are split inside one paragraph, list item or block quote; the end of the block, and a hard break, also end a sentence.

**S1.** A sentence ends after a run of `.`, `!`, `?` or `…`, plus any closing `)`, `]`, `"`, `'`, `”`, `’`, `»`, `*` or `_`, when whitespace or the end of the block follows. A run of three dots is an ellipsis and ends a sentence like `…`.

**S2.** A `.` does not end a sentence when the token before it is a single letter (`J. R. Smith`) or one of: `mr`, `mrs`, `ms`, `dr`, `prof`, `sr`, `jr`, `st`, `vs`, `cf`, `e.g`, `i.e`, `fig`, `approx`. `etc` is not on the list: it ends sentences as often as it sits inside them.

**S3.** A lowercase letter after `.` does not stop the split. Unicode's sentence rule SB8 would join `ok. then`; Substrate's users often write without capitals, and SB8 would merge their sentences.

**S4.** `:` and `;` never end a sentence.

## How the reference implementations differ

The measure library (sprint 304) checks its values against these packages. Where a value disagrees, these differences are the first place to look.

| | Substrate | lexicalrichness 0.5.1 | textstat 0.7.13 | quanteda 4 | koRpus |
|---|---|---|---|---|---|
| Source read | this spec | `lexicalrichness.py` (`preprocess`, `tokenize`) | `backend/` (`remove_punctuation`, `list_words`, `count_sentences`) | `tokens()` reference page | `tokenize()` reference page |
| Case | casefold | lowercase | kept (lowercase for syllables) | kept | not stated |
| Digits | tokens | deleted | kept | kept | not stated |
| Hyphenated words | one token | hyphen deleted: `wellknown` | hyphen deleted: `wellknown` | one token | one token (`ign.comp="-"`) |
| `don't` | one token | two: `don`, `t` | one token | one token (UAX #29) | split unless `suf` is on |
| `don’t` (U+2019) | one token `don't` | one token `don’t` | `dont` | one token (U+2019 is MidNumLet) | split unless `suf` is on |
| Punctuation | not tokens | not tokens | not tokens | tokens unless `remove_punct=TRUE` | not stated |
| URLs, emails | one token | split | split on punctuation | one token | not stated |
| Markdown, code | blocks and spans handled | none | none | none | none |
| Sentence ends | S1–S4 | — | every `.`, `!`, `?`; sentences of two words or fewer not counted | ICU with rules for `Mr.` | `. ! ? ; :` |

UAX #29 (Unicode 18.0.0, revision 49) puts U+0027, U+2019 and `.` in the classes that join letters (WB6, WB7) and `.` between digits (WB11, WB12); it leaves `-` out unless tailored. W1 follows it for apostrophes and periods and tailors in the hyphen, as quanteda 4 does.

## Known costs of these choices

- `Plan A. Then …` does not split (S2's single-letter rule).
- `__init__` in prose, outside backticks, becomes `init` (I3).
- A sentence that ends in `e.g.` or `vs.` is joined to the next one (S2).
- Indented code (four spaces) is read as text. Model replies fence their code.

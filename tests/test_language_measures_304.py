# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 304: the measure library.

Three kinds of check: the tokenizer reproduces K302's fixtures and K303's lexicon entries; each
measure equals a value computed by hand from its definition; and the measures with a published
implementation agree with it on the 600 length-experiment replies (lexicalrichness for MATTR, MTLD
and HD-D, powerlaw for the Zipf fit, nolds for DFA, the cmudict package for syllables).
"""

from __future__ import annotations

import json
import math
import random
import statistics
import time
import zlib
from collections import Counter
from pathlib import Path

import pytest

from substrate.language import measures as m
from substrate.language import parse, profile, words
from substrate.language import relation as rel
from substrate.language.lexicon import Matcher, load, word_runs
from substrate.language.profile import Params

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads(
    (ROOT / "tests/fixtures/language/substrate-text-1.json").read_text(encoding="utf-8")
)
REPLIES = [
    json.loads(line)["text"]
    for name in ("glm-5.2_cloud.jsonl", "kimi-k2.7-code_cloud.jsonl")
    for line in (ROOT / "process/runs/assays/length_drift_2026-10-12_k299" / name).open(
        encoding="utf-8"
    )
]
LEXICONS = sorted(p.stem for p in (ROOT / "src/substrate/language/lexicons").glob("*.toml"))


# ---- the tokenizer --------------------------------------------------------------------------


@pytest.mark.parametrize("case", FIXTURES["cases"], ids=lambda c: c["id"])
def test_tokenizer_reproduces_the_fixture(case: dict[str, object]) -> None:
    parsed = parse(str(case["text"]))
    assert [t.text for t in parsed.tokens] == case["tokens"]
    assert [[t.text for t in s] for s in parsed.sentences] == case["sentences"]


@pytest.mark.parametrize("name", LEXICONS)
def test_every_lexicon_entry_tokenizes_to_itself(name: str) -> None:
    lex = load(name)
    for key, entries in lex.lists.items():
        if key == "suffixes":
            continue
        for entry in entries:
            term = (
                entry[: -len(lex.wildcard)]
                if lex.wildcard and entry.endswith(lex.wildcard)
                else entry
            )
            assert [t.text for t in parse(term).tokens] == term.split(" "), (
                f"{name}.{key}: {entry!r}"
            )


# ---- each measure by hand ---------------------------------------------------------------------


def test_diversity_by_hand() -> None:
    assert m.ttr(["a", "b", "a"]) == pytest.approx(2 / 3)
    # Windows [a b], [b a], [a a]: TTR 1, 1, 0.5.
    assert m.mattr(["a", "b", "a", "a"], window=2) == pytest.approx(2.5 / 3)
    assert m.mattr(["a"] * 5, window=10) is None
    # a a b b: the running TTR reaches 0.5 at each second word, two full factors each way.
    assert m.mtld(["a", "a", "b", "b"]) == pytest.approx(2.0)
    assert m.mtld(["a", "b", "c"]) is None
    # 42 tokens, 6 types of 7: every type is certain to appear in a draw of 42.
    assert m.hdd([t for t in "abcdef" for _ in range(7)]) == pytest.approx(6 / 42)
    assert m.hdd(["a"] * 41) is None


def test_frequency_and_information_by_hand() -> None:
    z = m.zipf(["a", "b", "c", "c"])
    alpha = 1 + 3 / (math.log(1 / 0.5) * 2 + math.log(2 / 0.5))
    assert z["alpha"] == pytest.approx(alpha) and z["s"] == pytest.approx(1 / (alpha - 1))
    distinct = [f"w{i}" for i in range(500)]
    h = m.heaps(distinct)
    assert h["beta"] == pytest.approx(1.0) and h["k"] == pytest.approx(1.0)
    assert m.entropy(["a", "b"]) == pytest.approx(1.0)
    assert m.entropy(list("aabbccdd")) == pytest.approx(2.0)
    text = "the same line\n" * 50
    assert m.compression_ratio(text) == len(zlib.compress(text.encode(), 9)) / len(text.encode())


def test_repetition_and_burstiness_by_hand() -> None:
    # a b c a b c: trigrams abc, bca, cab, abc; abc occurs twice.
    assert m.repeated_ngram_rate([["a", "b", "c", "a", "b", "c"]], 3) == pytest.approx(0.5)
    periodic = [w for _ in range(10) for w in ("x", "y", "z")]
    assert m.burstiness(periodic, 5)["mean"] == pytest.approx(-1.0)
    # x at 0, 1, 11, 12, 22: gaps 1, 10, 1, 10; mean 5.5, sd 4.5; B = (4.5 - 5.5) / 10.
    clustered = [f"o{i}" for i in range(23)]
    for i in (0, 1, 11, 12, 22):
        clustered[i] = "x"
    out = m.burstiness(clustered, 5)
    assert out["mean"] == pytest.approx(-0.1) and out["words"] == 1.0


def test_rhythm_and_readability_by_hand() -> None:
    r = m.rhythm([10, 20])
    assert (r["mean"], r["sd"], r["cv"]) == (15.0, 5.0, pytest.approx(1 / 3))
    # "The cat sat." three words, one sentence, one syllable each in CMUdict.
    read = m.readability(["the", "cat", "sat"], 1)
    assert read["flesch_reading_ease"] == pytest.approx(206.835 - 1.015 * 3 - 84.6 * 1)
    assert read["flesch_kincaid_grade"] == pytest.approx(0.39 * 3 + 11.8 * 1 - 15.59)
    assert m.syllables("readability") == 5  # CMUdict
    assert (
        m.syllables("zorbleflax") == 3
    )  # not in CMUdict: vowel groups o, e, a; the final e is not silent


def test_relation_by_hand() -> None:
    user, reply = parse("deploy the server"), parse("the server is up now")
    assert rel.length_ratio(user, reply) == pytest.approx(5 / 3)
    # Content types: user {deploy, server}; reply {server, up}. "now" is a LIWC adverb.
    assert rel.lexical_echo(user, reply) == pytest.approx(1 / 2)
    copy = rel.phrase_copy(
        parse("the quick brown fox jumps"), parse("a quick brown fox jumps high")
    )
    assert copy["shared"] == 1.0 and copy["longest_run"] == 4.0
    same = parse("I think we should ship it now, because it is ready.")
    assert rel.lsm(same, same)["lsm"] == pytest.approx(1.0)
    x = "a sentence about compression distance " * 20
    cx = len(zlib.compress(x.encode(), 9))
    assert rel.ncd(x, x) == pytest.approx((len(zlib.compress((x + x).encode(), 9)) - cx) / cx)
    leader = [0, 1, 3, 2, 5, 4, 6, 9]
    assert rel.lagged_correlation(leader, [0, *leader[:-1]]) == pytest.approx(1.0)


def test_matcher_takes_the_longest_term_without_overlap() -> None:
    matcher = Matcher(["like", "looks like", "kind of"])
    assert matcher.matches(["it", "looks", "like", "rain", "kind", "of", "like", "that"]) == [
        (1, 2),
        (4, 2),
        (6, 1),
    ]
    liwc = load("liwc2007").matcher("impersonal_pronouns")
    assert liwc.matches(["anybody", "anybodies", "table"]) == [(0, 1), (1, 1)]


def test_padding_is_counted_where_it_sits() -> None:
    text = (
        "Great question. The port is 8080. It is set in the config. Let me know if you need more."
    )
    measures = profile(text)["partials"]["lexicon"]
    assert measures["padding_restatement_opening"] == 1
    assert measures["padding_offer_of_more_closing"] == 1
    assert measures["padding_restatement"] == 1


# ---- the published implementations ------------------------------------------------------------


def test_diversity_agrees_with_lexicalrichness() -> None:
    from lexicalrichness import LexicalRichness

    for text in REPLIES:
        ws = words(parse(text))
        ref = LexicalRichness(ws, preprocessor=None, tokenizer=None)
        if len(ws) >= 100:
            assert m.mattr(ws, 100) == pytest.approx(ref.mattr(100), abs=1e-12)
        assert m.mtld(ws) == pytest.approx(ref.mtld(0.72), abs=1e-9)
        assert m.hdd(ws) == pytest.approx(ref.hdd(42), abs=1e-12)


def test_zipf_agrees_with_powerlaw() -> None:
    import powerlaw

    for text in REPLIES[:200]:
        ws = words(parse(text))
        fit = powerlaw.Fit(
            list(Counter(ws).values()), discrete=True, xmin=1, estimate_discrete=True, verbose=False
        )
        assert m.zipf(ws)["alpha"] == pytest.approx(fit.power_law.alpha, abs=1e-12)


def test_dfa_agrees_with_nolds() -> None:
    import numpy as np
    import nolds

    rng = random.Random(3)  # noqa: S311 - a seeded test series, not a secret
    walk: list[float] = []
    acc = 0.0
    for _ in range(3000):
        acc += rng.gauss(0, 1)
        walk.append(acc)
    lengths = [
        float(sum(1 for t in s if t.kind == "word"))
        for text in REPLIES
        for s in parse(text).sentences
    ]
    for series in ([rng.gauss(0, 1) for _ in range(3000)], walk, lengths):
        sizes = m.dfa_windows(len(series))
        ref = nolds.dfa(np.array(series), nvals=sizes, overlap=False, order=1, fit_exp="poly")
        assert m.dfa(series, sizes) == pytest.approx(float(ref), abs=1e-9)


def test_syllable_table_equals_cmudict() -> None:
    import cmudict

    table = m._cmu()
    source = cmudict.dict()
    assert len(table) == sum(1 for prons in source.values() if prons)
    for word, prons in source.items():
        if prons:
            assert table[word] == sum(1 for p in prons[0] if p[-1].isdigit()), word


# ---- the profile ------------------------------------------------------------------------------


def test_profile_names_what_it_was_computed_with() -> None:
    out = profile("A short reply. It says two things.")
    assert out["preprocessing"] == "substrate-text-1"
    assert out["library"] and out["compressor"].startswith("zlib ")
    assert out["params"]["mattr_window"] == Params().mattr_window
    assert set(out["lexicons"]) >= {"liwc2007", "hedges_hyland_2005", "kobak_style_2024_rare"}
    assert out["measures"]["words"] == 7 and out["measures"]["sentences"] == 2
    assert out["measures"]["mattr"] is None  # shorter than the window


def test_every_reply_profiles() -> None:
    for text in REPLIES:
        out = profile(text)
        assert out["measures"]["words"] == len(words(parse(text)))
        assert sum(out["partials"]["freq"].values()) == out["measures"]["words"]
        assert len(word_runs(parse(text).units)) >= 1


def test_a_1500_token_reply_measures_in_under_5_ms() -> None:
    text = ""
    for reply in REPLIES:
        text = f"{text}\n\n{reply}" if text else reply
        if len(parse(text).tokens) >= 1500:
            break
    profile(text)
    times = []
    for _ in range(30):
        start = time.perf_counter()
        profile(text)
        times.append(time.perf_counter() - start)
    assert statistics.median(times) < 0.005, f"median {1000 * statistics.median(times):.2f} ms"

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Tests for the frame format and torn-tail recovery (technical §3.3)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

import substrate.record.framing as framing
from substrate.errors import CRCMismatchError, FrameTooLargeError, TornFrameError


def _env(seq, payload=None):
    return {
        "seq": seq,
        "kind": "K",
        "schema": "K@1",
        "producer": None,
        "t": 0.0,
        "payload": payload if payload is not None else {"n": seq},
    }


def test_frame_is_one_terminated_line_and_verifies():
    line = framing.frame(_env(1))
    assert line.endswith(b"\n") and line.count(b"\n") == 1
    env = framing.verify_line(line[:-1])
    assert env == _env(1)  # crc stripped; remainder is the original envelope
    assert "crc" not in env


def test_frame_rejects_preexisting_crc():
    with pytest.raises(ValueError):
        framing.frame({**_env(1), "crc": "deadbeef"})


def test_frame_too_large(monkeypatch):
    monkeypatch.setattr(framing, "FRAME_MAX_BYTES", 32)
    with pytest.raises(FrameTooLargeError):
        framing.frame(_env(1, payload={"big": "x" * 100}))


def test_verify_detects_crc_corruption():
    line = framing.frame(_env(7))[:-1]
    # flip a byte inside the payload so the recomputed crc no longer matches
    corrupt = line.replace(b'"n":7', b'"n":8')
    with pytest.raises(CRCMismatchError):
        framing.verify_line(corrupt)


def test_verify_unparseable_is_torn():
    with pytest.raises(TornFrameError):
        framing.verify_line(b"{not json")


def test_recover_keeps_whole_frames_and_cuts_torn_tail():
    good = framing.frame(_env(1)) + framing.frame(_env(2)) + framing.frame(_env(3))
    torn = good + b'{"seq":4,"kind":"K","sch'  # partial, unterminated final line
    frames, cut = framing.recover(torn)
    assert [f["seq"] for f in frames] == [1, 2, 3]
    assert cut == len(good)  # truncate point = end of the last whole frame


def test_recover_cuts_at_crc_mismatch_in_the_middle():
    f1 = framing.frame(_env(1))
    f2 = framing.frame(_env(2))
    bad = f2.replace(b'"n":2', b'"n":9')  # same length, broken crc, still newline-terminated
    frames, cut = framing.recover(f1 + bad + framing.frame(_env(3)))
    assert [f["seq"] for f in frames] == [1]
    assert cut == len(f1)


@given(seqs=st.lists(st.integers(min_value=0, max_value=2**53 - 1), min_size=0, max_size=30))
def test_property_frame_then_recover_roundtrips(seqs):
    data = b"".join(framing.frame(_env(s)) for s in seqs)
    frames, cut = framing.recover(data)
    assert [f["seq"] for f in frames] == seqs
    assert cut == len(data)


def test_crc_splice_is_byte_identical_to_full_reencode():
    # perf: frame() splices "crc":"<8hex>" into B_hash instead of re-encoding the whole
    # envelope a second time. Guard the byte-identity that optimization depends on — the
    # spliced frame MUST equal a full rfc8785 re-encode of {**envelope, crc} for every
    # envelope shape, across payloads exercising key-sort order and nested structures.
    import rfc8785

    from substrate.encoding import to_canonical_builtins

    cases = [
        {
            "seq": 0,
            "kind": "substrate.RunStarted",
            "schema": "substrate.RunStarted@1",
            "producer": None,
            "t": 1.0,
            "payload": {"a": 1, "z": [1, 2], "m": {"k": "v"}},
        },
        {
            "seq": 7,
            "kind": "CountReached",
            "schema": "CountReached@1",
            "producer": {"kind": "c", "instance": "01ABC", "parent": None},
            "t": 1.5,
            "payload": {"n": 3},
        },
        {"seq": 99, "kind": "X", "schema": "X@1", "producer": None, "t": 0.0, "payload": {}},
        # unicode / JCS-escape cases (review #6): non-ASCII, embedded quote/backslash/control,
        # and a U+2028 line separator — JCS escaping must be byte-identical through the splice.
        {
            "seq": 5,
            "kind": "Note",
            "schema": "Note@1",
            "producer": None,
            "t": 2.0,
            "payload": {
                "unicode": "café — naïve 日本語 😀",
                "quote": 'he said "hi"',
                "backslash": "a\\b\\c",
                "control": "tab\tnewline\nend",
                "u2028": "line sep para",
            },
        },
    ]
    for env in cases:
        line = framing.frame(env)
        b_disk = line[:-1]  # strip the trailing newline
        builtins = to_canonical_builtins(env)
        crc = b_disk[len(b'{"crc":"') :].split(b'"', 1)[0]  # extract the spliced crc
        full = rfc8785.dumps({**builtins, "crc": crc.decode()})
        assert b_disk == full, f"splice diverged from full re-encode for {env['kind']}"
        # and it still verifies (crc recomputes correctly over B_hash)
        assert framing.verify_line(b_disk)["seq"] == env["seq"]


def test_frame_fails_loud_if_a_key_sorts_before_crc():
    # the crc-splice precondition guard (review #6): a top-level envelope key sorting before
    # "crc" under JCS would make the splice emit non-canonical bytes — frame() MUST refuse it
    # loudly (a mis-spliced frame still verifies, so this guard is the only fail-loud catch).
    bad_env = {
        "seq": 0,
        "kind": "X",
        "schema": "X@1",
        "producer": None,
        "t": 0.0,
        "payload": {},
        "alpha": "a key that sorts before crc",  # 'a' < 'c'
    }
    with pytest.raises(ValueError, match="sort before 'crc'"):
        framing.frame(bad_env)

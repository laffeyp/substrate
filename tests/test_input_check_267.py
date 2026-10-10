# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The accepted Producer input types (technical §8.3 / F-PROD-3, amended K267).

Replaces test_sealing.py: the kernel no longer seals inputs (read-only mappings, tuples); it
validates them here and hands each Producer a fresh decode of the recorded bytes
(test_input_isolation_267.py). The rejections are unchanged.
"""

import datetime

import pytest
from msgspec import Struct

from substrate.errors import InputTypeError
from substrate.record.inputs import check_input
from substrate.types import BlobRef


class Frozen(Struct, frozen=True):
    n: int


class Mutable(Struct):
    n: int


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        3,
        2.5,
        "x",
        [1, [2, 3]],
        (1, 2),
        frozenset({1}),
        {"n": 2, "nested": {"a": [1]}},
        Frozen(1),
        BlobRef(sha256="sha256:" + "0" * 64, bytes=1),
    ],
)
def test_accepted_values_pass(value):
    check_input(value)


@pytest.mark.parametrize(
    "value, where",
    [
        (b"raw", "$"),
        ({"v": b"raw"}, "$.v"),
        (object(), "$"),
        (Mutable(1), "$"),
        ({1: "a"}, "$"),
        ({"when": datetime.datetime(2026, 10, 9)}, "$.when"),
        ([{"deep": [object()]}], "$[0].deep[0]"),
    ],
)
def test_rejected_values_name_their_path(value, where):
    with pytest.raises(InputTypeError) as exc:
        check_input(value)
    assert where in str(exc.value)

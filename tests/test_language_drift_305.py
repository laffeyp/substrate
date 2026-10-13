# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 305: the Page-Hinkley detector.

Checked against river 0.26.1's `PageHinkley` (no forgetting, increases only) on the series and on
its negation, which covers both directions; and on series whose answer is known.
"""

from __future__ import annotations

import random

import pytest

from substrate.language.drift import (
    DEFAULT_DRIFT,
    Direction,
    DriftParams,
    PageHinkley,
    detect,
    trajectory,
    warmup_scale,
)


def _river_first_alarm(series: list[float], p: DriftParams, sign: int) -> int | None:
    from river.drift import PageHinkley as RiverPH

    scale = warmup_scale(series, p.warmup)
    ref = RiverPH(
        min_instances=p.warmup, delta=p.delta, threshold=p.threshold, alpha=1.0, mode="up"
    )
    for i, x in enumerate(series):
        ref.update(sign * x / scale)
        if ref.drift_detected:
            return i
    return None


def test_both_directions_agree_with_river() -> None:
    rng = random.Random(11)  # noqa: S311 - a seeded test series, not a secret
    compared = 0
    for _ in range(300):
        n = rng.choice([40, 80, 200])
        size, at = rng.choice([0.0, 0.5, 1.0, 2.0, -1.0]), rng.randrange(10, n - 5)
        series = [rng.gauss(10, 3) + (3 * size if i >= at else 0.0) for i in range(n)]
        p = DriftParams(
            rng.choice([0.05, 0.25, 0.5]), rng.choice([2.0, 5.0, 10.0]), rng.choice([5, 10, 20])
        )
        steps = trajectory(series, p)
        for sign, k in ((1, 0), (-1, 1)):
            ours = next(
                (i for i, t in enumerate(steps) if i >= p.warmup - 1 and t[k] > p.threshold), None
            )
            assert ours == _river_first_alarm(series, p, sign)
            compared += 1
    assert compared == 600


def test_the_first_alarm_is_the_first_crossing_and_the_detector_restarts() -> None:
    rng = random.Random(4)  # noqa: S311 - a seeded test series, not a secret
    series = [rng.gauss(0, 1) for _ in range(30)] + [rng.gauss(4, 1) for _ in range(60)]
    p = DEFAULT_DRIFT
    alarms = detect(series, p)
    steps = trajectory(series, p)
    first = next(
        i for i, (up, down) in enumerate(steps) if i >= p.warmup - 1 and max(up, down) > p.threshold
    )
    assert alarms and alarms[0].index == first and alarms[0].direction is Direction.UP
    assert alarms[0].index >= 30
    # After an alarm the next one needs a new warm-up of 20 values.
    assert all(b.index - a.index >= p.warmup for a, b in zip(alarms, alarms[1:], strict=False))


def test_no_test_before_the_warm_up_ends() -> None:
    ph = PageHinkley(DriftParams(0.0, 0.1, 5))
    assert [ph.update(x, i) for i, x in enumerate([0, 100, 0, 100])] == [None] * 4


def test_a_drop_is_a_down_alarm() -> None:
    series = [10.0, 11.0, 9.0, 10.5, 9.5] * 4 + [2.0] * 10
    alarms = detect(series, DEFAULT_DRIFT)
    assert alarms and alarms[0].direction is Direction.DOWN and alarms[0].index >= 20


def test_defaults_on_known_series() -> None:
    rng = random.Random(9)  # noqa: S311 - a seeded test series, not a secret
    quiet = [rng.gauss(0, 1) for _ in range(50)]
    assert detect(quiet, DEFAULT_DRIFT) == []
    stepped = [rng.gauss(0, 1) for _ in range(25)] + [rng.gauss(3, 1) for _ in range(25)]
    alarms = detect(stepped, DEFAULT_DRIFT)
    assert alarms and 25 <= alarms[0].index < 40


def test_a_warm_up_under_two_values_is_refused() -> None:
    with pytest.raises(ValueError, match="warmup must be at least 2, got 1"):
        PageHinkley(DriftParams(0.1, 1.0, 1))

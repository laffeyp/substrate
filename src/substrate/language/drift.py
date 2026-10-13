# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The Page-Hinkley test for a change in the mean of one measure's series (sprint 305).

Page (1954), Hinkley (1971), in the incremental form MOA and river use: with x_bar_t the mean of
x_1..x_t,

    up:   m_t = sum_{i<=t} (x_i - x_bar_i - delta),   alarm when m_t - min_{k<=t} m_k > lambda
    down: n_t = sum_{i<=t} (x_i - x_bar_i + delta),   alarm when max_{k<=t} n_k - n_t > lambda

Both directions run together. `delta` and `lambda` are in standard deviations of the first
`warmup` values, as CUSUM designs state k and h (Montgomery, Introduction to Statistical Quality
Control): the detector holds those values, takes their sample standard deviation, then runs the
test over every value from the first, so one setting means the same for sentence length and for a
hedge rate. No test is made before `warmup` values. After an alarm the detector starts again,
warm-up included. There is no forgetting factor (river's `alpha`); Hinkley's test has none.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True, slots=True)
class DriftParams:
    delta: float
    threshold: float
    warmup: int


# Chosen by scripts/language_drift_table.py (docs/language/drift.md): the setting with the most
# 1 SD steps found within 25 values among those with at most 5% false alarms over 50 values.
DEFAULT_DRIFT = DriftParams(delta=0.25, threshold=10.0, warmup=20)


# The measures the live detector watches (§ W.2), one per thing a setting is meant to move:
# length (words, sentence length, padding), tone (hedges, boosters, contractions, positive emotion,
# exclamation marks) and guidance (Kobak's style words, em-dashes, bold, list items).
WATCHED: tuple[str, ...] = (
    "words",
    "sentence_length_mean",
    "rate_padding_restatement_opening",
    "rate_padding_offer_of_more_closing",
    "rate_hedges_hyland",
    "rate_boosters_hyland",
    "rate_contractions",
    "rate_liwc_positive_emotion",
    "format_exclamations",
    "rate_kobak_style",
    "format_em_dashes",
    "format_bold_spans",
    "format_list_items",
)


@dataclass(frozen=True, slots=True)
class Alarm:
    index: int  # position in the series of the value that raised it
    direction: Direction
    statistic: float  # the test value, in warm-up standard deviations


class PageHinkley:
    def __init__(self, params: DriftParams) -> None:
        if params.warmup < 2:
            raise ValueError(f"PageHinkley: warmup must be at least 2, got {params.warmup}")
        self.params = params
        self._reset()

    def _reset(self) -> None:
        self._buffer: list[float] = []
        self._scale: float | None = None
        self._n = 0
        self._mean = 0.0
        self._up = 0.0
        self._down = 0.0
        self._min_up = math.inf
        self._max_down = -math.inf

    def _step(self, x: float) -> tuple[float, float]:
        """Add one value scaled to warm-up SDs; return the up and down test values."""
        self._n += 1
        self._mean += (x - self._mean) / self._n
        dev = x - self._mean
        self._up += dev - self.params.delta
        self._down += dev + self.params.delta
        self._min_up = min(self._min_up, self._up)
        self._max_down = max(self._max_down, self._down)
        return self._up - self._min_up, self._max_down - self._down

    def update(self, x: float, index: int) -> Alarm | None:
        """Feed the value at `index`; return an alarm if this value raises one."""
        if self._scale is None:
            self._buffer.append(x)
            if len(self._buffer) < self.params.warmup:
                return None
            self._scale = warmup_scale(self._buffer, self.params.warmup)
            stats = (0.0, 0.0)
            for v in self._buffer:
                stats = self._step(v / self._scale)
            self._buffer = []
        else:
            stats = self._step(x / self._scale)
        up, down = stats
        alarm: Alarm | None = None
        if up > self.params.threshold:
            alarm = Alarm(index, Direction.UP, up)
        elif down > self.params.threshold:
            alarm = Alarm(index, Direction.DOWN, down)
        if alarm is not None:
            self._reset()
        return alarm


def detect(series: list[float], params: DriftParams) -> list[Alarm]:
    """Every alarm over a whole series."""
    ph = PageHinkley(params)
    return [a for i, x in enumerate(series) if (a := ph.update(x, i)) is not None]


def warmup_scale(series: list[float], warmup: int) -> float:
    """The sample standard deviation of the first `warmup` values, the detector's unit."""
    head = series[:warmup]
    mean = sum(head) / len(head)
    sd = math.sqrt(sum((v - mean) ** 2 for v in head) / (len(head) - 1))
    # A constant warm-up has no spread to measure against; any later change then alarms.
    return sd if sd > 0 else 1e-12


def trajectory(series: list[float], params: DriftParams) -> list[tuple[float, float]]:
    """The up and down test values after each value, with no reset; entries before the warm-up
    ends are the values the test would have had, though none is tested."""
    ph = PageHinkley(params)
    ph._scale = warmup_scale(series, params.warmup)
    return [ph._step(x / ph._scale) for x in series]

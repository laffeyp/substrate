# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The Page-Hinkley table on synthetic series, and the defaults chosen from it (sprint 305).

Series are independent N(0, 1) values, so delta and lambda are in standard deviations:
- no change: 50 values, and 200 values;
- a step of 0.5, 1 or 2 SD at value 25 of 75;
- a ramp from value 25 rising 2 SD over the remaining 50 values.

For each setting: the false-alarm rate (share of no-change series with any alarm), and for each
change the detection rate (first alarm at or after the change and within 25 values of it, with no
alarm before it) and the median delay of those detections.

The rule, fixed before the table was computed: among settings whose false-alarm rate on 50-value
series is at most 0.05, the default has the highest detection rate for a 1 SD step; ties go to the
smaller median delay, then to the larger warm-up.

Usage: language_drift_table.py [runs]   (default 4000; prints markdown)
"""

from __future__ import annotations

import random
import statistics
import sys

from substrate.language.drift import DriftParams, detect

DELTAS = (0.05, 0.1, 0.25, 0.5)
THRESHOLDS = (3.0, 5.0, 8.0, 10.0, 12.0, 16.0)
WARMUPS = (5, 10, 20)
CHANGE_AT, LENGTH, WINDOW = 25, 75, 25


def first_alarm(series: list[float], params: DriftParams) -> int | None:
    alarms = detect(series, params)
    return alarms[0].index if alarms else None


def null_rate(rng: random.Random, params: DriftParams, length: int, runs: int) -> float:
    hits = 0
    for _ in range(runs):
        if first_alarm([rng.gauss(0, 1) for _ in range(length)], params) is not None:
            hits += 1
    return hits / runs


def change(
    rng: random.Random, params: DriftParams, shape: str, size: float, runs: int
) -> tuple[float, float | None]:
    delays: list[int] = []
    for _ in range(runs):
        series = []
        for i in range(LENGTH):
            if shape == "step":
                shift = size if i >= CHANGE_AT else 0.0
            else:
                shift = size * max(0, i - CHANGE_AT + 1) / (LENGTH - CHANGE_AT)
            series.append(rng.gauss(0, 1) + shift)
        at = first_alarm(series, params)
        if at is not None and CHANGE_AT <= at < CHANGE_AT + WINDOW:
            delays.append(at - CHANGE_AT)
    return len(delays) / runs, (statistics.median(delays) if delays else None)


def main(argv: list[str]) -> None:
    runs = int(argv[1]) if len(argv) > 1 else 4000
    rows = []
    for warmup in WARMUPS:
        for delta in DELTAS:
            for threshold in THRESHOLDS:
                p = DriftParams(delta=delta, threshold=threshold, warmup=warmup)
                seed = hash((warmup, delta, threshold)) & 0xFFFF
                rng = random.Random(seed)
                row = {
                    "p": p,
                    "fa50": null_rate(rng, p, 50, runs),
                    "fa200": null_rate(rng, p, 200, runs),
                    **{f"step{s}": change(rng, p, "step", s, runs) for s in (0.5, 1.0, 2.0)},
                    "ramp": change(rng, p, "ramp", 2.0, runs),
                }
                rows.append(row)
    print(f"{runs} series per cell; seeds fixed per setting.\n")
    print(
        "| warm-up | δ | λ | false alarms, 50 | false alarms, 200 | 0.5 SD step | 1 SD step | 2 SD step | 2 SD ramp |"
    )
    print("|---|---|---|---|---|---|---|---|---|")

    def cell(v: tuple[float, float | None]) -> str:
        return f"{v[0]:.2f} ({v[1]:g})" if v[1] is not None else f"{v[0]:.2f}"

    for r in rows:
        p = r["p"]
        print(
            f"| {p.warmup} | {p.delta} | {p.threshold:g} | {r['fa50']:.3f} | {r['fa200']:.3f} | "
            f"{cell(r['step0.5'])} | {cell(r['step1.0'])} | {cell(r['step2.0'])} | {cell(r['ramp'])} |"
        )
    ok = [r for r in rows if r["fa50"] <= 0.05]
    best = max(
        ok,
        key=lambda r: (
            r["step1.0"][0],
            -(r["step1.0"][1] if r["step1.0"][1] is not None else 99),
            r["p"].warmup,
        ),
    )
    p = best["p"]
    print(
        f"\nChosen: delta {p.delta}, lambda {p.threshold:g}, warm-up {p.warmup}: false alarms {best['fa50']:.3f} over "
        f"50 values, 1 SD step found {best['step1.0'][0]:.2f} of the time, median delay {best['step1.0'][1]:g}."
    )


if __name__ == "__main__":
    main(sys.argv)

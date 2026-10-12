# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Tables for `length_drift.py`'s output: words per turn by arm, and each switched arm against the
arm that never changed. Run:

    uv run python scripts/experiments/length_drift_report.py process/runs/assays/length_drift_2026-10-12
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ARMS = ("normal", "terse", "n2t@2", "n2t@5", "t2n@5")
TURNS = range(10)


def mean_ci(xs: list[float]) -> tuple[float, float]:
    """Mean and the half-width of a 95% interval (t with n-1 degrees of freedom, n <= 30)."""
    t95 = {2: 12.71, 3: 4.30, 4: 3.18, 5: 2.78, 6: 2.57, 7: 2.45, 8: 2.36, 9: 2.31, 10: 2.26}
    n = len(xs)
    m = statistics.fmean(xs)
    if n < 2:
        return m, math.nan
    return m, t95.get(n, 2.0) * statistics.stdev(xs) / math.sqrt(n)


def slope(points: list[tuple[int, float]]) -> float:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in points) / den if den else math.nan


def report(folder: Path) -> str:
    out: list[str] = []
    for path in sorted(folder.glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        model = rows[0]["model"]
        words: dict[tuple[str, int], list[float]] = defaultdict(list)
        sessions: dict[str, set[int]] = defaultdict(set)
        for r in rows:
            words[(r["arm"], r["turn"])].append(r["words"])
            sessions[r["arm"]].add(r["rep"])
        out.append(f"### {model}\n")
        out.append(
            "Mean words per reply (± 95% interval), by turn. Sessions per arm: "
            + ", ".join(f"{a} {len(sessions[a])}" for a in ARMS)
            + ".\n"
        )
        out.append("| Turn | " + " | ".join(ARMS) + " |")
        out.append("|---|" + "---|" * len(ARMS))
        for t in TURNS:
            cells = []
            for a in ARMS:
                xs = words.get((a, t), [])
                if not xs:
                    cells.append("")
                    continue
                m, h = mean_ci(xs)
                cells.append(f"{m:.0f} ± {h:.0f}")
            out.append(f"| {t} | " + " | ".join(cells) + " |")
        normal = {
            t: statistics.fmean(words[("normal", t)]) for t in TURNS if words.get(("normal", t))
        }
        out.append("")
        out.append(
            "Each arm as a fraction of `normal` at the same turn, over the turns after a change (from turn 5 for the fixed arms), and the slope of that fraction per turn (positive: drifting toward normal).\n"
        )
        out.append("| Arm | Turns | Fraction of normal | Slope per turn |")
        out.append("|---|---|---|---|")
        for a, start in (("terse", 5), ("n2t@2", 2), ("n2t@5", 5), ("t2n@5", 5)):
            pts = [
                (t, statistics.fmean(words[(a, t)]) / normal[t])
                for t in TURNS
                if t >= start and words.get((a, t)) and normal.get(t)
            ]
            if not pts:
                continue
            frac = statistics.fmean(p[1] for p in pts)
            out.append(f"| {a} | {start}–9 | {frac:.2f} | {slope(pts):+.3f} |")
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    print(report(Path(sys.argv[1])))

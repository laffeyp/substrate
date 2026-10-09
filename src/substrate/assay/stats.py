# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Corrected statistics for the assay Report (external-review folds).

Replaces "collapse k trials to a boolean, feed McNemar, accept the null on non-significance" — which
under-propagates trial variance (crack 4) and treats non-significance as equivalence (crack 3) — with
the textbook instruments, applied to agent orchestration:

  - **pass^k** as the reliability estimand (tau-bench 2024): the probability that ALL k independent
    attempts pass, estimated from n trials as the unbiased subset ratio C(passes, k) / C(n, k). This
    is distinct from pass@k (which caps an oracle selector); pass^k measures consistency.
  - a PAIRED two-level bootstrap on the per-Case Δ-pass^k (resample Cases, then resample trials within
    each Case) — carrying the trial-level uncertainty the boolean collapse discarded.
  - an EQUIVALENCE verdict against a PRE-SPECIFIED margin by CI-inclusion (the percentile-bootstrap
    analogue of TOST, Lakens 2017 — NOT the Tango/Nam score-TOST the power analysis prefers; that
    score test is the upgrade owed before any equivalence claim actually runs). The CI is the
    bootstrap percentile interval, ~0.068 coverage error (the mild variant), not the Wald ~0.20. A
    non-significant result is NOT "no effect"; to claim equivalence the whole CI must sit inside
    ±margin, and a zero-width (all-identical) bootstrap is ruled INCONCLUSIVE, never equivalent.
  - Benjamini-Hochberg FDR across the arm matrix (Benjamini & Hochberg 1995) — raw per-arm p-values
    are uncorrected; BH is less conservative than Holm for many arms.

None of this is novel (Dietterich 1998; Lakens 2017; BH 1995; Miller, "Adding Error Bars to Evals,"
2024). The layer's contribution is importing it, not inventing it.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def pass_hat_k(passes: int, trials: int, k: int) -> float:
    """pass^k reliability estimate: P(all k of k independent attempts pass), from `passes`/`trials`
    observed. The unbiased subset ratio C(passes, k) / C(trials, k) (math.comb is 0 when passes < k, so
    a cell that never reached k passes scores 0). Requires 1 <= k <= trials and 0 <= passes <= trials."""
    if not (1 <= k <= trials) or not (0 <= passes <= trials):
        raise ValueError(
            f"need 1<=k<=trials and 0<=passes<=trials; got passes={passes} k={k} trials={trials}"
        )
    return math.comb(passes, k) / math.comb(trials, k)


SUPERIOR = "superior"
EQUIVALENT = "equivalent"
INFERIOR = "inferior"
INCONCLUSIVE = "inconclusive"
UNDERPOWERED = (
    "underpowered"  # would read equivalent, but too few cases for THIS margin to claim it
)


def equivalence_power_floor(margin: float) -> int:
    """Minimum paired cases to be ALLOWED to claim equivalence within ±margin. Equivalence sample size
    scales ~1/δ²; this yields ~90 / 160 / 360 at margin 0.20 / 0.15 / 0.10 (the figures the power
    analysis fixed). The 3.6 constant is a HEURISTIC, not a σ-derived quantity: it approximates ~80%
    TOST power at α=.05 under the worst-case Bernoulli variance (σ²=0.5, independent arms); pairing
    reduces variance, so the floor is conservative-leaning, but it is a round pre-registered figure,
    not a tight derivation. A looser margin needs fewer cases — which is exactly WHY the margin must be
    pre-registered, not chosen after seeing the data (the report binds it to the run's recorded config).
    The floor only stops an underpowered run from PRINTING equivalence; it never blocks a real
    difference (superior/inferior fire regardless of n)."""
    if margin <= 0:
        return 10**9
    return math.ceil(3.6 / (margin * margin))


@dataclass(frozen=True)
class DeltaCI:
    """A paired Δ-pass^k estimate with a bootstrap CI and a TOST equivalence verdict. `delta` is the
    arm's pass^k minus the control's, averaged over paired Cases. `verdict` is one of superior /
    equivalent / inferior / inconclusive against `margin`. `p_two_sided` is the bootstrap two-sided p
    for delta != 0 (RAW — apply FDR across arms separately)."""

    delta: float
    ci_low: float
    ci_high: float
    p_two_sided: float
    verdict: str
    n_cases: int
    k: int
    n_boot: int
    margin: float


def _phk(bools: Sequence[bool], k: int, draw: list[int] | None) -> float:
    n = len(bools)
    if n == 0:
        return 0.0
    kk = min(k, n)
    sample = [bools[i] for i in draw] if draw is not None else list(bools)
    return pass_hat_k(sum(1 for x in sample if x), len(sample), kk)


def bootstrap_delta_pass_k(
    arm_by_case: Mapping[str, Sequence[bool]],
    control_by_case: Mapping[str, Sequence[bool]],
    *,
    k: int,
    margin: float,
    n_boot: int = 5000,
    alpha: float = 0.05,
    seed: int = 0,
) -> DeltaCI:
    """Paired two-level bootstrap CI + TOST verdict on Δ-pass^k. `*_by_case` maps case_id -> the
    per-trial pass booleans for that (arm, case). Cases in BOTH arms are paired; each replicate
    resamples Cases with replacement (outer) and, within each, resamples trials with replacement
    (inner), recomputing pass^k per arm and averaging the per-Case delta. Percentile CI at 1-alpha.
    Deterministic given `seed` (so the Report is repeatable — the same results reproduce the same CI)."""
    cases = sorted(set(arm_by_case) & set(control_by_case))
    if not cases:
        return DeltaCI(0.0, 0.0, 0.0, 1.0, INCONCLUSIVE, 0, k, n_boot, margin)
    rng = random.Random(seed)  # noqa: S311 — a seeded bootstrap must be reproducible, not secret

    point = sum(
        _phk(arm_by_case[c], k, None) - _phk(control_by_case[c], k, None) for c in cases
    ) / len(cases)

    deltas: list[float] = []
    for _ in range(n_boot):
        picked = [cases[rng.randrange(len(cases))] for _ in range(len(cases))]
        total = 0.0
        for c in picked:
            a, ctrl = arm_by_case[c], control_by_case[c]
            da = [rng.randrange(len(a)) for _ in range(len(a))] if a else []
            dc = [rng.randrange(len(ctrl)) for _ in range(len(ctrl))] if ctrl else []
            total += _phk(a, k, da) - _phk(ctrl, k, dc)
        deltas.append(total / len(picked))
    deltas.sort()

    def _pct(a: float) -> tuple[float, float]:
        return deltas[max(0, int((a / 2) * n_boot))], deltas[
            min(n_boot - 1, int((1 - a / 2) * n_boot))
        ]

    lo, hi = _pct(alpha)  # the 1-alpha (95%) CI — reported for display + the difference (!=0) test
    # the verdict uses the 90% CI: a 5% TOST is two one-sided 5% tests, whose dual is the 90% interval,
    # NOT the 95%. Feeding the 95% CI (as before) is conservative — harder to call equivalent, the safe
    # direction — but mis-specified; this corrects the duality (review fold).
    tost_lo, tost_hi = _pct(2 * alpha)
    le = sum(1 for d in deltas if d <= 0) / n_boot
    ge = sum(1 for d in deltas if d >= 0) / n_boot
    p = min(1.0, 2 * min(le, ge))
    verdict = equivalence_verdict(tost_lo, tost_hi, margin=margin, n_pairs=len(cases))
    return DeltaCI(point, lo, hi, p, verdict, len(cases), k, n_boot, margin)


def equivalence_verdict(ci_low: float, ci_high: float, *, margin: float, n_pairs: int) -> str:
    """Margin-proper verdict from a CI on Δ against a pre-specified equivalence margin, GATED on power.
    The CI passed here should be the EQUIVALENCE interval (the 90% CI for a 5% TOST — two one-sided
    tests — NOT the 95% difference CI; see `bootstrap_delta_pass_k`).

      - equivalent: whole CI inside (-margin, margin) AND `n_pairs` >= the margin's power floor — a REAL
        'no meaningful difference', with enough cases to mean it.
      - underpowered: the CI sits inside ±margin but there are TOO FEW cases for this margin — the
        cargo-cult trap (a tight-looking CI, or a margin loose enough to swallow a wide CI, on a thin
        run); must NOT read as a real tie.
      - superior / inferior: whole CI clears +margin / -margin — a difference EXCEEDING the margin.
        Fires regardless of n (detecting a real difference needs less power than proving a tie).
      - inconclusive: the CI straddles a margin boundary (underpowered for either claim), OR is
        degenerate (zero width — an all-identical bootstrap cannot support an equivalence claim; the
        false-EQUIVALENT-at-[0,0] trap the power analysis warned about).

    The distinction the HEADLINE must respect: 'significantly worse than control' (the CI excludes 0)
    is NOT the same claim as 'inferior' here (worse by MORE than the margin). A CI of [-0.18, -0.06]
    at margin 0.10 excludes 0 (significantly worse) yet straddles -0.10 — so it is inconclusive FOR
    THE MARGIN: significantly worse, but not shown worse-by-the-margin. Report the two separately."""
    if ci_low >= margin:
        return SUPERIOR
    if ci_high <= -margin:
        return INFERIOR
    # EQUIVALENT needs the whole CI inside ±margin AND a NON-degenerate interval. A zero-width CI within
    # the margin is the false-equivalence trap: an all-identical bootstrap whose tightness is an
    # artifact of few/identical cases, not power — it falls through to INCONCLUSIVE. (A zero-width CI
    # that CLEARS a margin, e.g. [1,1] or [-1,-1], is a genuine maximal difference and is caught above.)
    if -margin <= ci_low and ci_high <= margin and ci_low != ci_high:
        return EQUIVALENT if n_pairs >= equivalence_power_floor(margin) else UNDERPOWERED
    return INCONCLUSIVE


def _restricted_mle_phi(b: int, c: int, n: int, delta: float) -> float:
    """Restricted MLE of the discordant-pair nuisance parameter phi := P(arm=0, control=1) under
    H0: pi_10 - pi_01 = delta, where pi_10 = P(arm=1, control=0) and pi_01 = P(arm=0, control=1).
    The parameterisation matches Tango 1998 §2: let a = concordant-both-pass count, d = concordant-
    both-fail count, b = discordant control-only ('01'), c = discordant arm-only ('10'), n = a+b+c+d.
    Under the constraint pi_10 = phi + delta, the constrained log-likelihood is

        L(phi) = b log(phi) + c log(phi + delta) + (a + d) log(1 - 2 phi - delta)

    valid on phi in (max(0, -delta), (1 - delta) / 2). Solved by bracketed bisection on the score
    dL/dphi = b/phi + c/(phi+delta) - 2 (a+d)/(1 - 2 phi - delta). The score is monotone (b, c, a+d
    all non-negative, so each term is monotone in phi over the valid interior), so bisection
    converges to machine precision in ~50 iterations. Nam 1997 §3 gives a closed form via a
    quadratic reduction; bisection is used here for legibility and to avoid the branch selection the
    closed form requires. Boundary case: b + c = 0 is guarded at the caller (see
    `equivalence_verdict_score_tost`), which returns INCONCLUSIVE with a `zero_discordant` note per
    the roadmap round-3 fold rather than pushing the MLE to a boundary that trivialises the test.
    """
    concordant = n - b - c
    lo = max(1e-12, -delta + 1e-12)
    hi = (1.0 - delta) / 2.0 - 1e-12
    if hi <= lo:
        return max(lo, min(hi, 0.0))

    def score(phi: float) -> float:
        return b / phi + c / (phi + delta) - 2.0 * concordant / (1.0 - 2.0 * phi - delta)

    s_lo, s_hi = score(lo), score(hi)
    if s_lo <= 0.0:
        return lo
    if s_hi >= 0.0:
        return hi
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        s_mid = score(mid)
        if abs(s_mid) < 1e-12 or (hi - lo) < 1e-14:
            return mid
        if s_mid > 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _score_z(b: int, c: int, n: int, delta: float) -> float:
    """Nam 1997 / Tango 1998 asymptotic score statistic for H0: pi_10 - pi_01 = delta on matched
    pairs. Delta_hat = (c - b) / n; the per-pair variance under H0 uses the restricted MLE:
    Var[X_i | H0] = pi_10 + pi_01 - delta^2 = (phi + (phi + delta)) - delta^2 = 2 phi + delta -
    delta^2 (Tango 1998, eq. 2). Returns z = (Delta_hat - delta) / sqrt(Var / n). Guarded against
    degenerate variance."""
    phi = _restricted_mle_phi(b, c, n, delta)
    var = (2.0 * phi + delta - delta * delta) / n
    if var <= 0.0:
        return 0.0
    return ((c - b) / n - delta) / math.sqrt(var)


def _phi_normal_cdf(z: float) -> float:
    """Standard normal CDF via math.erf — the ~1e-9 accuracy is more than enough for a 5%-level test
    and avoids a scipy dependency for a five-line function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


SCORE_TOST_ZERO_DISCORDANT = "zero_discordant"


def equivalence_verdict_score_tost(
    b: int,
    c: int,
    n: int,
    *,
    margin: float,
    alpha: float = 0.05,
) -> tuple[str, str]:
    """Tango 1998 / Nam 1997 score-TOST equivalence verdict for matched-pair proportion difference
    Delta = pi_10 - pi_01 (arm success rate minus control success rate on the discordant pairs).
    Inputs are the McNemar 2x2 discordant counts: b = control-only-passed, c = arm-only-passed,
    n = total paired cases (concordants included). Returns (verdict, note).

    The score test is the reference instrument for matched-pair equivalence: the primary literature
    (Tango 1998 Statistics in Medicine 17:891-908; Nam 1997 Biometrics 53:1422-1430) gives it as
    the standard, and it is what the assay design doc already names as owed (stats.py:12-14).
    Compared to the existing percentile-CI bootstrap it is (a) closed-form (up to a 1-D restricted
    MLE), (b) uses the restricted-under-H0 variance rather than the unrestricted bootstrap variance
    — the score test's power advantage in small samples, and (c) does not need to be seeded to be
    repeatable. The bootstrap CI stays as `equivalence_verdict` for the trivial cases where the
    two agree and as the display CI on the Report.

    TOST procedure at nominal level alpha: reject H0_L: Delta <= -margin at z(-margin) > z_{1-alpha}
    AND reject H0_U: Delta >= +margin at z(+margin) < -z_{1-alpha}. Both rejected -> EQUIVALENT.
    A one-sided rejection outside the margin fires SUPERIOR or INFERIOR (a difference test needs less
    power than proving a tie; no power gate). Otherwise INCONCLUSIVE.

    Power gate on EQUIVALENT: mirrors the bootstrap's `equivalence_power_floor` — n below the margin's
    floor downgrades to UNDERPOWERED, not equivalent, so a thin run cannot manufacture the claim.

    Zero-discordant fallback: b == c == 0 (every case had identical outcomes across arms) hits the
    boundary of the restricted MLE and (per roadmap round-3, sprint 150) returns INCONCLUSIVE with
    a `zero_discordant` note — the same conservative posture as the bootstrap's zero-width-CI
    fallback at stats.py:172-177. n = 0 is inherently inconclusive."""
    if n <= 0:
        return (INCONCLUSIVE, "n=0")
    if b + c == 0:
        return (INCONCLUSIVE, SCORE_TOST_ZERO_DISCORDANT)

    # inverse of the standard normal one-sided (1-alpha) critical value via Newton on the CDF; alpha
    # is a fixed test level so this is trivially fast and dependency-free.
    def _z_crit(p: float) -> float:
        z = 0.0
        for _ in range(50):
            f = _phi_normal_cdf(z) - p
            fp = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
            step = f / max(fp, 1e-300)
            z -= step
            if abs(step) < 1e-12:
                break
        return z

    zc = _z_crit(1.0 - alpha)
    z_upper_side = _score_z(b, c, n, +margin)  # test H0: Delta = +margin (evidence Delta < +margin)
    z_lower_side = _score_z(b, c, n, -margin)  # test H0: Delta = -margin (evidence Delta > -margin)

    reject_upper_H0 = z_upper_side < -zc
    reject_lower_H0 = z_lower_side > zc

    if reject_upper_H0 and reject_lower_H0:
        if n < equivalence_power_floor(margin):
            return (UNDERPOWERED, "score-tost")
        return (EQUIVALENT, "score-tost")

    # A one-sided rejection OUTSIDE the margin says the true difference lies beyond it in that
    # direction — SUPERIOR (Delta > +margin) or INFERIOR (Delta < -margin). No power gate; a
    # difference test needs less power than a tie.
    if not reject_upper_H0 and z_upper_side > zc:
        # z(margin) large POSITIVE means Delta_hat sits well ABOVE +margin -> reject H0: Delta = margin
        # in favour of Delta > margin. Superior.
        return (SUPERIOR, "score-tost")
    if not reject_lower_H0 and z_lower_side < -zc:
        return (INFERIOR, "score-tost")
    return (INCONCLUSIVE, "score-tost")


def benjamini_hochberg(pvalues: Sequence[float], *, alpha: float = 0.05) -> list[bool]:
    """Benjamini-Hochberg FDR control at `alpha` across a family (the arm matrix): return a reject flag
    per p-value. Less conservative than Holm for many comparisons; the right multiplicity control when
    several arms are each compared to one control."""
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    kmax = 0
    for rank, idx in enumerate(order, start=1):
        if pvalues[idx] <= alpha * rank / m:
            kmax = rank
    reject = [False] * m
    for rank, idx in enumerate(order, start=1):
        if rank <= kmax:
            reject[idx] = True
    return reject

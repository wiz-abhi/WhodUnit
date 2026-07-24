"""Per-itemset statistics over the *pre-enumerated* family.

For every itemset the FP-growth stage produced (the family is fixed before any
test — see :func:`whodunit.mine.fpgrowth.enumerate_family`) this module computes:

* the 2x2 contingency table against the label;
* ``lift`` = P(bad | itemset) / P(bad), with a seeded bootstrap CI;
* a p-value: Fisher's exact test when any expected cell count is below the
  threshold, else Pearson's chi-squared (df=1, via ``erfc``);
* Benjamini-Hochberg q-values across the **whole family**;
* the effect-size + tolerance gate (min lift, min bad-cohort support share),
  evaluated *before* significance, per Kayenta's lesson;
* a background-traffic penalty flag for itemsets matching too much of the
  healthy cohort.

Pure Python — no numpy/scipy — so it is deterministic and dependency-free.
``math.erfc`` gives the exact chi-squared (df=1) survival function, and
``math.lgamma`` powers Fisher's hypergeometric sum.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from whodunit.mine.config import MineConfig
from whodunit.mine.matrix import FeatureData


@dataclass(frozen=True)
class ItemsetStat:
    """Everything the ranker needs about one enumerated itemset."""

    itemset: frozenset[str]
    a: int  # present & bad
    b: int  # present & healthy
    c: int  # absent & bad
    d: int  # absent & healthy
    support_bad: int
    support_healthy: int
    lift: float
    ci_low: float
    ci_high: float
    p_value: float
    q_value: float
    precision: float
    recall: float
    background_share: float
    passes_effect_gate: bool
    background_penalized: bool

    @property
    def size(self) -> int:
        return len(self.itemset)


def _log_binom(n: int, k: int) -> float:
    if k < 0 or k > n:
        return -math.inf
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p-value for the 2x2 table ``[[a, b], [c, d]]``.

    Sums the hypergeometric probabilities of every table (with the observed
    margins) no more probable than the observed one. Matches scipy's convention.
    """
    row1 = a + b
    row2 = c + d
    col1 = a + c
    total = a + b + c + d
    if total == 0 or row1 == 0 or row2 == 0 or col1 == 0 or (b + d) == 0:
        return 1.0

    log_denom = _log_binom(total, col1)

    def prob(x: int) -> float:
        return math.exp(_log_binom(row1, x) + _log_binom(row2, col1 - x) - log_denom)

    p_observed = prob(a)
    lo = max(0, col1 - row2)
    hi = min(row1, col1)
    tol = p_observed * (1.0 + 1e-9)
    total_p = 0.0
    for x in range(lo, hi + 1):
        px = prob(x)
        if px <= tol:
            total_p += px
    return min(1.0, total_p)


def chi_squared_p(a: int, b: int, c: int, d: int) -> float:
    """Pearson chi-squared (df=1) p-value for a 2x2 table via ``erfc``.

    For one degree of freedom the survival function is
    ``erfc(sqrt(chi2 / 2))``, so no gamma integral is needed.
    """
    row1 = a + b
    row2 = c + d
    col1 = a + c
    col2 = b + d
    total = a + b + c + d
    if total == 0 or row1 == 0 or row2 == 0 or col1 == 0 or col2 == 0:
        return 1.0
    # chi2 = n (ad - bc)^2 / (row1 row2 col1 col2)
    num = total * (a * d - b * c) ** 2
    denom = row1 * row2 * col1 * col2
    chi2 = num / denom
    return math.erfc(math.sqrt(chi2 / 2.0))


def _expected_counts(a: int, b: int, c: int, d: int) -> tuple[float, float, float, float]:
    row1 = a + b
    row2 = c + d
    col1 = a + c
    col2 = b + d
    total = a + b + c + d
    if total == 0:
        return 0.0, 0.0, 0.0, 0.0
    return (
        row1 * col1 / total,
        row1 * col2 / total,
        row2 * col1 / total,
        row2 * col2 / total,
    )


def p_value(a: int, b: int, c: int, d: int, expected_threshold: float) -> float:
    """Fisher exact if any expected cell is below the threshold, else chi-squared."""
    expected = _expected_counts(a, b, c, d)
    if min(expected) < expected_threshold:
        return fisher_exact_two_sided(a, b, c, d)
    return chi_squared_p(a, b, c, d)


def compute_lift(a: int, b: int, n_bad: int, n: int) -> float:
    """P(bad | present) / P(bad). Zero when nothing matches or no bad cohort."""
    present = a + b
    if present == 0 or n == 0 or n_bad == 0:
        return 0.0
    p_bad_given_present = a / present
    p_bad = n_bad / n
    return p_bad_given_present / p_bad


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = q * (len(sorted_values) - 1)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return sorted_values[lo]
    frac = idx - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def bootstrap_ci(
    present_flags: list[int],
    bad_flags: list[int],
    n_bad: int,
    n: int,
    resamples: list[list[int]],
    ci_alpha: float,
) -> tuple[float, float]:
    """Percentile bootstrap CI for lift over pre-drawn resample index lists.

    ``resamples`` is shared across itemsets (drawn once from the seeded RNG),
    which keeps the whole family on a common resampling basis and is far cheaper
    than redrawing per itemset.
    """
    if not resamples:
        point = compute_lift(
            sum(present_flags[i] & bad_flags[i] for i in range(n)),
            sum(present_flags[i] & (1 - bad_flags[i]) for i in range(n)),
            n_bad,
            n,
        )
        return point, point

    lifts: list[float] = []
    for draw in resamples:
        a = 0
        present = 0
        bad = 0
        for i in draw:
            p = present_flags[i]
            bd = bad_flags[i]
            present += p
            bad += bd
            a += p & bd
        b = present - a
        lifts.append(compute_lift(a, b, bad, len(draw)))
    lifts.sort()
    return (
        _percentile(lifts, ci_alpha / 2.0),
        _percentile(lifts, 1.0 - ci_alpha / 2.0),
    )


def benjamini_hochberg(p_values: list[float], alpha: float) -> list[float]:
    """BH step-up adjusted q-values, monotone, in the input order.

    Computed across the *entire* family: the ``len(p_values)`` denominator is
    the enumerated family size, which is what makes the correction valid.
    """
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    q = [0.0] * m
    prev = 1.0
    for rank in range(m - 1, -1, -1):
        i = order[rank]
        val = p_values[i] * m / (rank + 1)
        prev = min(prev, val)
        q[i] = min(1.0, prev)
    return q


def compute_family_stats(
    data: FeatureData,
    family: dict[frozenset[str], int],
    config: MineConfig,
) -> list[ItemsetStat]:
    """Compute the full statistics table for the enumerated ``family``.

    The family MUST be the complete enumeration (fixed before testing); this
    function asserts each itemset is non-empty and computes q-values over the
    whole set so BH-FDR stays valid.
    """
    itemsets = sorted(family, key=lambda s: (len(s), sorted(s)))
    if any(len(s) == 0 for s in itemsets):
        raise ValueError("family contains the empty itemset; enumeration is malformed")

    # Pre-draw the shared bootstrap resamples once, deterministically.
    rng = random.Random(config.seed)
    resamples: list[list[int]] = [
        [rng.randrange(data.n) for _ in range(data.n)] for _ in range(config.n_bootstrap)
    ]
    bad_flags = [(data.label_bad >> i) & 1 for i in range(data.n)]

    raw: list[tuple[frozenset[str], int, int, int, int, float, float, float, float]] = []
    p_list: list[float] = []
    for itemset in itemsets:
        a, b, c, d = data.contingency(itemset)
        lift = compute_lift(a, b, data.n_bad, data.n)
        present_flags = [(data.cohort_mask(itemset) >> i) & 1 for i in range(data.n)]
        ci_low, ci_high = bootstrap_ci(
            present_flags, bad_flags, data.n_bad, data.n, resamples, config.ci_alpha
        )
        pv = p_value(a, b, c, d, config.expected_count_threshold)
        precision = a / (a + b) if (a + b) > 0 else 0.0
        raw.append((itemset, a, b, c, d, lift, ci_low, ci_high, precision))
        p_list.append(pv)

    q_list = benjamini_hochberg(p_list, config.fdr_alpha)

    stats: list[ItemsetStat] = []
    for (itemset, a, b, c, d, lift, ci_low, ci_high, precision), pv, qv in zip(
        raw, p_list, q_list, strict=True
    ):
        support_frac_bad = a / data.n_bad if data.n_bad > 0 else 0.0
        background_share = b / data.n_healthy if data.n_healthy > 0 else 0.0
        passes_effect_gate = (
            lift >= config.min_lift and support_frac_bad >= config.min_support_frac_bad
        )
        background_penalized = background_share > config.background_penalty_frac
        stats.append(
            ItemsetStat(
                itemset=itemset,
                a=a,
                b=b,
                c=c,
                d=d,
                support_bad=a,
                support_healthy=b,
                lift=lift,
                ci_low=ci_low,
                ci_high=ci_high,
                p_value=pv,
                q_value=qv,
                precision=precision,
                recall=a / data.n_bad if data.n_bad > 0 else 0.0,
                background_share=background_share,
                passes_effect_gate=passes_effect_gate,
                background_penalized=background_penalized,
            )
        )
    return stats

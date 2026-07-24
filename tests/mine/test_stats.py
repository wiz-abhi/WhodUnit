"""Statistics primitives: Fisher exact, chi-squared, BH-FDR, lift."""

from __future__ import annotations

import math

from whodunit.mine.stats import (
    benjamini_hochberg,
    chi_squared_p,
    compute_lift,
    fisher_exact_two_sided,
)


def test_fisher_known_value() -> None:
    # Classic 2x2 [[3,1],[1,3]]: two-sided p ~ 0.4857.
    p = fisher_exact_two_sided(3, 1, 1, 3)
    assert math.isclose(p, 0.4857142857, rel_tol=1e-6)


def test_fisher_strong_association_small() -> None:
    strong = fisher_exact_two_sided(10, 0, 0, 10)
    weak = fisher_exact_two_sided(6, 4, 4, 6)
    assert strong < weak
    assert 0.0 <= strong <= 1.0


def test_fisher_no_association_is_one() -> None:
    assert math.isclose(fisher_exact_two_sided(5, 5, 5, 5), 1.0, rel_tol=1e-9)


def test_chi_squared_perfect_separation() -> None:
    # [[10,0],[0,10]] -> chi2 = 20 -> p = erfc(sqrt(10)).
    p = chi_squared_p(10, 0, 0, 10)
    assert math.isclose(p, math.erfc(math.sqrt(10.0)), rel_tol=1e-12)
    assert p < 1e-4


def test_lift_basic() -> None:
    # Present matches 10 traces, all bad; 40 bad of 200 total -> lift = 5.
    lift = compute_lift(a=10, b=0, n_bad=40, n=200)
    assert math.isclose(lift, 5.0, rel_tol=1e-9)


def test_lift_zero_when_no_match() -> None:
    assert compute_lift(0, 0, 40, 200) == 0.0


def test_benjamini_hochberg_monotone_and_scaled() -> None:
    ps = [0.001, 0.01, 0.5, 0.9]
    qs = benjamini_hochberg(ps, alpha=0.05)
    assert len(qs) == 4
    # q_i = min over k>=i of p_(k)*m/k, all in [0,1].
    assert all(0.0 <= q <= 1.0 for q in qs)
    # smallest p should have the smallest q.
    assert qs[0] <= qs[1] <= qs[3]


def test_bh_lone_small_p_in_large_family_does_not_survive() -> None:
    # One p=0.01 among 500 tests -> q = 0.01 * 500 / 1 = 5 -> capped to 1.0.
    ps = [0.01] + [0.6] * 499
    qs = benjamini_hochberg(ps, alpha=0.05)
    assert qs[0] > 0.05

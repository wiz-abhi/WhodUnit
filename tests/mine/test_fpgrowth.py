"""FP-growth correctness: brute-force cross-check and determinism."""

from __future__ import annotations

from fixtures import make_random_matrix

from whodunit.mine.fpgrowth import brute_force_family, enumerate_family
from whodunit.mine.matrix import build_feature_data


def test_fpgrowth_matches_brute_force_200_rows() -> None:
    frame, columns = make_random_matrix(n=200, n_features=8, seed=7)
    data = build_feature_data(frame, columns)
    for min_support in (5, 20, 60):
        got = enumerate_family(data, min_support, max_len=3)
        ref = brute_force_family(data, min_support, max_len=3)
        assert got == ref, f"mismatch at min_support={min_support}"


def test_fpgrowth_respects_max_len() -> None:
    frame, columns = make_random_matrix(n=200, n_features=6, seed=3)
    data = build_feature_data(frame, columns)
    fam = enumerate_family(data, min_support=10, max_len=2)
    assert fam
    assert all(len(s) <= 2 for s in fam)


def test_fpgrowth_deterministic() -> None:
    frame, columns = make_random_matrix(n=200, n_features=8, seed=7)
    data = build_feature_data(frame, columns)
    first = enumerate_family(data, 15, 3)
    second = enumerate_family(data, 15, 3)
    assert first == second


def test_support_counts_are_bad_cohort() -> None:
    frame, columns = make_random_matrix(n=200, n_features=5, seed=1)
    data = build_feature_data(frame, columns)
    fam = enumerate_family(data, min_support=1, max_len=1)
    # Every single-item count must equal a direct bad-cohort popcount.
    for itemset, count in fam.items():
        (item,) = tuple(itemset)
        expected = (data.bitsets[item] & data.label_bad).bit_count()
        assert count == expected

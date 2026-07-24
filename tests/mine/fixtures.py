"""Deterministic fixture generators mirroring the corpus fault classes.

Each builder returns ``(frame, columns)`` ready for :func:`whodunit.mine.mine`.
All randomness flows through a seeded ``random.Random`` so fixtures are
reproducible. Presence features are boolean columns; the label column is
``label`` with ``True`` == the bad cohort.
"""

from __future__ import annotations

import random

import polars as pl

from whodunit.types import FeatureColumn, FeatureKind


def _frame(
    label: list[bool],
    feats: dict[str, list[bool]],
) -> pl.DataFrame:
    n = len(label)
    data: dict[str, list[bool] | list[str]] = {
        "trace_id": [f"t{i:05d}" for i in range(n)],
        "label": label,
    }
    data.update(feats)
    return pl.DataFrame(data)


def _cols(names: list[str], kind: FeatureKind = FeatureKind.SPAN_PREDICATE) -> list[FeatureColumn]:
    return [FeatureColumn(name=n, kind=kind) for n in names]


def make_conditional_dep(n: int = 400, seed: int = 1) -> tuple[pl.DataFrame, list[FeatureColumn]]:
    """A ∧ ¬B separates perfectly; neither single does.

    ``label = A and not B``. A and B are independent coin flips, so P(bad|A) and
    P(bad|¬B) are both ~0.5 (lift ~2), while P(bad | A ∧ ¬B) == 1 (lift ~4).
    The 2-itemset {A, NOT B} is the only clean discriminator. Extra noise
    features are decorrelated from the label.
    """
    rng = random.Random(seed)
    a: list[bool] = []
    b: list[bool] = []
    noise1: list[bool] = []
    noise2: list[bool] = []
    label: list[bool] = []
    for _ in range(n):
        av = rng.random() < 0.5
        bv = rng.random() < 0.5
        a.append(av)
        b.append(bv)
        noise1.append(rng.random() < 0.4)
        noise2.append(rng.random() < 0.3)
        label.append(av and not bv)
    feats = {"feat_A": a, "feat_B": b, "noise1": noise1, "noise2": noise2}
    return _frame(label, feats), _cols(["feat_A", "feat_B", "noise1", "noise2"])


def make_decoy(n: int = 400, seed: int = 2) -> tuple[pl.DataFrame, list[FeatureColumn]]:
    """A feature that correlates ~65% with the label non-causally.

    ``label`` is an independent coin flip. ``decoy`` is present in 65% of bad and
    50% of healthy traces — enough that a naive tool flags it, but its lift
    (~1.15) and precision (~0.57) are far below the gates, so it must never be a
    DISCRIMINATOR.
    """
    rng = random.Random(seed)
    label: list[bool] = []
    decoy: list[bool] = []
    other: list[bool] = []
    for _ in range(n):
        bad = rng.random() < 0.5
        label.append(bad)
        p = 0.65 if bad else 0.50
        decoy.append(rng.random() < p)
        other.append(rng.random() < 0.3)
    return _frame(label, {"decoy": decoy, "other": other}), _cols(["decoy", "other"])


def make_null(n: int = 400, seed: int = 3) -> tuple[pl.DataFrame, list[FeatureColumn]]:
    """Nothing broke: every feature is independent of the label -> ABSTAIN."""
    rng = random.Random(seed)
    label = [rng.random() < 0.5 for _ in range(n)]
    feats = {f"f{i}": [rng.random() < 0.4 for _ in range(n)] for i in range(6)}
    return _frame(label, feats), _cols(list(feats.keys()))


def make_random_matrix(
    n: int = 200, n_features: int = 8, seed: int = 7
) -> tuple[pl.DataFrame, list[FeatureColumn]]:
    """A generic random boolean matrix for FP-growth brute-force cross-checks."""
    rng = random.Random(seed)
    label = [rng.random() < 0.5 for _ in range(n)]
    feats = {
        f"c{i}": [rng.random() < (0.3 + 0.05 * i) for _ in range(n)] for i in range(n_features)
    }
    return _frame(label, feats), _cols(list(feats.keys()))


def make_post_selection(
    n: int = 300, n_features: int = 30, seed: int = 11
) -> tuple[pl.DataFrame, list[FeatureColumn], str]:
    """Many independent features + one planted feature with a marginal p~0.01.

    Returns ``(frame, columns, planted_name)``. The planted feature has a modest
    single-test association (small p) but, once BH-FDR corrects across the full
    ~hundreds-strong family, it must NOT survive. This is the post-selection
    inference regression guard.
    """
    rng = random.Random(seed)
    label = [rng.random() < 0.5 for _ in range(n)]
    feats: dict[str, list[bool]] = {}
    for i in range(n_features):
        feats[f"noise{i}"] = [rng.random() < 0.5 for _ in range(n)]
    # Planted: present a bit more often in bad than healthy -> marginal p ~ 0.01.
    planted = "planted"
    planted_col: list[bool] = []
    for bad in label:
        p = 0.62 if bad else 0.42
        planted_col.append(rng.random() < p)
    feats[planted] = planted_col
    return _frame(label, feats), _cols(list(feats.keys())), planted

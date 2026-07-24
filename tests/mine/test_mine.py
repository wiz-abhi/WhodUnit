"""End-to-end mining behaviour on corpus-mirroring fixtures."""

from __future__ import annotations

from fixtures import (
    make_conditional_dep,
    make_decoy,
    make_null,
    make_post_selection,
    make_random_matrix,
)

from whodunit.mine import MineConfig, mine
from whodunit.mine.fpgrowth import brute_force_family
from whodunit.mine.matrix import build_feature_data
from whodunit.mine.stats import compute_family_stats
from whodunit.types import Verdict


def test_conditional_dep_top_finding_is_the_conjunction() -> None:
    frame, columns = make_conditional_dep(n=400, seed=1)
    result = mine(frame, columns)
    assert not result.abstained
    assert result.findings
    top = result.findings[0]
    assert top.verdict is Verdict.DISCRIMINATOR
    # The winner is exactly {feat_A, NOT feat_B}.
    assert set(top.itemset) == {"feat_A", "NOT feat_B"}
    # Its lift dominates either single seen in the near-miss board.
    single_lifts = [
        f.lift for f in result.near_misses if set(f.itemset) <= {"feat_A", "NOT feat_B"}
    ]
    if single_lifts:
        assert top.lift > max(single_lifts) + 0.5


def test_decoy_is_not_a_discriminator() -> None:
    frame, columns = make_decoy(n=400, seed=2)
    result = mine(frame, columns)
    discriminator_sets = [
        set(f.itemset) for f in result.findings if f.verdict is Verdict.DISCRIMINATOR
    ]
    assert {"decoy"} not in discriminator_sets
    # And overall the run must not crown the decoy.
    assert all("decoy" not in f.itemset or f.verdict is not Verdict.DISCRIMINATOR
               for f in result.findings)


def test_null_scenario_abstains() -> None:
    frame, columns = make_null(n=400, seed=3)
    result = mine(frame, columns)
    assert result.abstained
    assert all(f.verdict is not Verdict.DISCRIMINATOR for f in result.findings)


def test_post_selection_family_size_and_fdr() -> None:
    frame, columns, planted = make_post_selection(n=300, n_features=30, seed=11)
    cfg = MineConfig(min_support=5, max_itemset_size=2, n_bootstrap=0)
    result = mine(frame, columns, cfg)

    # family_size is exactly the enumeration count (BH denominator integrity).
    data = build_feature_data(frame, columns)
    ref = brute_force_family(data, 5, 2)
    assert result.family_size == len(ref)
    assert result.family_size >= 100  # a genuinely large family

    # The planted marginal itemset must NOT survive FDR.
    stats = compute_family_stats(data, ref, cfg)
    planted_stat = next(s for s in stats if set(s.itemset) == {planted})
    assert planted_stat.p_value < 0.05  # marginally significant on its own
    assert planted_stat.q_value > cfg.fdr_alpha  # but killed by the correction
    assert all({planted} != set(f.itemset) or f.verdict is not Verdict.DISCRIMINATOR
               for f in result.findings)


def test_determinism_same_seed_same_findings() -> None:
    frame, columns = make_conditional_dep(n=400, seed=1)
    cfg = MineConfig(n_bootstrap=200, seed=99)
    r1 = mine(frame, columns, cfg)
    r2 = mine(frame, columns, cfg)
    assert [f.model_dump() for f in r1.findings] == [f.model_dump() for f in r2.findings]
    assert [f.model_dump() for f in r1.near_misses] == [f.model_dump() for f in r2.near_misses]


def test_family_is_fixed_before_testing() -> None:
    # family_size must equal the full enumeration, not the survivor count.
    frame, columns = make_random_matrix(n=200, n_features=6, seed=5)
    data = build_feature_data(frame, columns)
    result = mine(frame, columns, MineConfig(min_support=10, n_bootstrap=0))
    ref = brute_force_family(data, result.config.min_support or 10, 3)
    assert result.family_size == len(ref)


def test_bootstrap_ci_populated_when_enabled() -> None:
    frame, columns = make_conditional_dep(n=300, seed=4)
    result = mine(frame, columns, MineConfig(n_bootstrap=100))
    assert result.findings
    top = result.findings[0]
    assert top.ci_low <= top.lift <= top.ci_high + 1e-9

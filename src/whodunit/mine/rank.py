"""Ranking, MDL-flavored dominance pruning, and calibrated verdict assignment.

Turns the statistics table into ranked :class:`~whodunit.types.Finding` objects.

Ranking key: ``(lift CI lower bound desc, bad-cohort support desc, simplicity)``
— fewer items win ties, so a clean 2-itemset beats a noisier 3-itemset with the
same CI floor.

MDL-flavored dominance pruning: a superset is dropped when it fails to beat its
best surviving subset's CI-lower-bound by more than ``dominance_margin``. This
kills the "add a redundant conjunct" inflation that Apriori-style miners drown
in — the shorter description wins unless the longer one genuinely pays for its
extra bits.

Verdict assignment is calibrated: DISCRIMINATOR requires clearing every gate
(effect size, FDR significance, background traffic, precision, recall); PARTIAL
is honest signal below the bar; ABSTAIN is a first-class outcome returned when
nothing clears — on decoy/null inputs it is the *correct* answer.
"""

from __future__ import annotations

from whodunit.mine.config import MineConfig
from whodunit.mine.matrix import base_name, is_negation
from whodunit.mine.stats import ItemsetStat
from whodunit.types import Finding, Verdict


def itemset_to_list(itemset: frozenset[str]) -> list[str]:
    """Deterministic ordering of an itemset: presence tokens first (by name),
    then absence tokens (by base name)."""
    return sorted(itemset, key=lambda item: (is_negation(item), base_name(item), item))


def _rank_key(stat: ItemsetStat) -> tuple[float, int, int, list[str]]:
    # Higher CI floor, then higher support, then simpler, then name for ties.
    return (-stat.ci_low, -stat.support_bad, stat.size, itemset_to_list(stat.itemset))


def is_significant(stat: ItemsetStat, config: MineConfig) -> bool:
    return stat.q_value <= config.fdr_alpha


def classify(stat: ItemsetStat, config: MineConfig) -> Verdict:
    """Assign a calibrated verdict to a single itemset."""
    significant = is_significant(stat, config)
    if (
        stat.passes_effect_gate
        and significant
        and not stat.background_penalized
        and stat.precision >= config.precision_min
        and stat.recall >= config.recall_min
    ):
        return Verdict.DISCRIMINATOR
    # Some honest signal, but below the discriminator bar.
    if stat.lift > 1.0 and (significant or stat.passes_effect_gate):
        return Verdict.PARTIAL
    return Verdict.ABSTAIN


def _to_finding(stat: ItemsetStat, verdict: Verdict) -> Finding:
    return Finding(
        itemset=itemset_to_list(stat.itemset),
        lift=stat.lift,
        ci_low=stat.ci_low,
        ci_high=stat.ci_high,
        support_bad=stat.support_bad,
        support_healthy=stat.support_healthy,
        verdict=verdict,
        p_value=stat.p_value,
        q_value=stat.q_value,
        background_share=stat.background_share,
    )


def dominance_prune(stats: list[ItemsetStat], margin: float) -> list[ItemsetStat]:
    """Drop supersets that do not beat their best proper subset's CI floor.

    ``stats`` should already be the discriminator pool. Kept sets are those with
    no proper subset (within the pool) whose CI-lower-bound is within ``margin``
    of theirs.
    """
    kept: list[ItemsetStat] = []
    for stat in stats:
        dominated = False
        for other in stats:
            if other.itemset == stat.itemset:
                continue
            # proper subset that the superset fails to beat by the margin
            if other.itemset < stat.itemset and stat.ci_low <= other.ci_low + margin:
                dominated = True
                break
        if not dominated:
            kept.append(stat)
    # Guard against dropping everything if the pool is a single chain.
    if not kept and stats:
        kept = [min(stats, key=lambda s: (s.size, _rank_key(s)))]
    return kept


def rank_findings(
    stats: list[ItemsetStat],
    config: MineConfig,
) -> tuple[list[Finding], list[Finding], bool]:
    """Rank the statistics table into ``(findings, near_misses, abstained)``.

    ``findings`` are the surviving discriminators (dominance-pruned, ranked); if
    none survive, ``findings`` holds the single closest partial (honest framing)
    and ``abstained`` is True. ``near_misses`` are the top rejected candidates
    for the elimination board.
    """
    ranked = sorted(stats, key=_rank_key)
    discriminators = [s for s in ranked if classify(s, config) is Verdict.DISCRIMINATOR]

    if discriminators:
        pruned = dominance_prune(discriminators, config.dominance_margin)
        pruned_sorted = sorted(pruned, key=_rank_key)
        winners = {s.itemset for s in pruned_sorted}
        findings = [_to_finding(s, Verdict.DISCRIMINATOR) for s in pruned_sorted]
        rejected = [s for s in ranked if s.itemset not in winners]
        near = [_to_finding(s, classify(s, config)) for s in rejected][: config.near_miss_limit]
        return findings, near, False

    # No discriminator: calibrated abstention. Surface the closest partial.
    partials = [s for s in ranked if classify(s, config) is Verdict.PARTIAL]
    if partials:
        closest = partials[0]  # ranked already sorts by CI floor
        findings = [_to_finding(closest, Verdict.PARTIAL)]
        rejected = [s for s in ranked if s.itemset != closest.itemset]
        near = [_to_finding(s, classify(s, config)) for s in rejected][: config.near_miss_limit]
        return findings, near, True

    near = [_to_finding(s, Verdict.ABSTAIN) for s in ranked][: config.near_miss_limit]
    return [], near, True

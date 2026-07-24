"""The honest flat-attribute baseline (BubbleUp-style).

Given the SAME trace x feature boolean matrix the whodunit miner sees, rank every
*single* feature (in both polarities: presence and trace-scoped absence) by a
two-proportion z-test of its enrichment in the bad cohort vs the healthy cohort,
and return the top pick plus whether that single predicate actually separates the
cohorts (precision >= 0.80 AND recall >= 0.50 — the pipeline's own gate).

This is the fair "no conjunctions, no algebra" competitor. The thesis:
  * on single-feature faults (new_edge, cache_bypass) a single predicate wins,
    so the baseline ties/wins — reported honestly;
  * on the conjunctive fault (conditional_dep) no single predicate separates, so
    the baseline's best pick fails the gate — the conjunction earns its keep;
  * on inexpressible / non-causal faults (retry_storm, decoys, null) no single
    predicate separates either, so the baseline also (correctly) finds nothing —
    but, unlike whodunit, a naive tool would still *surface its top pick as the
    culprit*, which is the false-culprit trap we measure.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import polars as pl

from whodunit.mine.matrix import build_feature_data
from whodunit.types import FeatureColumn


@dataclass(frozen=True)
class BaselinePick:
    predicate: str          # e.g. "edge__shop_payment__redis_retry" or "NOT span__..."
    polarity: str           # "present" | "absent"
    z: float
    precision: float | None
    recall: float | None
    support_bad: int
    support_healthy: int
    found: bool             # top pick meets the precision/recall gate


def _ztest(p_bad_hits: int, n_bad: int, p_healthy_hits: int, n_healthy: int) -> float:
    """Two-proportion z for enrichment of a predicate in bad vs healthy."""
    if n_bad == 0 or n_healthy == 0:
        return 0.0
    p1 = p_bad_hits / n_bad
    p2 = p_healthy_hits / n_healthy
    pool = (p_bad_hits + p_healthy_hits) / (n_bad + n_healthy)
    denom = pool * (1 - pool) * (1 / n_bad + 1 / n_healthy)
    if denom <= 0:
        # Degenerate (predicate hits nobody or everybody): no separation signal
        # unless one side is all and the other none.
        if p1 == p2:
            return 0.0
        return math.inf if p1 > p2 else -math.inf
    return (p1 - p2) / math.sqrt(denom)


def run_baseline(
    frame: pl.DataFrame,
    columns: list[FeatureColumn],
    *,
    precision_min: float = 0.80,
    recall_min: float = 0.50,
) -> tuple[BaselinePick | None, list[BaselinePick]]:
    """Rank single features (both polarities) by bad-enrichment z; return top pick
    (highest z, i.e. most over-represented in the bad cohort) and the full ranking.
    """
    data = build_feature_data(frame, columns)
    n_bad, n_healthy = data.n_bad, data.n_healthy
    picks: list[BaselinePick] = []

    for col in columns:
        a, b, c, d = data.contingency(frozenset({col.name}))
        # a present&bad, b present&healthy, c absent&bad, d absent&healthy
        # presence polarity
        z_present = _ztest(a, n_bad, b, n_healthy)
        prec_p = a / (a + b) if (a + b) else None
        rec_p = a / n_bad if n_bad else None
        picks.append(BaselinePick(
            predicate=col.name, polarity="present", z=z_present,
            precision=prec_p, recall=rec_p, support_bad=a, support_healthy=b,
            found=bool(prec_p is not None and rec_p is not None
                       and prec_p >= precision_min and rec_p >= recall_min),
        ))
        # absence polarity (trace-scoped NOT)
        z_absent = _ztest(c, n_bad, d, n_healthy)
        prec_a = c / (c + d) if (c + d) else None
        rec_a = c / n_bad if n_bad else None
        picks.append(BaselinePick(
            predicate=f"NOT {col.name}", polarity="absent", z=z_absent,
            precision=prec_a, recall=rec_a, support_bad=c, support_healthy=d,
            found=bool(prec_a is not None and rec_a is not None
                       and prec_a >= precision_min and rec_a >= recall_min),
        ))

    # Rank by z descending (most enriched in bad), then by recall, then name.
    picks.sort(key=lambda p: (-(p.z if p.z != math.inf else 1e18),
                              -(p.recall or 0.0), p.predicate))
    top = picks[0] if picks else None
    return top, picks

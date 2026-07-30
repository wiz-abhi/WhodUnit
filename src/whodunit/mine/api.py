"""Public entry point for the mining stage.

``mine(frame, columns, config)`` takes the trace x feature boolean matrix (a
polars ``DataFrame`` with ``trace_id``, ``label: bool``, and boolean feature
columns) plus its :class:`~whodunit.types.FeatureColumn` metadata, and returns a
:class:`~whodunit.mine.config.MineResult`.

The pipeline, in order (the order is load-bearing for FDR validity):

1. lower the frame into bitsets (:mod:`whodunit.mine.matrix`);
2. FP-growth enumerates the **complete** frequent-itemset family over the bad
   cohort — the family is fixed here, before any test;
3. statistics over that fixed family: lift + bootstrap CI, Fisher/chi-squared
   p-values, BH-FDR q-values, effect-size gate, background penalty;
4. rank + MDL dominance prune + calibrated verdict;
5. topological demotion of symptoms.

Pure computation: no network, no LLM, deterministic given input + ``seed``. This
module deliberately does not import from ``whodunit.extract`` — it takes the
frame directly, keeping the dependency direction one-way.
"""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from whodunit.mine.config import MineConfig, MineResult
from whodunit.mine.demote import demote_findings
from whodunit.mine.fpgrowth import enumerate_family
from whodunit.mine.matrix import build_feature_data, is_negation
from whodunit.mine.rank import rank_findings
from whodunit.mine.stats import compute_family_stats
from whodunit.types import FeatureColumn, Finding


def default_min_support(n_bad: int, min_support_frac_bad: float = 0.5) -> int:
    """Default enumeration min-support in traces:
    ``max(10, round(min_support_frac_bad * n_bad))`` — a fraction of the bad
    cohort, or 10 traces, whichever is larger. Derives from the same fraction the
    tolerance gate uses (``MineConfig.min_support_frac_bad``) so the enumeration
    floor and the gate agree: nothing below the floor is enumerated, so the gate
    is never dead."""
    return max(10, round(min_support_frac_bad * n_bad))


def mine(
    frame: pl.DataFrame,
    columns: list[FeatureColumn],
    config: MineConfig | None = None,
    *,
    first_seen: dict[str, float] | None = None,
) -> MineResult:
    """Mine structural discriminators from the trace x feature matrix."""
    cfg = config if config is not None else MineConfig()
    data = build_feature_data(frame, columns)

    raw_min = (
        cfg.min_support
        if cfg.min_support is not None
        else default_min_support(data.n_bad, cfg.min_support_frac_bad)
    )
    min_support = max(1, raw_min)

    family = enumerate_family(data, min_support, cfg.max_itemset_size)
    family_size = len(family)

    stats = compute_family_stats(data, family, cfg)
    findings, near_misses, abstained = rank_findings(stats, cfg)

    findings = demote_findings(findings, data, data.columns_by_name, cfg, first_seen)

    noncompilable = _noncompilable_itemsets(findings, near_misses, data.span_negation_items)

    return MineResult(
        findings=findings,
        family_size=family_size,
        abstained=abstained,
        near_misses=near_misses,
        noncompilable_itemsets=noncompilable,
        config=cfg,
    )


def _noncompilable_itemsets(
    findings: Sequence[Finding],
    near_misses: Sequence[Finding],
    span_negation_items: frozenset[str],
) -> list[list[str]]:
    """Itemsets (across findings + near-misses) that reference a complement
    requiring span-level negation — minable, but the compiler must refuse."""
    out: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for group in (findings, near_misses):
        for f in group:
            itemset = f.itemset
            if any(is_negation(i) and i in span_negation_items for i in itemset):
                key = tuple(itemset)
                if key not in seen:
                    seen.add(key)
                    out.append(list(itemset))
    return out


__all__ = ["default_min_support", "mine"]

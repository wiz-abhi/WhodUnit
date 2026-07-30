"""Configuration and result envelope for the mining stage.

Defaults encode the calibration choices argued in ``WHODUNIT-CONCEPT.md`` §4.3:
an effect-size + tolerance gate *before* any significance test (Kayenta's
lesson), BH-FDR over the fully-enumerated family, and a background-traffic
penalty. Every value is overridable so the benchmark harness can sweep them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from whodunit.types import Finding


class MineConfig(BaseModel):
    """Knobs for :func:`whodunit.mine.mine`. Frozen so a run's config echo is a
    faithful, hashable record of exactly what produced the findings."""

    model_config = ConfigDict(frozen=True)

    max_itemset_size: int = Field(default=3, ge=1)
    """FP-growth enumerates itemsets up to this many items (k)."""

    min_support: int | None = None
    """Min bad-cohort support (traces) for enumeration. ``None`` -> computed
    default ``max(10, round(min_support_frac_bad * n_bad))`` (a fraction of the
    bad cohort, or 10 traces, whichever is larger)."""

    min_lift: float = Field(default=3.0, ge=1.0)
    """Effect-size gate: an itemset must reach at least this lift vs the label."""

    min_support_frac_bad: float = Field(default=0.50, ge=0.0, le=1.0)
    """Tolerance gate: an itemset must match at least this share of the bad
    cohort to be a candidate discriminator. Kept equal to the enumeration floor
    (``default_min_support`` derives from this same fraction), so the gate and the
    floor agree — nothing is enumerated below the floor, so a lower value here
    would be a dead gate. Lowering both together, to mine faults present in a
    minority of the bad cohort, is a deliberate, benchmark-re-validated change."""

    background_penalty_frac: float = Field(default=0.30, ge=0.0, le=1.0)
    """Flag/penalize itemsets matching more than this share of the healthy
    (background-traffic) cohort."""

    fdr_alpha: float = Field(default=0.05, gt=0.0, lt=1.0)
    """Benjamini-Hochberg target false-discovery rate across the family."""

    ci_alpha: float = Field(default=0.05, gt=0.0, lt=1.0)
    """Bootstrap CI two-sided alpha (0.05 -> 2.5/97.5 percentile lift band)."""

    n_bootstrap: int = Field(default=1000, ge=0)
    """Bootstrap resamples for the lift confidence interval."""

    seed: int = 42
    """Seed for the bootstrap RNG; fixes determinism given input + config."""

    dominance_margin: float = Field(default=0.0, ge=0.0)
    """MDL pruning: a superset must beat its best subset's CI-lower-bound by
    more than this margin to survive."""

    precision_min: float = Field(default=0.80, ge=0.0, le=1.0)
    """DISCRIMINATOR gate: min precision (share of matched traces that are bad)."""

    recall_min: float = Field(default=0.50, ge=0.0, le=1.0)
    """DISCRIMINATOR gate: min recall (share of the bad cohort matched)."""

    expected_count_threshold: float = Field(default=5.0, gt=0.0)
    """If any 2x2 expected cell is below this, use Fisher exact; else chi-squared."""

    demotion_lift_threshold: float | None = None
    """Parent's conditional lift below this -> demoted by the descendant.
    ``None`` -> reuse ``min_lift``."""

    near_miss_limit: int = Field(default=10, ge=0)
    """How many top rejected itemsets to surface for the elimination board."""


class MineResult(BaseModel):
    """The mining stage's output envelope."""

    model_config = ConfigDict(frozen=True)

    findings: list[Finding]
    """Surviving findings, best first. Empty iff fully abstained with no partial."""
    family_size: int = Field(..., ge=0)
    """The count of itemsets enumerated *before* any test — the BH-FDR family."""
    abstained: bool
    """True when no itemset cleared every gate (verdict is ABSTAIN/PARTIAL)."""
    near_misses: list[Finding] = Field(default_factory=list)
    """Top rejected candidates, for the elimination board."""
    noncompilable_itemsets: list[list[str]] = Field(default_factory=list)
    """Itemsets referencing a span-level-negation complement: minable, but the
    compiler must refuse them. Flagged here so nothing downstream is surprised."""
    config: MineConfig
    """Verbatim echo of the config that produced this result."""

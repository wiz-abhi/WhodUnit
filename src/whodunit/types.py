"""Core data models shared across Whodunit's stages.

These are the frozen interfaces the Wave-2 agents (Extractor, Miner, Compiler)
build against. Keep them minimal but real: every field here is load-bearing for
either the mining statistics or the trace-operator compiler's correctness.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- #
# Stage 1 — the feature matrix
# --------------------------------------------------------------------------- #


class FeatureKind(StrEnum):
    """What a boolean feature column represents in the trace x feature matrix."""

    SPAN_PREDICATE = "span_predicate"
    EDGE = "edge"
    ANCESTOR = "ancestor"
    LOG = "log"
    METRIC = "metric"


class FeatureColumn(BaseModel):
    """One boolean column of the feature matrix, with the metadata the compiler
    needs to later turn a mined feature back into a builder leaf query."""

    model_config = ConfigDict(frozen=True)

    name: str
    """Stable identifier, e.g. ``svc_payment__name_SELECT_products``."""
    kind: FeatureKind
    description: str = ""
    # Structured provenance so the compiler can rebuild a leaf query.
    service_name: str | None = None
    span_name: str | None = None
    status: str | None = None
    # For latency-bucket predicates derived from raw durationNano (ns).
    duration_ge_ns: int | None = None
    duration_lt_ns: int | None = None
    # For edge/ancestor features: the (parent, child) service pair.
    edge_parent: str | None = None
    edge_child: str | None = None
    # Whether span-level negation would be required to express this feature.
    # The compiler MUST refuse absence itemsets that need span-level NOT.
    requires_span_level_negation: bool = False


class FeatureMatrix(BaseModel):
    """Metadata describing a materialised trace x feature boolean matrix.

    The actual matrix body lives out-of-band (parquet/arrow, one row per
    ``trace_id`` with a bool per column plus the outcome label); this model
    carries only the metadata the miner and verifier reason over.
    """

    columns: list[FeatureColumn]
    n_traces_bad: int = Field(..., ge=0)
    n_traces_healthy: int = Field(..., ge=0)
    # The dimensions the healthy cohort was case-control matched on.
    matched_on: list[str] = Field(default_factory=list)
    # Time window and cohort provenance.
    window_start_unix_ms: int | None = None
    window_end_unix_ms: int | None = None
    bad_cohort_filter: str | None = None
    # Cost meter, surfaced from ExecStats (see caveat: cached buckets over-report).
    rows_scanned: int | None = None
    bytes_scanned: int | None = None
    duration_ms: float | None = None

    @property
    def n_traces_total(self) -> int:
        return self.n_traces_bad + self.n_traces_healthy


# --------------------------------------------------------------------------- #
# Stage 2 — a mined finding
# --------------------------------------------------------------------------- #


class Verdict(StrEnum):
    """Calibrated outcome of the mining stage."""

    DISCRIMINATOR = "discriminator"
    """A structural discriminator cleared every gate."""
    PARTIAL = "partial"
    """A weak/partial signal below the confidence gate; surfaced honestly."""
    ABSTAIN = "abstain"
    """No structural discriminator found; the engine refuses to invent one."""


class Finding(BaseModel):
    """A single mined itemset with its effect size and calibrated verdict.

    ``itemset`` references :class:`FeatureColumn` names; a negated feature is
    prefixed with ``NOT `` (e.g. ``["svc_payment__redis", "NOT flag-service"]``).
    """

    model_config = ConfigDict(frozen=True)

    itemset: list[str]
    lift: float = Field(..., ge=0.0)
    ci_low: float = Field(..., ge=0.0)
    ci_high: float = Field(..., ge=0.0)
    support_bad: int = Field(..., ge=0)
    """Count of bad-cohort traces matching the itemset."""
    support_healthy: int = Field(..., ge=0)
    """Count of healthy-cohort traces matching the itemset."""
    verdict: Verdict
    # BH-FDR adjusted significance and background prevalence (traffic share).
    p_value: float | None = None
    q_value: float | None = None
    background_share: float | None = None
    # Topological demotion: set when this node is a symptom of a descendant.
    demoted_by: str | None = None


# --------------------------------------------------------------------------- #
# Stage 4/5 — the compiled query and its verification receipt
# --------------------------------------------------------------------------- #


class LeafQuery(BaseModel):
    """A named trace-signal builder query referenced by the operator expression.

    Leaves are references matched by ``^[A-Za-z][A-Za-z0-9_]*$`` and must be
    sibling builder queries, never inline filters.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    filters: dict[str, object] = Field(default_factory=dict)
    description: str = ""


class Refusal(BaseModel):
    """A candidate the compiler declined to emit, with a loud explanation.

    The canonical case: an absence itemset whose semantics require span-level
    negation, which the trace-scoped ``NOT`` cannot express soundly.
    """

    model_config = ConfigDict(frozen=True)

    itemset: list[str]
    reason: str


class Verification(BaseModel):
    """Differential-verification receipt: mined count vs SigNoz count."""

    model_config = ConfigDict(frozen=True)

    mined_count: int = Field(..., ge=0)
    signoz_count: int = Field(..., ge=0)
    match: bool
    precision: float | None = Field(default=None, ge=0.0, le=1.0)
    recall: float | None = Field(default=None, ge=0.0, le=1.0)
    rows_scanned: int | None = None


class CompiledQuery(BaseModel):
    """The crown-jewel artifact: a valid ``builder_trace_operator`` request plus
    everything needed to trust it."""

    # The full v5 query_range envelope JSON, ready to POST.
    envelope: dict[str, object]
    # The operator expression, e.g. ``(A => B) && NOT C``.
    expression: str
    # Which operand carries the returned spans (left-bias normalised).
    return_spans_from: str
    leaf_queries: list[LeafQuery]
    refusals: list[Refusal] = Field(default_factory=list)
    verification: Verification | None = None
    # Version fingerprint of the evaluator this was compiled/verified against.
    signoz_version: str | None = None

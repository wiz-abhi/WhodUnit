"""Whodunit Wave-3 pipeline — glue the three engines into one honest answer.

``explain(client, spec, ...)`` runs the full chain and returns an
:class:`ExplainResult`:

    extract_matrix  ->  mine  ->  pick top Finding (or ABSTAIN)
                    ->  compile_finding  ->  verify

Everything here is orchestration; the statistics, the compiler, and the
verifier live in their sibling packages and are treated as frozen contracts.

The determinism proof (WHODUNIT-CONCEPT §7): running ``explain`` twice on the
same input yields byte-identical :attr:`ExplainResult.verdict_hash`.

──────────────────────────────────────────────────────────────────────────────
CONTRACT SEAM (the main integration risk, reconciled here — see
``adapt_columns_for_compiler``)
──────────────────────────────────────────────────────────────────────────────
The extractor (``extract/scan.py::_discover_edge_features``) builds every EDGE /
ANCESTOR :class:`~whodunit.types.FeatureColumn` from a ``p.svc`` / ``c.name``
self-join, so:

    edge_parent = the parent SERVICE name   (e.g. "shop-payment")
    edge_child  = the child SPAN name        (e.g. "redis-retry")

The compiler (``compile/ir.py::_edge_side_expr``) defaults *both* endpoints to
``service.name = '...'`` and only switches an endpoint to ``name = '...'`` when
it carries the ``span:`` sentinel prefix (``SPAN_ENDPOINT_PREFIX``). Left
unreconciled, ``payment => redis-retry`` would compile to
``service.name = 'shop-payment' => service.name = 'redis-retry'`` — and
``redis-retry`` is a span, not a service, so the query would silently return 0.

Neither ``extract/`` nor ``compile/`` may be modified (siblings own them). So we
reconcile *in this module*: before compiling, we rewrite each EDGE/ANCESTOR
column's ``edge_child`` to carry the ``span:`` prefix (``edge_parent`` stays a
service). This is sound because the extractor *always* puts a span name in
``edge_child``. The column ``.name`` is left untouched, so the mined finding's
itemset still resolves against the rewritten table.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from whodunit.compile import build_ir, compile_finding, verify
from whodunit.compile.ir import SPAN_ENDPOINT_PREFIX, count_operators
from whodunit.extract import ScanConfig, extract_matrix
from whodunit.mine import MineConfig, mine
from whodunit.types import (
    CompiledQuery,
    FeatureColumn,
    FeatureKind,
    FeatureMatrix,
    Finding,
    Refusal,
    Verdict,
    Verification,
)

if TYPE_CHECKING:
    from pathlib import Path

    from whodunit.extract import CohortSpec, MatchingConfig
    from whodunit.signoz_client import SigNozClient


# --------------------------------------------------------------------------- #
# Materializer seam (a sibling agent owns whodunit.materialize)
# --------------------------------------------------------------------------- #
@runtime_checkable
class Materializer(Protocol):
    """The interface the CLI's ``--arm`` / ``--dashboard`` flags drive.

    Implemented by the (concurrently authored) ``whodunit.materialize`` package.
    Kept here as a Protocol so this module and the CLI compile and test without
    that package installed.
    """

    def arm_alert(self, compiled: CompiledQuery, **kwargs: Any) -> str: ...

    def create_dashboard(self, compiled: CompiledQuery, **kwargs: Any) -> str: ...

    def permalink(self, compiled: CompiledQuery, **kwargs: Any) -> str: ...


def load_materializer(client: SigNozClient) -> Materializer | None:
    """Lazily import ``whodunit.materialize`` and build a :class:`Materializer`.

    Returns ``None`` when the package is not yet installed (the sibling agent is
    still writing it) so the CLI can print a graceful message instead of
    crashing.
    """
    try:
        from whodunit import materialize
    except ImportError:
        return None
    factory = getattr(materialize, "get_materializer", None) or getattr(
        materialize, "Materializer", None
    )
    if factory is None:
        return None
    built: Materializer = factory(client)
    return built


# --------------------------------------------------------------------------- #
# Result envelope
# --------------------------------------------------------------------------- #
class Cost(BaseModel):
    """A cost meter (not a bill — cached buckets over-report; see ExecStats)."""

    model_config = ConfigDict(frozen=True)

    scan_rows_scanned: int | None = None
    scan_bytes_scanned: int | None = None
    scan_duration_ms: float | None = None
    verify_rows_scanned: int | None = None
    family_size: int = 0
    n_features: int = 0


class ExplainResult(BaseModel):
    """The full, JSON-serialisable output of one :func:`explain` run."""

    model_config = ConfigDict(frozen=True)

    verdict: Verdict
    headline: str
    matrix_meta: FeatureMatrix
    mine_result_findings: list[Finding] = Field(default_factory=list)
    near_misses: list[Finding] = Field(default_factory=list)
    family_size: int = 0
    abstained: bool = False
    chosen_finding: Finding | None = None
    compiled: CompiledQuery | None = None
    verification: Verification | None = None
    refusals: list[Refusal] = Field(default_factory=list)
    verdict_hash: str = ""
    cost: Cost
    environment: str | None = None
    window_start_unix_ms: int | None = None
    window_end_unix_ms: int | None = None


# --------------------------------------------------------------------------- #
# Contract-seam reconciliation
# --------------------------------------------------------------------------- #
def booleanize_frame(frame: pl.DataFrame, columns: list[FeatureColumn]) -> pl.DataFrame:
    """Cast the extractor's ``Int8`` label + feature columns to ``Boolean``.

    A second (quieter) contract seam: the extractor materialises the matrix with
    ``label`` and every feature column as ``pl.Int8`` (0/1), while the miner's
    ``build_feature_data`` *requires* ``pl.Boolean`` and raises ``TypeError``
    otherwise. Neither package may be modified, so the pipeline bridges them here
    with a cast (``0 -> False``, non-zero -> ``True``). Columns already Boolean
    are left untouched.
    """
    casts: list[pl.Expr] = []
    for name in ("label", *(c.name for c in columns)):
        if name in frame.columns and frame.get_column(name).dtype != pl.Boolean:
            casts.append(pl.col(name).cast(pl.Boolean))
    return frame.with_columns(casts) if casts else frame


def adapt_columns_for_compiler(columns: list[FeatureColumn]) -> list[FeatureColumn]:
    """Reconcile the extractor's edge naming with the compiler's endpoint model.

    See the module docstring's CONTRACT SEAM section. For every EDGE/ANCESTOR
    column we prefix ``edge_child`` (a *span name* from the extractor) with the
    compiler's ``span:`` sentinel so it lowers to ``name = '...'`` rather than
    ``service.name = '...'``. ``edge_parent`` (a service) is left as-is. The
    column ``.name`` is untouched, so a mined itemset still resolves.
    """
    adapted: list[FeatureColumn] = []
    for col in columns:
        if (
            col.kind in (FeatureKind.EDGE, FeatureKind.ANCESTOR)
            and col.edge_child is not None
            and not col.edge_child.startswith(SPAN_ENDPOINT_PREFIX)
        ):
            adapted.append(
                col.model_copy(
                    update={"edge_child": f"{SPAN_ENDPOINT_PREFIX}{col.edge_child}"}
                )
            )
        else:
            adapted.append(col)
    return adapted


# --------------------------------------------------------------------------- #
# Verdict hash — the determinism proof
# --------------------------------------------------------------------------- #
def compute_verdict_hash(
    findings: list[Finding],
    expression: str,
    counts: dict[str, int | None],
) -> str:
    """SHA-256 over a canonical JSON of (findings, expression, counts).

    Deterministic given the mining input + seed: same input -> same hash. This
    is the "run twice, hashes identical" proof from the demo script.
    """
    payload = {
        "findings": [
            {
                "itemset": list(f.itemset),
                "lift": round(f.lift, 6),
                "ci_low": round(f.ci_low, 6),
                "ci_high": round(f.ci_high, 6),
                "support_bad": f.support_bad,
                "support_healthy": f.support_healthy,
                "verdict": str(f.verdict),
            }
            for f in findings
        ],
        "expression": expression,
        "counts": {k: counts[k] for k in sorted(counts)},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# The pipeline
# --------------------------------------------------------------------------- #
def _base_filter(environment: str | None) -> str | None:
    if not environment:
        return None
    escaped = environment.replace("'", "''")
    return f"deployment.environment = '{escaped}'"


def _positive_edge_count(finding: Finding, table: dict[str, FeatureColumn]) -> int:
    """How many *positive* items assert a structural edge/ancestor relationship."""
    n = 0
    for raw in finding.itemset:
        if raw.startswith("NOT "):
            continue
        col = table.get(raw)
        if col is not None and col.kind in (FeatureKind.EDGE, FeatureKind.ANCESTOR):
            n += 1
    return n


def _select_finding(
    findings: list[Finding],
    columns: list[FeatureColumn],
    *,
    base_filter: str | None,
    start: int,
    end: int,
) -> tuple[Finding | None, CompiledQuery | None, list[Refusal]]:
    """Choose the finding to publish, with a compile-aware tie-break.

    The miner routinely returns a whole *tier* of statistically indistinguishable
    perfect separators (same support, same lift) that differ only in how they
    phrase the same trace partition — e.g. a positive can be a span-presence or
    the richer ``payment => redis-retry`` edge, and the flag absence can be a
    plain service, a span, or a redundant edge. All verify identically, so the
    choice is an *engineering* one, made here (never in the miner):

    1. skip findings the compiler soundly refuses (log-lattice features,
       span-level negation, absence-only, operator budget);
    2. among the top statistically-tied tier, **maximise positive structural
       edges** (keep the causal ``=>``/``->`` relationship — it is the more
       informative root-cause statement), then **minimise total operators**
       (the simplest negation — a single ``NOT C`` leaf beats ``NOT (C => D)``),
       then original rank.

    Falls back to best-first compilation for anything outside the tier.
    """
    refusals: list[Refusal] = []
    if not findings:
        return None, None, refusals

    table = {c.name: c for c in columns}
    best = findings[0]
    tier = [
        f
        for f in findings
        if f.support_bad == best.support_bad
        and f.support_healthy == best.support_healthy
        and f.verdict == best.verdict
    ]

    scored: list[tuple[tuple[int, int, int], Finding]] = []
    for idx, finding in enumerate(tier):
        build = build_ir(finding, table)
        if build.root is None:
            continue
        key = (
            -_positive_edge_count(finding, table),
            count_operators(build.root),
            idx,
        )
        scored.append((key, finding))

    ordered: list[Finding]
    if scored:
        scored.sort(key=lambda t: t[0])
        chosen_tier = [f for _, f in scored]
        # Anything outside the tier, in original order, as a fallback.
        rest = [f for f in findings if f not in tier]
        ordered = chosen_tier + rest
    else:
        ordered = findings

    for finding in ordered:
        compiled = compile_finding(
            finding, columns, base_filter=base_filter, start=start, end=end
        )
        if compiled.envelope:
            return finding, compiled, refusals
        refusals.extend(compiled.refusals)
    return None, None, refusals


def explain(
    client: SigNozClient,
    spec: CohortSpec,
    *,
    scan_config: ScanConfig | None = None,
    mine_config: MineConfig | None = None,
    matching: MatchingConfig | None = None,
    workdir: str | Path | None = None,
    first_seen: dict[str, float] | None = None,
    do_verify: bool = True,
) -> ExplainResult:
    """Run the full extract -> mine -> compile -> verify chain.

    Parameters mirror the engine entry points; ``spec`` carries the cohort and
    the time window (also used to scope the compiled query + verification).
    """
    scan_config = scan_config or ScanConfig()
    mine_config = mine_config or MineConfig()

    # Stage 0/1 — one scan -> the trace x feature matrix.
    mm = extract_matrix(
        client, spec, matching=matching, scan_config=scan_config, workdir=workdir
    )

    # Stage 2 — mine structural discriminators (pure, deterministic).
    # Bridge the Int8 (extractor) -> Boolean (miner) column-type seam first.
    frame = booleanize_frame(mm.frame, mm.meta.columns)
    mine_result = mine(frame, mm.meta.columns, mine_config, first_seen=first_seen)

    # Stage 4 — reconcile the edge-naming seam, then compile best-first.
    adapted = adapt_columns_for_compiler(mm.meta.columns)
    base_filter = _base_filter(spec.environment)
    start, end = spec.window_start_unix_ms, spec.window_end_unix_ms

    chosen, compiled, refusals = _select_finding(
        mine_result.findings,
        adapted,
        base_filter=base_filter,
        start=start,
        end=end,
    )

    # Surface mined-but-noncompilable itemsets as refusals too (honesty).
    for itemset in mine_result.noncompilable_itemsets:
        refusals.append(
            Refusal(
                itemset=list(itemset),
                reason=(
                    "itemset references a complement requiring span-level negation; "
                    "the trace-scoped NOT cannot express it soundly"
                ),
            )
        )

    # Stage 5 — differential verification against the live engine.
    verification: Verification | None = None
    mined_count: int | None = None
    if chosen is not None and compiled is not None and compiled.envelope:
        mined_count = chosen.support_bad + chosen.support_healthy
        if do_verify:
            bad_ids = set(spec.trace_ids) if spec.trace_ids is not None else None
            verification = verify(
                client,
                compiled,
                mined_count=mined_count,
                start=start,
                end=end,
                bad_trace_ids=bad_ids,
                with_precision_recall=bad_ids is not None,
            )
            compiled = compiled.model_copy(update={"verification": verification})

    verdict = _overall_verdict(chosen, mine_result.abstained)
    headline = _headline(chosen, verdict)

    counts: dict[str, int | None] = {
        "family_size": mine_result.family_size,
        "mined": mined_count,
        "signoz": verification.signoz_count if verification is not None else None,
    }
    verdict_hash = compute_verdict_hash(
        mine_result.findings,
        compiled.expression if compiled is not None else "",
        counts,
    )

    cost = Cost(
        scan_rows_scanned=mm.meta.rows_scanned,
        scan_bytes_scanned=mm.meta.bytes_scanned,
        scan_duration_ms=mm.meta.duration_ms,
        verify_rows_scanned=verification.rows_scanned if verification else None,
        family_size=mine_result.family_size,
        n_features=len(mm.meta.columns),
    )

    return ExplainResult(
        verdict=verdict,
        headline=headline,
        matrix_meta=mm.meta,
        mine_result_findings=mine_result.findings,
        near_misses=mine_result.near_misses,
        family_size=mine_result.family_size,
        abstained=mine_result.abstained,
        chosen_finding=chosen,
        compiled=compiled,
        verification=verification,
        refusals=refusals,
        verdict_hash=verdict_hash,
        cost=cost,
        environment=spec.environment,
        window_start_unix_ms=start,
        window_end_unix_ms=end,
    )


def _overall_verdict(chosen: Finding | None, abstained: bool) -> Verdict:
    if chosen is not None:
        return chosen.verdict
    return Verdict.ABSTAIN


def _humanize_itemset(itemset: list[str]) -> str:
    parts: list[str] = []
    for raw in itemset:
        if raw.startswith("NOT "):
            parts.append(f"WITHOUT {raw[4:]}")
        else:
            parts.append(f"WITH {raw}")
    return " AND ".join(parts)


def _headline(chosen: Finding | None, verdict: Verdict) -> str:
    if chosen is None:
        return (
            "ABSTAIN — no structural discriminator cleared every gate. "
            "The engine refuses to invent a culprit."
        )
    culprit = _humanize_itemset(chosen.itemset)
    if verdict is Verdict.DISCRIMINATOR:
        lead = "The culprit is"
    else:
        lead = "A partial (below-confidence) signal:"
    tail = f" (lift {chosen.lift:.1f}x)"
    return f"{lead} {culprit}{tail}"


__all__ = [
    "Cost",
    "ExplainResult",
    "Materializer",
    "adapt_columns_for_compiler",
    "booleanize_frame",
    "compute_verdict_hash",
    "explain",
    "load_materializer",
]

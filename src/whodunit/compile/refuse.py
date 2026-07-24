"""The refusal path — honesty as a first-class feature.

The compiler declines, *loudly and with a judge-readable explanation*, any
itemset it cannot lower into ``builder_trace_operator`` algebra soundly. A
refusal is never a silent drop: it becomes a :class:`~whodunit.types.Refusal`
surfaced in :attr:`~whodunit.types.CompiledQuery.refusals`.

Refusal triggers (all recovered from the SigNoz generator / verified live):

* **Span-level negation.** ``NOT`` is trace-scoped (``GLOBAL NOT IN`` over
  trace_ids). An absence whose semantics are span-scoped
  (``FeatureColumn.requires_span_level_negation``) cannot be expressed — a
  single compliant sibling span would mask every violation in the trace.
* **LOG features.** Verified via a ClickHouse ``trace_id`` join, not expressible
  in the trace-operator algebra at all.
* **Unknown / METRIC feature kinds.** No lowering exists.
* **Operator budget.** ``MaxTraceOperators = 10`` per expression.
* **Unresolvable feature names.** An itemset entry with no matching column.
"""

from __future__ import annotations

from whodunit.compile.ir import (
    MAX_TRACE_OPERATORS,
    ParsedItem,
    count_operators,
    parse_item,
)
from whodunit.types import FeatureColumn, FeatureKind, Finding, Refusal

# Human-readable, judge-facing explanations. Kept as constants so tests and the
# conformance table can assert on stable text.
REASON_SPAN_NEGATION = (
    "span-scoped negation is not expressible: SigNoz's NOT is trace-scoped "
    "(GLOBAL NOT IN over trace_ids), so 'trace contains no such span anywhere' is "
    "soundly compilable but 'this span is not accompanied by ...' is not — a single "
    "compliant sibling span would silently mask every violation in the trace"
)
REASON_LOG = (
    "log-lattice feature; verified via ClickHouse join, not expressible in "
    "trace-operator algebra"
)
REASON_METRIC = (
    "metric feature; supplies denominator/context only, not expressible in "
    "trace-operator algebra"
)
REASON_UNKNOWN_KIND = "feature kind {kind!r} has no trace-operator lowering"
REASON_UNRESOLVED = "itemset entry {raw!r} does not resolve to any known feature column"
REASON_TOO_MANY_OPS = (
    "expression needs {n} trace operators but MaxTraceOperators = {cap}; "
    "SigNoz rejects expressions above the cap"
)
REASON_EMPTY = "itemset is empty; nothing to compile"


def unresolved_names(finding: Finding, columns: dict[str, FeatureColumn]) -> list[str]:
    """Return the raw itemset entries that resolve to no column."""
    missing: list[str] = []
    for raw in finding.itemset:
        if parse_item(raw, columns) is None:
            missing.append(raw)
    return missing


def _kind_reason(item: ParsedItem) -> str | None:
    """A refusal reason for an item's *kind*, or ``None`` if compilable."""
    kind = item.column.kind
    if kind is FeatureKind.LOG:
        return REASON_LOG
    if kind is FeatureKind.METRIC:
        return REASON_METRIC
    if kind in (FeatureKind.SPAN_PREDICATE, FeatureKind.EDGE, FeatureKind.ANCESTOR):
        return None
    return REASON_UNKNOWN_KIND.format(kind=str(kind))


def collect_refusal_reason(
    finding: Finding,
    columns: dict[str, FeatureColumn],
    *,
    operator_count: int | None = None,
) -> str | None:
    """Return the *first* reason ``finding`` must be refused, or ``None``.

    ``operator_count`` (if known from a built IR) is checked against the cap.
    The order below is deliberate: structural impossibilities before budget.
    """
    if not finding.itemset:
        return REASON_EMPTY

    missing = unresolved_names(finding, columns)
    if missing:
        return REASON_UNRESOLVED.format(raw=missing[0])

    for raw in finding.itemset:
        item = parse_item(raw, columns)
        assert item is not None  # narrowed by the unresolved check above
        kind_reason = _kind_reason(item)
        if kind_reason is not None:
            return kind_reason
        if item.negated and item.column.requires_span_level_negation:
            return REASON_SPAN_NEGATION

    if operator_count is not None and operator_count > MAX_TRACE_OPERATORS:
        return REASON_TOO_MANY_OPS.format(n=operator_count, cap=MAX_TRACE_OPERATORS)
    return None


def refusal_for(reason: str, finding: Finding) -> Refusal:
    """Wrap a reason string as a :class:`Refusal` carrying the full itemset."""
    return Refusal(itemset=list(finding.itemset), reason=reason)


def operator_budget_reason(root_operator_count: int) -> str | None:
    """Refusal reason if a built IR exceeds the operator cap, else ``None``."""
    if root_operator_count > MAX_TRACE_OPERATORS:
        return REASON_TOO_MANY_OPS.format(n=root_operator_count, cap=MAX_TRACE_OPERATORS)
    return None


__all__ = [
    "REASON_EMPTY",
    "REASON_LOG",
    "REASON_METRIC",
    "REASON_SPAN_NEGATION",
    "REASON_TOO_MANY_OPS",
    "REASON_UNKNOWN_KIND",
    "REASON_UNRESOLVED",
    "collect_refusal_reason",
    "count_operators",
    "operator_budget_reason",
    "refusal_for",
    "unresolved_names",
]

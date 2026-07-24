"""Shared builders that turn a :class:`CompiledQuery` into the typed
``compositeQuery.queries[]`` array SigNoz expects.

The same array shape is reused by the dashboard panels (inside a
``signoz/CompositeQuery`` query plugin) and by the v2alpha1 alert rule condition,
so it lives in one tested place. Leaves aggregate with ``count()``; the operator
aggregates with ``count_distinct(trace_id)`` — the trace-scoped count Probe 2
proved is the correct denominator/numerator unit.
"""

from __future__ import annotations

from typing import Any, cast

from whodunit.compile.emit import COUNT_DISTINCT_TRACE
from whodunit.types import CompiledQuery, LeafQuery

LEAF_AGG = "count()"
TRACE_SIGNAL = "traces"
DEFAULT_OPERATOR_NAME = "T1"
DENOM_SUFFIX = "Denom"


def leaf_query(
    name: str, expression: str, *, agg: str = LEAF_AGG, step_interval: int = 60
) -> dict[str, Any]:
    """A ``builder_query`` spec over the trace signal."""
    return {
        "type": "builder_query",
        "spec": {
            "name": name,
            "signal": TRACE_SIGNAL,
            "stepInterval": step_interval,
            "aggregations": [{"expression": agg}],
            "filter": {"expression": expression},
            "disabled": False,
        },
    }


def operator_query(
    name: str,
    expression: str,
    return_spans_from: str,
    *,
    agg: str = COUNT_DISTINCT_TRACE,
) -> dict[str, Any]:
    """A ``builder_trace_operator`` spec referencing sibling leaves by name."""
    return {
        "type": "builder_trace_operator",
        "spec": {
            "name": name,
            "expression": expression,
            "returnSpansFrom": return_spans_from,
            "aggregations": [{"expression": agg}],
            "stepInterval": 0,
            "disabled": False,
        },
    }


def formula_query(name: str, expression: str) -> dict[str, Any]:
    """A ``builder_formula`` spec (used for the share-of-traffic ratio)."""
    return {"type": "builder_formula", "spec": {"name": name, "expression": expression}}


def leaf_expression(leaf: LeafQuery) -> str:
    """Extract a leaf's v5 filter expression, or raise if it is missing."""
    expr = leaf.filters.get("expression")
    if not isinstance(expr, str) or not expr:
        raise ValueError(f"leaf {leaf.name!r} has no filter expression to materialise")
    return expr


def envelope_queries(compiled: CompiledQuery) -> list[dict[str, Any]]:
    """The raw typed queries stored on the compiled envelope (may be empty)."""
    composite = compiled.envelope.get("compositeQuery")
    if isinstance(composite, dict):
        queries = composite.get("queries")
        if isinstance(queries, list):
            return [cast(dict[str, Any], q) for q in queries if isinstance(q, dict)]
    return []


def operator_name(compiled: CompiledQuery) -> str:
    """The operator query's name from the envelope, or the ``T1`` default."""
    for query in envelope_queries(compiled):
        if query.get("type") == "builder_trace_operator":
            spec = query.get("spec")
            if isinstance(spec, dict):
                name = spec.get("name")
                if isinstance(name, str) and name:
                    return name
    return DEFAULT_OPERATOR_NAME


def anchor_leaf(compiled: CompiledQuery) -> LeafQuery:
    """The leaf whose spans the operator returns (``returnSpansFrom``).

    Falls back to the first leaf when the anchor name cannot be matched.
    """
    for leaf in compiled.leaf_queries:
        if leaf.name == compiled.return_spans_from:
            return leaf
    if not compiled.leaf_queries:
        raise ValueError("compiled query has no leaf queries to materialise")
    return compiled.leaf_queries[0]


def matching_count_queries(compiled: CompiledQuery) -> list[dict[str, Any]]:
    """Leaves + the operator: the ``count_distinct(trace_id)`` matching series."""
    queries = [
        leaf_query(leaf.name, leaf_expression(leaf)) for leaf in compiled.leaf_queries
    ]
    queries.append(
        operator_query(
            operator_name(compiled), compiled.expression, compiled.return_spans_from
        )
    )
    return queries


def share_of_traffic_queries(compiled: CompiledQuery) -> list[dict[str, Any]]:
    """Operator numerator + anchor denominator + the ratio formula.

    The denominator is the anchor leaf re-counted with ``count_distinct(trace_id)``
    under its own name so it executes independently of the operator-referenced leaf.
    """
    op_name = operator_name(compiled)
    anchor = anchor_leaf(compiled)
    denom_name = f"{anchor.name}{DENOM_SUFFIX}"
    return [
        *(
            leaf_query(leaf.name, leaf_expression(leaf))
            for leaf in compiled.leaf_queries
        ),
        operator_query(op_name, compiled.expression, compiled.return_spans_from),
        leaf_query(denom_name, leaf_expression(anchor), agg=COUNT_DISTINCT_TRACE),
        formula_query("F1", f"{op_name} / {denom_name}"),
    ]


__all__ = [
    "DEFAULT_OPERATOR_NAME",
    "DENOM_SUFFIX",
    "LEAF_AGG",
    "TRACE_SIGNAL",
    "anchor_leaf",
    "envelope_queries",
    "formula_query",
    "leaf_expression",
    "leaf_query",
    "matching_count_queries",
    "operator_name",
    "operator_query",
    "share_of_traffic_queries",
]

"""Conformance suite — replay a battery of expression shapes and publish a table.

For each shape (``A => B``, ``A -> B``, ``A && B``, ``A || B``, ``NOT`` variants,
operand flips, nesting) the compiled operator's trace-scoped count is compared
against an *independent* reference computed from per-leaf ``trace_id`` sets:

* ``&&`` / ``||`` / ``NOT`` are trace-scoped set algebra — the reference is exact,
  and any divergence is a genuine MISMATCH worth reporting upstream.
* ``=>`` / ``->`` add structural (parent/ancestor) filtering the membership
  reference cannot express, so the reference is an **upper bound**: the operator
  count should be ``<=`` it. Those rows are labelled ``STRUCTURAL`` — documented,
  not hidden.

Mismatches are findings. The output is a Markdown table for the blog/README.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from whodunit.compile.emit import COUNT_DISTINCT_TRACE, LEAF_AGG, TRACE_SIGNAL
from whodunit.compile.verify import _results, scalar_value
from whodunit.signoz_client import SigNozClient

_TRACE_SET_LIMIT = 10000


@dataclass(frozen=True)
class Shape:
    """One conformance case: a label, an expression, and its reference kind."""

    label: str
    expression: str
    return_spans_from: str
    # "set" => exact trace-set reference; "structural" => membership upper bound.
    reference_kind: str


@dataclass(frozen=True)
class ConformanceRow:
    label: str
    expression: str
    operator_count: int
    reference_count: int
    verdict: str


def default_shapes(a: str = "A", b: str = "B", c: str = "C") -> list[Shape]:
    """The standard battery over three leaves ``a``, ``b``, ``c``."""
    return [
        Shape(f"{a} => {b}", f"{a} => {b}", a, "structural"),
        Shape(f"{b} => {a} (flip)", f"{b} => {a}", b, "structural"),
        Shape(f"{a} -> {b}", f"{a} -> {b}", a, "structural"),
        Shape(f"{a} && {b}", f"{a} && {b}", a, "set"),
        Shape(f"{a} || {b}", f"{a} || {b}", a, "set"),
        Shape(f"NOT {c}", f"NOT {c}", c, "set_not"),
        Shape(f"{a} && NOT {c}", f"{a} && NOT {c}", a, "set"),
        Shape(f"({a} => {b}) && NOT {c}", f"({a} => {b}) && NOT {c}", a, "structural"),
    ]


def _leaf_spec(name: str, expr: str, agg: str) -> dict[str, Any]:
    return {
        "type": "builder_query",
        "spec": {
            "name": name,
            "signal": TRACE_SIGNAL,
            "stepInterval": 0,
            "aggregations": [{"expression": agg}],
            "filter": {"expression": expr},
            "disabled": False,
        },
    }


def _operator_scalar_envelope(
    leaves: dict[str, str],
    shape: Shape,
    *,
    base_filter: str | None,
    start: int,
    end: int,
) -> dict[str, Any]:
    scoped = {
        name: (f"{base_filter} AND {expr}" if base_filter else expr)
        for name, expr in leaves.items()
    }
    queries: list[dict[str, Any]] = [
        _leaf_spec(name, expr, LEAF_AGG) for name, expr in scoped.items()
    ]
    queries.append(
        {
            "type": "builder_trace_operator",
            "spec": {
                "name": "T",
                "expression": shape.expression,
                "returnSpansFrom": shape.return_spans_from,
                "aggregations": [{"expression": COUNT_DISTINCT_TRACE}],
                "disabled": False,
            },
        }
    )
    return {
        "schemaVersion": "v1",
        "start": start,
        "end": end,
        "requestType": "scalar",
        "compositeQuery": {"queries": queries},
    }


def leaf_trace_ids(
    client: SigNozClient,
    filter_expr: str,
    *,
    base_filter: str | None,
    start: int,
    end: int,
) -> set[str]:
    """Fetch the distinct ``trace_id`` set of a single leaf via ``trace`` requests."""
    expr = f"{base_filter} AND {filter_expr}" if base_filter else filter_expr
    envelope: dict[str, Any] = {
        "schemaVersion": "v1",
        "start": start,
        "end": end,
        "requestType": "trace",
        "compositeQuery": {
            "queries": [
                {
                    "type": "builder_query",
                    "spec": {
                        "name": "L",
                        "signal": TRACE_SIGNAL,
                        "stepInterval": 0,
                        "aggregations": [{"expression": LEAF_AGG}],
                        "filter": {"expression": expr},
                        "disabled": False,
                        "limit": _TRACE_SET_LIMIT,
                        "order": [{"key": {"name": "timestamp"}, "direction": "desc"}],
                    },
                }
            ]
        },
    }
    ids: set[str] = set()
    cursor = ""
    while True:
        env = copy.deepcopy(envelope)
        if cursor:
            env["compositeQuery"]["queries"][0]["spec"]["cursor"] = cursor
        response = client.query_range(env)
        next_cursor = ""
        seen = 0
        for result in _results(response):
            next_cursor = str(result.get("nextCursor") or "")
            rows = result.get("rows")
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and isinstance(row.get("data"), dict):
                        tid = row["data"].get("trace_id")
                        if isinstance(tid, str) and tid:
                            ids.add(tid)
                            seen += 1
        # Stop on no next page or a non-advancing cursor; do not stop merely
        # because one page came back empty while a new cursor was handed out.
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    return ids


def _reference_count(
    shape: Shape,
    sets: dict[str, set[str]],
    cohort: set[str],
) -> int:
    a, b, c = "A", "B", "C"
    if shape.reference_kind == "set_not":
        return len(cohort - sets[c])
    if shape.expression.strip() == f"{a} && {b}":
        return len(sets[a] & sets[b])
    if shape.expression.strip() == f"{a} || {b}":
        return len(sets[a] | sets[b])
    if shape.expression.strip() == f"{a} && NOT {c}":
        return len((sets[a] & cohort) - sets[c])
    # structural (=>, ->) and nested: membership upper bound over involved leaves.
    if shape.expression.strip() == f"{b} => {a}":
        return len(sets[a] & sets[b])
    if shape.expression.strip() in (f"{a} => {b}", f"{a} -> {b}"):
        return len(sets[a] & sets[b])
    if shape.expression.strip() == f"({a} => {b}) && NOT {c}":
        return len((sets[a] & sets[b]) - sets[c])
    return len(cohort)


def _verdict(shape: Shape, operator_count: int, reference_count: int) -> str:
    if shape.reference_kind in ("set", "set_not"):
        return "MATCH" if operator_count == reference_count else "MISMATCH"
    # structural: reference is an upper bound.
    if operator_count == reference_count:
        return "MATCH (no structural pruning)"
    if operator_count < reference_count:
        return "STRUCTURAL (ref is membership upper bound)"
    return "MISMATCH (operator exceeds membership bound)"


def run_conformance(
    client: SigNozClient,
    leaves: dict[str, str],
    *,
    base_filter: str | None = None,
    start: int,
    end: int,
    shapes: list[Shape] | None = None,
) -> list[ConformanceRow]:
    """Run the battery and return a row per shape."""
    shapes = shapes or default_shapes()
    sets = {
        name: leaf_trace_ids(
            client, expr, base_filter=base_filter, start=start, end=end
        )
        for name, expr in leaves.items()
    }
    cohort = set().union(*sets.values()) if sets else set()

    rows: list[ConformanceRow] = []
    for shape in shapes:
        envelope = _operator_scalar_envelope(
            leaves, shape, base_filter=base_filter, start=start, end=end
        )
        response = client.query_range(envelope)
        operator_count = scalar_value(response, "T")
        reference_count = _reference_count(shape, sets, cohort)
        rows.append(
            ConformanceRow(
                label=shape.label,
                expression=shape.expression,
                operator_count=operator_count,
                reference_count=reference_count,
                verdict=_verdict(shape, operator_count, reference_count),
            )
        )
    return rows


def to_markdown(rows: list[ConformanceRow]) -> str:
    """Render conformance rows as a Markdown table."""
    header = (
        "| Shape | Expression | Operator count | Reference count | Verdict |\n"
        "|---|---|---|---|---|"
    )
    lines = [header]
    for r in rows:
        lines.append(
            f"| {r.label} | `{r.expression}` | {r.operator_count} | "
            f"{r.reference_count} | {r.verdict} |"
        )
    return "\n".join(lines) + "\n"


__all__ = [
    "ConformanceRow",
    "Shape",
    "default_shapes",
    "leaf_trace_ids",
    "run_conformance",
    "to_markdown",
]

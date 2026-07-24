"""IR -> a full v5 ``query_range`` envelope, plus the top-level ``compile_finding``.

The emitter is the half of the crown jewel that has to be *exactly* right, so it
is boringly explicit:

* Sibling leaf builder queries carry a trace signal and a v5 filter expression;
  the operator references them **by name** — never inline filters.
* The operator expression is emitted **fully parenthesised** so the tree the
  right-to-left SigNoz parser recovers is provably the tree we intended,
  regardless of precedence.
* ``returnSpansFrom`` names the leftmost leaf (left-bias normalisation, done in
  :func:`build_ir`).
* The companion request is a ``scalar`` ``count_distinct(trace_id)`` over the
  operator — trace-scoped by construction (raw ``count()`` is span-scoped; see
  ``ENGINE-NOTES.md``). Separately-named denominator leaves are appended so the
  anchor feature's independent count survives (operator-referenced leaves are
  skipped from independent execution).
"""

from __future__ import annotations

from typing import Any

from whodunit.compile import refuse
from whodunit.compile.ir import (
    OP_AND,
    BinOp,
    IRBuild,
    IRNode,
    Leaf,
    Not,
    allocate_names,
    count_operators,
    iter_leaves,
    leftmost_leaf,
    parse_item,
)
from whodunit.compile.ir import (
    _fragment_for as fragment_for,  # re-exported intentionally for the pipeline
)
from whodunit.types import CompiledQuery, FeatureColumn, Finding, LeafQuery

TRACE_SIGNAL = "traces"
COUNT_DISTINCT_TRACE = "count_distinct(trace_id)"
LEAF_AGG = "count()"
DENOM_SUFFIX = "Denom"


# --------------------------------------------------------------------------- #
# IR construction with left-bias normalisation
# --------------------------------------------------------------------------- #


def build_ir(
    finding: Finding,
    columns: dict[str, FeatureColumn],
    *,
    vocabulary: frozenset[str] | None = None,
) -> IRBuild:
    """Build a named, left-bias-normalised IR tree for ``finding``.

    Returns an :class:`IRBuild` whose ``refusal_reason`` is set (and ``root`` is
    ``None``) when the finding cannot be compiled soundly.
    """
    reason = refuse.collect_refusal_reason(finding, columns)
    if reason is not None:
        return IRBuild(root=None, return_spans_from="", refusal_reason=reason)

    positives: list[IRNode] = []
    negatives: list[IRNode] = []
    for raw in finding.itemset:
        item = parse_item(raw, columns)
        assert item is not None  # collect_refusal_reason already checked resolvability
        try:
            fragment = fragment_for(item.column, vocabulary=vocabulary)
        except ValueError as exc:
            return IRBuild(root=None, return_spans_from="", refusal_reason=str(exc))
        if item.negated:
            negatives.append(fragment)
        else:
            positives.append(fragment)

    if not positives:
        # An absence-only itemset has no positive anchor whose spans to return.
        return IRBuild(
            root=None,
            return_spans_from="",
            refusal_reason=(
                "itemset is absence-only (all NOT); trace-operator expressions need a "
                "positive operand to return spans from"
            ),
        )

    # Left-bias: fold positives to the left, append negations on the right.
    root: IRNode = positives[0]
    for frag in positives[1:]:
        root = BinOp(op=OP_AND, left=root, right=frag)
    for frag in negatives:
        root = BinOp(op=OP_AND, left=root, right=Not(child=frag))

    op_count = count_operators(root)
    budget = refuse.operator_budget_reason(op_count)
    if budget is not None:
        return IRBuild(root=None, return_spans_from="", refusal_reason=budget)

    named = allocate_names(root)
    leaves = tuple(iter_leaves(named))
    return IRBuild(
        root=named,
        return_spans_from=leftmost_leaf(named).name,
        leaves=leaves,
    )


# --------------------------------------------------------------------------- #
# Expression emission (fully parenthesised)
# --------------------------------------------------------------------------- #


def emit_expression(node: IRNode) -> str:
    """Render ``node`` as a parenthesised operator expression.

    Every binary node is wrapped in ``(...)``; a ``NOT`` of a non-leaf wraps its
    child. The top-level redundant outer pair is stripped for readability — the
    inner parenthesisation already pins the parse tree.
    """
    rendered = _emit(node)
    if isinstance(node, BinOp) and rendered.startswith("(") and rendered.endswith(")"):
        return rendered[1:-1]
    return rendered


def _emit(node: IRNode) -> str:
    if isinstance(node, Leaf):
        return node.name
    if isinstance(node, Not):
        inner = _emit(node.child)
        if isinstance(node.child, Leaf):
            return f"NOT {inner}"
        # A BinOp child is already wrapped in parens; a Not child needs its own.
        return f"NOT {inner}" if isinstance(node.child, BinOp) else f"NOT ({inner})"
    return f"({_emit(node.left)} {node.op} {_emit(node.right)})"


# --------------------------------------------------------------------------- #
# Envelope emission
# --------------------------------------------------------------------------- #


def _leaf_spec(leaf: Leaf) -> dict[str, Any]:
    return {
        "type": "builder_query",
        "spec": {
            "name": leaf.name,
            "signal": TRACE_SIGNAL,
            "stepInterval": 0,
            "aggregations": [{"expression": LEAF_AGG}],
            "filter": {"expression": leaf.filter_expr},
            "disabled": False,
        },
    }


def _operator_spec(name: str, expression: str, return_spans_from: str) -> dict[str, Any]:
    return {
        "type": "builder_trace_operator",
        "spec": {
            "name": name,
            "expression": expression,
            "returnSpansFrom": return_spans_from,
            "aggregations": [{"expression": COUNT_DISTINCT_TRACE}],
            "disabled": False,
        },
    }


def _denominator_spec(leaf: Leaf) -> dict[str, Any]:
    """A separately-named duplicate of ``leaf`` that executes independently.

    Operator-referenced leaves are skipped from independent execution, so the
    anchor feature's own count needs its own query name.
    """
    return {
        "type": "builder_query",
        "spec": {
            "name": f"{leaf.name}{DENOM_SUFFIX}",
            "signal": TRACE_SIGNAL,
            "stepInterval": 0,
            "aggregations": [{"expression": COUNT_DISTINCT_TRACE}],
            "filter": {"expression": leaf.filter_expr},
            "disabled": False,
        },
    }


def emit_envelope(
    build: IRBuild,
    *,
    operator_name: str = "T1",
    base_filter: str | None = None,
    start: int = 0,
    end: int = 0,
    with_denominator: bool = True,
) -> dict[str, Any]:
    """Emit the full v5 ``scalar`` ``query_range`` envelope for a built IR.

    ``base_filter`` (a cohort scope such as ``deployment.environment = '...'``)
    is ANDed into every leaf so the compiled query counts only the cohort.
    """
    if build.root is None:
        raise ValueError("cannot emit an envelope for a refused finding")

    scoped = _scope_leaves(build.root, base_filter)
    leaves = tuple(iter_leaves(scoped))
    queries: list[dict[str, Any]] = [_leaf_spec(leaf) for leaf in leaves]
    queries.append(
        _operator_spec(operator_name, emit_expression(scoped), build.return_spans_from)
    )
    if with_denominator:
        queries.append(_denominator_spec(leftmost_leaf(scoped)))

    return {
        "schemaVersion": "v1",
        "start": start,
        "end": end,
        "requestType": "scalar",
        "compositeQuery": {"queries": queries},
    }


def _scope_leaves(node: IRNode, base_filter: str | None) -> IRNode:
    """Return a copy of ``node`` with ``base_filter`` ANDed into every leaf."""
    if base_filter is None:
        return node
    if isinstance(node, Leaf):
        return Leaf(
            filter_expr=f"{base_filter} AND {node.filter_expr}",
            description=node.description,
            name=node.name,
        )
    if isinstance(node, Not):
        return Not(child=_scope_leaves(node.child, base_filter))
    return BinOp(
        op=node.op,
        left=_scope_leaves(node.left, base_filter),
        right=_scope_leaves(node.right, base_filter),
    )


# --------------------------------------------------------------------------- #
# Top-level pipeline
# --------------------------------------------------------------------------- #


def compile_finding(
    finding: Finding,
    columns: list[FeatureColumn],
    *,
    base_filter: str | None = None,
    vocabulary: frozenset[str] | None = None,
    operator_name: str = "T1",
    start: int = 0,
    end: int = 0,
) -> CompiledQuery:
    """Compile a mined finding into a verifiable ``CompiledQuery``.

    On any unsound lowering the result carries an empty envelope and a populated
    :attr:`~whodunit.types.CompiledQuery.refusals` list — refusals are surfaced,
    never swallowed.
    """
    table = {col.name: col for col in columns}
    build = build_ir(finding, table, vocabulary=vocabulary)

    if build.root is None:
        reason = build.refusal_reason or "finding is not compilable"
        return CompiledQuery(
            envelope={},
            expression="",
            return_spans_from="",
            leaf_queries=[],
            refusals=[refuse.refusal_for(reason, finding)],
        )

    scoped = _scope_leaves(build.root, base_filter)
    envelope = emit_envelope(
        build,
        operator_name=operator_name,
        base_filter=base_filter,
        start=start,
        end=end,
    )
    leaf_queries = [
        LeafQuery(
            name=leaf.name,
            filters={"expression": leaf.filter_expr},
            description=leaf.description,
        )
        for leaf in iter_leaves(scoped)
    ]
    return CompiledQuery(
        envelope=envelope,
        expression=emit_expression(scoped),
        return_spans_from=build.return_spans_from,
        leaf_queries=leaf_queries,
    )


__all__ = [
    "COUNT_DISTINCT_TRACE",
    "build_ir",
    "compile_finding",
    "emit_envelope",
    "emit_expression",
]

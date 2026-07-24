"""Unit tests for the IR: naming, left-bias, operator mapping, filter safety."""

from __future__ import annotations

import pytest

from whodunit.compile.emit import build_ir
from whodunit.compile.ir import (
    OP_DIRECT,
    OP_INDIRECT,
    BinOp,
    Leaf,
    Not,
    build_filter_expr,
    count_operators,
    iter_leaves,
    leftmost_leaf,
)
from whodunit.types import FeatureColumn, FeatureKind, Finding, Verdict


def _finding(itemset: list[str]) -> Finding:
    return Finding(
        itemset=itemset,
        lift=10.0,
        ci_low=5.0,
        ci_high=15.0,
        support_bad=10,
        support_healthy=1,
        verdict=Verdict.DISCRIMINATOR,
    )


def _table(*cols: FeatureColumn) -> dict[str, FeatureColumn]:
    return {c.name: c for c in cols}


# --------------------------------------------------------------------------- #
# filter-expression construction
# --------------------------------------------------------------------------- #


def test_build_filter_expr_quotes_and_escapes() -> None:
    col = FeatureColumn(
        name="x", kind=FeatureKind.SPAN_PREDICATE, service_name="o'brien", span_name="GET /a"
    )
    expr = build_filter_expr(col)
    assert expr == "service.name = 'o''brien' AND name = 'GET /a'"


def test_build_filter_expr_duration_bounds() -> None:
    col = FeatureColumn(
        name="slow", kind=FeatureKind.SPAN_PREDICATE, duration_ge_ns=1000, duration_lt_ns=5000
    )
    assert build_filter_expr(col) == "duration_nano >= 1000 AND duration_nano < 5000"


def test_build_filter_expr_rejects_key_outside_vocabulary() -> None:
    col = FeatureColumn(name="x", kind=FeatureKind.SPAN_PREDICATE, service_name="s")
    with pytest.raises(ValueError, match="not in provided vocabulary"):
        build_filter_expr(col, vocabulary=frozenset({"name"}))


def test_build_filter_expr_empty_predicate_raises() -> None:
    col = FeatureColumn(name="x", kind=FeatureKind.SPAN_PREDICATE)
    with pytest.raises(ValueError, match="no compilable predicate"):
        build_filter_expr(col)


# --------------------------------------------------------------------------- #
# operator mapping (EDGE => direct, ANCESTOR => indirect)
# --------------------------------------------------------------------------- #


def test_edge_maps_to_direct_operator() -> None:
    col = FeatureColumn(
        name="e", kind=FeatureKind.EDGE, edge_parent="svc_a", edge_child="svc_b"
    )
    build = build_ir(_finding(["e"]), _table(col))
    assert isinstance(build.root, BinOp)
    assert build.root.op == OP_DIRECT


def test_ancestor_maps_to_indirect_operator() -> None:
    col = FeatureColumn(
        name="a", kind=FeatureKind.ANCESTOR, edge_parent="svc_a", edge_child="svc_b"
    )
    build = build_ir(_finding(["a"]), _table(col))
    assert isinstance(build.root, BinOp)
    assert build.root.op == OP_INDIRECT


# --------------------------------------------------------------------------- #
# deterministic naming and left-bias normalisation
# --------------------------------------------------------------------------- #


def test_names_allocated_left_to_right() -> None:
    edge = FeatureColumn(
        name="e", kind=FeatureKind.EDGE, edge_parent="p", edge_child="c"
    )
    build = build_ir(_finding(["e"]), _table(edge))
    assert build.root is not None
    names = [leaf.name for leaf in iter_leaves(build.root)]
    assert names == ["A", "B"]
    assert build.return_spans_from == "A"


def test_outcome_on_the_right_gets_flipped_left() -> None:
    edge = FeatureColumn(
        name="e", kind=FeatureKind.EDGE, edge_parent="shop-payment", edge_child="span:redis-retry"
    )
    flag = FeatureColumn(name="f", kind=FeatureKind.SPAN_PREDICATE, service_name="flag-svc")
    # Negation listed FIRST, positive edge SECOND: normaliser must move the edge left.
    build = build_ir(_finding(["NOT f", "e"]), _table(edge, flag))
    assert build.root is not None
    # Leftmost leaf must be the edge parent, not the negated flag.
    assert build.return_spans_from == "A"
    left = leftmost_leaf(build.root)
    assert "shop-payment" in left.filter_expr


def test_negations_pushed_right_of_and() -> None:
    edge = FeatureColumn(name="e", kind=FeatureKind.EDGE, edge_parent="p", edge_child="c")
    flag = FeatureColumn(name="f", kind=FeatureKind.SPAN_PREDICATE, service_name="flag")
    build = build_ir(_finding(["NOT f", "e"]), _table(edge, flag))
    root = build.root
    assert isinstance(root, BinOp)
    # top-level && : left is the positive edge, right is a NOT node.
    assert isinstance(root.right, Not)


# --------------------------------------------------------------------------- #
# tree helpers
# --------------------------------------------------------------------------- #


def test_count_operators() -> None:
    tree = BinOp(
        op="&&",
        left=BinOp(op="=>", left=Leaf("a", name="A"), right=Leaf("b", name="B")),
        right=Not(child=Leaf("c", name="C")),
    )
    # one && , one => , one NOT
    assert count_operators(tree) == 3

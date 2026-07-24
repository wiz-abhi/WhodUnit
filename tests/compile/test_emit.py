"""Unit tests for the emitter, including a golden-envelope assertion."""

from __future__ import annotations

import json
from pathlib import Path

from whodunit.compile.emit import compile_finding, emit_expression
from whodunit.compile.ir import BinOp, Leaf, Not
from whodunit.types import FeatureColumn, FeatureKind, Finding, Verdict

GOLDEN = Path(__file__).parent / "golden" / "ground_truth_conjunction.json"


def _ground_truth_columns() -> list[FeatureColumn]:
    return [
        FeatureColumn(
            name="pay_redis_edge",
            kind=FeatureKind.EDGE,
            edge_parent="shop-payment",
            edge_child="span:redis-retry",
        ),
        FeatureColumn(
            name="flag_service",
            kind=FeatureKind.SPAN_PREDICATE,
            service_name="shop-flag-service",
        ),
    ]


def _ground_truth_finding() -> Finding:
    # Negation deliberately first so the golden also proves left-bias flipping.
    return Finding(
        itemset=["NOT flag_service", "pay_redis_edge"],
        lift=41.0,
        ci_low=30.0,
        ci_high=55.0,
        support_bad=55,
        support_healthy=1,
        verdict=Verdict.DISCRIMINATOR,
    )


# --------------------------------------------------------------------------- #
# expression emission
# --------------------------------------------------------------------------- #


def test_emit_expression_fully_parenthesises_and_flattens_top_level() -> None:
    tree = BinOp(
        op="&&",
        left=BinOp(op="=>", left=Leaf("a", name="A"), right=Leaf("b", name="B")),
        right=Not(child=Leaf("c", name="C")),
    )
    assert emit_expression(tree) == "(A => B) && NOT C"


def test_emit_expression_wraps_not_of_subtree() -> None:
    tree = Not(child=BinOp(op="=>", left=Leaf("a", name="A"), right=Leaf("b", name="B")))
    assert emit_expression(tree) == "NOT (A => B)"


# --------------------------------------------------------------------------- #
# golden envelope
# --------------------------------------------------------------------------- #


def test_ground_truth_envelope_matches_golden() -> None:
    compiled = compile_finding(
        _ground_truth_finding(),
        _ground_truth_columns(),
        base_filter="deployment.environment = 'whodunit-demo'",
    )
    assert not compiled.refusals
    golden = json.loads(GOLDEN.read_text())
    assert compiled.expression == golden["expression"]
    assert compiled.return_spans_from == golden["return_spans_from"]
    assert compiled.envelope == golden["envelope"]


def test_leaf_names_match_regex() -> None:
    compiled = compile_finding(_ground_truth_finding(), _ground_truth_columns())
    for leaf in compiled.leaf_queries:
        assert leaf.name.isascii() and leaf.name[0].isalpha()
    assert [leaf.name for leaf in compiled.leaf_queries] == ["A", "B", "C"]


def test_operator_uses_count_distinct_trace() -> None:
    compiled = compile_finding(_ground_truth_finding(), _ground_truth_columns())
    ops = [
        q
        for q in compiled.envelope["compositeQuery"]["queries"]  # type: ignore[index]
        if q["type"] == "builder_trace_operator"
    ]
    assert len(ops) == 1
    assert ops[0]["spec"]["aggregations"][0]["expression"] == "count_distinct(trace_id)"


def test_denominator_leaf_present_and_independent() -> None:
    compiled = compile_finding(_ground_truth_finding(), _ground_truth_columns())
    names = [
        q["spec"]["name"]
        for q in compiled.envelope["compositeQuery"]["queries"]  # type: ignore[index]
    ]
    assert "ADenom" in names  # separately-named duplicate of the return operand
